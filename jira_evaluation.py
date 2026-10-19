"""Kennzahlen, Verdikt-Logik und Sensitivitätsprüfung. `analyse` ruft die Einheiten des Kerns nur der Reihe nach auf."""

import datetime as dt
from dataclasses import dataclass, replace

import numpy as np

import jira_algorithm as A
import jira_constants as C


@dataclass(frozen=True, kw_only=True)
class Settings:
    scheme: str = C.DEFAULT_SCHEME
    custom: tuple[tuple[str, float], ...] = ()          # nur für „Eigene Gewichte“: (Status, Gutschrift in 0..1)
    weight_mode: str = C.DEFAULT_WEIGHT_MODE
    unest_rule: str = C.DEFAULT_UNEST
    count_level: str = C.DEFAULT_LEVEL
    blend: bool = False
    dimension: str = C.DEFAULT_DIM
    dimension2: str = C.DEFAULT_DIM2


@dataclass(frozen=True)
class Analysis:
    settings: Settings
    credits: dict[str, float]
    n_atoms: int
    weight: float
    progress: float            # gewichtet nach Status
    progress_done: float       # nur erledigt, nach Gewicht
    progress_count: float      # nur erledigt, nach Ticketanzahl
    n_unestimated: int
    stats: A.GroupStats
    cross: A.GroupStats | None
    hierarchy: A.Hierarchy
    burn: tuple


def de(x: float, digits: int = 1, sign: bool = False) -> str:
    """Zahl mit Dezimalkomma; `sign` setzt ein Vorzeichen auch vor positive Werte (für Differenzen)."""
    return f"{x:{'+' if sign else ''}.{digits}f}".replace(".", ",")


def pct(x: float) -> str:
    return de(100 * x) + " %"


def status_list(issues) -> list[tuple[str, str]]:
    """Alle vorkommenden Status mit ihrer Kategorie (die häufigste Kategorie, falls ein Status unterschiedlich eingeordnet ist), sortiert nach Kategorie und Namen."""
    seen: dict[str, dict[str, int]] = {}
    for t in issues:
        seen.setdefault(t.status, {}).setdefault(t.category, 0)
        seen[t.status][t.category] += 1
    pairs = [(s, max(cats, key=lambda k: (cats[k], k))) for s, cats in seen.items()]
    return sorted(pairs, key=lambda p: (C.CATEGORIES.index(p[1]), p[0].lower()))


def analyse(issues, settings: Settings, today: dt.date = C.SAMPLE_TODAY) -> Analysis:
    credit_of = A.status_credits(status_list(issues), settings.scheme, settings.custom)
    atoms = A.select_atoms(issues, settings.count_level)
    w = A.atom_weights(issues, atoms, settings.weight_mode, settings.unest_rule)
    blend = settings.blend and settings.count_level == C.LEVEL_STORIES
    c = A.atom_credits(issues, atoms, credit_of, blend)
    done = np.array([issues[i].category == "done" for i in atoms], dtype=bool)
    unest = np.array([issues[i].points is None for i in atoms], dtype=bool)
    p_w, p_d, p_n = A.overall(w, c, done)
    first = A.assign_groups(issues, atoms, settings.dimension)
    stats = A.aggregate(first, w, c, done, unest)
    cross = None
    if settings.dimension2 != C.DIM_NONE:
        second = A.assign_groups(issues, atoms, settings.dimension2)
        cross = A.aggregate(A.cross_assignment(first, second), w, c, done, unest)
    return Analysis(settings, credit_of, len(atoms), float(w.sum()), p_w, p_d, p_n, int(unest.sum()), stats, cross,
                    A.hierarchy(issues, atoms, w, c), A.burn_up(issues, atoms, w, done, today))


def sensitivity(issues, settings: Settings) -> list[dict]:
    """Gesamtfortschritt unter jeder Kombination aus den drei festen Schemata und den zwei Gewichtungen; alles Übrige wie eingestellt."""
    rows = []
    for scheme in C.SENSITIVITY_SCHEMES:
        for mode in C.WEIGHT_MODES:
            a = analyse(issues, replace(settings, scheme=scheme, weight_mode=mode, dimension=C.DIM_ALL, dimension2=C.DIM_NONE))
            rows.append({"scheme": scheme, "mode": mode, "progress": a.progress})
    return rows


# ---------------------------------------------------------------- Verdikte (reine Funktionen: (Art, Text))

def verdict_measures(p_weighted: float, p_done: float, p_count: float) -> tuple[str, str]:
    """Wie weit liegen die drei Maße (nach Status gewichtet, nur Done nach Story Points, nur Done nach Ticketzahl) auseinander?"""
    values = [p_weighted, p_done, p_count]
    if any(np.isnan(v) for v in values):
        return "warning", "Mindestens ein Maß lässt sich nicht berechnen, weil kein Ticket Gewicht hat. Die Regel für ungeschätzte Tickets oder die Zählebene ändern."
    spread = round(100 * (max(values) - min(values)), 9)       # gerundet, damit genau 5,0 Punkte nicht an Rundungsrauschen scheitern
    line = f"Nach Status gewichtet {pct(p_weighted)}, nur Done nach Story Points {pct(p_done)}, nur Done nach Ticketzahl {pct(p_count)}"
    if spread < 5:
        return "success", f"{line}: Die Maße liegen nur {de(spread)} Prozentpunkte auseinander, die Wahl der Gewichte ändert das Bild hier kaum."
    return "warning", f"{line}: Die Maße liegen {de(spread)} Prozentpunkte auseinander. Welche Zahl berichtet wird, ist hier keine Formsache."


def verdict_unestimated(n_unestimated: int, n_atoms: int, rule: str, mode: str) -> tuple[str, str]:
    """Wie viele Tickets der Zählebene haben keine Story Points, und was macht die gewählte Regel daraus?"""
    if n_atoms == 0:
        return "warning", "Auf der gewählten Zählebene gibt es keine Tickets."
    if mode == C.WEIGHT_COUNT:
        return "info", f"Gewichtung nach Ticketanzahl: Story Points spielen keine Rolle, {n_unestimated} von {n_atoms} Tickets haben keine."
    if n_unestimated == 0:
        return "success", f"Alle {n_atoms} Tickets sind geschätzt."
    share = 100 * n_unestimated / n_atoms
    text = f"{n_unestimated} von {n_atoms} Tickets ({de(share)} %) haben keine Story Points; Regel: {rule}."
    if rule == C.UNEST_IGNORE:
        text += " Diese Tickets tauchen im Fortschritt nicht auf, auch wenn sie noch offen sind."
    return ("warning" if share >= 20 else "info"), text


def verdict_sensitivity(rows: list[dict]) -> tuple[str, str]:
    """Spanne des Gesamtfortschritts über alle Schema-Gewichtungs-Kombinationen."""
    valid = [r for r in rows if not np.isnan(r["progress"])]
    if not valid:
        return "warning", "Unter keiner Annahme lässt sich ein Fortschritt berechnen: Es fehlt überall Gewicht."
    lo, hi = min(valid, key=lambda r: r["progress"]), max(valid, key=lambda r: r["progress"])
    spread = round(100 * (hi["progress"] - lo["progress"]), 9)
    text = (f"Je nach Annahme liegt der Gesamtfortschritt zwischen {pct(lo['progress'])} ({lo['scheme']}, {lo['mode']}) und {pct(hi['progress'])} "
            f"({hi['scheme']}, {hi['mode']}): {de(spread)} Prozentpunkte Spanne.")
    return ("info" if spread < 10 else "warning"), text


def verdict_groups(stats: A.GroupStats, dim: str) -> tuple[str, str]:
    """Welche Gruppe der gewählten Ebene liegt am weitesten zurück, welche am weitesten vorn (nur Gruppen mit Gewicht)?"""
    p = stats.progress
    ok = [i for i in range(len(p)) if not np.isnan(p[i])]
    if dim == C.DIM_ALL:
        return "info", "Auf der Ebene „Gesamtes Projekt“ gibt es nur eine Gruppe; für einen Vergleich eine andere Ebene wählen."
    if len(ok) < 2:
        return "info", "Es gibt weniger als zwei Gruppen mit Gewicht; ein Vergleich ist nicht möglich."
    lo = min(ok, key=lambda i: (p[i], stats.labels[i]))
    hi = max(ok, key=lambda i: (p[i], stats.labels[i]))
    return "info", (f"Ebene {dim}: am weitesten zurück „{stats.labels[lo]}“ mit {pct(p[lo])} (Gewicht {de(stats.weight[lo])}), "
                    f"am weitesten vorn „{stats.labels[hi]}“ mit {pct(p[hi])} (Gewicht {de(stats.weight[hi])}).")


def check_consistency(a: Analysis, tol: float = 1e-9) -> list[str]:
    """Unabhängiger Prüfer, der auch in der App läuft: Jede Verletzung ist eine Meldung. Erwartet werden Fortschritt in [0, 1], Gruppen, deren Gewichte sich zum
    Gesamtgewicht summieren (Mehrfachwerte werden anteilig verteilt), und eine Kreuztabelle mit demselben Gesamtgewicht."""
    problems = []
    for name, value in (("gewichtet", a.progress), ("nur Done (Gewicht)", a.progress_done), ("nur Done (Anzahl)", a.progress_count)):
        if not np.isnan(value) and not -tol <= value <= 1 + tol:
            problems.append(f"Gesamtfortschritt {name} liegt außerhalb von 0 bis 100 %: {value:.4f}")
    for name, st_ in (("Ebene", a.stats), ("Kreuztabelle", a.cross)):
        if st_ is None:
            continue
        if abs(float(st_.weight.sum()) - a.weight) > tol * max(1.0, a.weight):
            problems.append(f"{name}: Gruppengewichte summieren sich zu {float(st_.weight.sum()):.6f}, erwartet {a.weight:.6f}")
        if abs(float(st_.count.sum()) - a.n_atoms) > tol * max(1, a.n_atoms):
            problems.append(f"{name}: Gruppen zählen {float(st_.count.sum()):.6f} Tickets, erwartet {a.n_atoms}")
    return problems
