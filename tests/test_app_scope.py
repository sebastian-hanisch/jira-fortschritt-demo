"""Teilprojekt-Auswahl und Hierarchiegraph in der Oberfläche."""

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev
from jira_scenario import make_sample
from test_app import TIMEOUT, _fresh_app, _ok


def test_the_sample_offers_every_parent_as_a_root_and_draws_the_graph():
    at = _fresh_app()
    _ok(at)
    box = at.selectbox(key="root")
    sample = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    assert box.value == C.ROOT_ALL and len(box.options) == 1 + len(A.root_choices(sample)) and box.options[0] == "(ganzes Projekt)"
    assert box.options[1].startswith("DEMO-1: ") and any(o.startswith("↳ ") for o in box.options[1:])       # Epics ohne Einrückung, Stories mit Sub-Tasks eingerückt
    assert any(h.value == "### 🌳 Hierarchiegraph" for h in at.markdown)


def test_choosing_a_root_scopes_the_headline_numbers_and_says_so():
    sample = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    key = A.root_choices(sample)[0][0]
    at = _fresh_app()
    at.selectbox(key="root").set_value(key).run(timeout=TIMEOUT)
    _ok(at)
    want = ev.analyse(sample, ev.Settings(root=key))
    assert at.metric[0].value == ev.pct(want.progress) and want.n_atoms < ev.analyse(sample, ev.Settings()).n_atoms
    assert any("beschränkt" in i.value and key in i.value for i in at.info)
    assert at.metric[3].label.startswith(f"Offenes Gewicht (SP, gesamt {ev.de(want.weight)})")


def test_every_root_of_the_sample_renders_without_error_in_both_count_levels():
    sample = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    for level in C.COUNT_LEVELS:
        at = _fresh_app()
        at.selectbox(key="count_level").set_value(level).run(timeout=TIMEOUT)
        for key, _ in A.root_choices(sample):
            at.selectbox(key="root").set_value(key).run(timeout=TIMEOUT)
            _ok(at, level, key)


def test_new_data_resets_a_root_that_no_longer_exists():
    gone = [k for k, _ in A.root_choices(make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)) if k not in dict(A.root_choices(make_sample(C.DEFAULT_N_EPICS, 5)))]
    assert gone, "die Beispielprojekte müssen sich in den Eltern unterscheiden"
    at = _fresh_app()
    at.selectbox(key="root").set_value(gone[0]).run(timeout=TIMEOUT)
    assert at.selectbox(key="root").value == gone[0]
    at.number_input(key="seed_input").set_value(5).run(timeout=TIMEOUT)
    _ok(at)
    assert at.selectbox(key="root").value == C.ROOT_ALL and not any("beschränkt" in i.value for i in at.info)


def test_period_widgets_restrict_the_headline_numbers_and_reset_with_new_data():
    import jira_evaluation as ev

    sample = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    order = A.sprint_order(sample)
    at = _fresh_app()
    assert at.toggle(key="sprint_none").disabled and not at.selectbox(key="sprint_from").disabled
    assert at.selectbox(key="sprint_from").options[0] == "(offen)" and list(at.selectbox(key="sprint_from").options[1:]) == order
    at.selectbox(key="sprint_from").set_value(order[1])
    at.selectbox(key="sprint_to").set_value(order[3]).run(timeout=TIMEOUT)
    _ok(at)
    want = ev.analyse(sample, ev.Settings(sprint_from=order[1], sprint_to=order[3]))
    assert at.metric[0].value == ev.pct(want.progress) and not at.toggle(key="sprint_none").disabled
    assert any(f"Zeitraum **{order[1]} bis {order[3]}**" in i.value and f"{want.n_outside} außerhalb" in i.value for i in at.info)
    at.toggle(key="sprint_none").set_value(True).run(timeout=TIMEOUT)
    _ok(at)
    assert any("einschließlich der Tickets ohne Sprint" in i.value for i in at.info)
    at.toggle(key="sprint_none").set_value(False)
    at.selectbox(key="sprint_from").set_value(order[3])
    at.selectbox(key="sprint_to").set_value(order[1]).run(timeout=TIMEOUT)          # Anfang hinter Ende, ohne Tickets ohne Sprint: nichts übrig
    _ok(at)
    assert any("liegt kein zählendes Ticket" in w.value for w in at.warning)
    at.number_input(key="seed_input").set_value(5).run(timeout=TIMEOUT)
    assert at.selectbox(key="sprint_from").value in ("", order[3]) and not at.exception


def test_hierarchy_level_selector_appears_only_for_that_dimension_and_every_level_renders():
    sample = make_sample(C.DEFAULT_N_EPICS, C.DEFAULT_SEED)
    at = _fresh_app()
    assert not [s for s in at.selectbox if s.key == "level"]
    at.selectbox(key="dimension").set_value(C.DIM_LEVEL).run(timeout=TIMEOUT)
    _ok(at)
    box = at.selectbox(key="level")
    assert len(box.options) == A.max_level(sample) and box.options[0] == "Stufe 1 (oberste)"
    for n in range(1, A.max_level(sample) + 1):
        at.selectbox(key="level").set_value(n).run(timeout=TIMEOUT)
        _ok(at, n)
    at.selectbox(key="dimension").set_value(C.DIM_EPIC)
    at.selectbox(key="dimension2").set_value(C.DIM_LEVEL).run(timeout=TIMEOUT)
    _ok(at)
    assert [s for s in at.selectbox if s.key == "level"]


def test_every_table_offers_wiki_markup_and_a_copyable_table():
    at = _fresh_app()
    _ok(at)
    assert [e.label for e in at.expander].count("📋 In Jira oder Confluence einfügen") >= 6                       # eine Tabelle je Tab
    wiki = [c.value for c in at.code if c.value.startswith("||")]
    assert len(wiki) >= 6 and all(w.split("\n")[0].endswith("||") and w.split("\n")[1].startswith("|") for w in wiki)
    html_blocks = [str(h.value) for h in at.get("html") if "<table" in str(h.value)]
    assert len(html_blocks) >= 6 and all("<thead>" in h for h in html_blocks)
