"""Teilprojekt als Wurzel der Auswertung und Hierarchiegraph: Zahlen an einem handgebauten Baum, Zyklen, Zusammenfassen tiefer Ebenen, unabhängiges Orakel am Beispielprojekt."""

import math
from fractions import Fraction

import numpy as np
import pytest

import jira_algorithm as A
import jira_constants as C
import jira_evaluation as ev
import jira_tables as T
from jira_scenario import Issue, make_sample
from jira_visualization import build_tree_graph

# Initiative I -> Epic E1 -> Story S1 (2 SP, done), Story S2 (3 SP, in Arbeit) -> Sub-Task S2a (1 SP, done);  I -> Epic E2 -> Story S3 (5 SP, offen);  Story X (4 SP, done) ohne Eltern
TREE = (
    Issue(key="I", type="Initiative", summary="Alles"),
    Issue(key="E1", type="Epic", summary="Eins", parent="I"),
    Issue(key="S1", type="Story", status="Done", category="done", points=2.0, parent="E1"),
    Issue(key="S2", type="Story", status="In Arbeit", category="indeterminate", points=3.0, parent="E1"),
    Issue(key="S2a", type="Sub-task", is_subtask=True, status="Done", category="done", points=1.0, parent="S2"),
    Issue(key="E2", type="Epic", summary="Zwei", parent="I"),
    Issue(key="S3", type="Story", status="To Do", category="new", points=5.0, parent="E2"),
    Issue(key="X", type="Story", status="Done", category="done", points=4.0),
)


def _progress(root="", level=C.LEVEL_STORIES, **kw):
    return ev.analyse(TREE, ev.Settings(root=root, count_level=level, **kw))


# ---------------------------------------------------------------- Teilbaum und Atome

def test_subtree_keys_by_hand():
    assert A.subtree_keys(TREE, "I") == {"I", "E1", "S1", "S2", "S2a", "E2", "S3"}
    assert A.subtree_keys(TREE, "E1") == {"E1", "S1", "S2", "S2a"}
    assert A.subtree_keys(TREE, "S2") == {"S2", "S2a"}
    assert A.subtree_keys(TREE, "X") == {"X"}


def test_select_atoms_with_root():
    keys = lambda level, root: [TREE[i].key for i in A.select_atoms(TREE, level, root)]       # noqa: E731
    assert keys(C.LEVEL_STORIES, "") == ["S1", "S2", "S3", "X"]
    assert keys(C.LEVEL_STORIES, "I") == ["S1", "S2", "S3"]
    assert keys(C.LEVEL_STORIES, "E1") == ["S1", "S2"]
    assert keys(C.LEVEL_STORIES, "S2") == ["S2"]               # die Story ist selbst ein Atom, ihre Sub-Task zählt auf dieser Ebene nicht
    assert keys(C.LEVEL_SUBTASKS, "") == ["S2a"] and keys(C.LEVEL_SUBTASKS, "E1") == ["S2a"] and keys(C.LEVEL_SUBTASKS, "E2") == []


def test_unknown_root_is_rejected_everywhere():
    for call in (lambda: A.subtree_keys(TREE, "Z"), lambda: A.select_atoms(TREE, C.LEVEL_STORIES, "Z"), lambda: A.tree_order(TREE, "Z"), lambda: _progress("Z")):
        with pytest.raises(ValueError):
            call()


def test_a_cycle_in_the_parent_links_ends_and_counts_once():
    loop = (Issue(key="A", parent="B", points=1.0), Issue(key="B", parent="A", points=2.0), Issue(key="C", parent="B", points=4.0))
    assert A.subtree_keys(loop, "A") == {"A", "B", "C"}
    assert [loop[i].key for i in A.select_atoms(loop, C.LEVEL_STORIES, "B")] == ["A", "B", "C"]
    assert sorted(i for i, _, _ in A.tree_order(loop)) == [0, 1, 2]                      # jedes Ticket genau einmal
    g = A.tree_graph(loop, A.select_atoms(loop, C.LEVEL_STORIES), np.array([1.0, 2.0, 4.0]), np.array([0.0, 0.5, 1.0]), {"To Do": 0.0})
    assert g.n_total == 4 and len(g.keys) == 4


# ---------------------------------------------------------------- Zahlen der Auswertung (Linear: offen 0, in Arbeit 50 %, Done 100 %)

@pytest.mark.parametrize("root,weight,credited", [("", 14.0, 7.5), ("I", 10.0, 3.5), ("E1", 5.0, 3.5), ("E2", 5.0, 0.0), ("S2", 3.0, 1.5), ("X", 4.0, 4.0)])
def test_scoped_progress_by_hand(root, weight, credited):
    a = _progress(root)
    assert a.weight == weight and a.progress == pytest.approx(credited / weight) and ev.check_consistency(a) == []


def test_scope_also_limits_done_measures_unestimated_and_median():
    a = _progress("E1", unest_rule=C.UNEST_ONE)
    assert a.progress_done == pytest.approx(2 / 5) and a.progress_count == pytest.approx(1 / 2) and a.n_atoms == 2 and a.n_unestimated == 0
    items = TREE[:2] + (Issue(key="U", points=None, parent="E1"), Issue(key="V", points=10.0, parent="E1"), Issue(key="W", points=1.0))
    median_scoped = ev.analyse(items, ev.Settings(root="E1", unest_rule=C.UNEST_MEDIAN))
    assert median_scoped.n_atoms == 2 and median_scoped.weight == 10.0 + 10.0                # Median der geschätzten Tickets im Teilbaum (nur V): 10, nicht der des Projekts


def test_scope_without_atoms_gives_no_progress_and_no_crash():
    a = _progress("E2", level=C.LEVEL_SUBTASKS)
    assert a.n_atoms == 0 and math.isnan(a.progress) and ev.check_consistency(a) == []
    assert a.tree.keys == ("E2", "S3") and a.tree.weight.tolist() == [0.0, 0.0] and math.isnan(a.tree.progress[0])       # S3 ist ein Blatt mit Status: Gutschrift 0 %
    assert a.tree.progress[1] == 0.0


def test_sensitivity_and_dimensions_follow_the_root():
    rows = ev.sensitivity(TREE, ev.Settings(root="E1"))
    linear = [r for r in rows if r["scheme"] == C.SCHEME_LINEAR and r["mode"] == C.WEIGHT_POINTS]
    assert len(rows) == 6 and len(linear) == 1 and linear[0]["progress"] == pytest.approx(0.7)
    for row in rows:
        again = ev.analyse(TREE, ev.Settings(root="E1", scheme=row["scheme"], weight_mode=row["mode"]))
        assert row["progress"] == pytest.approx(again.progress)
    a = _progress("I", dimension=C.DIM_EPIC)
    assert dict(zip(a.stats.labels, a.stats.weight.tolist())) == {"E1: Eins": 5.0, "E2: Zwei": 5.0}        # X und seine Gruppe „(ohne Epic)“ fehlen


def test_tables_and_summary_follow_the_root_and_name_it():
    a = _progress("E1")
    rows = T.contribution(a)
    assert rows[-1]["Gruppe"] == "Summe" and rows[-1]["Gewicht"] == 5.0 and [r["Gruppe"] for r in rows[:-1]] == ["E1: Eins"]
    text = T.summary_markdown(TREE, a, "SP", C.SAMPLE_TODAY)
    assert "Teilprojekt: E1: Eins und alles darunter" in text and "Gewicht 5,0 SP" in text and "70,0 %" in text
    assert "Teilprojekt" not in T.summary_markdown(TREE, _progress(""), "SP", C.SAMPLE_TODAY)


# ---------------------------------------------------------------- Wurzelwahl

def test_root_choices_are_the_parents_in_tree_order_with_depth():
    assert A.root_choices(TREE) == [("I", 0), ("E1", 1), ("S2", 2), ("E2", 1)]


def test_tree_order_is_depth_first_with_parent_links():
    order = [(TREE[i].key, d, TREE[p].key if p >= 0 else "") for i, d, p in A.tree_order(TREE)]
    assert order == [("I", 0, ""), ("E1", 1, "I"), ("S1", 2, "E1"), ("S2", 2, "E1"), ("S2a", 3, "S2"), ("E2", 1, "I"), ("S3", 2, "E2"), ("X", 0, "")]
    assert [(TREE[i].key, d) for i, d, _ in A.tree_order(TREE, "E1")] == [("E1", 0), ("S1", 1), ("S2", 1), ("S2a", 2)]


def test_children_listed_before_their_parent_still_hang_below_it():
    items = (Issue(key="S", parent="E", points=1.0), Issue(key="E", type="Epic"))
    assert A.tree_order(items) == [(1, 0, -1), (0, 1, 1)]


def test_a_leaf_without_weight_shows_its_status_credit_even_as_the_first_ticket():
    items = (Issue(key="U", status="In Arbeit", category="indeterminate", points=None), Issue(key="V", points=2.0))
    g = ev.analyse(items, ev.Settings(unest_rule=C.UNEST_IGNORE)).tree
    assert dict(zip(g.keys, g.progress.tolist()))["U"] == 0.5 and dict(zip(g.keys, g.weight.tolist()))["U"] == 0.0


# ---------------------------------------------------------------- Graph von Hand

def test_tree_graph_layout_and_aggregates_by_hand():
    g = _progress().tree
    assert g.keys == ("Projekt", "I", "E1", "S1", "S2", "S2a", "E2", "S3", "X")
    assert g.x.tolist() == [0, 1, 2, 3, 3, 4, 2, 3, 1]
    assert g.parent.tolist() == [-1, 0, 1, 2, 2, 4, 1, 6, 0]
    assert g.y.tolist() == [2.125, 1.25, 0.5, 0.0, 1.0, 1.0, 2.0, 2.0, 3.0]            # Blätter S1, S2a, S3, X in den Zeilen 0..3; Eltern mittig vor ihren Kindern
    assert g.weight.tolist() == [14.0, 10.0, 5.0, 2.0, 3.0, 0.0, 5.0, 5.0, 4.0]
    want = [7.5 / 14, 0.35, 0.7, 1.0, 0.5, 1.0, 0.0, 0.0, 1.0]                          # S2a zählt nicht (Zählebene), zeigt aber die Gutschrift seines Status
    assert g.progress.tolist() == pytest.approx(want)
    assert g.is_atom.tolist() == [False, False, False, True, True, False, False, True, True]
    assert g.is_leaf.tolist() == [False, False, False, True, False, True, False, True, True]
    assert g.hidden.tolist() == [0] * 9 and g.n_total == 9 and g.shown_depth == 4


def test_tree_graph_for_a_root_has_no_virtual_project_node():
    g = _progress("E1").tree
    assert g.keys == ("E1", "S1", "S2", "S2a") and g.parent.tolist() == [-1, 0, 0, 2] and g.x.tolist() == [0, 1, 1, 2]
    assert g.weight[0] == 5.0 and g.progress[0] == pytest.approx(0.7)


def test_tree_graph_at_sub_task_level_aggregates_over_sub_tasks():
    g = _progress(level=C.LEVEL_SUBTASKS).tree
    by_key = dict(zip(g.keys, zip(g.weight.tolist(), g.progress.tolist())))
    assert by_key["S2a"] == (1.0, 1.0) and by_key["S2"] == (1.0, 1.0) and by_key["E1"] == (1.0, 1.0) and by_key["Projekt"] == (1.0, 1.0)
    assert by_key["E2"][0] == 0.0 and math.isnan(by_key["E2"][1])                      # kein Gewicht darunter, nichts messbar
    assert math.isnan(by_key["S1"][1]) is False and by_key["S1"][0] == 0.0             # Blatt ohne Gewicht: Gutschrift des eigenen Status


def test_tree_graph_collapses_the_deepest_levels_when_too_big():
    a = _progress()
    g = A.tree_graph(TREE, a.atoms, a.w, a.c, a.credits, "", max_nodes=5)
    assert g.keys == ("Projekt", "I", "E1", "E2", "X") and g.shown_depth == 2 and g.n_total == 9
    assert g.hidden.tolist() == [0, 0, 3, 1, 0]                                        # E1: S1, S2, S2a; E2: S3
    assert g.y.tolist() == [1.25, 0.5, 0.0, 1.0, 2.0] and g.weight.tolist() == [14.0, 10.0, 5.0, 5.0, 4.0]
    assert g.progress.tolist() == pytest.approx([7.5 / 14, 0.35, 0.7, 0.0, 1.0])       # zusammengefasste Knoten tragen weiter ihre Summe
    tiny = A.tree_graph(TREE, a.atoms, a.w, a.c, a.credits, "", max_nodes=0)
    assert tiny.keys == ("Projekt",) and tiny.hidden.tolist() == [8]


def test_every_sample_node_appears_exactly_once_and_the_root_carries_the_total():
    sample = make_sample(6, 8)
    a = ev.analyse(sample, ev.Settings(count_level=C.LEVEL_SUBTASKS))
    g = a.tree
    assert sorted(g.keys[1:]) == sorted(t.key for t in sample) and g.weight[0] == pytest.approx(a.weight)
    assert g.progress[0] == pytest.approx(a.progress)


# ---------------------------------------------------------------- Zeichnung

def test_figure_has_one_marker_per_node_and_one_edge_per_link():
    g = _progress().tree
    fig = build_tree_graph(g, "SP")
    edges, *marks = fig.data
    assert sum(1 for v in edges.x if v is None) == len(g.keys) - 1
    assert sum(len(m.x) for m in marks) == len(g.keys)
    known = marks[0]
    assert list(known.marker.color) == pytest.approx([p for p in g.progress if not np.isnan(p)])
    assert all("Gewicht" in h for h in known.hovertext) and any("Eins" in h for h in known.hovertext)


def test_unmeasurable_nodes_are_drawn_grey_in_their_own_trace_and_labels_thin_out():
    sub = _progress(level=C.LEVEL_SUBTASKS).tree
    fig = build_tree_graph(sub, "T")
    assert len(fig.data) == 3 and fig.data[2].marker.color == "rgba(190,190,190,0.9)" and "E2" in fig.data[2].text
    big = ev.analyse(make_sample(12, 3), ev.Settings()).tree
    assert len(big.keys) > C.GRAPH_LABEL_MAX
    fig = build_tree_graph(big, "T")
    labelled = [t for tr in fig.data[1:] for t in tr.text if t]
    assert 0 < len(labelled) < len(big.keys)                                          # nur Knoten mit Kindern tragen eine Beschriftung


def test_figure_height_follows_the_number_of_leaves_and_is_capped():
    small = build_tree_graph(_progress().tree, "SP")
    assert small.layout.height == 300                                                    # 4 Blätter: 17 * 4 + 60 liegt unter der Mindesthöhe
    mid = A.TreeGraph(("a",) * 40, ("",) * 40, ("",) * 40, ("",) * 40, np.zeros(40), np.arange(40.0), np.full(40, -1), np.ones(40), np.full(40, 0.5),
                      np.ones(40, bool), np.ones(40, bool), np.zeros(40, int), 40, 0)
    assert build_tree_graph(mid, "SP").layout.height == 17 * 40 + 60
    wide = A.TreeGraph(("a",) * 400, ("",) * 400, ("",) * 400, ("",) * 400, np.zeros(400), np.arange(400.0), np.full(400, -1), np.ones(400), np.full(400, 0.5),
                       np.ones(400, bool), np.ones(400, bool), np.zeros(400, int), 400, 0)
    assert build_tree_graph(wide, "SP").layout.height == 2400


# ---------------------------------------------------------------- unabhängiges Orakel am Beispielprojekt

def _oracle_scope(issues, root, subtask_level):
    """Atome unter `root` durch Hochlaufen der Elternkette je Ticket, ohne den Teilbaum-Code des Kerns."""
    by_key = {t.key: t for t in issues}
    found = []
    for t in issues:
        if t.is_subtask != subtask_level or (not subtask_level and t.is_epic):
            continue
        cur, hops, inside = t, 0, False
        while cur is not None and hops < 50:
            if cur.key == root:
                inside = True
                break
            cur, hops = by_key.get(cur.parent), hops + 1
        if inside:
            found.append(t)
    return found


@pytest.mark.parametrize("n,seed", [(3, 1), (6, 8), (9, 4)])
def test_scoped_progress_matches_an_independent_walk_for_every_root_of_the_sample(n, seed):
    sample = make_sample(n, seed)
    for level, subtask_level in ((C.LEVEL_STORIES, False), (C.LEVEL_SUBTASKS, True)):
        full = ev.analyse(sample, ev.Settings(count_level=level, unest_rule=C.UNEST_ONE))
        for key, _ in A.root_choices(sample):
            atoms = _oracle_scope(sample, key, subtask_level)
            a = ev.analyse(sample, ev.Settings(count_level=level, unest_rule=C.UNEST_ONE, root=key))
            assert sorted(sample[i].key for i in a.atoms) == sorted(t.key for t in atoms) and a.weight <= full.weight + 1e-9
            weight = sum(Fraction(str(t.points if t.points is not None else 1)) for t in atoms)
            credit = sum(Fraction(str(t.points if t.points is not None else 1)) * Fraction(a.credits[t.status]).limit_denominator(1000) for t in atoms)
            if weight:
                assert a.progress == pytest.approx(float(credit / weight), abs=1e-9)


def test_labels_of_nodes_with_children_sit_above_and_leaf_labels_to_the_right():
    g = _progress().tree
    fig = build_tree_graph(g, "SP")
    known = fig.data[1]
    by_label = dict(zip(known.text, known.textposition))
    assert by_label["E1"] == "top center" and by_label["Projekt"] == "top center" and by_label["S1"] == "middle right" and by_label["X"] == "middle right"
