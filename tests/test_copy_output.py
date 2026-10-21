"""Ausgaben zum Einfügen in Jira und Confluence (Wiki-Markup, HTML-Tabelle): von Hand gerechnete Beispiele."""

import pytest

import jira_tables as T


@pytest.mark.parametrize("value,fmt,expected", [
    (None, None, ""), (float("nan"), "percent", ""), (True, None, "ja"), (False, None, "nein"), (3, None, "3"), (3.0, None, "3"), (3.25, None, "3,2"), (3.26, None, "3,3"),
    (0.5, "percent", "50,0 %"), (12.345, "%.1f", "12,3"), (12.5, "%.0f", "12"), (0.125, "%.2f", "0,12"), ("Text", None, "Text"), (1, "%.1f", "1,0"),
])
def test_format_cell_by_hand(value, fmt, expected):
    assert T.format_cell(value, fmt) == expected


ROWS = [
    {"Parent Ticket": "E-1: Eins | A", "Total": 45.0, "Anteil": 0.5, "Notiz": None},
    {"Parent Ticket": "E-2", "Total": 10.0, "Anteil": None, "Notiz": "⚠ weicht ab"},
    {"Parent Ticket": "Summe", "Total": 55.0, "Anteil": 0.4, "Notiz": ""},
]
FORMATS = {"Total": "%.1f", "Anteil": "percent"}


def test_wiki_markup_by_hand():
    assert T.rows_to_wiki(ROWS, FORMATS).split("\n") == [
        "||Parent Ticket||Total||Anteil||Notiz||",
        "|E-1: Eins \\| A|45,0|50,0 %| |",
        "|E-2|10,0| |⚠ weicht ab|",
        "|*Summe*|*55,0*|*40,0 %*| |",
    ]


def test_wiki_markup_protects_special_characters_and_handles_nothing():
    assert T.rows_to_wiki([{"A": "a*b_c{d}[e]\\f"}]).split("\n")[1] == "|a\\*b\\_c\\{d\\}\\[e\\]\\\\f|"
    assert T.rows_to_wiki([]) == "" and T.rows_to_html([]) == ""


def test_html_table_by_hand():
    out = T.rows_to_html(ROWS, FORMATS)
    assert out.startswith('<table style="border-collapse:collapse;"><thead><tr>') and out.endswith("</tbody></table>")
    assert out.count("<tr>") == 4 and out.count("<th ") == 4 and out.count("<td ") == 12
    assert "E-1: Eins | A" in out and ">45,0<" in out and ">50,0 %<" in out and "<strong>Summe</strong>" in out and "<strong>55,0</strong>" in out
    assert out.count("text-align:right") == 2 + 6 and out.count("text-align:left") == 2 + 6       # Total und Anteil rechts (Kopf + drei Zeilen je Spalte), Parent und Notiz links


def test_html_escapes_text():
    out = T.rows_to_html([{"A": "<b>&"}])
    assert "&lt;b&gt;&amp;" in out and "<b>" not in out
