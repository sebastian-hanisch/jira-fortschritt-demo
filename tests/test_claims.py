"""Jede Zahl der README, nachgerechnet über dieselben Auswertungsfunktionen wie in der App (DEMO-PLAYBOOK §4).

Das Beispielprojekt ist erzeugt: Die Zahlen zeigen den Mechanismus (wie stark die Wahl der Gewichte die Fortschrittszahl verschiebt), keine Aussage über echte Projekte.
Messreihen laufen über die festen Beispielprojekte SWEEP_SEEDS, nie über einen einzelnen Seed; die Zahlen des Standardprojekts sind Beschreibung, kein Befund."""

import re
import statistics
from pathlib import Path


import jira_constants as C
import jira_evaluation as ev
from jira_scenario import make_sample

README = (Path(__file__).resolve().parent.parent / "README.md").read_text(encoding="utf-8")
DEFAULT = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)


def _pct(x):
    return ev.pct(x)


def _in_readme(text):
    assert text in README, f"README nennt „{text}“ nicht"


def test_default_project_size():
    assert (len(DEFAULT), sum(i.is_epic for i in DEFAULT), sum(i.is_subtask for i in DEFAULT)) == (88, 6, 32)
    a = ev.analyse(DEFAULT, ev.Settings())
    assert (a.n_atoms, a.weight, a.n_unestimated) == (50, 211.0, 6)
    for text in ("88 Tickets", "6 Epics", "32 Sub-Tasks", "50 Stories, Tasks und Bugs", "211 Story Points", "6 davon ungeschätzt"):
        _in_readme(text)


def test_default_progress_under_each_preset():
    got = {name: ev.analyse(DEFAULT, ev.Settings(**p)) for name, p in C.PRESETS.items()}
    standard, strict, workflow = (got[n] for n in C.PRESETS)
    assert _pct(standard.progress) == "48,1 %" and _pct(strict.progress) == "37,4 %" and _pct(workflow.progress) == "56,4 %"
    assert _pct(standard.progress_count) == "40,0 %" and _pct(standard.progress_done) == "37,4 %"
    for text in ("48,1 %", "37,4 %", "56,4 %", "40,0 %"):
        _in_readme(text)


def test_default_sensitivity_range():
    rows = ev.sensitivity(DEFAULT, ev.Settings())
    values = [r["progress"] for r in rows]
    assert _pct(min(values)) == "37,4 %" and _pct(max(values)) == "54,4 %"
    assert ev.de(100 * (max(values) - min(values))) == "16,9"
    _in_readme("16,9 Prozentpunkte")


def test_linear_minus_only_done_over_the_fixed_projects():
    gaps = []
    for seed in C.SWEEP_SEEDS:
        s = make_sample(C.DEFAULT_N_EPICS, seed)
        gaps.append(100 * (ev.analyse(s, ev.Settings()).progress - ev.analyse(s, ev.Settings(scheme=C.SCHEME_DONE)).progress))
    assert len(gaps) == 10
    assert (ev.de(statistics.median(gaps)), ev.de(min(gaps)), ev.de(max(gaps))) == ("6,9", "4,2", "10,2")
    for text in ("10 feste Beispielprojekte", "Median 6,9 Prozentpunkte", "4,2 bis 10,2"):
        _in_readme(text)


def test_sensitivity_spread_over_the_fixed_projects():
    spreads = []
    for seed in C.SWEEP_SEEDS:
        s = make_sample(C.DEFAULT_N_EPICS, seed)
        v = [r["progress"] for r in ev.sensitivity(s, ev.Settings())]
        spreads.append(100 * (max(v) - min(v)))
    assert (ev.de(statistics.median(spreads)), ev.de(min(spreads)), ev.de(max(spreads))) == ("13,9", "8,8", "18,4")
    for text in ("Median 13,9 Prozentpunkte", "8,8 bis 18,4"):
        _in_readme(text)


def test_blend_lifts_the_workflow_scheme_on_the_default_project():
    plain = ev.analyse(DEFAULT, ev.Settings(scheme=C.SCHEME_WORKFLOW)).progress
    blended = ev.analyse(DEFAULT, ev.Settings(scheme=C.SCHEME_WORKFLOW, blend=True)).progress
    assert _pct(plain) == "54,4 %" and _pct(blended) == "56,4 %"
    _in_readme("54,4 % auf 56,4 %")


def test_readme_numbers_with_a_percent_sign_are_all_covered_by_a_claim():
    """Rückwärtsprobe: keine Prozentzahl im README, die kein Test oben kennt."""
    covered = {"48,1 %", "37,4 %", "56,4 %", "40,0 %", "54,4 %", "50 %", "100 %", "0 %", "80 %", "90 %", "40 %"}
    found = set(re.findall(r"\d+(?:,\d+)? %", README))
    assert found <= covered, sorted(found - covered)


def test_limits_stated_in_the_readme_match_the_constants():
    assert C.MAX_IMPORT_ISSUES == 5000 and C.API_PAGE_SIZE == 100
    _in_readme("5000 Tickets")
