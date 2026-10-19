"""Tabellarische Auswertungen: reine Funktionen, die aus einer `Analysis` Zeilen (Listen von Wörterbüchern) bauen.

Die Zeilen tragen Zahlen als Zahlen (kein Text); Formatierung übernimmt die Anzeige, `rows_to_csv` schreibt die Datei für Excel mit Dezimalkomma."""

import datetime as dt

import numpy as np

import jira_algorithm as A
import jira_constants as C
from jira_evaluation import Analysis, de, pct, status_list

METRIC_WEIGHT, METRIC_COUNT, METRIC_CREDITED = "Gewicht", "Tickets", "Angerechnet"
METRICS = (METRIC_WEIGHT, METRIC_COUNT, METRIC_CREDITED)
SUM_LABEL = "Summe"
MAX_LIST_ROWS = 200      # so viele Tickets nennt die Liste „ohne Story Points“ höchstens
MAX_SUMMARY_ROWS = 40    # so viele Gruppen nennt die Zusammenfassung zum Kopieren höchstens


def atom_statuses(issues, a: Analysis) -> list[str]:
    """Statusnamen der Atome in der Reihenfolge von Workflow-Kategorie und Name (nur Status, die bei Atomen vorkommen)."""
    used = {issues[i].status for i in a.atoms}
    return [s for s, _ in status_list(issues) if s in used]


def status_by_group(issues, a: Analysis, metric: str) -> list[dict]:
    """Gruppen der gewählten Ebene als Zeilen, Status als Spalten; Zelle = Gewicht, Ticketzahl oder angerechnetes Gewicht (anteilig bei Mehrfachwerten).
    Dazu je Zeile die Summe und der Fortschritt der Gruppe, am Ende eine Summenzeile."""
    if metric not in METRICS:
        raise ValueError(f"unbekannte Kennzahl {metric!r}")
    statuses = atom_statuses(issues, a)
    pos = {s: k for k, s in enumerate(statuses)}
    status_of = np.array([pos[issues[i].status] for i in a.atoms], dtype=int)
    base = {METRIC_WEIGHT: a.w, METRIC_COUNT: np.ones(len(a.w)), METRIC_CREDITED: a.w * a.c}[metric]
    n_groups, n_status = len(a.assign.labels), len(statuses)
    cells = np.bincount(a.assign.group * n_status + status_of[a.assign.atom], weights=base[a.assign.atom] * a.assign.share,
                        minlength=n_groups * n_status).reshape(n_groups, n_status)
    rows = []
    for g, label in enumerate(a.assign.labels):
        row = {"Gruppe": label, **{s: float(cells[g, k]) for k, s in enumerate(statuses)}, SUM_LABEL: float(cells[g].sum())}
        row["Fortschritt"] = None if np.isnan(a.stats.progress[g]) else float(a.stats.progress[g])
        rows.append(row)
    if rows:
        total = {"Gruppe": SUM_LABEL, **{s: float(cells[:, k].sum()) for k, s in enumerate(statuses)}, SUM_LABEL: float(cells.sum())}
        total["Fortschritt"] = None if np.isnan(a.progress) else float(a.progress)
        rows.append(total)
    return rows


def contribution(a: Analysis) -> list[dict]:
    """Beitrag je Gruppe zum Gesamtfortschritt: Anteil am Gesamtgewicht, eigener Fortschritt, Beitrag in Prozentpunkten (angerechnet / Gesamtgewicht), offenes
    Gewicht und dessen Anteil. Die Beiträge summieren sich zum Gesamtfortschritt."""
    s = a.stats
    total_w = float(s.weight.sum())
    open_w = s.weight - s.credited
    total_open = float(open_w.sum())
    rows = []
    for g, label in enumerate(s.labels):
        rows.append({
            "Gruppe": label, "Gewicht": float(s.weight[g]), "Anteil am Gewicht": float(s.weight[g]) / total_w if total_w > 0 else None,
            "Fortschritt": None if np.isnan(s.progress[g]) else float(s.progress[g]),
            "Beitrag (Punkte)": 100 * float(s.credited[g]) / total_w if total_w > 0 else None,
            "Offenes Gewicht": float(open_w[g]), "Anteil am Offenen": float(open_w[g]) / total_open if total_open > 0 else None})
    if rows:
        rows.append({
            "Gruppe": SUM_LABEL, "Gewicht": total_w, "Anteil am Gewicht": 1.0 if total_w > 0 else None, "Fortschritt": None if np.isnan(a.progress) else a.progress,
            "Beitrag (Punkte)": 100 * float(s.credited.sum()) / total_w if total_w > 0 else None, "Offenes Gewicht": total_open,
            "Anteil am Offenen": 1.0 if total_open > 0 else None})
    return rows


def status_overview(issues, a: Analysis) -> list[dict]:
    """Je Status: Tickets, Gewicht, Status-Gewicht in Prozent (laut Einstellung), angerechnetes Gewicht und Anteil am gesamten Angerechneten. Das angerechnete Gewicht
    nimmt die Gutschrift der Atome (mit der Sub-Task-Option kann sie über dem Status-Gewicht liegen)."""
    category = dict(status_list(issues))
    statuses = atom_statuses(issues, a)
    rows = []
    credited_total = float((a.w * a.c).sum())
    for status in statuses:
        mask = np.array([issues[i].status == status for i in a.atoms], dtype=bool)
        credited = float((a.w * a.c)[mask].sum())
        rows.append({
            "Status": status, "Kategorie": C.CATEGORY_LABEL[category[status]], "Tickets": int(mask.sum()), "Gewicht": float(a.w[mask].sum()),
            "Status-Gewicht (%)": 100 * a.credits[status], "Angerechnet": credited, "Anteil am Angerechneten": credited / credited_total if credited_total > 0 else None})
    if rows:
        rows.append({"Status": SUM_LABEL, "Kategorie": "", "Tickets": a.n_atoms, "Gewicht": a.weight, "Status-Gewicht (%)": None, "Angerechnet": credited_total,
                     "Anteil am Angerechneten": 1.0 if credited_total > 0 else None})
    return rows


def done_by_month(issues, a: Analysis) -> tuple[list[dict], int]:
    """Erledigte Atome je Kalendermonat des Lösungsdatums (lückenlos von der ersten bis zur letzten Lösung, Monate ohne Lösung mit 0). Rückgabe: Zeilen und die Zahl
    erledigter Atome ohne Lösungsdatum, die hier fehlen."""
    counts: dict[int, list[float]] = {}
    missing = 0
    for pos, i in enumerate(a.atoms):
        if not a.done[pos]:
            continue
        day = issues[i].resolved
        if day is None:
            missing += 1
            continue
        entry = counts.setdefault(day.year * 12 + day.month - 1, [0.0, 0.0])
        entry[0] += 1
        entry[1] += float(a.w[pos])
    if not counts:
        return [], missing
    rows, cumulative = [], 0.0
    for month in range(min(counts), max(counts) + 1):
        n, weight = counts.get(month, [0.0, 0.0])
        cumulative += weight
        rows.append({"Monat": f"{month // 12:04d}-{month % 12 + 1:02d}", "Tickets erledigt": int(n), "Gewicht erledigt": weight, "Gewicht kumuliert": cumulative})
    return rows, missing


def _status_category_conflicts(issues) -> int:
    seen: dict[str, set[str]] = {}
    for t in issues:
        seen.setdefault(t.status, set()).add(t.category)
    return sum(len(cats) > 1 for cats in seen.values())


def data_quality(issues, a: Analysis) -> list[dict]:
    """Prüfungen der Eingangsdaten mit Anzahl, Anteil an den Atomen und dem Hinweis, wie sich der Befund auf die Zahl auswirkt."""
    atoms = list(a.atoms)
    n = len(atoms)
    by_key = {t.key: t for t in issues}
    epics = A.epic_of(issues)
    kids = A.children_of(issues)
    epic_names: dict[str, str] = {}
    checks = {
        "Ohne Story Points": sum(issues[i].points is None for i in atoms),
        "Story Points = 0": sum(issues[i].points == 0 for i in atoms),
        "Ohne Epic": sum(epics[i] == "" for i in atoms),
        "Ohne Sprint": sum(A.group_labels(by_key, issues[i], epics[i], epic_names, C.DIM_SPRINT) == ["(ohne Sprint)"] for i in atoms),
        "Erledigt ohne Lösungsdatum": sum(issues[i].category == "done" and issues[i].resolved is None for i in atoms),
        "Lösungsdatum vor Erstelldatum": sum(issues[i].resolved is not None and issues[i].created is not None and issues[i].resolved < issues[i].created for i in atoms),
        "Erledigt, aber Sub-Tasks offen": sum(issues[i].category == "done" and any(
            issues[j].is_subtask and issues[j].category != "done" for j in kids.get(issues[i].key, [])) for i in atoms),
    }
    hints = {
        "Ohne Story Points": "Gewicht nach der gewählten Regel; bei „nicht zählen“ fehlen sie im Fortschritt ganz.",
        "Story Points = 0": "Zählen als geschätzt mit Gewicht 0: Das Ticket hat keinen Einfluss auf den Fortschritt.",
        "Ohne Epic": "Landen in der Gruppe „(ohne Epic)“ der Ebene Epic.",
        "Ohne Sprint": "Landen in der Gruppe „(ohne Sprint)“ der Ebene Sprint.",
        "Erledigt ohne Lösungsdatum": "Fehlen im Verlauf (Burn-up) und in „Erledigt je Monat“.",
        "Lösungsdatum vor Erstelldatum": "Der Verlauf zeigt sie als zu früh erledigt; meist ein Fehler im Export oder bei einer Migration.",
        "Erledigt, aber Sub-Tasks offen": "Der Status der Story zählt; die Sub-Task-Option kann das nicht verbessern, weil der Status die Untergrenze ist.",
    }
    rows = [{"Prüfung": name, "Anzahl": count, "Anteil an den Tickets": count / n if n else None, "Wirkung": hints[name]} for name, count in checks.items()]
    conflicts = _status_category_conflicts(issues)
    rows.append({"Prüfung": "Status mit uneinheitlicher Kategorie", "Anzahl": conflicts, "Anteil an den Tickets": None,
                 "Wirkung": "Derselbe Status steht in Jira in zwei Kategorien (z. B. je Projekt); die Tabelle der Status-Gewichte nimmt die häufigste."})
    return rows


def unestimated_tickets(issues, a: Analysis, limit: int = MAX_LIST_ROWS) -> tuple[list[dict], int]:
    """Atome ohne Story Points als Liste (Schlüssel, Titel, Typ, Status, Epic), höchstens `limit`; dazu die Gesamtzahl."""
    epics = A.epic_of(issues)
    found = [i for i in a.atoms if issues[i].points is None]
    rows = [{"Schlüssel": issues[i].key, "Titel": issues[i].summary, "Typ": issues[i].type, "Status": issues[i].status, "Epic": epics[i]} for i in found[:limit]]
    return rows, len(found)


def rows_to_csv(rows: list[dict]) -> bytes:
    """CSV für Excel im deutschen Raum: Semikolon, Dezimalkomma, UTF-8 mit Kennung. Zahlen unverändert genau, leere Zellen für None, Semikolon in Text durch Komma ersetzt."""
    if not rows:
        return "".encode("utf-8-sig")

    def cell(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        if isinstance(v, float):
            return repr(v).replace(".", ",")
        if isinstance(v, (dt.date,)):
            return v.isoformat()
        return str(v).replace(";", ",").replace("\n", " ")
    header = list(rows[0])
    lines = [";".join(h.replace(";", ",") for h in header)] + [";".join(cell(r.get(h)) for h in header) for r in rows]
    return ("\n".join(lines) + "\n").encode("utf-8-sig")


def _pct_or_dash(x) -> str:
    return "–" if x is None or x != x else pct(x)


def summary_markdown(issues, a: Analysis, unit: str, as_of: dt.date) -> str:
    """Zusammenfassung als Markdown zum Kopieren (Confluence, Mail, Chat): Gesamtfortschritt in allen drei Maßen, Umfang, die Annahmen und die Gruppentabelle der gewählten
    Ebene. Die Annahmen stehen immer dabei, damit die Zahl nicht ohne Kontext weitergegeben wird."""
    s = a.settings
    credits = ", ".join(f"{status} {round(100 * a.credits[status])} %" for status in atom_statuses(issues, a))
    assumptions = [f"Status-Gewichte {credits}", f"Gewicht {s.weight_mode}"]
    if s.weight_mode == C.WEIGHT_POINTS:
        assumptions.append(f"ungeschätzte Tickets {s.unest_rule}")
    assumptions += [f"Zählebene {s.count_level}", f"Sub-Task-Option {'an' if s.blend and s.count_level == C.LEVEL_STORIES else 'aus'}"]
    lines = [
        f"**Jira-Fortschritt** (Stand {as_of.strftime('%d.%m.%Y')})", "",
        f"- Fortschritt (nach Status gewichtet): {_pct_or_dash(a.progress)}",
        f"- Nur Done: {_pct_or_dash(a.progress_done)} nach Gewicht, {_pct_or_dash(a.progress_count)} nach Ticketzahl",
        f"- Umfang: {a.n_atoms} Tickets ({a.n_unestimated} ohne Story Points), Gewicht {de(a.weight)} {unit}",
        f"- Annahmen: {'; '.join(assumptions)}", ""]
    rows = contribution(a)
    if rows:
        shown = rows if len(rows) - 1 <= MAX_SUMMARY_ROWS else rows[:MAX_SUMMARY_ROWS] + rows[-1:]       # Gruppen bis zur Obergrenze: alle samt Summenzeile
        head = s.dimension if s.dimension != C.DIM_ALL else "Gruppe"
        lines += [f"| {head} | Gewicht ({unit}) | Fortschritt | Offen ({unit}) |", "|---|---:|---:|---:|"]
        for r in shown:
            lines.append(f"| {str(r['Gruppe']).replace('|', '/')} | {de(r['Gewicht'])} | {_pct_or_dash(r['Fortschritt'])} | {de(r['Offenes Gewicht'])} |")
        if len(rows) > len(shown):
            lines += ["", f"(Gezeigt: die ersten {MAX_SUMMARY_ROWS} von {len(rows) - 1} Gruppen und die Summe.)"]
    return "\n".join(lines) + "\n"
