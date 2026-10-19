"""End-to-end Rauchtests via Streamlits AppTest: lädt app.py, klickt jeden Button, fährt jeden Regler an seine Grenzen, wählt jede Option jeder Auswahl und
prüft, dass kein Python-Fehler und keine Meldung der internen Prüfung auftritt. Dazu Datei- und API-Pfad, Eigene Gewichte und Permalink."""

import itertools
import os

import pytest
from streamlit.testing.v1 import AppTest

import jira_constants as C
from test_import import FakeJira

APP_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
TIMEOUT = int(os.environ.get("APPTEST_TIMEOUT", "300"))  # unter Last (parallele Läufe) reichen 180 s nicht immer; Umgebungsvariable zum Anpassen
AUTOPLAY_MARKER = "▶"  # Auto-Play-Buttons (Animation mit sleep) im Smoke-Test auslassen


def _fresh_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    at.run(timeout=TIMEOUT)
    assert not at.exception, [str(e) for e in at.exception]
    return at


def _ok(at, *context):
    assert not at.exception, (context, [str(e) for e in at.exception])
    assert not [e for e in at.error if "Interne Prüfung" in e.value], (context, [e.value for e in at.error])


def test_app_loads_without_exception_and_shows_the_headline_numbers():
    at = _fresh_app()
    _ok(at)
    assert [m.label for m in at.metric][0] == "Fortschritt (nach Status gewichtet)" and len(at.metric) == 4
    assert at.get("download_button")


def test_every_button_click_does_not_raise():
    labels = [b.label for b in _fresh_app().button]
    assert labels, "keine Buttons gefunden"
    for index, label in enumerate(labels):
        if AUTOPLAY_MARKER in label:
            continue
        at = _fresh_app()
        at.button[index].click().run(timeout=TIMEOUT)
        _ok(at, label)


def test_every_slider_at_its_min_and_max_does_not_raise():
    labels = [s.label for s in _fresh_app().slider]
    assert labels, "keine Slider gefunden"
    for index, label in enumerate(labels):
        for edge in ("min", "max"):
            at = _fresh_app()
            slider = at.slider[index]
            value = slider.min if edge == "min" else slider.max
            if isinstance(slider.value, int):
                value = int(value)
            slider.set_value(value).run(timeout=TIMEOUT)
            _ok(at, label, edge)


@pytest.mark.parametrize("key,options", [("scheme", C.SCHEMES), ("unest_rule", C.UNEST_RULES), ("count_level", C.COUNT_LEVELS), ("dimension", C.DIMENSIONS),
                                          ("dimension2", C.DIMENSIONS_2)])
def test_every_option_of_every_selectbox(key, options):
    for option in options:
        at = _fresh_app()
        at.selectbox(key=key).set_value(option).run(timeout=TIMEOUT)
        _ok(at, key, option)


def test_every_weight_mode_and_the_blend_toggle():
    for mode, blend in itertools.product(C.WEIGHT_MODES, (False, True)):
        at = _fresh_app()
        at.radio(key="weight_mode").set_value(mode)
        at.toggle(key="blend").set_value(blend).run(timeout=TIMEOUT)
        _ok(at, mode, blend)


def test_dimension_pairs_including_the_cross_table():
    pairs = [(d, C.DIM_NONE) for d in C.DIMENSIONS] + [(C.DIM_EPIC, d2) for d2 in C.DIMENSIONS[1:]] + [(C.DIM_ALL, C.DIM_SPRINT), (C.DIM_LABEL, C.DIM_COMPONENT)]
    for d1, d2 in pairs:
        at = _fresh_app()
        at.selectbox(key="dimension").set_value(d1)
        at.selectbox(key="dimension2").set_value(d2).run(timeout=TIMEOUT)
        _ok(at, d1, d2)


def test_all_minima_and_all_maxima_together():
    for edge in ("min", "max"):
        at = _fresh_app()
        at.slider(key="n_epics").set_value(C.N_EPICS_MIN if edge == "min" else C.N_EPICS_MAX)
        at.number_input(key="seed_input").set_value(0 if edge == "min" else C.SEED_MAX)
        at.radio(key="weight_mode").set_value(C.WEIGHT_COUNT if edge == "min" else C.WEIGHT_POINTS)
        at.selectbox(key="unest_rule").set_value(C.UNEST_IGNORE)
        at.selectbox(key="count_level").set_value(C.LEVEL_SUBTASKS if edge == "min" else C.LEVEL_STORIES)
        at.toggle(key="blend").set_value(edge == "max")
        at.selectbox(key="dimension").set_value(C.DIM_LABEL)
        at.selectbox(key="dimension2").set_value(C.DIM_COMPONENT).run(timeout=TIMEOUT)
        _ok(at, edge)


def test_ignore_rule_with_all_tickets_unestimated_still_renders_on_the_subtask_level():
    at = _fresh_app()
    at.selectbox(key="unest_rule").set_value(C.UNEST_IGNORE)
    at.selectbox(key="count_level").set_value(C.LEVEL_SUBTASKS).run(timeout=TIMEOUT)         # Sub-Tasks sind im Beispiel nie geschätzt: Gesamtgewicht 0
    _ok(at)
    assert at.metric[0].value == "–" and any("Kein Ticket hat Gewicht" in i.value for i in at.info)


def test_disabled_controls_follow_their_condition():
    at = _fresh_app()
    assert not at.selectbox(key="unest_rule").disabled and not at.toggle(key="blend").disabled and not at.slider(key="n_epics").disabled
    at.radio(key="weight_mode").set_value(C.WEIGHT_COUNT).run(timeout=TIMEOUT)
    assert at.selectbox(key="unest_rule").disabled
    at.selectbox(key="count_level").set_value(C.LEVEL_SUBTASKS).run(timeout=TIMEOUT)
    assert at.toggle(key="blend").disabled
    at.radio(key="source").set_value(C.SOURCE_FILE).run(timeout=TIMEOUT)
    assert at.slider(key="n_epics").disabled and at.number_input(key="seed_input").disabled


def test_file_source_without_a_file_asks_for_one_and_stops():
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_FILE).run(timeout=TIMEOUT)
    _ok(at)
    assert any("Bitte eine Datei wählen" in i.value for i in at.info) and not at.metric


def test_api_source_empty_form_shows_a_validation_error_not_a_crash():
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_API).run(timeout=TIMEOUT)
    assert any("Noch nichts geladen" in i.value for i in at.info)
    at.button(key="api_load").click().run(timeout=TIMEOUT)
    _ok(at)
    assert any("Adresse der Jira-Instanz" in e.value for e in at.error)


def test_api_source_loads_tickets_with_a_faked_connection(monkeypatch):
    import requests

    fake = FakeJira(40)
    monkeypatch.setattr(requests, "Session", lambda: fake)
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_API).run(timeout=TIMEOUT)
    at.text_input(key="api_url").set_value("https://firma.atlassian.net")
    at.text_input(key="api_email").set_value("a@b.de")
    at.text_input(key="api_token").set_value("SUPERTOKEN")
    at.text_area(key="api_jql").set_value("project = P")
    at.button(key="api_load").click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric and any("40 Tickets" in c.value for c in at.caption)
    assert fake.calls[0]["auth"] == ("a@b.de", "SUPERTOKEN")
    page = " ".join(str(x.value) for x in at.markdown) + " ".join(str(c.value) for c in at.caption) + " ".join(e.value for e in at.error)
    assert "SUPERTOKEN" not in page and "a@b.de" not in page and "SUPERTOKEN" not in str(at.query_params)


def test_api_connection_error_is_reported_without_credentials(monkeypatch):
    import requests

    class Broken:
        def get(self, *a, **k):
            raise ConnectionError("geheim: SUPERTOKEN")

    monkeypatch.setattr(requests, "Session", lambda: Broken())
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_API).run(timeout=TIMEOUT)
    at.text_input(key="api_url").set_value("https://firma.atlassian.net")
    at.text_input(key="api_token").set_value("SUPERTOKEN")
    at.text_area(key="api_jql").set_value("project = P")
    at.button(key="api_load").click().run(timeout=TIMEOUT)
    assert not at.exception
    assert any("Verbindung zu Jira fehlgeschlagen" in e.value and "SUPERTOKEN" not in e.value for e in at.error)


def test_custom_credits_change_the_result_and_the_scheme():
    base = _fresh_app()
    at = _fresh_app()
    at.session_state["custom_credits"] = (("In Progress", 0.0), ("In Review", 0.0), ("Testing", 0.0))
    at.selectbox(key="scheme").set_value(C.SCHEME_CUSTOM).run(timeout=TIMEOUT)
    _ok(at)
    assert at.metric[0].value != base.metric[0].value
    assert at.metric[0].value == at.metric[1].value                      # alle Teilstatus 0 %: gewichtet = nur Done


def test_permalink_is_clamped_and_unknown_values_are_ignored():
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    at.query_params["epics"] = "999"
    at.query_params["schema"] = "Gibt es nicht"
    at.query_params["gewicht"] = C.WEIGHT_COUNT
    at.query_params["subtasks"] = "true"
    at.run(timeout=TIMEOUT)
    _ok(at)
    assert at.slider(key="n_epics").value == C.N_EPICS_MAX and at.selectbox(key="scheme").value == C.DEFAULT_SCHEME
    assert at.radio(key="weight_mode").value == C.WEIGHT_COUNT and at.toggle(key="blend").value is True


def test_the_custom_scheme_and_the_source_are_not_written_to_the_address_bar():
    at = _fresh_app()
    at.selectbox(key="scheme").set_value(C.SCHEME_CUSTOM).run(timeout=TIMEOUT)
    assert "src" not in at.query_params and at.query_params["schema"] != C.SCHEME_CUSTOM


# ---------------------------------------------------------------- Datei-Pfad (echter Upload über AppTest)

def _upload(name, data, mime="text/csv"):
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_FILE).run(timeout=TIMEOUT)
    at.file_uploader(key="upload").set_value((name, data, mime)).run(timeout=TIMEOUT)
    return at


def test_uploaded_csv_gives_the_same_numbers_as_the_generated_sample():
    import jira_evaluation as ev
    import jira_import as J
    from jira_scenario import make_sample

    sample = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    at = _upload("export.csv", J.to_csv(sample))
    _ok(at)
    want = ev.analyse(sample, ev.Settings())
    assert at.metric[0].value == ev.pct(want.progress) and at.metric[2].value == ev.pct(want.progress_count)
    assert not at.warning or not any("Spalte" in w.value for w in at.warning)


def test_uploaded_csv_with_missing_columns_warns_instead_of_guessing():
    at = _upload("export.csv", b"Issue key,Status\nA-1,Done\nA-2,To Do\nA-3,In Progress\n")
    _ok(at)
    assert any("Story-Point-Spalte" in w.value for w in at.warning)
    # kein Ticket geschätzt, Regel „Median“ ohne geschätztes Ticket = Gewicht 1 je Ticket: linear (1 + 0 + 0,5) / 3
    assert at.metric[0].value == "50,0 %"


def test_uploaded_garbage_shows_an_error_and_stops():
    at = _upload("kaputt.csv", b"Spalte A,Spalte B\n1,2\n")
    assert not at.exception
    assert any("Issue key" in e.value or "Status" in e.value for e in at.error) and not at.metric
    at = _upload("kaputt.json", b"{nicht json", "application/json")
    assert not at.exception and any("gültige JSON" in e.value for e in at.error)


def test_uploaded_json_response_is_read():
    import json

    raw = {"issues": [{"key": "P-1", "fields": {"issuetype": {"name": "Story"}, "status": {"name": "Done", "statusCategory": {"key": "done"}}, "customfield_10016": 5}},
                      {"key": "P-2", "fields": {"issuetype": {"name": "Story"}, "status": {"name": "To Do", "statusCategory": {"key": "new"}}, "customfield_10016": 5}}]}
    at = _upload("antwort.json", json.dumps(raw).encode(), "application/json")
    _ok(at)
    assert at.metric[0].value == "50,0 %" and at.metric[1].value == "50,0 %"


# ---------------------------------------------------------------- Tabellen

def test_all_table_tabs_and_csv_downloads_are_there():
    import jira_tables as T

    at = _fresh_app()
    _ok(at)
    assert [t.label for t in at.tabs] == ["Je Gruppe", "Status × Gruppe", "Beitrag zum Fortschritt", "Status-Übersicht", "Erledigt je Monat", "Datenqualität"]
    assert len(at.get("download_button")) >= 7                                     # Beispiel, sechs Tabellen, dazu die Liste ohne Story Points
    assert at.radio(key="table_metric").value == T.METRIC_WEIGHT


def test_every_table_metric_and_dimension_renders():
    import jira_tables as T

    for metric in T.METRICS:
        for dim in (C.DIM_EPIC, C.DIM_COMPONENT, C.DIM_STATUS, C.DIM_ALL):
            at = _fresh_app()
            at.radio(key="table_metric").set_value(metric)
            at.selectbox(key="dimension").set_value(dim).run(timeout=TIMEOUT)
            _ok(at, metric, dim)


def test_tables_on_the_subtask_level_with_no_weight_do_not_crash():
    at = _fresh_app()
    at.selectbox(key="unest_rule").set_value(C.UNEST_IGNORE)
    at.selectbox(key="count_level").set_value(C.LEVEL_SUBTASKS).run(timeout=TIMEOUT)
    _ok(at)


def test_uploaded_project_without_resolution_dates_warns_in_the_month_tab():
    at = _upload("export.csv", b"Issue key,Status,Story Points\nA-1,Done,3\nA-2,To Do,2\n")
    _ok(at)
    assert any("kein lesbares Lösungsdatum" in w.value for w in at.warning)
