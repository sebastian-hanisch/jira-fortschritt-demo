"""Kern gegen Handrechnung an der Mini-Instanz (conftest.py): jede Einheit einzeln (DEMO-PLAYBOOK §1b)."""

import datetime as dt

import numpy as np
import pytest

import jira_algorithm as A
import jira_constants as C
from conftest import TODAY
from jira_scenario import Issue

LINEAR = {"To Do": 0.0, "In Progress": 0.5, "In Review": 0.5, "Done": 1.0}


def _atoms(mini):
    return A.select_atoms(mini, C.LEVEL_STORIES)


# ---------------------------------------------------------------- Status und Gutschriften

def test_scheme_credits_by_hand():
    assert [A.scheme_credit(C.SCHEME_DONE, s, c) for s, c in (("To Do", "new"), ("In Review", "indeterminate"), ("Done", "done"))] == [0.0, 0.0, 1.0]
    assert [A.scheme_credit(C.SCHEME_LINEAR, s, c) for s, c in (("To Do", "new"), ("In Review", "indeterminate"), ("Done", "done"))] == [0.0, 0.5, 1.0]
    wf = {s: A.scheme_credit(C.SCHEME_WORKFLOW, s, c) for s, c in (("To Do", "new"), ("In Progress", "indeterminate"), ("In Review", "indeterminate"),
                                                                    ("Testing", "indeterminate"), ("Warten auf Kunde", "indeterminate"), ("Done", "done"))}
    assert wf == {"To Do": 0.0, "In Progress": 0.4, "In Review": 0.8, "Testing": 0.9, "Warten auf Kunde": 0.5, "Done": 1.0}


def test_workflow_scheme_never_overrides_the_category_of_new_or_done():
    assert A.scheme_credit(C.SCHEME_WORKFLOW, "Review offen", "new") == 0.0       # „review“ im Namen, aber Kategorie To Do
    assert A.scheme_credit(C.SCHEME_WORKFLOW, "Test bestanden", "done") == 1.0


def test_status_credits_custom_uses_own_values_and_falls_back_to_linear():
    got = A.status_credits([("To Do", "new"), ("In Progress", "indeterminate"), ("Done", "done")], C.SCHEME_CUSTOM, (("In Progress", 0.25),))
    assert got == {"To Do": 0.0, "In Progress": 0.25, "Done": 1.0}


def test_apply_credit_edits_changes_the_named_rows_and_clamps():
    base = (("To Do", 0.0), ("In Progress", 0.5), ("Done", 1.0))
    assert A.apply_credit_edits(base, {1: {"Gewicht (%)": 35}}) == (("To Do", 0.0), ("In Progress", 0.35), ("Done", 1.0))
    assert A.apply_credit_edits(base, {0: {"Gewicht (%)": -20}, 2: {"Gewicht (%)": 250}})[0::2] == (("To Do", 0.0), ("Done", 1.0))
    assert A.apply_credit_edits(base, {1: {"Status": "x"}}) == base            # andere Spalten ändern nichts
    assert A.apply_credit_edits(base, {}) == base


# ---------------------------------------------------------------- Hierarchie

def test_epic_of_follows_the_parent_chain(mini):
    assert dict(zip((i.key for i in mini), A.epic_of(mini))) == {"E1": "E1", "E2": "E2", "S1": "E1", "S2": "E1", "S3": "E2", "S4": "E2", "B1": "", "T1": "E1", "T2": "E1"}


def test_epic_of_survives_cycles_and_missing_parents():
    loop = (Issue(key="A", parent="B"), Issue(key="B", parent="A"), Issue(key="C", parent="gibt-es-nicht"))
    assert A.epic_of(loop) == ["", "", ""]


def test_select_atoms_by_level(mini):
    assert [mini[i].key for i in _atoms(mini)] == ["S1", "S2", "S3", "S4", "B1"]
    assert [mini[i].key for i in A.select_atoms(mini, C.LEVEL_SUBTASKS)] == ["T1", "T2"]
    with pytest.raises(ValueError):
        A.select_atoms(mini, "Unbekannt")


# ---------------------------------------------------------------- Gewichte und Gutschriften

def test_weights_by_rule(mini):
    atoms = _atoms(mini)       # Story Points 3, 5, 2, ?, 1  -> Median der geschätzten (1, 2, 3, 5) = 2,5
    assert A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_MEDIAN).tolist() == [3, 5, 2, 2.5, 1]
    assert A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_ONE).tolist() == [3, 5, 2, 1, 1]
    assert A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_IGNORE).tolist() == [3, 5, 2, 0, 1]
    assert A.atom_weights(mini, atoms, C.WEIGHT_COUNT, C.UNEST_IGNORE).tolist() == [1, 1, 1, 1, 1]


def test_weights_without_any_estimate_use_one_for_the_median_rule(mini):
    atoms = A.select_atoms(mini, C.LEVEL_SUBTASKS)                  # beide Sub-Tasks ungeschätzt
    assert A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_MEDIAN).tolist() == [1, 1]


def test_atom_credits_plain_and_blended(mini):
    atoms = _atoms(mini)
    wf = A.status_credits([("To Do", "new"), ("In Progress", "indeterminate"), ("In Review", "indeterminate"), ("Done", "done")], C.SCHEME_WORKFLOW)
    plain = A.atom_credits(mini, atoms, wf, blend=False)
    assert plain.tolist() == [1.0, 0.4, 0.0, 0.8, 1.0]
    # S2: eigener Status 0,4, Sub-Tasks T1 (1) und T2 (0) gleich gewichtet = 0,5 -> Maximum 0,5
    assert A.atom_credits(mini, atoms, wf, blend=True).tolist() == [1.0, 0.5, 0.0, 0.8, 1.0]


def test_blended_credit_weights_by_story_points_only_if_all_subtasks_have_them():
    c = np.array([1.0, 0.0])
    assert A.blended_credit(c, [3.0, 1.0]) == pytest.approx(0.75)
    assert A.blended_credit(c, [3.0, None]) == pytest.approx(0.5)       # eine ohne Punkte: gleich gewichtet
    assert A.blended_credit(c, [3.0, 0.0]) == pytest.approx(0.5)        # 0 Punkte zählt als nicht geschätzt
    assert A.blended_credit(np.zeros(0), []) == 0.0


def test_story_status_is_a_lower_bound_for_the_blend(mini):
    atoms = _atoms(mini)
    done_all = {"To Do": 0.0, "In Progress": 0.9, "In Review": 0.5, "Done": 1.0}
    assert A.atom_credits(mini, atoms, done_all, blend=True)[1] == pytest.approx(0.9)      # S2: Status 0,9 > Sub-Task-Mittel 0,5


# ---------------------------------------------------------------- Ebenen

def _stats(mini, dim, level=C.LEVEL_STORIES, mode=C.WEIGHT_POINTS, rule=C.UNEST_MEDIAN):
    atoms = A.select_atoms(mini, level)
    w = A.atom_weights(mini, atoms, mode, rule)
    c = A.atom_credits(mini, atoms, LINEAR, blend=False)
    done = np.array([mini[i].category == "done" for i in atoms])
    unest = np.array([mini[i].points is None for i in atoms])
    assign = A.assign_groups(mini, atoms, dim)
    return A.aggregate(assign, w, c, done, unest)


def test_group_by_epic(mini):
    s = _stats(mini, C.DIM_EPIC)
    assert s.labels == ("E1: Epic A", "E2: Epic B", "(ohne Epic)")
    assert s.weight.tolist() == [8, 4.5, 1] and s.credited.tolist() == [5.5, 1.25, 1]
    assert s.progress.tolist() == pytest.approx([0.6875, 1.25 / 4.5, 1.0])


def test_group_by_sprint_uses_the_last_sprint(mini):
    s = _stats(mini, C.DIM_SPRINT)
    assert s.labels == ("Sprint 1", "Sprint 2", "(ohne Sprint)")
    assert s.weight.tolist() == [3, 8.5, 2] and s.credited.tolist() == [3, 4.75, 0]


def test_subtasks_inherit_the_sprint_of_their_story(mini):
    s = _stats(mini, C.DIM_SPRINT, level=C.LEVEL_SUBTASKS)
    assert s.labels == ("Sprint 2",) and s.weight.tolist() == [2.0] and s.credited.tolist() == [1.0]


def test_multi_valued_dimension_splits_the_weight_evenly(mini):
    s = _stats(mini, C.DIM_COMPONENT)
    assert s.labels == ("Backend", "Frontend", "(ohne Komponente)")
    assert s.weight.tolist() == [7.5, 4.0, 2.0] and s.credited.tolist() == [5.0, 2.75, 0.0]
    assert s.weight.sum() == pytest.approx(13.5)                 # nichts geht verloren, nichts wird doppelt gezählt


def test_group_by_all_type_and_status(mini):
    assert _stats(mini, C.DIM_ALL).weight.tolist() == [13.5]
    t = _stats(mini, C.DIM_TYPE)
    assert t.labels == ("Bug", "Story") and t.weight.tolist() == [1, 12.5]
    st_ = _stats(mini, C.DIM_STATUS)
    assert st_.labels == ("Done", "In Progress", "In Review", "To Do") and st_.weight.tolist() == [4, 5, 2.5, 2]


def test_unknown_dimension_is_an_error(mini):
    with pytest.raises(ValueError):
        A.assign_groups(mini, _atoms(mini), "Unbekannt")


def test_natural_key_sorts_numbers_as_numbers_and_empty_groups_last():
    labels = ["Sprint 10", "(ohne Sprint)", "Sprint 2", "Sprint 1"]
    assert sorted(labels, key=A.natural_key) == ["Sprint 1", "Sprint 2", "Sprint 10", "(ohne Sprint)"]


def test_cross_assignment_epic_by_sprint(mini):
    atoms = _atoms(mini)
    cross = A.cross_assignment(A.assign_groups(mini, atoms, C.DIM_EPIC), A.assign_groups(mini, atoms, C.DIM_SPRINT))
    w = A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_MEDIAN)
    c = A.atom_credits(mini, atoms, LINEAR, False)
    s = A.aggregate(cross, w, c, np.zeros(5, dtype=bool), np.zeros(5, dtype=bool))
    assert s.labels == ("E1: Epic A | Sprint 1", "E1: Epic A | Sprint 2", "E2: Epic B | Sprint 2", "E2: Epic B | (ohne Sprint)", "(ohne Epic) | Sprint 2")
    assert s.weight.tolist() == [3, 5, 2.5, 2, 1] and s.credited.tolist() == [3, 2.5, 1.25, 0, 1]


def test_cross_of_two_multi_valued_levels_multiplies_the_shares():
    issues = (Issue(key="A", labels=("x", "y"), components=("p", "q"), points=4.0),)
    atoms = [0]
    cross = A.cross_assignment(A.assign_groups(issues, atoms, C.DIM_LABEL), A.assign_groups(issues, atoms, C.DIM_COMPONENT))
    assert cross.share.tolist() == [0.25] * 4 and cross.labels == ("x | p", "x | q", "y | p", "y | q")


# ---------------------------------------------------------------- Kennzahlen

def test_overall_by_hand(mini):
    atoms = _atoms(mini)
    w = A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_MEDIAN)
    c = A.atom_credits(mini, atoms, LINEAR, False)
    done = np.array([mini[i].category == "done" for i in atoms])
    p_w, p_d, p_n = A.overall(w, c, done)
    assert p_w == pytest.approx(7.75 / 13.5) and p_d == pytest.approx(4 / 13.5) and p_n == pytest.approx(0.4)


def test_overall_without_weight_or_atoms_is_nan():
    p_w, p_d, p_n = A.overall(np.zeros(2), np.zeros(2), np.zeros(2, dtype=bool))
    assert np.isnan(p_w) and np.isnan(p_d) and p_n == 0.0
    assert all(np.isnan(v) for v in A.overall(np.zeros(0), np.zeros(0), np.zeros(0, dtype=bool)))


def test_group_without_weight_has_nan_progress_but_a_count(mini):
    s = _stats(mini, C.DIM_STATUS, rule=C.UNEST_IGNORE)       # S4 (In Review) hat Gewicht 0
    i = s.labels.index("In Review")
    assert s.weight[i] == 0 and np.isnan(s.progress[i]) and s.count[i] == 1 and s.unestimated[i] == 1


def test_progress_variants_per_group(mini):
    s = _stats(mini, C.DIM_EPIC)
    assert s.done_weight.tolist() == [3, 0, 1] and s.progress_done.tolist() == pytest.approx([3 / 8, 0.0, 1.0])
    assert s.done_count.tolist() == [1, 0, 1] and s.progress_count.tolist() == [0.5, 0.0, 1.0]


# ---------------------------------------------------------------- Verlauf und Hierarchie

def test_burn_up_by_hand(mini):
    atoms = _atoms(mini)
    w = A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_MEDIAN)
    done = np.array([mini[i].category == "done" for i in atoms])
    grid, scope, finished, missing = A.burn_up(mini, atoms, w, done, TODAY)
    assert grid == [dt.date(2026, 1, 1), dt.date(2026, 1, 8), dt.date(2026, 1, 15)]
    assert scope.tolist() == [3, 11, 13.5] and finished.tolist() == [0, 0, 4] and missing == 0


def test_burn_up_counts_done_tickets_without_resolution_date():
    issues = (Issue(key="A", status="Done", category="done", points=2.0, created=dt.date(2026, 1, 1)),
              Issue(key="B", status="Done", category="done", points=3.0, created=dt.date(2026, 1, 1), resolved=dt.date(2026, 1, 3)))
    grid, scope, finished, missing = A.burn_up(issues, [0, 1], np.array([2.0, 3.0]), np.array([True, True]), dt.date(2026, 1, 3))
    assert missing == 1 and finished.tolist()[-1] == 3 and scope.tolist()[-1] == 5


def test_burn_up_without_any_date_is_empty():
    grid, scope, finished, missing = A.burn_up((Issue(key="A"),), [0], np.array([1.0]), np.array([False]), TODAY)
    assert grid == [] and len(scope) == 0 and len(finished) == 0 and missing == 0


def test_hierarchy_sums_children_and_omits_weightless_atoms(mini):
    atoms = _atoms(mini)
    w = A.atom_weights(mini, atoms, C.WEIGHT_POINTS, C.UNEST_IGNORE)           # S4 ohne Gewicht
    c = A.atom_credits(mini, atoms, LINEAR, False)
    h = A.hierarchy(mini, atoms, w, c)
    by_id = {i: (v, p) for i, v, p in zip(h.ids, h.values, h.progress)}
    assert "atom:S4" not in by_id
    assert by_id["Projekt"][0] == 11 and by_id["epic:E1"][0] == 8 and by_id["epic:E2"][0] == 2 and by_id["epic:(ohne Epic)"][0] == 1
    assert by_id["epic:E1"][1] == pytest.approx(5.5 / 8) and by_id["Projekt"][1] == pytest.approx(6.5 / 11)
    for parent in ("Projekt", "epic:E1", "epic:E2", "epic:(ohne Epic)"):
        assert by_id[parent][0] == pytest.approx(sum(v for i, v, p_ in zip(h.ids, h.values, h.parents) if p_ == parent))


def test_ratio_is_nan_exactly_where_the_denominator_is_not_positive():
    out = A.ratio(np.array([1.0, 2.0, 3.0, 0.0]), np.array([2.0, 0.0, 1.0, 0.0]))
    assert out[0] == 0.5 and np.isnan(out[1]) and out[2] == 3.0 and np.isnan(out[3])
    assert len(A.ratio(np.zeros(0), np.zeros(0))) == 0


def test_epic_search_depth_limit_is_ten_levels():
    def chain(depth):
        return tuple([Issue(key="E", type="Epic")] + [Issue(key=f"L{n}", parent="E" if n == 1 else f"L{n - 1}") for n in range(1, depth + 1)])
    assert A.epic_of(chain(9))[-1] == "E"           # Epic neun Ebenen über dem Ticket
    assert A.epic_of(chain(10))[-1] == ""           # zehn Ebenen: außerhalb der Suchtiefe (Schutz gegen Zyklen)


def test_fractional_story_points_below_one_still_give_a_progress():
    """Jira erlaubt 0,5 Story Points: ein Gesamtgewicht unter 1 darf nicht wie „kein Gewicht“ behandelt werden."""
    issues = (Issue(key="A", type="Story", status="Done", category="done", points=0.5), Issue(key="B", type="Story", status="To Do", category="new", points=0.25))
    atoms = [0, 1]
    w = A.atom_weights(issues, atoms, C.WEIGHT_POINTS, C.UNEST_IGNORE)
    c = A.atom_credits(issues, atoms, {"Done": 1.0, "To Do": 0.0}, False)
    p_w, p_d, p_n = A.overall(w, c, np.array([True, False]))
    assert p_w == pytest.approx(2 / 3) and p_d == pytest.approx(2 / 3) and p_n == 0.5
    h = A.hierarchy(issues, atoms, w, c)
    assert h.progress[0] == pytest.approx(2 / 3) and h.values[0] == pytest.approx(0.75)


def test_burn_up_grid_ends_at_the_latest_date_even_if_the_reference_day_is_earlier():
    issues = (Issue(key="A", status="Done", category="done", points=1.0, created=dt.date(2026, 1, 1), resolved=dt.date(2026, 1, 20)),)
    grid, scope, finished, _ = A.burn_up(issues, [0], np.array([1.0]), np.array([True]), dt.date(2026, 1, 5))
    assert grid[-1] == dt.date(2026, 1, 20) and finished[-1] == 1
