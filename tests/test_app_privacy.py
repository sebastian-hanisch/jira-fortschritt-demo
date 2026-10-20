"""Datenschutz in der Oberfläche: Wächter bei unerwarteten Fehlern, Upload-Lebenslauf (laden, verwerfen, löschen), Titel verwerfen, Erkennungsbericht, Zusammenfassung, Hinweis."""

import ast
import tomllib
from pathlib import Path

import jira_constants as C
import jira_evaluation as ev
import jira_import as J
from test_app import APP_PATH, TIMEOUT, _fresh_app, _ok, _upload

ROOT = Path(APP_PATH).parent


def test_the_app_installs_the_log_filter_at_the_start():
    tree = ast.parse(Path(APP_PATH).read_text(encoding="utf-8"))
    calls = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "scrub_streamlit_logs"]
    uploads = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "file_uploader"]
    assert calls and uploads and min(calls) < min(uploads)


# ---------------------------------------------------------------- Wächter, Upload-Lebenslauf

def test_unexpected_error_after_upload_shows_only_the_type(monkeypatch):
    def boom(*args, **kwargs):
        raise ValueError("GEHEIM-12345 Kundenname")
    monkeypatch.setattr(ev, "analyse", boom)
    at = _upload("export.csv", b"Issue key,Status\nA-1,Done\n")
    assert not at.exception
    assert any("Unerwarteter Fehler bei „Auswertung“ (ValueError)" in e.value for e in at.error)
    texts = " ".join([e.value for e in at.error] + [str(m.value) for m in at.markdown] + [c.value for c in at.caption])
    assert "GEHEIM" not in texts and not at.metric


def test_unexpected_error_while_parsing_shows_only_the_type(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("GEHEIM-98765")
    monkeypatch.setattr(J, "read_file", boom)
    at = _upload("export.csv", b"Issue key,Status\nA-1,Done\n")
    assert not at.exception and any("RuntimeError" in e.value and "GEHEIM" not in e.value for e in at.error)


def test_upload_lifecycle_loads_once_resets_the_uploader_and_can_be_deleted():
    raw = b"Issue key,Status,Story Points\nA-1,Done,3\nA-2,To Do,2\n"
    at = _upload("projekt.csv", raw)
    _ok(at)
    assert any("Geladen: projekt.csv mit 2 Tickets" in s.value for s in at.success)
    assert not at.get("file_uploader") and at.button(key="clear_loaded")           # nach dem Laden gibt es kein Upload-Feld mit der Datei mehr
    assert at.checkbox(key="pseudo").disabled and at.checkbox(key="drop_titles").disabled
    assert at.metric[0].value == "50,0 %" or at.metric[0].value.endswith("%")
    at.button(key="clear_loaded").click().run(timeout=TIMEOUT)
    _ok(at)
    assert at.get("file_uploader") and not at.metric and any("Bitte eine Datei wählen" in i.value for i in at.info)
    assert not at.checkbox(key="pseudo").disabled and "loaded" not in at.session_state


def test_titles_are_dropped_by_default_but_epic_titles_stay():
    raw = ("Issue key,Summary,Issue Type,Status,Parent\nE-1,Kundenprojekt Alpha,Epic,In Progress,\n"
           "E-2,Geheimer Kundenname,Story,To Do,E-1\nE-3,Noch ein Titel,Story,Done,E-1\n").encode("utf-8")
    at = _upload("export.csv", raw)
    _ok(at)
    assert at.checkbox(key="drop_titles").value is True
    tables = " ".join(t.value.to_string() for t in at.dataframe)
    page = " ".join(str(m.value) for m in at.markdown) + " ".join(c.value for c in at.caption) + tables
    assert "Geheimer Kundenname" not in page and "Noch ein Titel" not in page and "Kundenprojekt Alpha" in tables
    assert not any("Titel" in t.value.columns for t in at.dataframe if "Schlüssel" in t.value.columns)          # Liste der ungeschätzten Tickets ohne Titelspalte


def test_titles_can_be_kept_when_switched_off_before_loading():
    raw = b"Issue key,Summary,Issue Type,Status\nE-2,Titel der Story,Story,To Do\n"
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_FILE).run(timeout=TIMEOUT)
    at.checkbox(key="drop_titles").set_value(False)
    at.file_uploader(key="upload_0").set_value(("export.csv", raw, "text/csv")).run(timeout=TIMEOUT)
    _ok(at)
    unest = next(t.value for t in at.dataframe if "Schlüssel" in t.value.columns)
    assert list(unest["Titel"]) == ["Titel der Story"]


def test_recognition_report_is_shown_after_an_upload():
    at = _upload("export.csv", b"Issue key,Status\nA-1,Done\n")
    assert any("Was wurde erkannt" in e.label for e in at.expander)
    report = next(t.value for t in at.dataframe if "Gefunden in" in t.value.columns)
    assert len(report) == 14 and J.NOT_FOUND in set(report["Gefunden in"])


def test_summary_for_copying_is_shown_as_markdown_code():
    at = _fresh_app()
    assert any("Zusammenfassung zum Kopieren" in e.label for e in at.expander)
    block = next(c for c in at.code if "Jira-Fortschritt" in c.value)
    assert block.language == "markdown" and "| Epic |" in block.value and "Annahmen:" in block.value


def test_notice_names_the_limits():
    at = _fresh_app()
    at.radio(key="source").set_value(C.SOURCE_FILE).run(timeout=TIMEOUT)
    notice = next(w.value for w in at.warning if "Bitte vor dem Hochladen lesen" in w.value)
    assert f"{C.MAX_UPLOAD_MB} MB" in notice and f"{C.MAX_IMPORT_ISSUES} Tickets" in notice


# ---------------------------------------------------------------- Konfiguration

def test_server_config_limits_the_upload_size_and_disables_usage_statistics():
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["server"]["maxUploadSize"] == C.MAX_UPLOAD_MB == 50
    assert config["browser"]["gatherUsageStats"] is False


def test_app_points_to_the_repository_and_local_hosting():
    at = _fresh_app()
    caption = next(c.value for c in at.caption if "Open Source" in c.value)
    assert "MIT-Lizenz" in caption and C.REPO_URL in caption and "lokal ausführen" in caption
    at.radio(key="source").set_value(C.SOURCE_FILE).run(timeout=TIMEOUT)
    notice = next(w.value for w in at.warning if "Bitte vor dem Hochladen lesen" in w.value)
    assert "Open Source (MIT-Lizenz)" in notice and C.REPO_URL in notice and "lokal ausführen" in notice
