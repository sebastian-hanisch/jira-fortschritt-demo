"""Kern der Demo (nur numpy/Standardbibliothek): gewichteter Fortschritt aus Status, Story Points und Aggregationsebenen.

Jede Regel ist eine eigene Funktion mit expliziten Ein- und Ausgaben (DEMO-PLAYBOOK §1b); `analyse` in jira_evaluation.py ruft nur der Reihe nach auf.

Modell: Ein *Atom* ist ein Ticket der gewählten Zählebene (Stories/Tasks/Bugs oder Sub-Tasks). Es hat ein Gewicht w (Story Points oder 1) und eine
Gutschrift c in [0, 1] (Anteil der Arbeit, der laut Status als getan gilt). Der Fortschritt einer Gruppe G ist  P(G) = sum_G w*c / sum_G w."""

import datetime as dt
import re
from dataclasses import dataclass
from statistics import median

import numpy as np

import jira_constants as C
from jira_scenario import Issue

# ---------------------------------------------------------------- Status und Gutschriften


def scheme_credit(scheme: str, status: str, category: str) -> float:
    """Gutschrift eines Status unter einem festen Schema (Nur Done, Linear, Workflow-gewichtet)."""
    if scheme == C.SCHEME_DONE:
        return 1.0 if category == "done" else 0.0
    if scheme == C.SCHEME_LINEAR:
        return C.CATEGORY_CREDIT_LINEAR[category]
    if scheme == C.SCHEME_WORKFLOW:
        if category != "indeterminate":
            return C.CATEGORY_CREDIT_LINEAR[category]
        name = status.lower()
        for words, credit in C.WORKFLOW_KEYWORDS:
            if any(w in name for w in words):
                return credit
        return C.CATEGORY_CREDIT_LINEAR["indeterminate"]
    raise ValueError(f"unbekanntes Schema {scheme!r}")


def status_credits(statuses, scheme: str, custom=()) -> dict[str, float]:
    """Gutschrift je Status. `statuses`: Paare (Status, Kategorie). Bei `Eigene Gewichte` zählen die Werte aus `custom` (Paare Status, Gutschrift);
    ein Status ohne eigenen Wert fällt auf das lineare Schema zurück."""
    if scheme == C.SCHEME_CUSTOM:
        own = dict(custom)
        return {s: float(own[s]) if s in own else scheme_credit(C.SCHEME_LINEAR, s, cat) for s, cat in statuses}
    return {s: scheme_credit(scheme, s, cat) for s, cat in statuses}


def apply_credit_edits(base, edited_rows: dict) -> tuple[tuple[str, float], ...]:
    """Überträgt Änderungen der Tabelle (`edited_rows` von st.data_editor: {Zeile: {Spalte: Wert}}) auf die Basis (Paare Status, Gutschrift in 0..1).
    Die Spalte der Tabelle heißt `Gewicht (%)`; Werte werden auf 0 bis 100 begrenzt."""
    out = [[s, float(c)] for s, c in base]
    for row, changes in edited_rows.items():
        if "Gewicht (%)" in changes and changes["Gewicht (%)"] is not None:
            out[int(row)][1] = min(max(float(changes["Gewicht (%)"]), 0.0), 100.0) / 100.0
    return tuple((s, c) for s, c in out)


# ---------------------------------------------------------------- Hierarchie

def epic_of(issues) -> list[str]:
    """Schlüssel des Epics je Ticket (Elternkette bis zu einem Ticket vom Typ Epic), leer ohne Epic. Zyklen und fehlende Eltern enden mit leer."""
    by_key = {i.key: i for i in issues}
    result = []
    for issue in issues:
        current, found, steps = issue, "", 0
        while current is not None and steps < 10:
            if current.is_epic:
                found = current.key
                break
            current = by_key.get(current.parent)
            steps += 1
        result.append(found)
    return result


def children_of(issues) -> dict[str, list[int]]:
    """Indizes der direkten Kinder je Eltern-Schlüssel."""
    out: dict[str, list[int]] = {}
    for idx, issue in enumerate(issues):
        if issue.parent:
            out.setdefault(issue.parent, []).append(idx)
    return out


def subtree_keys(issues, root: str) -> set[str]:
    """Schlüssel des Tickets `root` und aller Tickets darunter (Kinder, Enkel, ...); Zyklen in den Eltern-Verweisen enden, ohne etwas doppelt zu zählen."""
    if root not in {t.key for t in issues}:
        raise ValueError(f"unbekannte Wurzel {root!r}")
    kids = children_of(issues)
    seen, stack = {root}, [root]
    while stack:
        for j in kids.get(stack.pop(), []):
            if issues[j].key not in seen:
                seen.add(issues[j].key)
                stack.append(issues[j].key)
    return seen


def select_atoms(issues, level: str, root: str = C.ROOT_ALL) -> list[int]:
    """Zählebene: Stories/Tasks/Bugs (alles außer Epics und Sub-Tasks) oder Sub-Tasks. Mit `root` nur die Tickets im Teilbaum unter diesem Ticket (es selbst eingeschlossen)."""
    if level == C.LEVEL_SUBTASKS:
        found = [i for i, t in enumerate(issues) if t.is_subtask]
    elif level == C.LEVEL_STORIES:
        found = [i for i, t in enumerate(issues) if not t.is_subtask and not t.is_epic]
    else:
        raise ValueError(f"unbekannte Zählebene {level!r}")
    if root == C.ROOT_ALL:
        return found
    scope = subtree_keys(issues, root)
    return [i for i in found if issues[i].key in scope]


def tree_order(issues, root: str = C.ROOT_ALL) -> list[tuple[int, int, int]]:
    """Die Tickets als Wald in Tiefensuche-Reihenfolge: (Index, Tiefe, Index des Elternknotens im Baum oder -1). Wurzeln sind Tickets ohne Eltern in der Datei; ein Zyklus
    ohne Wurzel folgt am Ende und beginnt bei seinem ersten Ticket. Mit `root` nur dieser Teilbaum, die Wurzel in Tiefe 0."""
    index = {t.key: n for n, t in enumerate(issues)}
    kids = children_of(issues)
    out: list[tuple[int, int, int]] = []
    seen: set[int] = set()

    def walk(start: int) -> None:
        stack = [(start, 0, -1)]
        while stack:
            i, depth, parent = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            out.append((i, depth, parent))
            for j in reversed(kids.get(issues[i].key, [])):
                stack.append((j, depth + 1, i))

    if root != C.ROOT_ALL:
        if root not in index:
            raise ValueError(f"unbekannte Wurzel {root!r}")
        walk(index[root])
        return out
    for n, t in enumerate(issues):
        if t.parent not in index or t.parent == t.key:
            walk(n)
    for n in range(len(issues)):
        walk(n)
    return out


def root_choices(issues) -> list[tuple[str, int]]:
    """Tickets, die als Wurzel einer Teilauswertung taugen (alle mit Kindern, außer Sub-Tasks), in der Reihenfolge des Baums mit ihrer Tiefe."""
    kids = children_of(issues)
    return [(issues[i].key, depth) for i, depth, _ in tree_order(issues) if issues[i].key in kids and not issues[i].is_subtask]


# ---------------------------------------------------------------- Gewichte und Gutschriften

def atom_weights(issues, atoms, mode: str, rule: str) -> np.ndarray:
    """Gewicht je Atom. Story Points: der Wert des Tickets; fehlt er, entscheidet die Regel (nicht zählen = 0, als 1 Story Point, Median der geschätzten Atome
    - ohne geschätztes Atom gilt 1). Ticketanzahl: jedes Atom 1."""
    if mode == C.WEIGHT_COUNT:
        return np.ones(len(atoms))
    if mode != C.WEIGHT_POINTS:
        raise ValueError(f"unbekannter Gewichtungsmodus {mode!r}")
    given = [issues[i].points for i in atoms if issues[i].points is not None]
    fill = {C.UNEST_IGNORE: 0.0, C.UNEST_ONE: 1.0, C.UNEST_MEDIAN: float(median(given)) if given else 1.0}[rule]
    return np.array([issues[i].points if issues[i].points is not None else fill for i in atoms], dtype=float)


def blended_credit(sub_credits: np.ndarray, sub_points: list[float | None]) -> float:
    """Fortschritt einer Story aus ihren Sub-Tasks: gewichtet mit den Story Points der Sub-Tasks, wenn alle welche haben (> 0), sonst gleich gewichtet."""
    if len(sub_credits) == 0:
        return 0.0
    if all(p is not None and p > 0 for p in sub_points):
        weights = np.array(sub_points, dtype=float)
    else:
        weights = np.ones(len(sub_credits))
    return float(np.dot(weights, sub_credits) / weights.sum())


def atom_credits(issues, atoms, credit_of: dict[str, float], blend: bool) -> np.ndarray:
    """Gutschrift je Atom aus dem Status. Mit `blend` (nur sinnvoll auf der Ebene Stories) gilt das Maximum aus dem eigenen Status und dem Fortschritt der
    Sub-Tasks: der Status der Story ist eine Untergrenze."""
    own = np.array([credit_of[issues[i].status] for i in atoms], dtype=float)
    if not blend:
        return own
    kids = children_of(issues)
    out = own.copy()
    for pos, i in enumerate(atoms):
        subs = [j for j in kids.get(issues[i].key, []) if issues[j].is_subtask]
        if subs:
            sub_c = np.array([credit_of[issues[j].status] for j in subs], dtype=float)
            out[pos] = max(own[pos], blended_credit(sub_c, [issues[j].points for j in subs]))
    return out


# ---------------------------------------------------------------- Aggregationsebenen

@dataclass(frozen=True)
class Assignment:
    """Zuordnung der Atome zu Gruppen in Koordinatenform: Eintrag k ordnet Atom `atom[k]` der Gruppe `group[k]` mit Anteil `share[k]` zu.
    Mehrfachwerte (mehrere Labels, Komponenten) teilen das Atom gleichmäßig auf, damit die Summe über alle Gruppen die Gesamtsumme bleibt."""

    labels: tuple[str, ...]
    atom: np.ndarray    # Position in der Atomliste
    group: np.ndarray
    share: np.ndarray


def natural_key(label: str):
    """Sortierschlüssel mit Zahlen als Zahlen (Sprint 2 vor Sprint 10); Gruppen „(ohne …)“ zuletzt."""
    return (label.startswith("("), [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", label)])


def _inherited(by_key: dict[str, Issue], issue: Issue, getter):
    """Wert des Tickets, bei leerem Wert der des übergeordneten Tickets (Sub-Tasks erben Sprint, Komponente und Release)."""
    value = getter(issue)
    parent = by_key.get(issue.parent) if not value else None
    return getter(parent) if parent is not None else value


def ticket_sprint(by_key: dict[str, Issue], t: Issue) -> str:
    """Der Sprint eines Tickets: bei mehreren der letzte, bei keinem der des übergeordneten Tickets (wie bei der Ebene Sprint); leer ohne Sprint."""
    sprints = _inherited(by_key, t, lambda x: x.sprints)
    return sprints[-1] if sprints else ""


def sprint_order(issues) -> list[str]:
    """Alle Sprints der Tickets in natürlicher Reihenfolge (Sprint 2 vor Sprint 10): die Reihenfolge, in der „von … bis …“ gilt."""
    by_key = {i.key: i for i in issues}
    return sorted({ticket_sprint(by_key, t) for t in issues} - {""}, key=natural_key)


def filter_sprints(issues, atoms: list[int], first: str = C.SPRINT_OPEN, last: str = C.SPRINT_OPEN, include_none: bool = False) -> list[int]:
    """Zeitraum der Auswertung: nur Atome, deren Sprint zwischen `first` und `last` liegt (beide eingeschlossen, offen = bis zum ersten bzw. letzten Sprint). Ohne beide Grenzen
    bleibt alles. Atome ohne Sprint bleiben nur mit `include_none`. Ein Sprint, den es nicht gibt, ist ein Fehler; `first` hinter `last` ergibt nichts."""
    if first == C.SPRINT_OPEN and last == C.SPRINT_OPEN:
        return list(atoms)
    order = sprint_order(issues)
    for name in (first, last):
        if name != C.SPRINT_OPEN and name not in order:
            raise ValueError(f"unbekannter Sprint {name!r}")
    lo = order.index(first) if first != C.SPRINT_OPEN else 0
    hi = order.index(last) if last != C.SPRINT_OPEN else len(order) - 1
    by_key = {i.key: i for i in issues}
    keep = []
    for i in atoms:
        sprint = ticket_sprint(by_key, issues[i])
        if (sprint == "" and include_none) or (sprint != "" and lo <= order.index(sprint) <= hi):
            keep.append(i)
    return keep


def hierarchy_chains(issues) -> list[list[int]]:
    """Je Ticket die Kette der Tickets von der obersten Stufe bis zu ihm selbst (Indizes); Zyklen und fehlende Eltern enden an der Stelle, an der der Baum aufhört."""
    chains: list[list[int]] = [[] for _ in issues]
    for i, _, parent in tree_order(issues):
        chains[i] = (chains[parent] if parent >= 0 else []) + [i]
    return chains


def max_level(issues) -> int:
    """Tiefste vorkommende Hierarchiestufe (1 = oberste Stufe), höchstens `C.MAX_LEVELS`."""
    return min(max((len(c) for c in hierarchy_chains(issues)), default=1), C.MAX_LEVELS)


def level_labels(issues, atoms, level: int) -> list[str]:
    """Gruppe je Atom auf der Hierarchiestufe `level` (1 = oberste Stufe): das Ticket der Kette auf dieser Stufe, bei einem Atom auf genau dieser Stufe es selbst. Ein Atom, das höher
    steht, bekommt „(keine Stufe n)“."""
    chains = hierarchy_chains(issues)
    out = []
    for i in atoms:
        chain = chains[i]
        if len(chain) >= level:
            t = issues[chain[level - 1]]
            out.append(f"{t.key}: {t.summary}" if t.summary else t.key)
        else:
            out.append(f"(keine Stufe {level})")
    return out


def group_labels(by_key: dict[str, Issue], t: Issue, epic_key: str, epic_names: dict[str, str], dim: str) -> list[str]:
    """Gruppenbezeichnungen eines Tickets in der Ebene `dim` (eine, bei Mehrfachwerten mehrere)."""
    if dim == C.DIM_ALL:
        return ["Gesamtes Projekt"]
    if dim == C.DIM_EPIC:
        return [f"{epic_key}: {epic_names[epic_key]}" if epic_key else "(ohne Epic)"]
    if dim == C.DIM_SPRINT:
        sprints = _inherited(by_key, t, lambda x: x.sprints)
        return [sprints[-1]] if sprints else ["(ohne Sprint)"]       # bei übernommenen Tickets zählt der letzte Sprint
    if dim == C.DIM_RELEASE:
        return list(_inherited(by_key, t, lambda x: x.versions)) or ["(ohne Release)"]
    if dim == C.DIM_COMPONENT:
        return list(_inherited(by_key, t, lambda x: x.components)) or ["(ohne Komponente)"]
    if dim == C.DIM_LABEL:
        return list(t.labels) or ["(ohne Label)"]
    if dim == C.DIM_ASSIGNEE:
        return [t.assignee or "(nicht zugewiesen)"]
    if dim == C.DIM_TEAM:
        return [t.team or "(ohne Team)"]
    if dim == C.DIM_AREA:
        return [t.area or "(ohne Bereich)"]
    if dim == C.DIM_PRIORITY:
        return [t.priority or "(ohne Priorität)"]
    if dim == C.DIM_TYPE:
        return [t.type]
    if dim == C.DIM_STATUS:
        return [t.status]
    raise ValueError(f"unbekannte Ebene {dim!r}")


def assign_groups(issues, atoms, dim: str, level: int = 1) -> Assignment:
    """Ordnet jedes Atom den Gruppen der Ebene `dim` zu (bei der Ebene Hierarchiestufe die Stufe `level`)."""
    epics = epic_of(issues)
    epic_names = {i.key: i.summary or i.key for i in issues if i.is_epic}
    by_key = {i.key: i for i in issues}
    if dim == C.DIM_LEVEL:
        per_atom = [[label] for label in level_labels(issues, atoms, level)]
    else:
        per_atom = [group_labels(by_key, issues[i], epics[i], epic_names, dim) for i in atoms]
    labels = tuple(sorted({g for gs in per_atom for g in gs}, key=natural_key))
    index = {g: n for n, g in enumerate(labels)}
    a_idx, g_idx, share = [], [], []
    for pos, gs in enumerate(per_atom):
        for g in gs:
            a_idx.append(pos)
            g_idx.append(index[g])
            share.append(1.0 / len(gs))
    return Assignment(labels, np.array(a_idx, dtype=int), np.array(g_idx, dtype=int), np.array(share, dtype=float))


PAIR_SEP = " | "      # trennt die Bezeichnungen der beiden Ebenen in einer Kreuzgruppe


def cross_assignment(a: Assignment, b: Assignment) -> Assignment:
    """Zwei Ebenen zugleich: Gruppen sind Paare (Zeile × Spalte), der Anteil ist das Produkt der Einzelanteile. Bezeichnung „Zeile | Spalte“ (PAIR_SEP)."""
    b_of: dict[int, list[tuple[int, float]]] = {}
    for atom, g, s in zip(b.atom, b.group, b.share):
        b_of.setdefault(int(atom), []).append((int(g), float(s)))
    pairs: dict[tuple[int, int], int] = {}
    atom_l, group_l, share_l = [], [], []
    for atom, g, s in zip(a.atom, a.group, a.share):
        for g2, s2 in b_of.get(int(atom), []):
            pair = (int(g), g2)
            pairs.setdefault(pair, len(pairs))
            atom_l.append(int(atom))
            group_l.append(pairs[pair])
            share_l.append(float(s) * s2)
    order = sorted(pairs, key=lambda p: (natural_key(a.labels[p[0]]), natural_key(b.labels[p[1]])))
    rank = {pairs[p]: n for n, p in enumerate(order)}
    labels = tuple(f"{a.labels[p[0]]}{PAIR_SEP}{b.labels[p[1]]}" for p in order)
    return Assignment(labels, np.array(atom_l, dtype=int), np.array([rank[g] for g in group_l], dtype=int), np.array(share_l, dtype=float))


@dataclass(frozen=True)
class GroupStats:
    labels: tuple[str, ...]
    weight: np.ndarray      # sum w
    credited: np.ndarray    # sum w*c
    done_weight: np.ndarray  # sum w über Atome mit Statuskategorie Done
    count: np.ndarray       # Atome (anteilig)
    done_count: np.ndarray
    unestimated: np.ndarray  # Atome ohne Story Points (anteilig)

    @property
    def progress(self) -> np.ndarray:
        """Gewichteter Fortschritt je Gruppe in [0, 1]; NaN, wenn die Gruppe kein Gewicht hat."""
        return ratio(self.credited, self.weight)

    @property
    def progress_done(self) -> np.ndarray:
        return ratio(self.done_weight, self.weight)

    @property
    def progress_count(self) -> np.ndarray:
        return ratio(self.done_count, self.count)


def ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Quotient je Eintrag; NaN, wo der Nenner nicht positiv ist (eine Gruppe ohne Gewicht hat keinen Fortschritt)."""
    out = np.full(len(denominator), np.nan)
    np.divide(numerator, denominator, out=out, where=denominator > 0)
    return out


def aggregate(assign: Assignment, w: np.ndarray, c: np.ndarray, done: np.ndarray, unest: np.ndarray) -> GroupStats:
    """Summiert Gewicht, Gutschrift und Zähler je Gruppe mit einem Scatter-Add (np.bincount)."""
    n = len(assign.labels)
    a, s = assign.atom, assign.share
    def total(values):
        return np.bincount(assign.group, weights=values[a] * s, minlength=n)
    return GroupStats(assign.labels, total(w), total(w * c), total(w * done), total(np.ones(len(w))), total(done.astype(float)), total(unest.astype(float)))


def overall(w: np.ndarray, c: np.ndarray, done: np.ndarray) -> tuple[float, float, float]:
    """Gesamtfortschritt über alle Atome: (gewichtet nach Status, nur erledigt nach Gewicht, nur erledigt nach Ticketanzahl); NaN ohne Gewicht bzw. Atome."""
    total = np.array([w.sum()])
    p_w, p_d = (float(ratio(np.array([x]), total)[0]) for x in (np.dot(w, c), np.dot(w, done)))
    p_n = float(done.sum() / len(done)) if len(done) else float("nan")
    return p_w, p_d, p_n


# ---------------------------------------------------------------- Verlauf und Hierarchie

def burn_up(issues, atoms, w: np.ndarray, done: np.ndarray, today: dt.date, step_days: int = C.BURNUP_STEP_DAYS):
    """Burn-up aus Erstell- und Lösungsdatum: Umfang(t) = Gewicht aller bis t erstellten Atome, Erledigt(t) = Gewicht der bis t gelösten Done-Atome.
    Rückgabe (Stichtage, Umfang, Erledigt, Zahl Done-Atome ohne Lösungsdatum). Ohne Erstelldatum gilt das früheste Datum. Der Statusverlauf liegt hier
    nicht vor, deshalb gibt es keine zeitliche Fassung der Status-Gutschriften."""
    created = [issues[i].created for i in atoms]
    dates = [d for d in created if d is not None] + [issues[i].resolved for i in atoms if issues[i].resolved is not None]
    if not dates:
        return [], np.zeros(0), np.zeros(0), 0
    start = min(dates)
    end = max(max(dates), today)
    grid = [start + dt.timedelta(days=step_days * k) for k in range((end - start).days // step_days + 1)]
    if grid[-1] != end:
        grid.append(end)
    ordinals = np.array([g.toordinal() for g in grid])
    c_ord = np.array([(d or start).toordinal() for d in created])
    missing = 0
    r_ord, r_w = [], []
    for pos, i in enumerate(atoms):
        if done[pos]:
            if issues[i].resolved is None:
                missing += 1
            else:
                r_ord.append(issues[i].resolved.toordinal())
                r_w.append(w[pos])
    scope = np.array([w[c_ord <= o].sum() for o in ordinals])
    r_ord_a, r_w_a = np.array(r_ord, dtype=int), np.array(r_w, dtype=float)
    finished = np.array([r_w_a[r_ord_a <= o].sum() for o in ordinals]) if len(r_w_a) else np.zeros(len(ordinals))
    return grid, scope, finished, missing


@dataclass(frozen=True)
class Hierarchy:
    ids: tuple[str, ...]
    labels: tuple[str, ...]
    parents: tuple[str, ...]
    values: tuple[float, ...]
    progress: tuple[float, ...]


def hierarchy(issues, atoms, w: np.ndarray, c: np.ndarray) -> Hierarchy:
    """Baum Projekt → Epic → Atom für die Flächenansicht: Fläche = Gewicht, Farbe = Fortschritt. Atome ohne Gewicht fehlen (Fläche 0);
    ein Elternknoten trägt die Summe seiner Kinder."""
    epics = epic_of(issues)
    names = {i.key: f"{i.key}: {i.summary}" if i.summary else i.key for i in issues if i.is_epic}
    ids, labels, parents, values, wc = ["Projekt"], ["Projekt"], [""], [0.0], [0.0]
    epic_row: dict[str, int] = {}
    for pos, i in enumerate(atoms):
        if w[pos] <= 0:
            continue
        ek = epics[i]
        eid = f"epic:{ek}" if ek else "epic:(ohne Epic)"
        if eid not in epic_row:
            epic_row[eid] = len(ids)
            ids.append(eid)
            labels.append(names.get(ek, "(ohne Epic)"))
            parents.append("Projekt")
            values.append(0.0)
            wc.append(0.0)
        ids.append(f"atom:{issues[i].key}")
        labels.append(issues[i].key)
        parents.append(eid)
        values.append(float(w[pos]))
        wc.append(float(w[pos] * c[pos]))
        values[epic_row[eid]] += float(w[pos])
        wc[epic_row[eid]] += float(w[pos] * c[pos])
        values[0] += float(w[pos])
        wc[0] += float(w[pos] * c[pos])
    progress = [wc_k / v if v > 0 else 0.0 for wc_k, v in zip(wc, values)]
    return Hierarchy(tuple(ids), tuple(labels), tuple(parents), tuple(values), tuple(progress))


@dataclass(frozen=True)
class TreeGraph:
    """Knoten des Hierarchiegraphen, ein Eintrag je Knoten in Tiefensuche-Reihenfolge (Eltern vor Kindern). `x` ist die Tiefe, `y` die Zeile; Elternknoten stehen mittig
    vor ihren Kindern. `progress` ist NaN, wenn der Knoten nichts Messbares trägt."""

    keys: tuple[str, ...]
    titles: tuple[str, ...]
    types: tuple[str, ...]
    statuses: tuple[str, ...]
    x: np.ndarray
    y: np.ndarray
    parent: np.ndarray        # Position des Elternknotens, -1 für die Wurzel
    weight: np.ndarray
    progress: np.ndarray
    is_atom: np.ndarray
    is_leaf: np.ndarray       # ohne gezeichnete Kinder
    hidden: np.ndarray        # Zahl der Tickets darunter, die nicht gezeichnet werden (zusammengefasste Ebene)
    n_total: int              # Knoten vor dem Zusammenfassen
    shown_depth: int          # tiefste gezeichnete Ebene
    ignored: np.ndarray | None = None      # Tickets außerhalb des Zeitraums: zählen nicht, nichts messbar


def tree_graph(issues, atoms, w: np.ndarray, c: np.ndarray, credit_of: dict[str, float], root: str = C.ROOT_ALL, max_nodes: int = C.GRAPH_MAX_NODES,
               excluded: frozenset[int] = frozenset()) -> TreeGraph:
    """Gewicht und Fortschritt je Knoten des Hierarchiebaums. Ein Knoten trägt die Summe seiner Atome (er selbst, falls er eins ist, und alle darunter), der Fortschritt ist
    die gewichtete Gutschrift dieser Summe. Ein Blatt ohne Gewicht zeigt die Gutschrift seines Status (z. B. Sub-Tasks, wenn Stories zählen); alles andere ohne Gewicht bleibt
    leer. Ohne `root` steht ein Knoten „Projekt“ über allen Wurzeln. Über `max_nodes` hinaus wird die tiefste Ebene so lange zusammengefasst, bis der Graph passt."""
    order = tree_order(issues, root)
    shift = 0 if root != C.ROOT_ALL else 1
    n = len(order) + shift
    keys = [""] * n
    titles = [""] * n
    types = [""] * n
    statuses = [""] * n
    depth = np.zeros(n, dtype=int)
    parent = np.full(n, -1, dtype=int)
    node_issue = [-1] * n
    if shift:
        keys[0] = "Projekt"
    for p, (i, d, par) in enumerate(order, start=shift):
        node_issue[p] = i
        keys[p], titles[p], types[p], statuses[p] = issues[i].key, issues[i].summary, issues[i].type, issues[i].status
        depth[p] = d + shift
    pos_of_issue = {i: p for p, i in enumerate(node_issue) if i >= 0}
    for p, (_, _, par) in enumerate(order, start=shift):
        parent[p] = pos_of_issue[par] if par >= 0 else (0 if shift else -1)
    wsum = np.zeros(n)
    csum = np.zeros(n)
    is_atom = np.zeros(n, dtype=bool)
    for k, i in enumerate(atoms):
        p = pos_of_issue.get(i)
        if p is not None:
            wsum[p] += w[k]
            csum[p] += w[k] * c[k]
            is_atom[p] = True
    size = np.ones(n, dtype=int)
    for p in range(n - 1, 0, -1):          # Kinder stehen nach ihren Eltern (jeder Knoten außer der ersten hat einen): von hinten summieren
        wsum[parent[p]] += wsum[p]
        csum[parent[p]] += csum[p]
        size[parent[p]] += size[p]
    # zusammenfassen: tiefste Ebene, bei der höchstens max_nodes Knoten bleiben (mindestens die Wurzel)
    fits = np.nonzero(np.cumsum(np.bincount(depth)) <= max_nodes)[0]
    shown_depth = int(fits[-1]) if len(fits) else 0
    keep = [p for p in range(n) if depth[p] <= shown_depth]
    slot = {p: s for s, p in enumerate(keep)}
    kept_kids: dict[int, list[int]] = {}
    for p in keep:
        if parent[p] >= 0:
            kept_kids.setdefault(parent[p], []).append(p)
    y = {}
    row = 0
    for p in keep:                           # Blätter in Tiefensuche-Reihenfolge untereinander
        if p not in kept_kids:
            y[p] = float(row)
            row += 1
    for p in reversed(keep):
        if p in kept_kids:
            y[p] = (y[kept_kids[p][0]] + y[kept_kids[p][-1]]) / 2
    progress, weight, hidden = [], [], []
    for p in keep:
        weight.append(float(wsum[p]))
        if node_issue[p] in excluded:
            progress.append(float("nan"))
        elif wsum[p] > 0:
            progress.append(float(csum[p] / wsum[p]))
        elif p not in kept_kids and size[p] == 1 and node_issue[p] >= 0 and not issues[node_issue[p]].is_epic:
            progress.append(float(credit_of.get(issues[node_issue[p]].status, np.nan)))
        else:
            progress.append(float("nan"))
        hidden.append(int(size[p] - 1) if depth[p] == shown_depth else 0)
    return TreeGraph(
        tuple(keys[p] for p in keep), tuple(titles[p] for p in keep), tuple(types[p] for p in keep), tuple(statuses[p] for p in keep), np.array([depth[p] for p in keep]), np.array([y[p] for p in keep]),
        np.array([slot[parent[p]] if parent[p] >= 0 else -1 for p in keep], dtype=int), np.array(weight), np.array(progress), np.array([is_atom[p] for p in keep]),
        np.array([p not in kept_kids for p in keep]), np.array(hidden, dtype=int), n, shown_depth, np.array([node_issue[p] in excluded for p in keep]))
