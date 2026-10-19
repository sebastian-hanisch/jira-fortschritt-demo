"""Tabellarische Auswertungen gegen Handrechnung an der Mini-Instanz (conftest.py), Randfälle und CSV."""

import datetime as dt

import pytest

import jira_constants as C
import jira_evaluation as ev
import jira_tables as T
from conftest import TODAY
from jira_scenario import Issue


def _a(mini, **kw):
    return ev.analyse(mini, ev.Settings(**kw), TODAY)


def _row(rows, label, key="Gruppe"):
    return next(r for r in rows if r[key] == label)


def test_status_order_follows_category_then_name(mini):
    assert T.atom_statuses(mini, _a(mini)) == ["To Do", "In Progress", "In Review", "Done"]


def test_status_by_group_weight_by_hand(mini):
    rows = T.status_by_group(mini, _a(mini), T.METRIC_WEIGHT)
    assert [r["Gruppe"] for r in rows] == ["E1: Epic A", "E2: Epic B", "(ohne Epic)", "Summe"]
    cols = ("To Do", "In Progress", "In Review", "Done", "Summe")
    assert [rows[0][c] for c in cols] == [0, 5, 0, 3, 8] and [rows[1][c] for c in cols] == [2, 0, 2.5, 0, 4.5]
    assert [rows[2][c] for c in cols] == [0, 0, 0, 1, 1] and [rows[3][c] for c in cols] == [2, 5, 2.5, 4, 13.5]
    assert rows[0]["Fortschritt"] == pytest.approx(0.6875) and rows[3]["Fortschritt"] == pytest.approx(7.75 / 13.5)


def test_status_by_group_count_and_credited_by_hand(mini):
    counts = T.status_by_group(mini, _a(mini), T.METRIC_COUNT)
    assert [counts[0][c] for c in ("To Do", "In Progress", "In Review", "Done", "Summe")] == [0, 1, 0, 1, 2] and counts[3]["Summe"] == 5
    credited = T.status_by_group(mini, _a(mini), T.METRIC_CREDITED)
    assert [credited[0][c] for c in ("To Do", "In Progress", "In Review", "Done")] == [0, 2.5, 0, 3]
    assert credited[1]["In Review"] == 1.25 and credited[3]["Summe"] == pytest.approx(7.75)


def test_status_by_group_with_multi_valued_dimension_splits_fractions(mini):
    rows = T.status_by_group(mini, _a(mini, dimension=C.DIM_COMPONENT), T.METRIC_WEIGHT)
    backend = _row(rows, "Backend")
    assert backend["Done"] == 1.5 + 1 and backend["In Progress"] == 5 and backend["Summe"] == 7.5      # S1 zur Hälfte, B1 ganz
    assert _row(rows, "Summe")["Summe"] == pytest.approx(13.5)


def test_status_by_group_unknown_metric_is_an_error(mini):
    with pytest.raises(ValueError):
        T.status_by_group(mini, _a(mini), "Unsinn")


def test_contribution_by_hand_and_sums_to_the_overall_progress(mini):
    rows = T.contribution(_a(mini))
    e1, e2, none, total = rows
    assert e1["Gewicht"] == 8 and e1["Anteil am Gewicht"] == pytest.approx(8 / 13.5) and e1["Fortschritt"] == pytest.approx(0.6875)
    assert e1["Beitrag (Punkte)"] == pytest.approx(100 * 5.5 / 13.5) and e2["Beitrag (Punkte)"] == pytest.approx(100 * 1.25 / 13.5)
    assert (e1["Offenes Gewicht"], e2["Offenes Gewicht"], none["Offenes Gewicht"]) == (2.5, 3.25, 0.0)
    assert e2["Anteil am Offenen"] == pytest.approx(3.25 / 5.75) and total["Offenes Gewicht"] == 5.75
    assert sum(r["Beitrag (Punkte)"] for r in rows[:-1]) == pytest.approx(total["Beitrag (Punkte)"]) == pytest.approx(100 * 7.75 / 13.5)
    assert sum(r["Anteil am Gewicht"] for r in rows[:-1]) == pytest.approx(1.0)


def test_status_overview_by_hand(mini):
    rows = T.status_overview(mini, _a(mini))
    assert [r["Status"] for r in rows] == ["To Do", "In Progress", "In Review", "Done", "Summe"]
    todo, prog, review, done, total = rows
    assert (todo["Tickets"], todo["Gewicht"], todo["Status-Gewicht (%)"], todo["Angerechnet"]) == (1, 2, 0, 0)
    assert (prog["Tickets"], prog["Gewicht"], prog["Status-Gewicht (%)"], prog["Angerechnet"]) == (1, 5, 50, 2.5)
    assert (review["Gewicht"], review["Angerechnet"], done["Tickets"], done["Gewicht"], done["Angerechnet"]) == (2.5, 1.25, 2, 4, 4)
    assert prog["Anteil am Angerechneten"] == pytest.approx(2.5 / 7.75) and done["Anteil am Angerechneten"] == pytest.approx(4 / 7.75)
    assert (total["Tickets"], total["Gewicht"], total["Angerechnet"], total["Kategorie"]) == (5, 13.5, 7.75, "")
    assert todo["Kategorie"] == "To Do" and prog["Kategorie"] == "In Arbeit" and done["Kategorie"] == "Erledigt"


def test_status_overview_shows_the_effective_credit_with_the_subtask_option(mini):
    rows = T.status_overview(mini, _a(mini, scheme=C.SCHEME_WORKFLOW, blend=True))
    prog = _row(rows, "In Progress", "Status")
    assert prog["Status-Gewicht (%)"] == 40 and prog["Angerechnet"] == pytest.approx(5 * 0.5)         # Story S2 zählt wegen der Sub-Tasks 50 % statt 40 %


def test_done_by_month_by_hand_with_gap_months_and_missing_dates(mini):
    extra = mini + (Issue(key="S9", type="Story", status="Done", category="done", points=2.0, resolved=dt.date(2026, 3, 2)),
                    Issue(key="S10", type="Story", status="Done", category="done", points=7.0))
    rows, missing = T.done_by_month(extra, _a(extra))
    assert [r["Monat"] for r in rows] == ["2026-01", "2026-02", "2026-03"] and missing == 1
    assert [r["Tickets erledigt"] for r in rows] == [2, 0, 1] and [r["Gewicht erledigt"] for r in rows] == [4, 0, 2]
    assert [r["Gewicht kumuliert"] for r in rows] == [4, 4, 6]


def test_done_by_month_spans_year_boundaries():
    issues = (Issue(key="A", status="Done", category="done", points=1.0, resolved=dt.date(2025, 12, 31)),
              Issue(key="B", status="Done", category="done", points=1.0, resolved=dt.date(2026, 1, 1)))
    rows, _ = T.done_by_month(issues, ev.analyse(issues, ev.Settings()))
    assert [r["Monat"] for r in rows] == ["2025-12", "2026-01"]


def test_done_by_month_without_any_done_ticket_is_empty():
    issues = (Issue(key="A", points=1.0),)
    assert T.done_by_month(issues, ev.analyse(issues, ev.Settings())) == ([], 0)


def test_data_quality_by_hand(mini):
    rows = {r["Prüfung"]: r for r in T.data_quality(mini, _a(mini))}
    assert {k: v["Anzahl"] for k, v in rows.items()} == {
        "Ohne Story Points": 1, "Story Points = 0": 0, "Ohne Epic": 1, "Ohne Sprint": 1, "Erledigt ohne Lösungsdatum": 0, "Lösungsdatum vor Erstelldatum": 0,
        "Erledigt, aber Sub-Tasks offen": 0, "Status mit uneinheitlicher Kategorie": 0}
    assert rows["Ohne Story Points"]["Anteil an den Tickets"] == pytest.approx(0.2) and rows["Status mit uneinheitlicher Kategorie"]["Anteil an den Tickets"] is None
    assert all(r["Wirkung"] for r in rows.values())


def test_data_quality_finds_each_defect():
    d = dt.date
    issues = (
        Issue(key="E", type="Epic"),
        Issue(key="A", type="Story", status="Done", category="done", points=0.0, parent="E", sprints=("Sprint 1",), created=d(2026, 2, 1), resolved=d(2026, 1, 1)),
        Issue(key="B", type="Story", status="Done", category="done", points=3.0, parent="E", sprints=("Sprint 1",)),
        Issue(key="T", type="Sub-task", is_subtask=True, status="To Do", category="new", parent="B"),
        Issue(key="C", type="Story", status="Seltsam", category="new", points=1.0), Issue(key="D", type="Story", status="Seltsam", category="done", points=1.0))
    got = {r["Prüfung"]: r["Anzahl"] for r in T.data_quality(issues, ev.analyse(issues, ev.Settings()))}
    assert got == {"Ohne Story Points": 0, "Story Points = 0": 1, "Ohne Epic": 2, "Ohne Sprint": 2, "Erledigt ohne Lösungsdatum": 2, "Lösungsdatum vor Erstelldatum": 1,
                   "Erledigt, aber Sub-Tasks offen": 1, "Status mit uneinheitlicher Kategorie": 1}


def test_unestimated_tickets_list_and_limit(mini):
    rows, total = T.unestimated_tickets(mini, _a(mini))
    assert rows == [{"Schlüssel": "S4", "Titel": "", "Typ": "Story", "Status": "In Review", "Epic": "E2"}] and total == 1
    many = tuple(Issue(key=f"X{n}", type="Story") for n in range(5))
    rows, total = T.unestimated_tickets(many, ev.analyse(many, ev.Settings()), limit=3)
    assert [r["Schlüssel"] for r in rows] == ["X0", "X1", "X2"] and total == 5


# ---------------------------------------------------------------- Randfälle

def test_every_table_on_an_empty_project_is_empty_and_does_not_raise():
    a = ev.analyse((), ev.Settings())
    assert T.status_by_group((), a, T.METRIC_WEIGHT) == [] and T.contribution(a) == [] and T.status_overview((), a) == []
    assert T.done_by_month((), a) == ([], 0) and T.unestimated_tickets((), a) == ([], 0)
    rows = {r["Prüfung"]: r for r in T.data_quality((), a)}
    assert rows["Ohne Story Points"]["Anzahl"] == 0 and rows["Ohne Story Points"]["Anteil an den Tickets"] is None


def test_tables_without_weight_show_none_instead_of_dividing_by_zero():
    issues = (Issue(key="A", type="Story", status="Done", category="done"),)
    a = ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_IGNORE))
    row = T.contribution(a)[0]
    assert row["Anteil am Gewicht"] is None and row["Fortschritt"] is None and row["Beitrag (Punkte)"] is None and row["Anteil am Offenen"] is None
    assert T.status_overview(issues, a)[0]["Anteil am Angerechneten"] is None
    assert T.status_by_group(issues, a, T.METRIC_COUNT)[0]["Done"] == 1


def test_subtask_level_tables(mini):
    a = ev.analyse(mini, ev.Settings(count_level=C.LEVEL_SUBTASKS), TODAY)
    rows = T.status_by_group(mini, a, T.METRIC_COUNT)
    assert rows[-1]["Summe"] == 2 and T.atom_statuses(mini, a) == ["To Do", "Done"]


# ---------------------------------------------------------------- CSV

def test_rows_to_csv_uses_semicolons_decimal_commas_and_a_byte_order_mark():
    rows = [{"Gruppe": "A; B", "Gewicht": 2.5, "Tickets": 3, "Anteil": None, "Notiz": "x\ny", "Tag": dt.date(2026, 1, 2)}, {"Gruppe": "C", "Gewicht": 0.1, "Tickets": 0}]
    data = T.rows_to_csv(rows)
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig") == "Gruppe;Gewicht;Tickets;Anteil;Notiz;Tag\nA, B;2,5;3;;x y;2026-01-02\nC;0,1;0;;;\n"
    assert T.rows_to_csv([]) == b"\xef\xbb\xbf"


def test_rows_to_csv_writes_nan_as_empty():
    assert T.rows_to_csv([{"a": float("nan"), "b": 1.0}]).decode("utf-8-sig") == "a;b\n;1,0\n"


def test_summary_rows_without_any_weight_are_none_not_one():
    issues = (Issue(key="A", type="Story", status="Done", category="done"),)
    a = ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_IGNORE))
    total = T.contribution(a)[-1]
    assert total["Anteil am Gewicht"] is None and total["Anteil am Offenen"] is None and total["Beitrag (Punkte)"] is None and total["Fortschritt"] is None
    assert T.status_overview(issues, a)[-1]["Anteil am Angerechneten"] is None and T.status_by_group(issues, a, T.METRIC_WEIGHT)[-1]["Fortschritt"] is None


def test_fractional_story_points_below_one_are_shown_not_treated_as_no_weight():
    issues = (Issue(key="A", type="Story", status="Done", category="done", points=0.5), Issue(key="B", type="Story", status="To Do", category="new", points=0.25))
    a = ev.analyse(issues, ev.Settings())
    rows = T.contribution(a)
    assert rows[-1]["Gewicht"] == 0.75 and rows[-1]["Anteil am Gewicht"] == 1.0 and rows[0]["Anteil am Gewicht"] == pytest.approx(1.0)
    assert rows[-1]["Beitrag (Punkte)"] == pytest.approx(100 * 0.5 / 0.75)
    assert rows[0]["Beitrag (Punkte)"] == pytest.approx(100 * 0.5 / 0.75) and rows[0]["Anteil am Offenen"] == pytest.approx(1.0) and rows[-1]["Anteil am Offenen"] == 1.0
    over = T.status_overview(issues, a)
    assert over[0]["Anteil am Angerechneten"] == pytest.approx(0.0) and over[1]["Anteil am Angerechneten"] == pytest.approx(1.0) and over[-1]["Anteil am Angerechneten"] == 1.0
    assert ev.check_consistency(a) == []


def test_data_quality_resolution_on_the_creation_day_is_fine_and_done_subtasks_do_not_count():
    d = dt.date
    issues = (Issue(key="A", type="Story", status="Done", category="done", points=1.0, created=d(2026, 1, 1), resolved=d(2026, 1, 1)),
              Issue(key="T", type="Sub-task", is_subtask=True, status="Done", category="done", parent="A"),
              Issue(key="B", type="Story", status="Done", category="done", points=1.0, parent="A"))
    got = {r["Prüfung"]: r["Anzahl"] for r in T.data_quality(issues, ev.analyse(issues, ev.Settings()))}
    assert got["Lösungsdatum vor Erstelldatum"] == 0 and got["Erledigt, aber Sub-Tasks offen"] == 0
