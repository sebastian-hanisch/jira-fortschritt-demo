"""Teilprojekt als eigenständiger Datensatz: Alle Auswahlen (Status, Zeitraum, Ebenen, Stufen) sehen nur das Ticket und alles darunter; nichts zeigt nach außen."""

import numpy as np
import pytest

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev
from jira_scenario import Issue, make_sample

# Initiative I -> Epic E1 (S1 Done Sprint 1, S2 In Progress Sprint 2 mit Sub-Task U1), Epic E2 (S3 To Do Sprint 5); Story X (Review, Sprint 9) ohne Eltern
TREE = (
    Issue(key="I", type="Initiative", summary="Alles"),
    Issue(key="E1", type="Epic", summary="Eins", parent="I"),
    Issue(key="S1", status="Done", category="done", points=2.0, parent="E1", sprints=("Sprint 1",)),
    Issue(key="S2", status="In Progress", category="indeterminate", points=3.0, parent="E1", sprints=("Sprint 2",)),
    Issue(key="U1", type="Sub-task", is_subtask=True, status="Testing", category="indeterminate", points=1.0, parent="S2"),
    Issue(key="E2", type="Epic", summary="Zwei", parent="I"),
    Issue(key="S3", status="To Do", category="new", points=5.0, parent="E2", sprints=("Sprint 5",)),
    Issue(key="X", status="In Review", category="indeterminate", points=4.0, sprints=("Sprint 9",)),
)


def test_scope_issues_by_hand():
    scoped = A.scope_issues(TREE, "E1")
    assert [t.key for t in scoped] == ["E1", "S1", "S2", "U1"] and scoped[0].parent == "" and TREE[1].parent == "I"             # die Wurzel verliert ihren Parent, das Original bleibt
    assert A.scope_issues(TREE, "") == TREE and [t.key for t in A.scope_issues(TREE, "S2")] == ["S2", "U1"]
    with pytest.raises(ValueError):
        A.scope_issues(TREE, "Z")


def test_the_choices_of_the_analysis_only_see_the_scope():
    scoped = A.scope_issues(TREE, "E1")
    assert A.sprint_order(TREE) == ["Sprint 1", "Sprint 2", "Sprint 5", "Sprint 9"] and A.sprint_order(scoped) == ["Sprint 1", "Sprint 2"]
    assert {s for s, _ in ev.status_list(TREE)} == {"To Do", "Done", "In Progress", "Testing", "In Review"}
    assert {s for s, _ in ev.status_list(scoped)} == {"To Do", "Done", "In Progress", "Testing"}                    # „In Review“ (nur X) fehlt
    assert A.max_level(TREE) == 4 and A.max_level(scoped) == 3                                                    # I-E1-S2-U1 gegen E1-S2-U1
    assert [k for k, _ in A.root_choices(TREE)] == ["I", "E1", "S2", "E2"] and [k for k, _ in A.root_choices(scoped)] == ["E1", "S2"]


def test_level_one_is_the_root_and_epics_above_the_root_do_not_exist():
    scoped = A.scope_issues(TREE, "S2")
    a = ev.analyse(scoped, ev.Settings(dimension=C.DIM_LEVEL, level=1, root="S2"))
    assert dict(zip(a.stats.labels, a.stats.weight.tolist())) == {"S2": 3.0}
    epic = ev.analyse(scoped, ev.Settings(dimension=C.DIM_EPIC, root="S2"))
    assert list(epic.stats.labels) == ["(ohne Epic)"]                                          # der Epic über der Wurzel liegt außerhalb des Datensatzes
    full = ev.analyse(TREE, ev.Settings(dimension=C.DIM_EPIC, root="S2"))
    assert list(full.stats.labels) == ["E1: Eins"]


def test_an_inherited_sprint_from_outside_the_scope_is_not_inherited():
    items = (Issue(key="P", sprints=("Sprint 9",), points=1.0), Issue(key="S", parent="P", points=2.0), Issue(key="U", type="Sub-task", is_subtask=True, parent="S", points=1.0))
    by_key = {t.key: t for t in items}
    assert A.ticket_sprint(by_key, items[1]) == "Sprint 9"
    scoped = A.scope_issues(items, "S")
    assert A.ticket_sprint({t.key: t for t in scoped}, scoped[0]) == "" and A.sprint_order(scoped) == []


@pytest.mark.parametrize("seed", [1, 8, 3])
def test_scoped_analysis_equals_the_analysis_of_the_same_tickets_as_a_standalone_dataset(seed):
    sample = make_sample(5, seed)
    for key, _ in A.root_choices(sample):
        scoped = A.scope_issues(sample, key)
        for kw in ({}, {"count_level": C.LEVEL_SUBTASKS}, {"blend": True, "unest_rule": C.UNEST_ONE}, {"weight_mode": C.WEIGHT_COUNT, "dimension": C.DIM_SPRINT}):
            with_root = ev.analyse(scoped, ev.Settings(root=key, **kw))
            alone = ev.analyse(scoped, ev.Settings(**kw))
            assert with_root.atoms == alone.atoms and with_root.progress == alone.progress or (np.isnan(with_root.progress) and np.isnan(alone.progress))
            assert list(with_root.stats.labels) == list(alone.stats.labels) and np.allclose(with_root.stats.weight, alone.stats.weight) and with_root.n_unestimated == alone.n_unestimated
            assert ev.check_consistency(with_root) == []


def test_the_median_for_unestimated_tickets_comes_from_the_scope_only():
    items = (Issue(key="E", type="Epic"), Issue(key="A", parent="E", points=2.0), Issue(key="B", parent="E", points=None), Issue(key="X", points=100.0))
    scoped = A.scope_issues(items, "E")
    assert ev.analyse(scoped, ev.Settings(root="E")).weight == 2 + 2
    assert ev.analyse(items, ev.Settings()).weight == 2 + 51 + 100                                   # Median 51 aus 2 und 100 ohne Eingrenzung
