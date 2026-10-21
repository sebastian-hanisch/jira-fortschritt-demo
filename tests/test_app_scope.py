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
