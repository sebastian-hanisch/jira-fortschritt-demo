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
    assert (len(DEFAULT), sum(i.is_epic for i in DEFAULT), sum(i.is_subtask for i in DEFAULT)) == (78, 6, 28)
    a = ev.analyse(DEFAULT, ev.Settings())
    assert (a.n_atoms, a.weight, a.n_unestimated) == (44, 177.0, 7)
    for text in ("78 Tickets", "6 Epics", "28 Sub-Tasks", "44 Stories, Tasks und Bugs", "177 Story Points", "7 davon ungeschätzt"):
        _in_readme(text)


def test_default_progress_under_each_preset():
    got = {name: ev.analyse(DEFAULT, ev.Settings(**p)) for name, p in C.PRESETS.items()}
    standard, strict, workflow = (got[n] for n in C.PRESETS)
    assert _pct(standard.progress) == "54,0 %" and _pct(strict.progress) == "43,5 %" and _pct(workflow.progress) == "62,0 %"
    assert _pct(standard.progress_count) == "52,3 %" and _pct(standard.progress_done) == "43,5 %"
    for text in ("54,0 %", "43,5 %", "62,0 %", "52,3 %"):
        _in_readme(text)


def test_default_sensitivity_range():
    rows = ev.sensitivity(DEFAULT, ev.Settings())
    values = [r["progress"] for r in rows]
    assert _pct(min(values)) == "43,5 %" and _pct(max(values)) == "68,0 %"
    assert ev.de(100 * (max(values) - min(values))) == "24,5"
    _in_readme("24,5 Prozentpunkte")


def test_linear_minus_only_done_over_the_fixed_projects():
    gaps = []
    for seed in C.SWEEP_SEEDS:
        s = make_sample(C.DEFAULT_N_EPICS, seed)
        gaps.append(100 * (ev.analyse(s, ev.Settings()).progress - ev.analyse(s, ev.Settings(scheme=C.SCHEME_DONE)).progress))
    assert len(gaps) == 10
    assert (ev.de(statistics.median(gaps)), ev.de(min(gaps)), ev.de(max(gaps))) == ("7,2", "1,3", "11,5")
    for text in ("10 feste Beispielprojekte", "Median 7,2 Prozentpunkte", "1,3 bis 11,5"):
        _in_readme(text)


def test_sensitivity_spread_over_the_fixed_projects():
    spreads = []
    for seed in C.SWEEP_SEEDS:
        s = make_sample(C.DEFAULT_N_EPICS, seed)
        v = [r["progress"] for r in ev.sensitivity(s, ev.Settings())]
        spreads.append(100 * (max(v) - min(v)))
    assert (ev.de(statistics.median(spreads)), ev.de(min(spreads)), ev.de(max(spreads))) == ("17,0", "8,0", "19,3")
    for text in ("Median 17,0 Prozentpunkte", "8,0 bis 19,3"):
        _in_readme(text)


def test_blend_lifts_the_workflow_scheme_on_the_default_project():
    plain = ev.analyse(DEFAULT, ev.Settings(scheme=C.SCHEME_WORKFLOW)).progress
    blended = ev.analyse(DEFAULT, ev.Settings(scheme=C.SCHEME_WORKFLOW, blend=True)).progress
    assert _pct(plain) == "61,4 %" and _pct(blended) == "62,0 %"
    _in_readme("61,4 % auf 62,0 %")


def test_readme_numbers_with_a_percent_sign_are_all_covered_by_a_claim():
    """Rückwärtsprobe: keine Prozentzahl im README, die kein Test oben kennt."""
    covered = {"54,0 %", "43,5 %", "62,0 %", "52,3 %", "61,4 %", "68,0 %", "50 %", "100 %", "0 %", "80 %", "90 %", "40 %"}
    found = set(re.findall(r"\d+(?:,\d+)? %", README))
    assert found <= covered, sorted(found - covered)
