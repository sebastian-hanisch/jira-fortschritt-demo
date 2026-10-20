"""Reine Hilfen ohne Oberfläche: deutsche Datumsformate, Erkennungsbericht, Titel verwerfen, Protokoll-Filter, Zusammenfassung zum Kopieren, Serverkonfiguration.
(Getrennt von den App-Tests, damit der Mutationstest diese Datei mitnimmt: er lässt Dateien mit Oberflächen-Tests aus.)"""

import datetime as dt
import io
import logging

import pytest

import jira_constants as C
import jira_evaluation as ev
import jira_import as J
import jira_privacy as P
import jira_tables as T
from conftest import TODAY
from jira_scenario import Issue, make_sample

# ---------------------------------------------------------------- deutsche Datumsformate

@pytest.mark.parametrize("text,expected", [
    ("19/Okt/26 15:45", dt.date(2026, 10, 19)), ("19/Mär/26 3:45 PM", dt.date(2026, 3, 19)), ("5/Mrz/2026 9:05 vorm.", dt.date(2026, 3, 5)),
    ("19/Dez/26 3:45 nachm.", dt.date(2026, 12, 19)), ("19/Okt./26 15:45", dt.date(2026, 10, 19)), ("19/OKT/26 15:45", dt.date(2026, 10, 19)),
    ("19/Mai/26 08:00", dt.date(2026, 5, 19)), ("1/Sept/26 08:00", dt.date(2026, 9, 1)), ("19/Oct/26 3:45 PM", dt.date(2026, 10, 19)),
    ("19.10.2026 15:45", dt.date(2026, 10, 19)), ("2026-10-19T15:45:00.000+0200", dt.date(2026, 10, 19)),
])
def test_german_and_english_dates_are_read(text, expected):
    assert J.parse_date(text) == expected


@pytest.mark.parametrize("text", ["19/Foo/26 08:00", "32/Okt/26 08:00", "gestern", "", None, "Okt/19/26"])
def test_unreadable_dates_stay_none(text):
    assert J.parse_date(text) is None


def test_every_german_month_abbreviation_maps_to_the_right_month():
    names = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    for month, name in enumerate(names, start=1):
        assert J.parse_date(f"15/{name}/26 10:00") == dt.date(2026, month, 15), name


def test_csv_with_german_dates_fills_the_burn_up_inputs():
    raw = "Issue key;Status;Story Points;Erstellt;Gelöst\nA-1;Erledigt;3;01/Okt/26 09:00;05/Okt/26 10:30\n".encode("utf-8")
    issues, report = J.read_csv(raw)
    assert issues[0].created == dt.date(2026, 10, 1) and issues[0].resolved == dt.date(2026, 10, 5)
    assert not any("Datumswerte" in n for n in report.notes)


# ---------------------------------------------------------------- Erkennungsbericht

def _by_field(report):
    return {r["Feld"]: r for r in report.columns}


def test_csv_report_names_the_source_column_and_counts_values():
    sample = make_sample(3, 1)
    _, report = J.read_csv(J.to_csv(sample))
    rows = _by_field(report)
    assert len(report.columns) == len(J.FIELD_LABELS) == 14
    assert rows["Story Points"]["Gefunden in"] == "Custom field (Story Points)" and rows["Story Points"]["von"] == len(sample)
    assert rows["Story Points"]["Tickets mit Wert"] == sum(i.points is not None for i in sample)
    assert rows["Sprint"]["Tickets mit Wert"] == sum(bool(i.sprints) for i in sample) and rows["Gelöst"]["Gefunden in"] == "Resolved"


def test_csv_report_marks_missing_columns_and_guessed_categories():
    _, report = J.read_csv(b"Issue key,Status\nA-1,Done\n")
    rows = _by_field(report)
    assert rows["Story Points"]["Gefunden in"] == J.NOT_FOUND and rows["Story Points"]["Tickets mit Wert"] == 0
    assert rows["Statuskategorie"]["Gefunden in"] == "(aus dem Statusnamen geraten)" and rows["Status"]["Gefunden in"] == "Status"


def test_csv_report_with_repeated_columns_lists_each_name_once():
    _, report = J.read_csv(b"Issue key,Status,Sprint,Sprint,Labels\nA-1,Done,S1,S2,x\n")
    assert _by_field(report)["Sprint"]["Gefunden in"] == "Sprint" and _by_field(report)["Sprint"]["Tickets mit Wert"] == 1


def test_json_report_names_the_fields_in_use():
    sample = make_sample(3, 1)
    _, report = J.read_json(J.to_json(sample))
    rows = _by_field(report)
    assert rows["Story Points"]["Gefunden in"] == "fields.customfield_10016" and rows["Sprint"]["Gefunden in"] == "fields.customfield_10020"
    assert rows["Übergeordnetes Ticket"]["Gefunden in"] == "fields.parent" and rows["Bearbeiter"]["Gefunden in"] == "fields.assignee"
    other = J.parse_field_ids("customfield_999", "customfield_888", "")
    _, report2 = J.read_json(J.to_json(sample), other)
    assert _by_field(report2)["Story Points"]["Gefunden in"] == J.NOT_FOUND and _by_field(report2)["Sprint"]["Gefunden in"] == J.NOT_FOUND


def test_field_counts_by_hand(mini):
    counts = J.field_counts(mini)
    assert counts["key"] == 9 and counts["points"] == 4 and counts["parent"] == 6 and counts["sprint"] == 4 and counts["resolved"] == 3 and counts["assignee"] == 0


# ---------------------------------------------------------------- Titel verwerfen

def test_drop_titles_keeps_only_the_epic_titles():
    issues = (Issue(key="E", type="Epic", summary="Kundenprojekt Alpha"), Issue(key="S", type="Story", summary="Geheimer Kundenname"), Issue(key="T", type="Sub-task", is_subtask=True, summary="x"))
    out = J.drop_titles(issues)
    assert [i.summary for i in out] == ["Kundenprojekt Alpha", "", ""]
    assert [i.summary for i in J.drop_titles(issues, keep_epics=False)] == ["", "", ""]
    assert [(a.key, a.status) for a in out] == [(b.key, b.status) for b in issues] and J.drop_titles(()) == ()


# ---------------------------------------------------------------- Protokoll-Filter

def _logger_with_filter():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    handler.addFilter(P.ScrubExceptionDetails())
    logger = logging.getLogger("test_privacy_scrub")
    logger.handlers = [handler]
    logger.propagate = False
    return logger, stream


def test_filter_replaces_the_exception_message_but_keeps_type_and_call_stations():
    logger, stream = _logger_with_filter()
    secret = "GEHEIM-12345 Kundenname"      # steht nur als Wert da, nicht in der Quelltextzeile, die der Traceback zeigt
    try:
        raise ValueError(secret)
    except ValueError:
        logger.error("Uncaught app execution", exc_info=True)
    text = stream.getvalue()
    assert "GEHEIM-12345" not in text and "Kundenname" not in text
    assert "Uncaught app execution" in text and "ValueError" in text and P.SUPPRESSED in text and "test_filter_replaces_the_exception_message" in text


def test_filter_leaves_records_without_exception_untouched():
    logger, stream = _logger_with_filter()
    logger.warning("Nur eine Warnung %s", "mit Zahl 42")
    assert stream.getvalue().strip() == "WARNING Nur eine Warnung mit Zahl 42"


def test_filter_survives_a_traceback_free_exc_info_and_many_frames():
    logger, stream = _logger_with_filter()

    secret = "Schlüssel mit Daten"

    def deep(n):
        if n == 0:
            raise KeyError(secret)
        deep(n - 1)
    try:
        deep(4)
    except KeyError:
        logger.exception("Fehler")
    assert "Schlüssel mit Daten" not in stream.getvalue() and stream.getvalue().count("deep") >= 5
    logger.error("ohne Traceback", exc_info=(ValueError, ValueError("GEHEIM"), None))
    assert "GEHEIM" not in stream.getvalue() and "ValueError" in stream.getvalue()


def test_scrub_streamlit_logs_installs_the_filter_once_on_every_streamlit_handler():
    import streamlit.logger as sl
    sl.get_logger("streamlit.runtime.scriptrunner.exec_code")            # legt den Logger mit eigenem Handler an
    first = P.scrub_streamlit_logs()
    second = P.scrub_streamlit_logs()
    assert first == second and first >= 1
    for logger in P._streamlit_loggers():
        for handler in logger.handlers:
            assert sum(isinstance(f, P.ScrubExceptionDetails) for f in handler.filters) == 1


# ---------------------------------------------------------------- Zusammenfassung zum Kopieren

def test_summary_markdown_by_hand(mini):
    a = ev.analyse(mini, ev.Settings(), TODAY)
    assert T.summary_markdown(mini, a, "SP", TODAY) == (
        "**Jira-Fortschritt** (Stand 15.01.2026)\n\n"
        "- Fortschritt (nach Status gewichtet): 57,4 %\n"
        "- Nur Done: 29,6 % nach Gewicht, 40,0 % nach Ticketzahl\n"
        "- Umfang: 5 Tickets (1 ohne Story Points), Gewicht 13,5 SP\n"
        "- Annahmen: Status-Gewichte To Do 0 %, In Progress 50 %, In Review 50 %, Done 100 %; Gewicht Story Points; ungeschätzte Tickets Median der geschätzten Tickets; "
        "Zählebene Stories, Tasks und Bugs; Sub-Task-Option aus\n\n"
        "| Epic | Gewicht (SP) | Fortschritt | Offen (SP) |\n|---|---:|---:|---:|\n"
        "| E1: Epic A | 8,0 | 68,8 % | 2,5 |\n| E2: Epic B | 4,5 | 27,8 % | 3,2 |\n| (ohne Epic) | 1,0 | 100,0 % | 0,0 |\n| Summe | 13,5 | 57,4 % | 5,8 |\n")


def test_summary_markdown_follows_the_settings(mini):
    text = T.summary_markdown(mini, ev.analyse(mini, ev.Settings(scheme=C.SCHEME_WORKFLOW, blend=True, weight_mode=C.WEIGHT_COUNT, dimension=C.DIM_ALL), TODAY), "Tickets", TODAY)
    assert "Gewicht Ticketanzahl; Zählebene" in text and "ungeschätzte Tickets" not in text and "Sub-Task-Option an" in text and "In Review 80 %" in text
    assert "| Gruppe | Gewicht (Tickets) | Fortschritt | Offen (Tickets) |" in text and "Gewicht 5,0 Tickets" in text


def test_summary_markdown_without_weight_shows_dashes_and_escapes_pipes():
    issues = (Issue(key="E", type="Epic", summary="A | B"), Issue(key="S", type="Story", status="Done", category="done", parent="E"))
    text = T.summary_markdown(issues, ev.analyse(issues, ev.Settings(unest_rule=C.UNEST_IGNORE), TODAY), "SP", TODAY)
    assert "(nach Status gewichtet): –" in text and "| E: A / B |" in text and "A | B" not in text


def test_summary_markdown_caps_long_group_lists():
    issues = tuple(Issue(key=f"A-{n}", type="Story", status="Done", category="done", points=1.0, assignee=f"Name {n:03d}") for n in range(T.MAX_SUMMARY_ROWS + 5))
    text = T.summary_markdown(issues, ev.analyse(issues, ev.Settings(dimension=C.DIM_ASSIGNEE), TODAY), "SP", TODAY)
    assert text.count("\n| Name ") == T.MAX_SUMMARY_ROWS and "| Summe |" in text and f"die ersten {T.MAX_SUMMARY_ROWS} von {T.MAX_SUMMARY_ROWS + 5} Gruppen" in text
    assert T.summary_markdown((), ev.analyse((), ev.Settings(), TODAY), "SP", TODAY).count("|") == 0


@pytest.mark.parametrize("extra,capped", [(0, False), (1, True)])
def test_summary_markdown_cap_boundary_is_inclusive(extra, capped):
    n = T.MAX_SUMMARY_ROWS + extra
    issues = tuple(Issue(key=f"A-{k}", type="Story", status="Done", category="done", points=1.0, assignee=f"Name {k:03d}") for k in range(n))
    text = T.summary_markdown(issues, ev.analyse(issues, ev.Settings(dimension=C.DIM_ASSIGNEE), TODAY), "SP", TODAY)
    assert text.count("\n| Name ") == T.MAX_SUMMARY_ROWS and ("Gezeigt:" in text) is capped and "| Summe |" in text
    assert f"| Name {T.MAX_SUMMARY_ROWS - 1:03d} |" in text and (f"| Name {T.MAX_SUMMARY_ROWS:03d} |" in text) is False


def test_summary_markdown_just_below_the_cap_has_exactly_one_total_row():
    n = T.MAX_SUMMARY_ROWS - 1
    issues = tuple(Issue(key=f"A-{k}", type="Story", status="Done", category="done", points=1.0, assignee=f"Name {k:03d}") for k in range(n))
    text = T.summary_markdown(issues, ev.analyse(issues, ev.Settings(dimension=C.DIM_ASSIGNEE), TODAY), "SP", TODAY)
    assert text.count("| Summe |") == 1 and text.count("\n| Name ") == n and "Gezeigt:" not in text


def test_license_and_readme_agree_on_open_source_and_local_hosting():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License") and "Sebastian Hanisch" in license_text and "WITHOUT WARRANTY" in license_text
    assert "MIT-Lizenz" in readme and "Open Source" in readme and "selbst gehostet" in readme
    assert f"git clone {C.REPO_URL}.git" in readme and "--server.address localhost" in readme and "http://localhost:8501" in readme
    assert C.REPO_URL.startswith("https://github.com/") and C.REPO_URL.endswith("/" + root.name)
