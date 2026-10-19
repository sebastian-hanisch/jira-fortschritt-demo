"""Einlesen: CSV (englisch, deutsch, Semikolon, Vorgangs-IDs), JSON (Antwort der REST-Suche), Fehlerfälle und Rundlauf. Es gibt keine API-Anbindung."""

import datetime as dt
import json

import pytest

import jira_constants as C
import jira_import as J
from jira_scenario import Issue, make_sample

CSV_EN = """Summary,Issue key,Issue id,Issue Type,Status,Status Category,Parent,Custom field (Story Points),Sprint,Sprint,Labels,Labels,Component/s,Assignee,Fix versions,Created,Resolved
Epic eins,P-1,100,Epic,In Progress,In Progress,,,,,,,,,,19/Oct/26 3:45 PM,
Story eins,P-2,101,Story,Done,Done,100,5,Sprint 1,Sprint 2,a,b,Backend,Person A,Release 1,01/Oct/26 9:00 AM,05/Oct/26 10:30 AM
Unteraufgabe,P-3,102,Sub-task,To Do,To Do,101,,,,,,,,,02/Oct/26 9:00 AM,
"""


def test_csv_english_export_with_repeated_columns_and_id_parents():
    issues, report = J.read_csv(CSV_EN.encode("utf-8"))
    by_key = {i.key: i for i in issues}
    assert [i.key for i in issues] == ["P-1", "P-2", "P-3"] and report.issues == 3 and report.notes == []
    s = by_key["P-2"]
    assert (s.type, s.status, s.category, s.points, s.parent) == ("Story", "Done", "done", 5.0, "P-1")      # Parent 100 ist die Vorgangs-ID von P-1
    assert s.sprints == ("Sprint 1", "Sprint 2") and s.labels == ("a", "b") and s.components == ("Backend",) and s.versions == ("Release 1",)
    assert s.created == dt.date(2026, 10, 1) and s.resolved == dt.date(2026, 10, 5)
    assert by_key["P-3"].is_subtask and by_key["P-3"].parent == "P-2" and by_key["P-3"].points is None


def test_csv_german_headers_semicolon_and_decimal_comma_points():
    text = ("Vorgangsschlüssel;Vorgangstyp;Status;Statuskategorie;Story Points;Übergeordneter Vorgang;Erstellt;Gelöst\n"
            "X-1;Epic;Offen;Zu erledigen;;;19.10.2026 10:00;\n"
            "X-2;Story;Erledigt;Erledigt;2,5;X-1;01.10.2026;03.10.2026 12:00\n")
    issues, report = J.read_csv(text.encode("utf-8"))
    assert issues[1].points == 2.5 and issues[1].category == "done" and issues[1].parent == "X-1"
    assert issues[1].created == dt.date(2026, 10, 1) and issues[1].resolved == dt.date(2026, 10, 3)
    assert issues[0].category == "new"


def test_csv_cp1252_encoding_is_read():
    text = "Issue key,Status\nA-1,Fertig\n".replace("Fertig", "Geschlossen für Käufer")
    issues, _ = J.read_csv(text.encode("cp1252"))
    assert issues[0].status == "Geschlossen für Käufer"


def test_csv_missing_columns_are_reported_not_guessed():
    issues, report = J.read_csv(b"Issue key,Status\nA-1,Done\nA-2,To Do\n")
    assert [i.category for i in issues] == ["done", "new"] and all(i.points is None for i in issues)
    joined = " ".join(report.notes)
    for part in ("Story-Point-Spalte", "Statuskategorie", "übergeordnete", "Sprint-Spalte"):
        assert part in joined


def test_csv_bad_dates_and_points_are_counted():
    text = "Issue key,Status,Story Points,Created,Resolved\nA-1,Done,viele,gestern,\nA-2,Done,3,2026-10-01,morgen\n"
    issues, report = J.read_csv(text.encode("utf-8"))
    assert issues[0].points is None and issues[1].points == 3.0 and issues[1].created == dt.date(2026, 10, 1)
    joined = " ".join(report.notes)
    assert "2 Datumswerte" in joined and "1 Story-Point-Werte" in joined


def test_csv_parent_outside_the_export_is_dropped():
    issues, _ = J.read_csv(b"Issue key,Status,Parent\nA-1,Done,Z-9\n")
    assert issues[0].parent == ""


def test_csv_errors():
    with pytest.raises(J.JiraImportError, match="leer"):
        J.read_csv(b"")
    with pytest.raises(J.JiraImportError, match="Status"):
        J.read_csv(b"Issue key,Summary\nA-1,x\n")
    with pytest.raises(J.JiraImportError, match="Obergrenze"):
        J.read_csv(b"Issue key,Status\nA-1,Done\nA-2,Done\nA-3,Done\n", max_issues=2)


def test_parse_number_and_date_edge_cases():
    assert [J.parse_number(x) for x in ("5", "2,5", " 3.5 ", "", None, "x", True, 4, 0)] == [5.0, 2.5, 3.5, None, None, None, None, 4.0, 0.0]
    assert J.parse_date("2026-10-19T15:45:00.000+0200") == dt.date(2026, 10, 19)
    assert J.parse_date("19/Oct/26 3:45 PM") == dt.date(2026, 10, 19) and J.parse_date("19.10.2026") == dt.date(2026, 10, 19)
    assert J.parse_date("2026-13-45") is None and J.parse_date("") is None and J.parse_date(None) is None


def test_roundtrip_sample_through_csv_is_lossless():
    for n, seed in ((2, 1), (6, 42), (12, 7)):
        sample = make_sample(n, seed)
        again, report = J.read_csv(J.to_csv(sample))
        assert again == sample and report.notes == []


# ---------------------------------------------------------------- JSON / REST-Felder

def _raw(key, **fields):
    base = {"summary": f"Titel {key}", "issuetype": {"name": "Story", "subtask": False}, "status": {"name": "In Review", "statusCategory": {"key": "indeterminate"}},
            "labels": ["x"], "components": [{"name": "Backend"}], "fixVersions": [{"name": "R1"}], "assignee": {"displayName": "Person A"},
            "created": "2026-10-01T09:00:00.000+0200", "resolutiondate": None, "customfield_10016": 8, "customfield_10020": [{"id": 1, "name": "Sprint 3"}]}
    base.update(fields)
    return {"key": key, "fields": base}


def test_issue_from_rest_maps_all_fields():
    issue = J.issue_from_rest(_raw("P-1", parent={"key": "P-0"}), J.FieldIds())
    assert issue == Issue(key="P-1", summary="Titel P-1", type="Story", status="In Review", category="indeterminate", points=8.0, parent="P-0",
                          sprints=("Sprint 3",), components=("Backend",), labels=("x",), assignee="Person A", versions=("R1",), created=dt.date(2026, 10, 1))


def test_issue_from_rest_subtask_flag_epic_link_and_legacy_sprint_text():
    sub = J.issue_from_rest(_raw("P-2", issuetype={"name": "Teilaufgabe", "subtask": True}), J.FieldIds())
    assert sub.is_subtask
    legacy = J.issue_from_rest(_raw("P-3", customfield_10014="P-0", customfield_10020=["com.atlassian.greenhopper.service.sprint.Sprint@1[id=7,name=Sprint 9,state=ACTIVE]"]), J.FieldIds())
    assert legacy.parent == "P-0" and legacy.sprints == ("Sprint 9",)


def test_points_field_candidates_take_the_first_present_one():
    fields = J.parse_field_ids("customfield_999, customfield_10026", "", "")
    issue = J.issue_from_rest(_raw("P-1", customfield_10026=3), fields)
    assert issue.points == 3.0 and fields.sprint == C.DEFAULT_SPRINT_FIELD and fields.epic_link == ""


def test_read_json_object_and_list_and_errors():
    payload = {"issues": [_raw("P-1"), _raw("P-2")]}
    assert [i.key for i in J.read_json(json.dumps(payload).encode())[0]] == ["P-1", "P-2"]
    assert len(J.read_json(json.dumps(payload["issues"]).encode())[0]) == 2
    with pytest.raises(J.JiraImportError, match="gültige JSON"):
        J.read_json(b"{kaputt")
    with pytest.raises(J.JiraImportError, match="Liste von Tickets"):
        J.read_json(b'{"foo": 1}')


def test_issues_from_rest_reports_missing_points_and_sprints():
    raw = [_raw("P-1", customfield_10016=None, customfield_10020=None)]
    _, report = J.issues_from_rest(raw, J.FieldIds())
    assert "Kein Ticket hat Story Points" in report.notes[0] and "customfield_10016" in report.notes[0]
    assert "Kein Ticket hat einen Sprint" in report.notes[1]


def test_read_file_dispatches_by_extension_and_content():
    assert J.read_file("x.json", json.dumps([_raw("P-1")]).encode())[0][0].key == "P-1"
    assert J.read_file("export.txt", json.dumps({"issues": [_raw("P-2")]}).encode())[0][0].key == "P-2"
    assert J.read_file("export.csv", b"Issue key,Status\nA-1,Done\n")[0][0].key == "A-1"


def test_roundtrip_sample_through_json_is_lossless():
    for n, seed in ((2, 1), (6, 9), (12, 7)):
        sample = make_sample(n, seed)
        again, report = J.read_json(J.to_json(sample))
        assert again == sample and report.notes == []


def test_json_example_has_the_rest_shape_a_user_can_recognize():
    data = json.loads(J.to_json(make_sample(2, 1)))
    first_story = next(i for i in data["issues"] if i["fields"]["issuetype"]["name"] == "Story")
    f = first_story["fields"]
    assert set(data) == {"issues"} and first_story["key"].startswith("DEMO-")
    assert {"summary", "issuetype", "status", "customfield_10016", "customfield_10020", "components", "labels", "fixVersions", "created", "resolutiondate", "parent"} <= set(f)
    assert f["status"]["statusCategory"]["key"] in ("new", "indeterminate", "done") and f["created"].endswith("T00:00:00.000+0000")


def test_json_export_uses_the_given_field_ids():
    fields = J.parse_field_ids("customfield_777", "customfield_888", "")
    issues = (Issue(key="A-1", points=3.0, sprints=("Sprint 1",)),)
    data = json.loads(J.to_json(issues, fields))
    assert data["issues"][0]["fields"]["customfield_777"] == 3.0 and data["issues"][0]["fields"]["customfield_888"] == [{"name": "Sprint 1"}]
    assert J.read_json(J.to_json(issues, fields), fields)[0] == issues


def test_json_export_of_an_empty_list_and_missing_optional_values():
    assert J.read_json(J.to_json(()))[0] == ()
    bare = (Issue(key="A-1"),)
    again, _ = J.read_json(J.to_json(bare))
    assert again == bare


def test_pseudonymize_assignees_numbers_by_name_independent_of_ticket_order():
    issues = (Issue(key="1", assignee="Zoë Zeta"), Issue(key="2", assignee="Anna Alpha"), Issue(key="3", assignee=""), Issue(key="4", assignee="Zoë Zeta"))
    out = J.pseudonymize_assignees(issues)
    assert [i.assignee for i in out] == ["Person 2", "Person 1", "", "Person 2"]
    assert [i.assignee for i in J.pseudonymize_assignees(issues[::-1])][::-1] == ["Person 2", "Person 1", "", "Person 2"]
    assert all(a.key == b.key and a.status == b.status for a, b in zip(issues, out))


def test_pseudonymize_leaves_no_original_name_anywhere():
    out = J.pseudonymize_assignees(make_sample(6, 9))
    assert {i.assignee for i in out} <= {f"Person {k}" for k in range(1, 6)} | {""}
    assert J.pseudonymize_assignees(()) == ()
