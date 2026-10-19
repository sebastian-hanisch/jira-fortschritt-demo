"""Datenmodell der Tickets und der erzeugte Beispiel-Projektbestand (deterministisch aus Epic-Zahl und Zufalls-Seed)."""

import datetime as dt
from dataclasses import dataclass

import jira_constants as C
from jira_rng import SplitMix64


@dataclass(frozen=True)
class Issue:
    """Ein Jira-Ticket in der Form, die der Kern braucht. `points` ist None, wenn das Ticket nicht geschätzt ist."""

    key: str
    summary: str = ""
    type: str = "Story"
    is_subtask: bool = False
    status: str = "To Do"
    category: str = "new"            # new | indeterminate | done (Statuskategorie von Jira)
    points: float | None = None
    parent: str = ""                 # Schlüssel des übergeordneten Tickets (Epic oder Story), leer ohne Eltern
    sprints: tuple[str, ...] = ()    # in Jira-Reihenfolge; der letzte ist der aktuelle
    components: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    assignee: str = ""
    versions: tuple[str, ...] = ()
    created: dt.date | None = None
    resolved: dt.date | None = None

    @property
    def is_epic(self) -> bool:
        return self.type.strip().lower() in ("epic",)


# Status des Beispiel-Workflows mit Statuskategorie
SAMPLE_STATUS = {
    "Backlog": "new", "To Do": "new", "In Progress": "indeterminate", "In Review": "indeterminate", "Testing": "indeterminate", "Done": "done"}


def _pick(rng: SplitMix64, items, probs=None):
    """Zieht ein Element; ohne Wahrscheinlichkeiten gleichverteilt."""
    u = rng.uniform()
    if probs is None:
        return items[min(int(u * len(items)), len(items) - 1)]
    acc = 0.0
    for item, p in zip(items, probs):
        acc += p
        if u < acc:
            return item
    return items[-1]


def _sprint_start(number: int) -> dt.date:
    return C.SAMPLE_START + dt.timedelta(days=14 * (number - 1))


def _story_status(rng: SplitMix64, sprint: int) -> str:
    """Status einer Story nach Lage ihres Sprints zum aktuellen: Vergangenes ist meist fertig, Künftiges offen."""
    cur = C.SAMPLE_CURRENT_SPRINT
    if sprint < cur:
        return "Done" if rng.uniform() < 0.85 else _pick(rng, ("In Review", "Testing"))
    if sprint == cur:
        return _pick(rng, ("To Do", "In Progress", "In Review", "Testing", "Done"), (0.15, 0.30, 0.20, 0.15, 0.20))
    return "To Do" if sprint == cur + 1 else "Backlog"


def _subtask_status(rng: SplitMix64, story_status: str) -> str:
    if story_status == "Done":
        return "Done"
    if story_status in ("To Do", "Backlog"):
        return "To Do"
    done_prob = {"In Progress": 0.5, "In Review": 0.8, "Testing": 0.95}[story_status]
    return "Done" if rng.uniform() < done_prob else _pick(rng, ("To Do", "In Progress"))


def _resolved_on(rng: SplitMix64, sprint: int) -> dt.date:
    day = _sprint_start(sprint) + dt.timedelta(days=3 + int(rng.uniform() * 10))
    return min(day, C.SAMPLE_TODAY)


def make_sample(n_epics: int, seed: int) -> tuple[Issue, ...]:
    """Beispielprojekt: Epics mit Stories, Bugs und Tasks (Story Points aus der Fibonacci-Skala, ein Teil ungeschätzt) und Sub-Tasks ohne Schätzung."""
    rng = SplitMix64(seed)
    issues: list[Issue] = []
    counter = 0

    def next_key() -> str:
        nonlocal counter
        counter += 1
        return f"DEMO-{counter}"

    for e in range(n_epics):
        epic_key = next_key()
        first_sprint = 1 + (e * (C.SAMPLE_SPRINTS - 4)) // max(n_epics, 1)
        span = 5 + int(rng.uniform() * 3)
        release = "Release 1.0" if e < (n_epics + 1) // 2 else "Release 1.1"
        children: list[Issue] = []
        for _ in range(4 + int(rng.uniform() * 6)):
            kind = _pick(rng, ("Story", "Bug", "Task"), (0.75, 0.15, 0.10))
            sprint = min(first_sprint + int(rng.uniform() * span), C.SAMPLE_SPRINTS)
            status = _story_status(rng, sprint)
            unestimated = rng.uniform() < (0.30 if kind == "Bug" else 0.12)
            points = None if unestimated else float(_pick(rng, C.STORY_POINT_SCALE, C.STORY_POINT_PROBS))
            sprint_names = ()
            if sprint <= C.SAMPLE_CURRENT_SPRINT + 1:
                sprint_names = (f"Sprint {sprint}",)
                if status != "Done" and sprint < C.SAMPLE_CURRENT_SPRINT:    # nicht fertig geworden: in den aktuellen Sprint übernommen
                    sprint_names += (f"Sprint {C.SAMPLE_CURRENT_SPRINT}",)
            created = min(_sprint_start(sprint), C.SAMPLE_TODAY) - dt.timedelta(days=int(rng.uniform() * 20))      # nie nach dem Stichtag erstellt
            key = next_key()
            story = Issue(
                key=key, summary=f"{kind} {key}", type=kind, status=status, category=SAMPLE_STATUS[status], points=points, parent=epic_key,
                sprints=sprint_names, components=(_pick(rng, C.COMPONENTS),), labels=tuple(sorted({_pick(rng, C.LABELS)} if rng.uniform() < 0.5 else ())),
                assignee=_pick(rng, C.ASSIGNEES), versions=(release,) if rng.uniform() < 0.85 else (), created=max(created, C.SAMPLE_START - dt.timedelta(days=30)),
                resolved=_resolved_on(rng, sprint) if status == "Done" else None,
            )
            children.append(story)
            if points is not None and points >= 3 and rng.uniform() < 0.45:
                for number in range(2 + int(rng.uniform() * 3)):
                    sub_status = _subtask_status(rng, status)
                    sub_key = next_key()
                    children.append(Issue(
                        key=sub_key, summary=f"Sub-Task {sub_key}", type="Sub-task", is_subtask=True, status=sub_status, category=SAMPLE_STATUS[sub_status],
                        parent=key, assignee=_pick(rng, C.ASSIGNEES), created=story.created,
                        resolved=_resolved_on(rng, sprint) if sub_status == "Done" else None,
                    ))
        epic_done = all(c.category == "done" for c in children)
        epic_status = "Done" if epic_done else "In Progress"
        epic_resolved = max(c.resolved for c in children) if epic_done else None
        issues.append(Issue(
            key=epic_key, summary=C.EPIC_NAMES[e % len(C.EPIC_NAMES)], type="Epic", status=epic_status, category=SAMPLE_STATUS[epic_status],
            created=C.SAMPLE_START - dt.timedelta(days=30), resolved=epic_resolved))
        issues.extend(children)
    return tuple(issues)
