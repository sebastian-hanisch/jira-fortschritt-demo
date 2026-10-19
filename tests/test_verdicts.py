"""Verdikte an von Hand gesetzten Werten (DEMO-PLAYBOOK §12): jede Zahl im Text und jede Schwelle der Art steht hier."""

import numpy as np

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev

NAN = float("nan")


def test_de_and_pct_use_a_decimal_comma_and_a_sign_on_request():
    assert ev.de(12.345) == "12,3" and ev.de(12.345, 2) == "12,35" and ev.pct(0.4429) == "44,3 %"
    assert ev.de(6.6, sign=True) == "+6,6" and ev.de(-6.6, sign=True) == "-6,6" and ev.de(0.0, sign=True) == "+0,0"


def test_measures_threshold_is_five_points_exclusive():
    kind, text = ev.verdict_measures(0.50, 0.46, 0.48)               # Spanne genau 4 Punkte
    assert kind == "success" and "4,0 Prozentpunkte" in text
    kind, text = ev.verdict_measures(0.50, 0.45, 0.48)               # genau 5 Punkte: nicht mehr „kaum“
    assert kind == "warning" and "5,0 Prozentpunkte" in text and "keine Formsache" in text


def test_measures_names_all_three_values():
    _, text = ev.verdict_measures(0.443, 0.377, 0.40)
    assert "Nach Status gewichtet 44,3 %" in text and "nur Done nach Story Points 37,7 %" in text and "nur Done nach Ticketzahl 40,0 %" in text
    assert "6,6 Prozentpunkte" in text


def test_measures_without_weight_is_a_warning():
    assert ev.verdict_measures(NAN, NAN, 0.5)[0] == "warning"


def test_unestimated_branches():
    assert ev.verdict_unestimated(0, 0, C.UNEST_MEDIAN, C.WEIGHT_POINTS)[0] == "warning"                 # keine Tickets
    assert ev.verdict_unestimated(3, 10, C.UNEST_MEDIAN, C.WEIGHT_COUNT) == ("info", "Gewichtung nach Ticketanzahl: Story Points spielen keine Rolle, 3 von 10 Tickets haben keine.")
    assert ev.verdict_unestimated(0, 10, C.UNEST_MEDIAN, C.WEIGHT_POINTS) == ("success", "Alle 10 Tickets sind geschätzt.")
    kind, text = ev.verdict_unestimated(1, 10, C.UNEST_MEDIAN, C.WEIGHT_POINTS)
    assert kind == "info" and "1 von 10 Tickets (10,0 %)" in text and "Regel: Median der geschätzten Tickets" in text and "tauchen" not in text


def test_unestimated_threshold_is_twenty_percent_inclusive_and_ignore_adds_a_warning_sentence():
    assert ev.verdict_unestimated(2, 10, C.UNEST_ONE, C.WEIGHT_POINTS)[0] == "warning"          # genau 20 %
    assert ev.verdict_unestimated(19, 100, C.UNEST_ONE, C.WEIGHT_POINTS)[0] == "info"
    _, text = ev.verdict_unestimated(2, 10, C.UNEST_IGNORE, C.WEIGHT_POINTS)
    assert "tauchen im Fortschritt nicht auf" in text


def test_sensitivity_names_the_extremes_and_the_threshold():
    rows = [{"scheme": "A", "mode": "Story Points", "progress": 0.40}, {"scheme": "B", "mode": "Ticketanzahl", "progress": 0.49}, {"scheme": "C", "mode": "Story Points", "progress": 0.45}]
    kind, text = ev.verdict_sensitivity(rows)
    assert kind == "info" and "zwischen 40,0 % (A, Story Points) und 49,0 % (B, Ticketanzahl)" in text and "9,0 Prozentpunkte Spanne" in text
    rows[1]["progress"] = 0.50                                                                  # genau 10 Punkte
    assert ev.verdict_sensitivity(rows)[0] == "warning"
    assert ev.verdict_sensitivity([{"scheme": "A", "mode": "m", "progress": NAN}])[0] == "warning"


def _stats(labels, weight, progress):
    w = np.array(weight, dtype=float)
    return A.GroupStats(tuple(labels), w, w * np.array(progress), w * 0, w * 0 + 1, w * 0, w * 0)


def test_groups_verdict_names_lowest_and_highest_with_weight():
    kind, text = ev.verdict_groups(_stats(["X", "Y", "Z"], [10, 4, 6], [0.5, 0.25, 0.75]), C.DIM_EPIC)
    assert kind == "info" and "am weitesten zurück „Y“ mit 25,0 % (Gewicht 4,0)" in text and "am weitesten vorn „Z“ mit 75,0 % (Gewicht 6,0)" in text and "Ebene Epic" in text


def test_groups_verdict_skips_groups_without_weight_and_handles_few_groups():
    s = _stats(["X", "Y", "Z"], [10, 0, 6], [0.5, 0.0, 0.75])
    _, text = ev.verdict_groups(s, C.DIM_SPRINT)
    assert "„X“" in text and "„Z“" in text and "„Y“" not in text
    assert "weniger als zwei Gruppen" in ev.verdict_groups(_stats(["X"], [3], [0.5]), C.DIM_SPRINT)[1]
    assert "nur eine Gruppe" in ev.verdict_groups(_stats(["Gesamt"], [3], [0.5]), C.DIM_ALL)[1]


def test_groups_verdict_breaks_ties_by_label():
    _, text = ev.verdict_groups(_stats(["B", "A", "C"], [1, 1, 1], [0.5, 0.5, 0.5]), C.DIM_EPIC)
    assert "zurück „A“" in text and "vorn „C“" in text


def test_consistency_checker_flags_each_kind_of_violation():
    import dataclasses
    import jira_evaluation as ev_
    from conftest import make_mini
    a = ev_.analyse(make_mini(), ev_.Settings(dimension=C.DIM_COMPONENT, dimension2=C.DIM_LABEL))
    assert ev_.check_consistency(a) == []
    broken = dataclasses.replace(a, progress=1.2, weight=a.weight + 1)
    msgs = ev_.check_consistency(broken)
    assert any("außerhalb von 0 bis 100 %" in m for m in msgs) and any("Gruppengewichte" in m for m in msgs)
    bad_stats = dataclasses.replace(a.stats, count=a.stats.count + 1)
    assert any("zählen" in m for m in ev_.check_consistency(dataclasses.replace(a, stats=bad_stats)))


def test_status_list_orders_by_category_then_name_and_takes_the_most_frequent_category():
    from jira_scenario import Issue
    issues = (Issue(key="1", status="b-doing", category="indeterminate"), Issue(key="2", status="Done", category="done"), Issue(key="3", status="a-open", category="new"),
              Issue(key="4", status="Gemischt", category="new"), Issue(key="5", status="Gemischt", category="done"), Issue(key="6", status="Gemischt", category="done"),
              Issue(key="7", status="A-doing", category="indeterminate"))
    assert ev.status_list(issues) == [("a-open", "new"), ("A-doing", "indeterminate"), ("b-doing", "indeterminate"), ("Done", "done"), ("Gemischt", "done")]


def test_consistency_checker_flags_contributions_that_do_not_add_up():
    import dataclasses
    from conftest import make_mini
    a = ev.analyse(make_mini(), ev.Settings())
    assert ev.check_consistency(a) == []
    msgs = ev.check_consistency(dataclasses.replace(a, progress=a.progress - 0.01))
    assert any("Beiträge der Gruppen" in m for m in msgs)


def test_consistency_contribution_check_also_covers_total_weights_below_one():
    import dataclasses
    from jira_scenario import Issue
    issues = (Issue(key="A", type="Story", status="Done", category="done", points=0.5), Issue(key="B", type="Story", status="To Do", category="new", points=0.25))
    a = ev.analyse(issues, ev.Settings())
    assert ev.check_consistency(a) == []
    assert any("Beiträge der Gruppen" in m for m in ev.check_consistency(dataclasses.replace(a, progress=0.5)))
