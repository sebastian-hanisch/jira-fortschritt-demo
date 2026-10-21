"""Zeitraum (Sprint von … bis …) als Einschränkung der Datengrundlage und Hierarchiestufe als Ebene: Zahlen von Hand, Randfälle, Wechselwirkung mit dem Teilprojekt."""

import math

import pytest

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev
import jira_tables as T
from jira_scenario import Issue

# Sprints in natürlicher Reihenfolge: Sprint 2 < Sprint 3 < Sprint 10
PROJECT = (
    Issue(key="S1", status="Done", category="done", points=2.0, sprints=("Sprint 2",)),
    Issue(key="S2", status="In Progress", category="indeterminate", points=10.0, sprints=("Sprint 10",)),
    Issue(key="S3", status="To Do", category="new", points=5.0, sprints=("Sprint 2", "Sprint 3")),             # übernommen: es zählt der letzte, Sprint 3
    Issue(key="S4", status="Done", category="done", points=4.0),                                                 # ohne Sprint
    Issue(key="S5", status="To Do", category="new", points=None, sprints=("Sprint 3",)),                         # ungeschätzt
    Issue(key="U1", type="Sub-task", is_subtask=True, status="Done", category="done", points=1.0, parent="S2"),     # erbt Sprint 10
    Issue(key="U2", type="Sub-task", is_subtask=True, status="To Do", category="new", points=1.0, parent="S4"),     # erbt nichts: ohne Sprint
)


def _keys(found):
    return [PROJECT[i].key for i in found]


def _stories():
    return A.select_atoms(PROJECT, C.LEVEL_STORIES)


# ---------------------------------------------------------------- Sprint-Reihenfolge und Filter

def test_sprint_order_is_natural_and_uses_the_inherited_sprint():
    assert A.sprint_order(PROJECT) == ["Sprint 2", "Sprint 3", "Sprint 10"]
    by_key = {t.key: t for t in PROJECT}
    assert [A.ticket_sprint(by_key, t) for t in PROJECT] == ["Sprint 2", "Sprint 10", "Sprint 3", "", "Sprint 3", "Sprint 10", ""]


@pytest.mark.parametrize("first,last,none,expected", [
    ("", "", False, ["S1", "S2", "S3", "S4", "S5"]),                  # keine Einschränkung: auch das Ticket ohne Sprint
    ("", "", True, ["S1", "S2", "S3", "S4", "S5"]),
    ("Sprint 3", "", False, ["S2", "S3", "S5"]),
    ("", "Sprint 3", False, ["S1", "S3", "S5"]),
    ("Sprint 2", "Sprint 3", False, ["S1", "S3", "S5"]),
    ("Sprint 3", "Sprint 3", False, ["S3", "S5"]),
    ("Sprint 10", "Sprint 10", False, ["S2"]),
    ("Sprint 3", "", True, ["S2", "S3", "S4", "S5"]),                 # mit Tickets ohne Sprint
    ("Sprint 10", "Sprint 2", False, []),                             # Anfang hinter Ende
])
def test_filter_sprints_by_hand(first, last, none, expected):
    assert _keys(A.filter_sprints(PROJECT, _stories(), first, last, none)) == expected


def test_filter_on_the_sub_task_level_and_unknown_sprints():
    subs = A.select_atoms(PROJECT, C.LEVEL_SUBTASKS)
    assert _keys(A.filter_sprints(PROJECT, subs, "Sprint 10", "")) == ["U1"]
    assert _keys(A.filter_sprints(PROJECT, subs, "Sprint 10", "", True)) == ["U1", "U2"]
    with pytest.raises(ValueError):
        A.filter_sprints(PROJECT, subs, "Sprint 99", "")


# ---------------------------------------------------------------- Auswertung im Zeitraum

def test_progress_in_the_period_by_hand_including_the_median_of_the_remaining_tickets():
    a = ev.analyse(PROJECT, ev.Settings(sprint_from="Sprint 2", sprint_to="Sprint 3"))        # S1 (2, Done), S3 (5, offen), S5 (ungeschätzt)
    assert [PROJECT[i].key for i in a.atoms] == ["S1", "S3", "S5"] and a.n_outside == 2 and a.n_unestimated == 1
    assert a.weight == 2 + 5 + 3.5 and a.progress == pytest.approx(2 / 10.5)                   # Median der geschätzten Tickets im Zeitraum: 3,5 (nicht 4,5 des ganzen Projekts)
    full = ev.analyse(PROJECT, ev.Settings())
    assert full.n_outside == 0 and full.weight == 2 + 10 + 5 + 4 + 4.5 and ev.check_consistency(a) == [] and ev.check_consistency(full) == []


def test_period_with_nothing_inside_gives_no_progress_and_no_crash():
    a = ev.analyse(PROJECT, ev.Settings(sprint_from="Sprint 10", sprint_to="Sprint 2"))
    assert a.n_atoms == 0 and a.n_outside == 5 and math.isnan(a.progress) and ev.check_consistency(a) == []


def test_period_applies_to_sensitivity_burn_up_and_tables():
    s = ev.Settings(sprint_from="Sprint 3", sprint_to="")
    for row in ev.sensitivity(PROJECT, s):
        again = ev.analyse(PROJECT, ev.Settings(sprint_from="Sprint 3", scheme=row["scheme"], weight_mode=row["mode"]))
        assert row["progress"] == pytest.approx(again.progress) or (math.isnan(row["progress"]) and math.isnan(again.progress))
    a = ev.analyse(PROJECT, s)
    assert sum(r["Gewicht"] for r in T.contribution(a)[:-1]) == pytest.approx(a.weight)


def test_period_combines_with_root_and_sub_task_level():
    scoped = ev.analyse(PROJECT, ev.Settings(root="S2", sprint_from="Sprint 10", sprint_to="Sprint 10", count_level=C.LEVEL_SUBTASKS))
    assert [PROJECT[i].key for i in scoped.atoms] == ["U1"] and scoped.progress == 1.0


def test_graph_marks_tickets_outside_the_period_as_ignored():
    g = ev.analyse(PROJECT, ev.Settings(sprint_from="Sprint 3", sprint_to="Sprint 3")).tree
    by = {k: (ign, w) for k, ign, w in zip(g.keys, g.ignored.tolist(), g.weight.tolist())}
    assert by["S1"][0] and by["S2"][0] and by["S4"][0] and not by["S3"][0] and not by["S5"][0] and by["S3"][1] == 5.0 and by["S1"][1] == 0.0


def test_summary_names_the_period():
    a = ev.analyse(PROJECT, ev.Settings(sprint_from="Sprint 2", sprint_to="Sprint 3", include_no_sprint=True))
    text = T.summary_markdown(PROJECT, a, "SP", C.SAMPLE_TODAY)
    assert "Zeitraum: Sprint 2 bis Sprint 3, einschließlich Tickets ohne Sprint (1 Tickets außerhalb)" in text
    assert "Zeitraum" not in T.summary_markdown(PROJECT, ev.analyse(PROJECT, ev.Settings()), "SP", C.SAMPLE_TODAY)
    assert "Zeitraum: Anfang bis Sprint 3" in T.summary_markdown(PROJECT, ev.analyse(PROJECT, ev.Settings(sprint_to="Sprint 3")), "SP", C.SAMPLE_TODAY)


# ---------------------------------------------------------------- Hierarchiestufe

# Initiative I -> Epic E1 (S1 2, S2 3 mit Sub-Task S2a), Epic E2 (S3 5); Story X (4) ohne Eltern
TREE = (
    Issue(key="I", type="Initiative", summary="Alles"),
    Issue(key="E1", type="Epic", summary="Eins", parent="I"),
    Issue(key="S1", status="Done", category="done", points=2.0, parent="E1"),
    Issue(key="S2", status="In Progress", category="indeterminate", points=3.0, parent="E1"),
    Issue(key="S2a", type="Sub-task", is_subtask=True, status="Done", category="done", points=1.0, parent="S2"),
    Issue(key="E2", type="Epic", summary="Zwei", parent="I"),
    Issue(key="S3", status="To Do", category="new", points=5.0, parent="E2"),
    Issue(key="X", status="Done", category="done", points=4.0),
)


def _groups(level, **kw):
    a = ev.analyse(TREE, ev.Settings(dimension=C.DIM_LEVEL, level=level, **kw))
    return dict(zip(a.stats.labels, zip(a.stats.weight.tolist(), a.stats.progress.tolist()))), a


def test_chains_and_levels_by_hand():
    chains = A.hierarchy_chains(TREE)
    assert [[TREE[k].key for k in c] for c in chains] == [["I"], ["I", "E1"], ["I", "E1", "S1"], ["I", "E1", "S2"], ["I", "E1", "S2", "S2a"], ["I", "E2"], ["I", "E2", "S3"], ["X"]]
    assert A.max_level(TREE) == 4 and A.max_level(()) == 1


def test_level_one_aggregates_to_the_top_and_keeps_the_weighted_progress():
    groups, a = _groups(1)
    assert groups == {"I: Alles": (10.0, pytest.approx(3.5 / 10)), "X": (4.0, 1.0)} and ev.check_consistency(a) == []      # I: 2 + 1,5 + 0 von 10


def test_level_two_is_the_epic_level_and_names_what_has_no_such_level():
    groups, _ = _groups(2)
    assert groups == {"E1: Eins": (5.0, pytest.approx(3.5 / 5)), "E2: Zwei": (5.0, 0.0), "(keine Stufe 2)": (4.0, 1.0)}


def test_a_ticket_on_exactly_the_chosen_level_is_its_own_group_and_deeper_levels_work():
    groups, _ = _groups(3)
    assert set(groups) == {"S1", "S2", "S3", "(keine Stufe 3)"} and groups["S2"] == (3.0, 0.5) and groups["S1"] == (2.0, 1.0)
    sub_groups, _ = _groups(4, count_level=C.LEVEL_SUBTASKS)
    assert sub_groups == {"S2a": (1.0, 1.0)}


def test_the_level_works_in_the_cross_table_with_the_same_total():
    a = ev.analyse(TREE, ev.Settings(dimension=C.DIM_LEVEL, dimension2=C.DIM_STATUS, level=2))
    assert a.cross.weight.sum() == pytest.approx(a.weight) and ev.check_consistency(a) == []


def test_level_is_combined_with_the_period_and_the_root():
    items = TREE[:2] + (Issue(key="S1", status="Done", category="done", points=2.0, parent="E1", sprints=("Sprint 1",)),
                        Issue(key="S2", status="To Do", category="new", points=3.0, parent="E1", sprints=("Sprint 2",)))
    a = ev.analyse(items, ev.Settings(dimension=C.DIM_LEVEL, level=3, sprint_from="Sprint 2", sprint_to="Sprint 2", root="E1"))
    assert dict(zip(a.stats.labels, a.stats.weight.tolist())) == {"S2": 3.0}           # Stufe 3 = die Stories unter den Epics


def test_cycles_do_not_break_the_level_chains():
    loop = (Issue(key="A", parent="B", points=1.0), Issue(key="B", parent="A", points=2.0))
    chains = A.hierarchy_chains(loop)
    assert all(1 <= len(c) <= 2 for c in chains) and len(A.level_labels(loop, [0, 1], 1)) == 2


def test_a_root_listed_after_the_subtree_of_the_last_ticket_still_starts_its_own_chain():
    items = (Issue(key="X"), Issue(key="Z"), Issue(key="C", parent="X"))          # Z ist Wurzel; C steht zuletzt in der Liste, kommt im Baum aber vor Z
    assert [[items[k].key for k in c] for c in A.hierarchy_chains(items)] == [["X"], ["Z"], ["X", "C"]]
