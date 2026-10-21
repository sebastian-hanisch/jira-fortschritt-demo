"""Orakel-Test: der vektorisierte Kern gegen eine einfache Schleifenfassung in exakter Bruchrechnung (anderer Rechenweg, DEMO-PLAYBOOK §12).

Das Orakel steht allein in diesem Test: keine Funktion aus jira_algorithm.py, nur `fractions`, Wörterbücher und Schleifen über die Definition
P(G) = sum s*w*c / sum s*w. Dazu Eigenschaften, die jede richtige Fassung erfüllen muss (Skalierung der Story Points, Reihenfolge der Tickets, Monotonie)."""

import datetime as dt
from fractions import Fraction as F

import numpy as np
import pytest

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev
from jira_rng import SplitMix64
from jira_scenario import make_sample

KEYWORDS = (("review", F(4, 5)), ("prüfung", F(4, 5)), ("pruefung", F(4, 5)), ("test", F(9, 10)), ("qa", F(9, 10)), ("abnahme", F(9, 10)), ("verif", F(9, 10)),
            ("progress", F(2, 5)), ("bearbeitung", F(2, 5)), ("arbeit", F(2, 5)), ("doing", F(2, 5)))


def o_credit(scheme, status, category, custom):
    if scheme == C.SCHEME_CUSTOM:
        return F(str(dict(custom)[status])) if status in dict(custom) else o_credit(C.SCHEME_LINEAR, status, category, ())
    if category == "done":
        return F(1)
    if category == "new" or scheme == C.SCHEME_DONE:
        return F(0)
    if scheme == C.SCHEME_LINEAR:
        return F(1, 2)
    for word, value in KEYWORDS:                       # Workflow-gewichtet, Kategorie in Arbeit: erster Treffer der Reihenfolge
        if word in status.lower():
            return value
    return F(1, 2)


def o_epic(by_key, issue):
    cur, steps = issue, 0
    while cur is not None and steps < 10:
        if cur.type.strip().lower() == "epic":
            return cur.key
        cur = by_key.get(cur.parent)
        steps += 1
    return ""


def o_labels(by_key, issue, dim, level=1):
    def inherited(getter):
        value = getter(issue)
        if not value and issue.parent in by_key:
            value = getter(by_key[issue.parent])
        return list(value)
    if dim == C.DIM_ALL:
        return ["Gesamtes Projekt"]
    if dim == C.DIM_EPIC:
        e = o_epic(by_key, issue)
        return [f"{e}: {by_key[e].summary or e}" if e else "(ohne Epic)"]
    if dim == C.DIM_LEVEL:
        chain, cur = [issue], by_key.get(issue.parent)
        while cur is not None and len(chain) < 50:
            chain.append(cur)
            cur = by_key.get(cur.parent)
        chain.reverse()
        if len(chain) < level:
            return [f"(keine Stufe {level})"]
        t = chain[level - 1]
        return [f"{t.key}: {t.summary}" if t.summary else t.key]
    if dim == C.DIM_SPRINT:
        v = inherited(lambda x: x.sprints)
        return [v[-1]] if v else ["(ohne Sprint)"]
    if dim == C.DIM_RELEASE:
        return inherited(lambda x: x.versions) or ["(ohne Release)"]
    if dim == C.DIM_COMPONENT:
        return inherited(lambda x: x.components) or ["(ohne Komponente)"]
    if dim == C.DIM_LABEL:
        return list(issue.labels) or ["(ohne Label)"]
    if dim == C.DIM_ASSIGNEE:
        return [issue.assignee or "(nicht zugewiesen)"]
    if dim == C.DIM_TEAM:
        return [issue.team or "(ohne Team)"]
    if dim == C.DIM_AREA:
        return [issue.area or "(ohne Bereich)"]
    if dim == C.DIM_PRIORITY:
        return [issue.priority or "(ohne Priorität)"]
    if dim == C.DIM_TYPE:
        return [issue.type]
    return [issue.status]


def oracle_atoms(issues, s: ev.Settings):
    """Liste (Ticket, Gewicht, Gutschrift) der Atome als Brüche."""
    if s.count_level == C.LEVEL_SUBTASKS:
        atoms = [i for i in issues if i.is_subtask]
    else:
        atoms = [i for i in issues if not i.is_subtask and i.type.strip().lower() != "epic"]
    given = sorted(F(str(i.points)) for i in atoms if i.points is not None)
    if given:
        mid = len(given) // 2
        median = given[mid] if len(given) % 2 else (given[mid - 1] + given[mid]) / 2
    else:
        median = F(1)
    fill = {C.UNEST_IGNORE: F(0), C.UNEST_ONE: F(1), C.UNEST_MEDIAN: median}[s.unest_rule]

    def weight(i):
        if s.weight_mode == C.WEIGHT_COUNT:
            return F(1)
        return F(str(i.points)) if i.points is not None else fill

    def credit(i):
        own = o_credit(s.scheme, i.status, i.category, s.custom)
        if not (s.blend and s.count_level == C.LEVEL_STORIES):
            return own
        subs = [j for j in issues if j.parent == i.key and j.is_subtask]
        if not subs:
            return own
        vs = [F(str(j.points)) for j in subs] if all(j.points is not None and j.points > 0 for j in subs) else [F(1)] * len(subs)
        mean = sum(v * o_credit(s.scheme, j.status, j.category, s.custom) for v, j in zip(vs, subs)) / sum(vs)
        return max(own, mean)

    return [(i, weight(i), credit(i)) for i in atoms]


def oracle(issues, s: ev.Settings):
    """{Gruppe: (Gewicht, Gutschrift, Anzahl)} als Brüche, plus (Gesamtgewicht, Gesamtgutschrift)."""
    by_key = {i.key: i for i in issues}
    atoms = oracle_atoms(issues, s)
    groups = {}
    total_w = total_c = F(0)
    for i, w, c in atoms:
        total_w += w
        total_c += w * c
        labels = o_labels(by_key, i, s.dimension)
        for label in labels:
            g = groups.setdefault(label, [F(0), F(0), F(0)])
            g[0] += w / len(labels)
            g[1] += w * c / len(labels)
            g[2] += F(1, len(labels))
    return groups, (total_w, total_c)


def _settings(rng: SplitMix64, dim) -> ev.Settings:
    pick = lambda items: items[int(rng.uniform() * len(items))]  # noqa: E731
    return ev.Settings(scheme=pick((C.SCHEME_DONE, C.SCHEME_LINEAR, C.SCHEME_WORKFLOW)), weight_mode=pick(C.WEIGHT_MODES), unest_rule=pick(C.UNEST_RULES),
                       count_level=pick(C.COUNT_LEVELS), blend=rng.uniform() < 0.5, dimension=dim)


@pytest.mark.parametrize("seed", range(12))
def test_every_dimension_matches_the_exact_oracle(seed):
    issues = make_sample(2 + seed % 4, seed)
    rng = SplitMix64(seed)
    for dim in C.DIMENSIONS:
        s = _settings(rng, dim)
        a = ev.analyse(issues, s)
        groups, (total_w, total_c) = oracle(issues, s)
        assert set(a.stats.labels) == set(groups), (seed, dim, s)
        for k, label in enumerate(a.stats.labels):
            w, c, n = groups[label]
            assert a.stats.weight[k] == pytest.approx(float(w), rel=1e-9, abs=1e-12), (seed, dim, label)
            assert a.stats.credited[k] == pytest.approx(float(c), rel=1e-9, abs=1e-12), (seed, dim, label)
            assert a.stats.count[k] == pytest.approx(float(n), rel=1e-9), (seed, dim, label)
            if w > 0:
                assert a.stats.progress[k] == pytest.approx(float(c / w), rel=1e-9), (seed, dim, label)
            else:
                assert np.isnan(a.stats.progress[k])
        assert a.weight == pytest.approx(float(total_w), rel=1e-9)
        if total_w > 0:
            assert a.progress == pytest.approx(float(total_c / total_w), rel=1e-9)


def test_custom_credits_match_the_oracle():
    issues = make_sample(4, 3)
    custom = (("In Progress", 0.35), ("In Review", 0.7), ("Done", 0.95))
    s = ev.Settings(scheme=C.SCHEME_CUSTOM, custom=custom, dimension=C.DIM_EPIC)
    a = ev.analyse(issues, s)
    groups, (tw, tc) = oracle(issues, s)
    assert a.progress == pytest.approx(float(tc / tw), rel=1e-9)
    assert sorted(a.stats.labels) == sorted(groups)


@pytest.mark.parametrize("seed", range(6))
def test_cross_table_matches_the_oracle(seed):
    issues = make_sample(3, seed)
    s = ev.Settings(dimension=C.DIM_COMPONENT, dimension2=C.DIM_LABEL, unest_rule=C.UNEST_ONE)
    a = ev.analyse(issues, s)
    by_key = {i.key: i for i in issues}
    expected: dict[str, list[F]] = {}
    atoms = [i for i in issues if not i.is_subtask and i.type != "Epic"]
    given = sorted(F(str(i.points)) for i in atoms if i.points is not None)
    for i in atoms:
        w = F(str(i.points)) if i.points is not None else F(1)
        c = o_credit(C.SCHEME_LINEAR, i.status, i.category, ())
        first, second = o_labels(by_key, i, C.DIM_COMPONENT), o_labels(by_key, i, C.DIM_LABEL)
        for x in first:
            for y in second:
                g = expected.setdefault(f"{x}{A.PAIR_SEP}{y}", [F(0), F(0)])
                g[0] += w / (len(first) * len(second))
                g[1] += w * c / (len(first) * len(second))
    assert given or not atoms
    assert set(a.cross.labels) == set(expected)
    for k, label in enumerate(a.cross.labels):
        assert a.cross.weight[k] == pytest.approx(float(expected[label][0]), rel=1e-9)
        assert a.cross.credited[k] == pytest.approx(float(expected[label][1]), rel=1e-9)


# ---------------------------------------------------------------- Eigenschaften

@pytest.mark.parametrize("seed", range(8))
def test_scaling_all_story_points_leaves_every_progress_unchanged(seed):
    from dataclasses import replace
    issues = make_sample(3, seed)
    scaled = tuple(replace(i, points=None if i.points is None else i.points * 7) for i in issues)
    for rule in (C.UNEST_MEDIAN, C.UNEST_IGNORE):          # „als 1 SP“ ist nicht skalierungsinvariant: das Gewicht 1 bleibt 1
        s = ev.Settings(unest_rule=rule, dimension=C.DIM_EPIC)
        a, b = ev.analyse(issues, s), ev.analyse(scaled, s)
        assert np.allclose(a.stats.progress, b.stats.progress, equal_nan=True) and a.progress == pytest.approx(b.progress)


@pytest.mark.parametrize("seed", range(8))
def test_ticket_order_does_not_change_any_group_value(seed):
    issues = make_sample(3, seed)
    rng = SplitMix64(seed + 1000)
    order = sorted(range(len(issues)), key=lambda _: rng.uniform())
    shuffled = tuple(issues[i] for i in order)
    for dim in (C.DIM_EPIC, C.DIM_SPRINT, C.DIM_COMPONENT, C.DIM_LABEL):
        s = ev.Settings(dimension=dim, blend=True)
        a, b = ev.analyse(issues, s), ev.analyse(shuffled, s)
        assert a.stats.labels == b.stats.labels
        assert np.allclose(a.stats.weight, b.stats.weight) and np.allclose(a.stats.credited, b.stats.credited)
        assert a.progress == pytest.approx(b.progress)


@pytest.mark.parametrize("seed", range(8))
def test_only_done_is_never_above_linear_and_both_stay_inside_zero_one(seed):
    issues = make_sample(4, seed)
    strict = ev.analyse(issues, ev.Settings(scheme=C.SCHEME_DONE))
    linear = ev.analyse(issues, ev.Settings(scheme=C.SCHEME_LINEAR))
    assert 0 <= strict.progress <= linear.progress <= 1
    assert strict.progress == pytest.approx(strict.progress_done)         # unter „Nur Done“ ist der gewichtete Fortschritt der Done-Anteil


@pytest.mark.parametrize("seed", range(8))
def test_raising_one_status_credit_never_lowers_the_progress(seed):
    issues = make_sample(4, seed)
    low = ev.analyse(issues, ev.Settings(scheme=C.SCHEME_CUSTOM, custom=(("In Review", 0.2),))).progress
    high = ev.analyse(issues, ev.Settings(scheme=C.SCHEME_CUSTOM, custom=(("In Review", 0.9),))).progress
    assert low <= high + 1e-12


def test_equal_story_points_make_the_weighted_progress_equal_the_ticket_average():
    from dataclasses import replace
    issues = tuple(replace(i, points=3.0) for i in make_sample(3, 5))
    a = ev.analyse(issues, ev.Settings(weight_mode=C.WEIGHT_POINTS))
    b = ev.analyse(issues, ev.Settings(weight_mode=C.WEIGHT_COUNT))
    assert a.progress == pytest.approx(b.progress)


def test_burn_up_matches_a_direct_count_per_date():
    issues = make_sample(3, 9)
    today = C.SAMPLE_TODAY
    a = ev.analyse(issues, ev.Settings(), today)
    grid, scope, finished, missing = a.burn
    atoms = [i for i in issues if not i.is_subtask and i.type != "Epic"]
    given = sorted(i.points for i in atoms if i.points is not None)
    mid = len(given) // 2
    median = given[mid] if len(given) % 2 else (given[mid - 1] + given[mid]) / 2
    first = min([i.created for i in atoms if i.created] + [i.resolved for i in atoms if i.resolved])
    for day, sc, fi in zip(grid, scope, finished):
        want_scope = sum((i.points if i.points is not None else median) for i in atoms if (i.created or first) <= day)
        want_done = sum((i.points if i.points is not None else median) for i in atoms if i.category == "done" and i.resolved and i.resolved <= day)
        assert sc == pytest.approx(want_scope) and fi == pytest.approx(want_done), day
    last = max([i.created for i in atoms if i.created] + [i.resolved for i in atoms if i.resolved] + [today])
    assert grid[0] == first and grid[-1] == last and isinstance(grid[0], dt.date)


# ---------------------------------------------------------------- Tabellen

@pytest.mark.parametrize("seed", range(8))
def test_status_by_group_matches_the_exact_oracle(seed):
    import jira_tables as T
    issues = make_sample(2 + seed % 3, seed)
    rng = SplitMix64(seed + 500)
    by_key = {i.key: i for i in issues}
    for dim in (C.DIM_EPIC, C.DIM_SPRINT, C.DIM_COMPONENT, C.DIM_LABEL, C.DIM_STATUS):
        s = _settings(rng, dim)
        a = ev.analyse(issues, s)
        cells = {}
        for issue, w, c in oracle_atoms(issues, s):
            labels = o_labels(by_key, issue, dim)
            for label in labels:
                for metric, value in ((T.METRIC_WEIGHT, w), (T.METRIC_COUNT, F(1)), (T.METRIC_CREDITED, w * c)):
                    cells[(metric, label, issue.status)] = cells.get((metric, label, issue.status), F(0)) + value / len(labels)
        for metric in T.METRICS:
            rows = T.status_by_group(issues, a, metric)
            statuses = T.atom_statuses(issues, a)
            for row in rows[:-1]:
                for status in statuses:
                    assert row[status] == pytest.approx(float(cells.get((metric, row["Gruppe"], status), 0)), rel=1e-9, abs=1e-12), (seed, dim, metric, row["Gruppe"], status)
            for status in statuses:                                    # Summenzeile = Summe über alle Gruppen
                assert rows[-1][status] == pytest.approx(sum(float(v) for (m, _, st), v in cells.items() if m == metric and st == status), rel=1e-9, abs=1e-12)


@pytest.mark.parametrize("seed", range(8))
def test_status_overview_and_contribution_match_the_exact_oracle(seed):
    import jira_tables as T
    issues = make_sample(3, seed)
    s = ev.Settings(scheme=C.SCHEME_WORKFLOW, blend=bool(seed % 2), dimension=C.DIM_EPIC)
    a = ev.analyse(issues, s)
    atoms = oracle_atoms(issues, s)
    total_w, total_c = sum(w for _, w, _ in atoms), sum(w * c for _, w, c in atoms)
    for row in T.status_overview(issues, a)[:-1]:
        mine = [(w, c) for i, w, c in atoms if i.status == row["Status"]]
        assert row["Tickets"] == len(mine) and row["Gewicht"] == pytest.approx(float(sum(w for w, _ in mine)))
        assert row["Angerechnet"] == pytest.approx(float(sum(w * c for w, c in mine)), rel=1e-9, abs=1e-12)
    rows = T.contribution(a)
    assert rows[-1]["Beitrag (Punkte)"] == pytest.approx(float(100 * total_c / total_w), rel=1e-9)
    assert sum(r["Beitrag (Punkte)"] for r in rows[:-1]) == pytest.approx(float(100 * total_c / total_w), rel=1e-9)
    assert sum(r["Anteil am Offenen"] for r in rows[:-1]) == pytest.approx(1.0)


@pytest.mark.parametrize("seed", range(8))
def test_done_by_month_matches_a_direct_count(seed):
    import jira_tables as T
    issues = make_sample(4, seed)
    a = ev.analyse(issues, ev.Settings())
    rows, missing = T.done_by_month(issues, a)
    atoms = oracle_atoms(issues, ev.Settings())
    done = [(i, w) for i, w, _ in atoms if i.category == "done"]
    assert missing == sum(i.resolved is None for i, _ in done)
    for row in rows:
        year, month = (int(x) for x in row["Monat"].split("-"))
        mine = [w for i, w in done if i.resolved and (i.resolved.year, i.resolved.month) == (year, month)]
        assert row["Tickets erledigt"] == len(mine) and row["Gewicht erledigt"] == pytest.approx(float(sum(mine)))
    assert rows[-1]["Gewicht kumuliert"] == pytest.approx(float(sum(w for i, w in done if i.resolved)))
