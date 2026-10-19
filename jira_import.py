"""Einlesen von Jira-Daten: CSV-Export, JSON (REST-Antwort) und die REST-API selbst. Alle Wege enden in derselben Liste von `Issue`.

Der Kern kennt nur `Issue`; hier steht alles, was von Jira-Instanz zu Jira-Instanz verschieden ist (Spaltennamen, Feld-IDs, Datumsformate).
Fehlendes wird nicht erraten, sondern im `ImportReport` gemeldet."""

import csv
import datetime as dt
import io
import json
import re
from dataclasses import dataclass, field, replace
from urllib.parse import urlparse

import jira_constants as C
from jira_algorithm import category_from_status_name, normalize_category
from jira_scenario import Issue


class JiraImportError(Exception):
    """Eingabe unbrauchbar (kein Schlüssel, kein Status, falsches Format); der Text ist für die Anzeige gedacht."""


@dataclass
class ImportReport:
    """Was beim Einlesen auffiel; die App zeigt es an, bevor eine Zahl gezeigt wird."""

    issues: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- Hilfen

def parse_number(text) -> float | None:
    """Story Points aus Text oder Zahl; Komma oder Punkt als Dezimaltrenner, leer oder unlesbar = None."""
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


_DATE_FORMATS = ("%d/%b/%y %I:%M %p", "%d/%b/%Y %I:%M %p", "%d/%b/%y %H:%M", "%d/%b/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                 "%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y")


def parse_date(text) -> dt.date | None:
    """Datum aus den üblichen Jira-Formaten (CSV-Export „19/Oct/26 3:45 PM“, ISO 8601 der API, deutsche Schreibweise); sonst None."""
    if not text:
        return None
    t = str(text).strip()
    if not t:
        return None
    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", t)
    if iso and ("T" in t or len(t) == 10):
        try:
            return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def _split_list(text: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in re.split(r"[,;]", text) if p.strip()) if text else ()


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


# ---------------------------------------------------------------- CSV

_ALIASES = {
    "key": ("issue key", "key", "vorgangsschlüssel", "schlüssel"),
    "id": ("issue id", "id", "vorgangs-id"),
    "summary": ("summary", "zusammenfassung"),
    "type": ("issue type", "vorgangstyp", "type", "typ"),
    "status": ("status",),
    "category": ("status category", "statuskategorie"),
    "points": ("custom field (story points)", "custom field (story point estimate)", "story points", "story point estimate", "storypunkte", "story-points"),
    "parent": ("parent", "parent key", "parent id", "übergeordneter vorgang", "custom field (parent link)", "epic link", "custom field (epic link)"),
    "sprint": ("sprint",),
    "components": ("component/s", "components", "komponenten", "komponente/n"),
    "labels": ("labels", "etiketten"),
    "assignee": ("assignee", "bearbeiter", "zugewiesene person"),
    "versions": ("fix version/s", "fix versions", "lösungsversion/en", "fixversion/s"),
    "created": ("created", "erstellt"),
    "resolved": ("resolved", "gelöst", "resolution date", "lösungsdatum"),
}
_SUBTASK_NAMES = {"sub-task", "subtask", "sub task", "teilaufgabe", "unteraufgabe", "untervorgang"}


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _columns(header: list[str]) -> dict[str, list[int]]:
    """Spaltenindizes je Feld; mehrfach vorkommende Spalten (Sprint, Labels, Komponenten) liefern alle Indizes."""
    normed = [_norm(h) for h in header]
    found: dict[str, list[int]] = {}
    for fieldname, names in _ALIASES.items():
        idx = [n for n, h in enumerate(normed) if h in names]
        if idx:
            found[fieldname] = idx
    return found


def read_csv(data: bytes, max_issues: int = C.MAX_IMPORT_ISSUES) -> tuple[tuple[Issue, ...], ImportReport]:
    """Liest einen Jira-CSV-Export (Trennzeichen Komma oder Semikolon). Pflicht sind Schlüssel und Status; alles andere ist optional."""
    text = _decode(data)
    sample = text[:4096]
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    if not rows:
        raise JiraImportError("Die Datei ist leer.")
    cols = _columns(rows[0])
    for needed, label in (("key", "Issue key"), ("status", "Status")):
        if needed not in cols:
            raise JiraImportError(f"Die Spalte „{label}“ fehlt. Gefunden: {', '.join(h for h in rows[0] if h) or '(keine Kopfzeile)'}.")
    report = ImportReport()
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    if len(body) > max_issues:
        raise JiraImportError(f"{len(body)} Tickets sind mehr als die Obergrenze von {max_issues}. Bitte den Export nach Projekt oder Zeitraum einschränken.")

    def cell(row, name, first_only=True):
        idx = cols.get(name, [])
        vals = [row[i].strip() for i in idx if i < len(row) and row[i].strip()]
        return (vals[0] if vals else "") if first_only else vals

    id_to_key = {cell(r, "id"): cell(r, "key") for r in body if "id" in cols and cell(r, "id")}
    issues, bad_dates, bad_points = [], 0, 0
    for row in body:
        key = cell(row, "key")
        if not key:
            continue
        status = cell(row, "status")
        category = normalize_category(cell(row, "category")) if "category" in cols and cell(row, "category") else category_from_status_name(status)
        type_name = cell(row, "type") or "Story"
        raw_points = cell(row, "points")
        points = parse_number(raw_points)
        bad_points += bool(raw_points) and points is None
        created, resolved = cell(row, "created"), cell(row, "resolved")
        d_created, d_resolved = parse_date(created), parse_date(resolved)
        bad_dates += (bool(created) and d_created is None) + (bool(resolved) and d_resolved is None)
        parent = cell(row, "parent")
        issues.append(Issue(
            key=key, summary=cell(row, "summary"), type=type_name, is_subtask=_norm(type_name) in _SUBTASK_NAMES, status=status, category=category,
            points=points, parent=parent, sprints=tuple(cell(row, "sprint", False)), labels=tuple(p for v in cell(row, "labels", False) for p in _split_list(v)),
            components=tuple(p for v in cell(row, "components", False) for p in _split_list(v)), assignee=cell(row, "assignee"),
            versions=tuple(p for v in cell(row, "versions", False) for p in _split_list(v)), created=d_created, resolved=d_resolved))
    issues = _resolve_parents(issues, id_to_key)
    report.issues = len(issues)
    if "points" not in cols:
        report.notes.append("Keine Story-Point-Spalte gefunden: alle Tickets gelten als ungeschätzt (Gewichtung nach Ticketanzahl bleibt möglich).")
    if "category" not in cols:
        report.notes.append("Keine Statuskategorie-Spalte: Die Kategorie wird aus dem Statusnamen geraten und lässt sich in der Gewichtstabelle prüfen.")
    if "parent" not in cols:
        report.notes.append("Keine Spalte für übergeordnete Tickets (Parent oder Epic Link): Epics und Sub-Tasks lassen sich nicht zuordnen.")
    if "sprint" not in cols:
        report.notes.append("Keine Sprint-Spalte gefunden.")
    if bad_dates:
        report.notes.append(f"{bad_dates} Datumswerte waren nicht lesbar (im Burn-up fehlen sie).")
    if bad_points:
        report.notes.append(f"{bad_points} Story-Point-Werte waren keine Zahl und gelten als ungeschätzt.")
    return tuple(issues), report


def _resolve_parents(issues: list[Issue], id_to_key: dict[str, str]) -> list[Issue]:
    """Elternverweis als Schlüssel: ein Wert, der ein Ticketschlüssel ist, bleibt; ein Treffer in der Spalte Issue id wird in den Schlüssel übersetzt;
    alles andere (Parent außerhalb des Exports) wird gelöscht, damit nichts ins Leere zeigt."""
    keys = {i.key for i in issues}
    out = []
    for issue in issues:
        p = issue.parent
        if p and p not in keys:
            p = id_to_key.get(p, "")
        if p and p not in keys:
            p = ""
        out.append(issue if p == issue.parent else replace(issue, parent=p))
    return out


# ---------------------------------------------------------------- JSON und REST

@dataclass(frozen=True)
class FieldIds:
    """Feld-IDs der Jira-Instanz für Story Points, Sprint und (alte) Epic-Verknüpfung."""

    points: tuple[str, ...] = tuple(s.strip() for s in C.DEFAULT_POINTS_FIELDS.split(","))
    sprint: str = C.DEFAULT_SPRINT_FIELD
    epic_link: str = C.DEFAULT_EPIC_LINK_FIELD

    def requested(self) -> list[str]:
        base = ["summary", "issuetype", "status", "parent", "labels", "components", "fixVersions", "assignee", "created", "resolutiondate"]
        return base + [f for f in (*self.points, self.sprint, self.epic_link) if f]


def parse_field_ids(points: str, sprint: str, epic_link: str) -> FieldIds:
    """Feld-IDs aus Texteingaben (Story Points als kommagetrennte Liste); leere Eingaben fallen auf die Voreinstellung zurück."""
    pts = tuple(p.strip() for p in (points or "").split(",") if p.strip()) or FieldIds().points
    return FieldIds(points=pts, sprint=(sprint or "").strip() or C.DEFAULT_SPRINT_FIELD, epic_link=(epic_link or "").strip())


def _sprint_names(value) -> tuple[str, ...]:
    """Sprint-Namen aus dem Sprint-Feld: Liste von Objekten ({name}) oder alte Textform („…[id=1,name=Sprint 1,…]“)."""
    names = []
    for item in value or []:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            m = re.search(r"name=([^,\]]+)", item)
            if m:
                names.append(m.group(1))
    return tuple(names)


def issue_from_api(raw: dict, fields: FieldIds) -> Issue:
    """Ein Ticket aus der REST-Antwort (Jira Cloud v3 oder Server/Data Center v2)."""
    f = raw.get("fields") or {}
    itype = f.get("issuetype") or {}
    status = f.get("status") or {}
    cat = (status.get("statusCategory") or {})
    category = normalize_category(cat.get("key") or cat.get("name") or "") if cat else category_from_status_name(status.get("name", ""))
    points = next((parse_number(f[p]) for p in fields.points if f.get(p) is not None), None)
    parent = (f.get("parent") or {}).get("key", "") or (f.get(fields.epic_link) if fields.epic_link and isinstance(f.get(fields.epic_link), str) else "") or ""
    assignee = f.get("assignee") or {}
    type_name = itype.get("name", "Story")
    return Issue(
        key=raw.get("key", ""), summary=f.get("summary") or "", type=type_name, is_subtask=bool(itype.get("subtask")) or _norm(type_name) in _SUBTASK_NAMES,
        status=status.get("name", ""), category=category, points=points, parent=parent, sprints=_sprint_names(f.get(fields.sprint)),
        components=tuple(c.get("name", "") for c in f.get("components") or [] if c.get("name")), labels=tuple(f.get("labels") or []),
        assignee=assignee.get("displayName", "") or assignee.get("name", ""), versions=tuple(v.get("name", "") for v in f.get("fixVersions") or [] if v.get("name")),
        created=parse_date(f.get("created")), resolved=parse_date(f.get("resolutiondate")))


def issues_from_api(raw_issues, fields: FieldIds) -> tuple[tuple[Issue, ...], ImportReport]:
    issues = tuple(issue_from_api(r, fields) for r in raw_issues if r.get("key"))
    report = ImportReport(issues=len(issues))
    if issues and all(i.points is None for i in issues):
        report.notes.append(
            f"Kein Ticket hat Story Points. Prüfen, ob das Feld {', '.join(fields.points)} in dieser Jira-Instanz das Story-Point-Feld ist "
            "(unter „Jira-Felder“ ändern) oder ob die Tickets wirklich ungeschätzt sind.")
    if issues and not any(i.sprints for i in issues):
        report.notes.append(f"Kein Ticket hat einen Sprint (Feld {fields.sprint}); die Ebene Sprint zeigt dann nur „(ohne Sprint)“.")
    return issues, report


def read_json(data: bytes, fields: FieldIds | None = None, max_issues: int = C.MAX_IMPORT_ISSUES) -> tuple[tuple[Issue, ...], ImportReport]:
    """Liest eine gespeicherte REST-Antwort (`{"issues": [...]}`) oder eine Liste solcher Tickets."""
    try:
        payload = json.loads(_decode(data))
    except json.JSONDecodeError as exc:
        raise JiraImportError(f"Keine gültige JSON-Datei: {exc.msg} (Zeile {exc.lineno}).") from exc
    raw = payload.get("issues") if isinstance(payload, dict) else payload
    if not isinstance(raw, list) or not all(isinstance(r, dict) for r in raw):
        raise JiraImportError("Erwartet wird eine Liste von Tickets oder ein Objekt mit dem Feld „issues“ (Antwort der Jira-REST-Suche).")
    if len(raw) > max_issues:
        raise JiraImportError(f"{len(raw)} Tickets sind mehr als die Obergrenze von {max_issues}.")
    return issues_from_api(raw, fields or FieldIds())


def read_file(name: str, data: bytes, fields: FieldIds | None = None) -> tuple[tuple[Issue, ...], ImportReport]:
    """Wählt nach Dateiendung (.json) oder Inhalt (beginnt mit { oder [) den Leser, sonst CSV."""
    head = _decode(data[:200]).lstrip()
    if name.lower().endswith(".json") or head[:1] in "{[":
        return read_json(data, fields)
    return read_csv(data)


# ---------------------------------------------------------------- API

CLOUD, SERVER = "Jira Cloud", "Jira Server / Data Center"
FLAVORS = (CLOUD, SERVER)


def normalize_base_url(url: str, keep_path: bool = False) -> str:
    """Basisadresse ohne Schrägstrich am Ende; nur https. Der Pfad bleibt nur für Server/Data Center (Kontextpfad wie /jira), bei Cloud entfällt er. Alles andere
    wird abgewiesen, bevor Zugangsdaten gesendet werden."""
    u = (url or "").strip().rstrip("/")
    if not u:
        raise JiraImportError("Bitte die Adresse der Jira-Instanz eintragen, z. B. https://firma.atlassian.net.")
    if not u.lower().startswith("https://"):
        raise JiraImportError("Aus Sicherheitsgründen nur https:// -Adressen: Zugangsdaten gehen nicht unverschlüsselt über das Netz.")
    parsed = urlparse(u)
    if not parsed.hostname or "." not in parsed.hostname:
        raise JiraImportError("Die Adresse ist kein gültiger Hostname.")
    return f"https://{parsed.netloc}{parsed.path.rstrip('/') if keep_path else ''}"


def fetch_issues(base_url: str, flavor: str, jql: str, fields: FieldIds, session, auth=None, token: str = "", max_issues: int = C.MAX_IMPORT_ISSUES,
                 page_size: int = C.API_PAGE_SIZE) -> tuple[list[dict], bool]:
    """Holt Tickets seitenweise. `session` hat `get(url, params=, auth=, headers=, timeout=)` wie `requests.Session`; `auth` = (E-Mail, API-Token) für Cloud,
    `token` = persönliches Zugriffstoken für Server/Data Center. Rückgabe: (Tickets, abgeschnitten) – abgeschnitten, wenn die Obergrenze erreicht wurde, bevor Jira
    weitere Tickets meldete.

    Cloud: /rest/api/3/search/jql mit nextPageToken (die frühere Suche /rest/api/3/search ist entfernt); Felder müssen ausdrücklich angefragt werden.
    Server: /rest/api/2/search mit startAt."""
    base = normalize_base_url(base_url, keep_path=flavor == SERVER)
    if not (jql or "").strip():
        raise JiraImportError("Bitte eine JQL-Abfrage eintragen, z. B. project = ABC.")
    headers = {"Accept": "application/json"}
    if flavor == SERVER:
        headers["Authorization"] = f"Bearer {token}"
        http_auth = None
    else:
        http_auth = auth
    out: list[dict] = []
    token_next, start_at = None, 0
    while True:
        want = min(page_size, max_issues - len(out))
        params = {"jql": jql, "fields": ",".join(fields.requested()), "maxResults": want}
        if flavor == CLOUD:
            url = f"{base}/rest/api/3/search/jql"
            if token_next:
                params["nextPageToken"] = token_next
        else:
            url = f"{base}/rest/api/2/search"
            params["startAt"] = start_at
        response = session.get(url, params=params, auth=http_auth, headers=headers, timeout=C.API_TIMEOUT_S)
        if response.status_code in (401, 403):
            raise JiraImportError(f"Jira lehnt die Anmeldung ab (HTTP {response.status_code}). E-Mail, API-Token bzw. Zugriffstoken und Berechtigungen prüfen.")
        if response.status_code >= 400:
            detail = ""
            try:
                body = response.json()
                detail = "; ".join(body.get("errorMessages") or []) or str(body.get("message", ""))
            except Exception:
                pass
            raise JiraImportError(f"Jira meldet HTTP {response.status_code}" + (f": {detail}" if detail else "") + ".")
        payload = response.json()
        page = payload.get("issues") or []
        out.extend(page)
        if len(out) >= max_issues:
            more = bool(payload.get("nextPageToken")) if flavor == CLOUD else (start_at + len(page) < int(payload.get("total", 0)))
            return out[:max_issues], more
        if flavor == CLOUD:
            token_next = payload.get("nextPageToken")
            if not token_next or payload.get("isLast") or not page:
                return out, False
        else:
            start_at += len(page)
            if not page or start_at >= int(payload.get("total", 0)):
                return out, False


# ---------------------------------------------------------------- CSV-Export (Beispieldatei und Rundlauf-Gegenprobe)

def to_csv(issues) -> bytes:
    """Schreibt Tickets im Spaltenaufbau eines Jira-CSV-Exports (Mehrfachwerte in wiederholten Spalten). Dient als Beispieldatei zum Herunterladen und
    als Gegenprobe: `read_csv(to_csv(x))` liefert wieder `x`."""
    def width(getter):
        return max([len(getter(i)) for i in issues] + [1])
    k_sprint, k_comp, k_label, k_ver = width(lambda i: i.sprints), width(lambda i: i.components), width(lambda i: i.labels), width(lambda i: i.versions)
    header = (["Issue key", "Summary", "Issue Type", "Status", "Status Category", "Custom field (Story Points)", "Parent"] + ["Sprint"] * k_sprint
              + ["Component/s"] * k_comp + ["Labels"] * k_label + ["Assignee"] + ["Fix versions"] * k_ver + ["Created", "Resolved"])
    label_of = {"new": "To Do", "indeterminate": "In Progress", "done": "Done"}

    def pad(values, k):
        return list(values) + [""] * (k - len(values))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for i in issues:
        writer.writerow([i.key, i.summary, i.type, i.status, label_of[i.category], "" if i.points is None else f"{i.points:g}", i.parent]
                        + pad(i.sprints, k_sprint) + pad(i.components, k_comp) + pad(i.labels, k_label) + [i.assignee] + pad(i.versions, k_ver)
                        + [i.created.isoformat() if i.created else "", i.resolved.isoformat() if i.resolved else ""])
    return buffer.getvalue().encode("utf-8-sig")
