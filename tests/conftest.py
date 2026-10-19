"""Gemeinsame Fixtures: die Mini-Instanz, an der jede Einheit von Hand geprüft wird (DEMO-PLAYBOOK §1b).

Mini-Projekt (alle Zahlen von Hand gerechnet, siehe die Tests):

    E1 Epic A   |  S1 Story  3 SP  Done         Sprint 1               Komponenten Backend + Frontend
                |  S2 Story  5 SP  In Progress  Sprint 1, Sprint 2     Backend      Sub-Tasks T1 (Done), T2 (To Do), ohne SP
    E2 Epic B   |  S3 Story  2 SP  To Do        (kein Sprint)          (keine)
                |  S4 Story  ? SP  In Review    Sprint 2               Frontend
    ohne Epic   |  B1 Bug    1 SP  Done         Sprint 2               Backend
"""

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jira_scenario import Issue  # noqa: E402

TODAY = dt.date(2026, 1, 15)


def make_mini() -> tuple[Issue, ...]:
    d = dt.date
    return (
        Issue(key="E1", summary="Epic A", type="Epic", status="In Progress", category="indeterminate"),
        Issue(key="E2", summary="Epic B", type="Epic", status="To Do", category="new"),
        Issue(key="S1", type="Story", status="Done", category="done", points=3.0, parent="E1", sprints=("Sprint 1",),
              components=("Backend", "Frontend"), created=d(2026, 1, 1), resolved=d(2026, 1, 10)),
        Issue(key="S2", type="Story", status="In Progress", category="indeterminate", points=5.0, parent="E1", sprints=("Sprint 1", "Sprint 2"),
              components=("Backend",), created=d(2026, 1, 3)),
        Issue(key="S3", type="Story", status="To Do", category="new", points=2.0, parent="E2", created=d(2026, 1, 8)),
        Issue(key="S4", type="Story", status="In Review", category="indeterminate", points=None, parent="E2", sprints=("Sprint 2",),
              components=("Frontend",), created=d(2026, 1, 12)),
        Issue(key="B1", type="Bug", status="Done", category="done", points=1.0, sprints=("Sprint 2",), components=("Backend",),
              created=d(2026, 1, 5), resolved=d(2026, 1, 12)),
        Issue(key="T1", type="Sub-task", is_subtask=True, status="Done", category="done", parent="S2", created=d(2026, 1, 3), resolved=d(2026, 1, 9)),
        Issue(key="T2", type="Sub-task", is_subtask=True, status="To Do", category="new", parent="S2", created=d(2026, 1, 3)),
    )


@pytest.fixture
def mini():
    return make_mini()
