"""Beispielprojekt: deterministisch und in sich stimmig (Schlüssel, Eltern, Daten, Status, Kategorien)."""

import pytest

import jira_constants as C
from jira_scenario import SAMPLE_STATUS, make_sample


@pytest.mark.parametrize("n_epics", range(C.N_EPICS_MIN, C.N_EPICS_MAX + 1))
def test_sample_is_consistent(n_epics):
    issues = make_sample(n_epics, 7)
    keys = [i.key for i in issues]
    assert len(keys) == len(set(keys))
    by_key = {i.key: i for i in issues}
    assert sum(i.is_epic for i in issues) == n_epics
    for i in issues:
        assert SAMPLE_STATUS[i.status] == i.category
        if i.parent:
            assert i.parent in by_key
            assert by_key[i.parent].is_epic != i.is_subtask or i.is_epic is False      # Stories hängen an Epics, Sub-Tasks an Stories
        if i.is_subtask:
            assert i.points is None and by_key[i.parent].type != "Epic"
        assert i.created is None or i.created <= C.SAMPLE_TODAY
        if i.resolved:
            assert i.category == "done" and i.created <= i.resolved <= C.SAMPLE_TODAY
        else:
            assert i.category != "done"


def test_sample_is_deterministic_and_seed_dependent():
    assert make_sample(6, 42) == make_sample(6, 42)
    assert make_sample(6, 42) != make_sample(6, 43)


def test_sample_has_every_feature_the_app_shows():
    issues = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    assert any(i.points is None and not i.is_epic and not i.is_subtask for i in issues)       # ungeschätzte Tickets
    assert any(i.is_subtask for i in issues) and any(len(i.sprints) > 1 for i in issues)       # Sub-Tasks, übernommene Sprints
    assert any(len(i.components) > 1 or i.labels for i in issues) and {i.type for i in issues} >= {"Epic", "Story", "Bug", "Sub-task"}
    assert {i.category for i in issues} == {"new", "indeterminate", "done"}
