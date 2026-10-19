"""Randfälle, an denen Kernroutinen erfahrungsgemäß brechen (DEMO-PLAYBOOK §12): leere Menge, ein und zwei Tickets, alles gleich, alles ungeschätzt, Gewicht 0."""

import datetime as dt

import numpy as np
import pytest

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev
from jira_scenario import Issue


def _story(key, status="To Do", category="new", points=None, **kw):
    return Issue(key=key, type="Story", status=status, category=category, points=points, **kw)


@pytest.mark.parametrize("dim", C.DIMENSIONS)
def test_empty_project_does_not_raise_in_any_dimension(dim):
    a = ev.analyse((), ev.Settings(dimension=dim, dimension2=C.DIM_TYPE if dim != C.DIM_TYPE else C.DIM_NONE))
    assert a.n_atoms == 0 and np.isnan(a.progress) and a.stats.labels == () and a.burn[0] == []
    assert ev.check_consistency(a) == []


def test_one_ticket():
    a = ev.analyse((_story("A", "Done", "done", 5.0),), ev.Settings())
    assert a.progress == 1.0 and a.progress_count == 1.0 and a.stats.labels == ("(ohne Epic)",)


def test_exactly_two_tickets_median_and_groups():
    issues = (_story("A", "Done", "done", 3.0), _story("B", points=None))
    a = ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_MEDIAN))
    assert a.progress == pytest.approx(3.0 / 6.0)                           # Median der einen geschätzten Zahl: B wiegt 3
    assert ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_IGNORE)).progress == 1.0
    assert ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_ONE)).progress == pytest.approx(3.0 / 4.0)


def test_all_unestimated_with_ignore_rule_has_no_weight_but_counts():
    issues = (_story("A", "Done", "done"), _story("B"))
    a = ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_IGNORE))
    assert a.weight == 0 and np.isnan(a.progress) and a.progress_count == 0.5 and a.n_unestimated == 2
    assert a.hierarchy.values == (0.0,) and ev.check_consistency(a) == []


def test_zero_story_points_count_as_estimated_with_weight_zero():
    issues = (_story("A", "Done", "done", 0.0), _story("B", points=4.0))
    a = ev.analyse(issues, ev.Settings())
    assert a.weight == 4.0 and a.progress == 0.0 and a.n_unestimated == 0


def test_all_tickets_equal_and_all_done_or_all_open():
    done = tuple(_story(f"D{i}", "Done", "done", 2.0) for i in range(3))
    open_ = tuple(_story(f"O{i}", points=2.0) for i in range(3))
    assert ev.analyse(done, ev.Settings()).progress == 1.0 and ev.analyse(open_, ev.Settings()).progress == 0.0
    assert ev.analyse(done + open_, ev.Settings()).progress == 0.5


def test_ticket_without_epic_parent_in_a_deep_chain_still_finds_its_epic():
    issues = (Issue(key="E", type="Epic", summary="Z"), _story("S", parent="E"), Issue(key="T", type="Sub-task", is_subtask=True, parent="S", status="Done", category="done"))
    assert A.epic_of(issues) == ["E", "E", "E"]


def test_blend_when_parent_has_only_subtasks_without_points_and_zero_credit():
    issues = (_story("S", points=2.0), Issue(key="T", type="Sub-task", is_subtask=True, parent="S", status="To Do", category="new"))
    a = ev.analyse(issues, ev.Settings(blend=True))
    assert a.progress == 0.0


def test_unknown_status_category_defaults_to_in_progress_credit():
    issues = (_story("A", "Seltsam", "indeterminate", 2.0),)
    assert ev.analyse(issues, ev.Settings(scheme=C.SCHEME_LINEAR)).progress == 0.5


def test_dates_only_on_some_tickets_do_not_break_the_burn_up():
    issues = (_story("A", "Done", "done", 1.0, resolved=dt.date(2026, 1, 5)), _story("B", points=1.0, created=dt.date(2026, 1, 1)))
    grid, scope, finished, missing = ev.analyse(issues, ev.Settings(), dt.date(2026, 1, 10)).burn
    assert grid[0] == dt.date(2026, 1, 1) and scope[-1] == 2 and finished[-1] == 1 and missing == 0


def test_bounds_of_the_status_edit_clamp_inclusively():
    base = (("A", 0.5),)
    assert A.apply_credit_edits(base, {0: {"Gewicht (%)": 0}}) == (("A", 0.0),) and A.apply_credit_edits(base, {0: {"Gewicht (%)": 100}}) == (("A", 1.0),)
    assert A.apply_credit_edits(base, {0: {"Gewicht (%)": None}}) == base


def test_worst_case_at_the_import_limit_finishes_and_stays_consistent():
    """Obergrenze von MAX_IMPORT_ISSUES Tickets mit allen Ebenen, Kreuztabelle, Sub-Task-Mischung und Sensitivität (kein Zeitvergleich: das Pytest-Limit ist das Netz)."""
    import dataclasses

    from jira_scenario import make_sample
    big = []
    for k in range(60):
        for i in make_sample(C.N_EPICS_MAX, k):
            big.append(dataclasses.replace(i, key=f"{i.key}-{k}", parent=f"{i.parent}-{k}" if i.parent else ""))
    big = tuple(big[:C.MAX_IMPORT_ISSUES])
    assert len(big) == C.MAX_IMPORT_ISSUES
    for dim in C.DIMENSIONS:
        a = ev.analyse(big, ev.Settings(dimension=dim, dimension2=C.DIM_LABEL if dim != C.DIM_LABEL else C.DIM_COMPONENT, blend=True))
        assert ev.check_consistency(a) == [], dim
    assert len(ev.sensitivity(big, ev.Settings())) == 6


def test_consistency_checker_accepts_exactly_one_hundred_percent_and_huge_weights():
    all_done = ev.analyse((_story("A", "Done", "done", 5.0),), ev.Settings())
    assert all_done.progress == 1.0 and ev.check_consistency(all_done) == []
    thirds = (Issue(key="A", type="Story", status="Done", category="done", points=1e12, labels=("x", "y", "z")),)
    assert ev.check_consistency(ev.analyse(thirds, ev.Settings(dimension=C.DIM_LABEL, dimension2=C.DIM_COMPONENT))) == []


def test_consistency_tolerance_scales_with_the_total_weight():
    """Sieben Labels teilen 1e12 Story Points: die Summe der Siebtel weicht in den letzten Stellen ab (absolut weit über 1e-9), relativ aber um 1e-16."""
    seven = (Issue(key="A", type="Story", status="Done", category="done", points=1e12, labels=tuple("abcdefg")),)
    a = ev.analyse(seven, ev.Settings(dimension=C.DIM_LABEL))
    assert abs(float(a.stats.weight.sum()) - a.weight) > 1e-9           # die Aufgabe des Tests: der absolute Fehler ist groß
    assert ev.check_consistency(a) == []
