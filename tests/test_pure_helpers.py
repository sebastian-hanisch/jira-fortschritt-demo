"""Reine Hilfen ohne Oberfläche: Zusammenfassung zum Kopieren, Ticketliste und Anleitung zum lokalen Betrieb in der README.
(Getrennt von den App-Tests, damit der Mutationstest diese Datei mitnimmt: er lässt Dateien mit Oberflächen-Tests aus.)"""


import pytest

import jira_constants as C
import jira_evaluation as ev
import jira_tables as T
from conftest import TODAY
from jira_scenario import Issue

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


def test_readme_explains_the_local_run_with_the_repository_address():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert f"git clone {C.REPO_URL}.git" in readme and "--server.address localhost" in readme and "http://localhost:8501" in readme
    assert C.REPO_URL.startswith("https://github.com/") and C.REPO_URL.endswith("/jira-fortschritt-demo")
    assert not (root / "LICENSE").exists() and "Lizenz" not in readme
