"""Jira-Fortschritt: gewichtet über Status, Story Points und Ebenen - interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Lauffähig mit: streamlit run app.py
"""

import streamlit as st

import jira_algorithm as A
import jira_constants as C
import jira_tables as T
from jira_evaluation import (
    Settings,
    analyse,
    check_consistency,
    de,
    pct,
    sensitivity,
    status_list,
    verdict_groups,
    verdict_measures,
    verdict_sensitivity,
    verdict_unestimated,
)
from jira_layout import dunkles_design, kopf_css
from jira_presets import (
    SETTING_SPECS,
    bounds,
    init_session_state_defaults,
    load_permalink_settings,
    randomize_seed,
    sidebar_presets,
    sync_query_params,
)
from jira_scenario import make_sample
from jira_tables import rows_to_csv
from jira_visualization import build_burnup, build_heatmap, build_progress_bars, build_sensitivity, build_tree_graph, build_treemap

st.set_page_config(page_title="Jira-Fortschritt – Sebastian Hanisch", layout="wide")

@st.cache_data(show_spinner=False)
def _sample(n_epics, seed):
    return make_sample(n_epics, seed)


def _on_credit_edit(version, base):
    """Tabelle der Status-Gewichte wurde bearbeitet: Änderungen übernehmen und auf „Eigene Gewichte“ umschalten."""
    edited = st.session_state[f"credit_editor_{version}"].get("edited_rows", {})
    st.session_state["custom_credits"] = A.apply_credit_edits(base, edited)
    st.session_state["scheme"] = C.SCHEME_CUSTOM
    st.session_state["editor_version"] = version + 1


# Fester Kopf: nur der Titel bleibt beim Scrollen oben (Stylesheet in jira_layout.py).
st.html(kopf_css(dunkles_design()))
with st.container(key="kopf"):
    st.title("📊 Jira-Fortschritt: gewichtet über Status, Story Points und Ebenen")
st.markdown(
    """
Wie weit ist ein Projekt? Die Zahl hängt davon ab, **was zählt**: Ein Ticket in Review ist mehr als offen und weniger als erledigt, eine Story mit 13 **Story Points**
wiegt mehr als eine mit 1, und ein Bericht über das ganze Projekt sieht anders aus als einer je **Epic**, Sprint oder Komponente. Diese Demo rechnet an einem
erzeugten **Beispielprojekt** den Fortschritt mit frei wählbaren **Status-Gewichten** und zeigt ihn über mehrere **Aggregationsebenen**, auch als **Tabellen** (z. B. nach Status aufgesplittet).

Unten: die **Kernfrage** (wie stark hängt die Zahl von den Annahmen ab?) und die Expander **🔧 Das Beispielprojekt**, **📐 Mathematische Formulierung** und
**🚧 Wo die Annahmen enden**.
"""
)
st.caption("🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, um ein Szenario zu teilen.")
load_permalink_settings()
init_session_state_defaults()
st.session_state.setdefault("editor_version", 0)

with st.sidebar:
    sidebar_presets()  # Schnellstart oben, das aktive Preset ist hervorgehoben
    st.header("📥 Beispielprojekt")
    n_epics = st.slider("Epics im Beispielprojekt", *bounds("n_epics"), key="n_epics", help="Wie groß das erzeugte Projekt ist.")
    seed = st.number_input("Zufalls-Seed der Beispieldaten", *bounds("seed_input"), key="seed_input", step=1)
    st.header("⚖️ Gewichte")
    scheme = st.selectbox(
        "Gewicht je Status", C.SCHEMES, key="scheme",
        help="Wie viel eines Tickets als getan gilt, je nach Status. „Eigene Gewichte“ entsteht, sobald Sie die Tabelle unten ändern.")
    weight_mode = st.radio("Gewicht eines Tickets", C.WEIGHT_MODES, key="weight_mode", help="Story Points oder jedes Ticket gleich schwer.")
    unest_rule = st.selectbox(
        "Ungeschätzte Tickets", C.UNEST_RULES, key="unest_rule", disabled=weight_mode == C.WEIGHT_COUNT,
        help="Was ein Ticket ohne Story Points wiegt. Bei der Gewichtung nach Ticketanzahl ohne Wirkung.")
    st.header("🧱 Zählebene")
    count_level = st.selectbox("Was ist ein Ticket?", C.COUNT_LEVELS, key="count_level", help="Epics zählen nie selbst; sie fassen ihre Tickets zusammen.")
    blend = st.toggle(
        "Fortschritt der Story aus ihren Sub-Tasks", key="blend", disabled=count_level == C.LEVEL_SUBTASKS,
        help="Eine Story in Arbeit zählt mindestens so viel wie ihre Sub-Tasks zeigen. Auf der Ebene Sub-Tasks ohne Wirkung.")
    st.button("🎲 Neues Beispielprojekt", width="stretch", on_click=randomize_seed)

sync_query_params({key: st.session_state[key] for key in SETTING_SPECS})

# --- Daten ---------------------------------------------------------------------------------------------------------------------------------

issues = _sample(int(n_epics), int(seed))
st.markdown("## 📥 Daten")
st.caption(f"Erzeugtes Beispielprojekt (Stichtag {C.SAMPLE_TODAY.strftime('%d.%m.%Y')}, Sprint {C.SAMPLE_CURRENT_SPRINT} läuft): {len(issues)} Tickets. "
           "Keine echten Daten: Das Projekt entsteht aus der Epic-Zahl und dem Zufalls-Seed links.")
with st.expander("🎫 Die Tickets des Beispielprojekts ansehen"):
    st.caption("Alle Tickets mit den Feldern, die in die Rechnung eingehen. Tickets ohne Story Points sind ungeschätzt; ein Ticket ohne Lösungsdatum ist nicht erledigt.")
    ticket_rows = T.ticket_rows(issues)
    st.dataframe(ticket_rows, hide_index=True, width="stretch", key="df_tickets")
    st.download_button("⬇️ Als CSV", rows_to_csv(ticket_rows), file_name="beispielprojekt-tickets.csv", mime="text/csv", key="csv_tickets")

# --- Status-Gewichte -----------------------------------------------------------------------------------------------------------------------

statuses = status_list(issues)
custom = tuple(st.session_state.get("custom_credits", ()))
credits_now = A.status_credits(statuses, scheme, custom)
with st.expander("⚖️ Gewichte je Status – Tabelle ansehen und ändern", expanded=False):
    st.caption(
        "Anteil der Arbeit, der bei diesem Status als getan gilt. Eine Änderung schaltet auf „Eigene Gewichte“. "
        "Die Kategorie entspricht der Statuskategorie in Jira und bestimmt, was als „erledigt“ zählt.")
    version = st.session_state["editor_version"]
    base = tuple((s, credits_now[s]) for s, _ in statuses)
    st.data_editor(
        [{"Status": s, "Kategorie": C.CATEGORY_LABEL[cat], "Gewicht (%)": round(100 * credits_now[s], 1)} for s, cat in statuses],
        disabled=["Status", "Kategorie"], hide_index=True, key=f"credit_editor_{version}", on_change=_on_credit_edit, args=(version, base),
        column_config={"Gewicht (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=5, format="%.0f")})

# --- Ergebnis ------------------------------------------------------------------------------------------------------------------------------

unit = C.SAMPLE_UNIT if weight_mode == C.WEIGHT_POINTS else "Tickets"
st.markdown("## 🎯 Ergebnis")
metrics_box = st.container()
root_choices = A.root_choices(issues)
root_depth = dict(root_choices)
by_key = {t.key: t for t in issues}
root_options = (C.ROOT_ALL, *root_depth)
if st.session_state.get("root", C.ROOT_ALL) not in root_options:        # die Daten haben gewechselt: die alte Wurzel gibt es nicht mehr
    st.session_state["root"] = C.ROOT_ALL


def root_label(key):
    if key == C.ROOT_ALL:
        return "(ganzes Projekt)"
    title = by_key[key].summary
    return "↳ " * root_depth[key] + key + (f": {title}" if title else "")


root = st.selectbox(
    "Teilprojekt (Wurzel der Auswertung)", root_options, key="root", format_func=root_label, disabled=not root_choices,
    help="Beschränkt die gesamte Auswertung (Kennzahlen, Diagramme, Tabellen, Zusammenfassung, Sensitivität) auf dieses Ticket und alles darunter: z. B. eine Initiative, ein Epic "
         "oder eine Story mit ihren Sub-Tasks. Die Auswahl wird nicht in die Adresszeile geschrieben, weil Ticketschlüssel nicht in eine Adresse gehören.")
view_left, view_right = st.columns(2)
with view_left:
    dimension = st.selectbox("Ebene", C.DIMENSIONS, key="dimension", help="Wonach die Tickets zusammengefasst werden. Tickets mit mehreren Werten (Labels, Komponenten) zählen anteilig.")
with view_right:
    dimension2 = st.selectbox("Zweite Ebene (Kreuztabelle)", C.DIMENSIONS_2, key="dimension2", help="Zeigt zusätzlich den Fortschritt je Kombination beider Ebenen.")

settings = Settings(scheme=scheme, custom=custom, weight_mode=weight_mode, unest_rule=unest_rule, count_level=count_level, blend=blend,
                    dimension=dimension, dimension2=dimension2, root=root)
as_of = C.SAMPLE_TODAY
a = analyse(issues, settings, as_of)

for problem in check_consistency(a):
    st.error(f"Interne Prüfung verletzt: {problem}")
if root != C.ROOT_ALL:
    in_scope = len(A.subtree_keys(issues, root))
    st.info(f"Die Auswertung ist auf **{root_label(root).lstrip('↳ ')}** und alles darunter beschränkt: {in_scope} von {len(issues)} Tickets, davon {a.n_atoms} zählende. "
            "Kennzahlen, Diagramme, Tabellen, Zusammenfassung und Sensitivität gelten nur für diesen Teilbaum.")

def na(x, fmt):
    """NaN (kein Gewicht) als Strich zeigen."""
    return "–" if x != x else fmt(x)


with metrics_box:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fortschritt (nach Status gewichtet)", na(a.progress, pct))
    # Delta immer als „mein Wert minus Referenz“ (Referenz: der gewichtete Fortschritt); die Farbe bleibt neutral, weil kleiner nicht schlechter heißt.
    m2.metric("Nur Done, nach Gewicht", na(a.progress_done, pct),
              delta=None if a.progress != a.progress or a.progress_done != a.progress_done else f"{de(100 * (a.progress_done - a.progress), sign=True)} Punkte",
              delta_color="off")
    m3.metric("Nur Done, nach Ticketzahl", na(a.progress_count, pct),
              delta=None if a.progress != a.progress or a.progress_count != a.progress_count else f"{de(100 * (a.progress_count - a.progress), sign=True)} Punkte",
              delta_color="off")
    open_weight = a.weight * (1 - a.progress) if a.progress == a.progress else 0.0
    m4.metric(f"Offenes Gewicht ({unit}, gesamt {de(a.weight)})", de(open_weight))

for kind, text in (verdict_measures(a.progress, a.progress_done, a.progress_count), verdict_unestimated(a.n_unestimated, a.n_atoms, unest_rule, weight_mode)):
    getattr(st, kind)(text)

st.markdown(f"### Fortschritt je {dimension}" if dimension != C.DIM_ALL else "### Fortschritt des gesamten Projekts")
st.plotly_chart(build_progress_bars(a.stats, unit), width="stretch", key="chart_bars")
st.caption("Balkenlänge = Gewicht der Gruppe. Dunkel: erledigt; hell: durch den Status angerechnet (z. B. 50 % für ein Ticket in Arbeit); grau: offen. "
           f"Rechts: Fortschritt und Gewicht in {unit}.")
if len(a.stats.labels) > 30:
    st.caption(f"Gezeigt werden die 30 gewichtsstärksten von {len(a.stats.labels)} Gruppen; die Tabelle unten enthält alle.")
kind, text = verdict_groups(a.stats, dimension)
getattr(st, kind)(text)

if a.cross is not None:
    st.markdown(f"### Kreuztabelle: {dimension} × {dimension2}")
    st.plotly_chart(build_heatmap(a.cross, dimension, dimension2), width="stretch", key="chart_heat")
    st.caption("Farbe und Zahl: Fortschritt der Kombination; leere Felder haben kein Ticket. Ein Ticket mit mehreren Werten zählt anteilig in jedem Feld.")

st.markdown("### 🗺️ Flächenansicht: Projekt → Epic → Ticket")
if a.hierarchy.values[0] > 0:
    st.plotly_chart(build_treemap(a.hierarchy), width="stretch", key="chart_tree")
    st.caption("Fläche = Gewicht, Farbe = Fortschritt. Ein Klick auf ein Epic zoomt hinein. Tickets ohne Gewicht (ungeschätzt und „nicht zählen“) haben keine Fläche.")
else:
    st.info("Kein Ticket hat Gewicht; die Flächenansicht bleibt leer. Die Regel für ungeschätzte Tickets oder die Gewichtung ändern.")

st.markdown("### 🌳 Hierarchiegraph")
g = a.tree
st.plotly_chart(build_tree_graph(g, unit), width="stretch", key="chart_graph")
st.caption(f"Von links nach rechts: {'das gewählte Teilprojekt' if root != C.ROOT_ALL else 'Projekt'} → Ebenen darunter → Tickets. Größe = Gewicht aller zählenden Tickets darunter, Farbe = Fortschritt, "
           "Quadrat = fasst Tickets zusammen, Kreis = Ticket ohne Kinder, grau = nichts messbar (kein Gewicht). Alle Angaben stehen im Hover.")
if g.hidden.any():
    st.caption(f"Der Graph hätte {g.n_total} Knoten; gezeichnet werden die obersten Ebenen bis Ebene {g.shown_depth} (Knoten höchstens {C.GRAPH_MAX_NODES}). "
               "Ein Teilprojekt als Wurzel zeigt mehr Tiefe.")

st.markdown("### 📈 Verlauf: Umfang und Erledigtes")
grid, scope, finished, missing = a.burn
if len(grid) >= 2:
    st.plotly_chart(build_burnup(grid, scope, finished, unit), width="stretch", key="chart_burn")
    st.caption("Aus Erstell- und Lösungsdatum. Nur erledigte Tickets zählen: Der Statusverlauf (wann ein Ticket in Review ging) steht in diesen Daten nicht, "
               "deshalb gibt es keine zeitliche Fassung der Status-Gewichte.")
    if missing:
        st.warning(f"{missing} erledigte Tickets haben kein lesbares Lösungsdatum und fehlen im Verlauf.")
else:
    st.info("Für den Verlauf fehlen Erstell- und Lösungsdaten.")

st.markdown("## 📋 Tabellen")
st.caption("Alle Tabellen folgen den Einstellungen links und der gewählten Ebene; jede lässt sich als CSV für Excel laden (Semikolon, Dezimalkomma).")


def show_table(rows, key, formats=None, file_name="tabelle"):
    """Zeigt Zeilen (Wörterbücher) als Tabelle und bietet sie als CSV an. `formats`: Spalte -> Streamlit-Zahlenformat."""
    if not rows:
        st.info("Keine Daten für diese Tabelle.")
        return
    config = {name: st.column_config.NumberColumn(format=fmt) for name, fmt in (formats or {}).items() if name in rows[0]}
    if "Wirkung" in rows[0]:
        config["Wirkung"] = st.column_config.TextColumn(width="large")
    st.dataframe(rows, hide_index=True, width="stretch", column_config=config, key=f"df_{key}")
    st.download_button("⬇️ Als CSV", rows_to_csv(rows), file_name=f"{file_name}.csv", mime="text/csv", key=f"csv_{key}")


tab_group, tab_status, tab_contrib, tab_overview, tab_month, tab_quality = st.tabs(
    ["Je Gruppe", "Status × Gruppe", "Beitrag zum Fortschritt", "Status-Übersicht", "Erledigt je Monat", "Datenqualität"])
with tab_group:
    group_rows = [
        {dimension: lbl, f"Gewicht ({unit})": float(w), "Fortschritt": None if p != p else float(p), "Nur Done (Gewicht)": None if d != d else float(d),
         "Tickets": float(n), "ohne Story Points": float(u)}
        for lbl, w, p, d, n, u in zip(a.stats.labels, a.stats.weight, a.stats.progress, a.stats.progress_done, a.stats.count, a.stats.unestimated)]
    show_table(group_rows, "group", {f"Gewicht ({unit})": "%.1f", "Fortschritt": "percent", "Nur Done (Gewicht)": "percent", "Tickets": "%.1f", "ohne Story Points": "%.1f"},
               "fortschritt-je-gruppe")
with tab_status:
    st.caption(f"Wie verteilt sich jede Gruppe der Ebene „{dimension}“ auf die Status? Tickets mit mehreren Werten zählen anteilig.")
    metric = st.radio("Kennzahl je Zelle", T.METRICS, key="table_metric", horizontal=True,
                      help="Gewicht = Story Points (bzw. 1 je Ticket), Tickets = Anzahl, Angerechnet = Gewicht mal Gutschrift des Status.")
    status_rows = T.status_by_group(issues, a, metric)
    status_names = T.atom_statuses(issues, a)
    show_table(status_rows, "status", {**{name: "%.1f" for name in (*status_names, T.SUM_LABEL)}, "Fortschritt": "percent"}, "status-je-gruppe")
with tab_contrib:
    st.caption("Wer treibt die Zahl? Der Beitrag einer Gruppe ist ihr angerechnetes Gewicht geteilt durch das Gesamtgewicht, in Prozentpunkten; die Beiträge summieren sich zum Gesamtfortschritt. "
               "Das offene Gewicht zeigt, wo noch am meisten Arbeit steckt.")
    show_table(T.contribution(a), "contrib", {"Gewicht": "%.1f", "Anteil am Gewicht": "percent", "Fortschritt": "percent", "Beitrag (Punkte)": "%.1f", "Offenes Gewicht": "%.1f",
                                              "Anteil am Offenen": "percent"}, "beitrag-zum-fortschritt")
with tab_overview:
    st.caption("Was hinter den Status-Gewichten steckt: Wie viel Gewicht liegt in welchem Status, und wie viel davon wird angerechnet?")
    show_table(T.status_overview(issues, a), "overview", {"Gewicht": "%.1f", "Status-Gewicht (%)": "%.0f", "Angerechnet": "%.1f", "Anteil am Angerechneten": "percent"}, "status-uebersicht")
with tab_month:
    month_rows, month_missing = T.done_by_month(issues, a)
    st.caption("Erledigtes Gewicht nach Monat des Lösungsdatums, lückenlos von der ersten bis zur letzten Lösung. Daran lässt sich das bisherige Tempo ablesen; eine Prognose daraus macht die Demo nicht.")
    show_table(month_rows, "month", {"Gewicht erledigt": "%.1f", "Gewicht kumuliert": "%.1f"}, "erledigt-je-monat")
    if month_missing:
        st.warning(f"{month_missing} erledigte Tickets haben kein lesbares Lösungsdatum und fehlen in dieser Tabelle.")
with tab_quality:
    st.caption("Prüfungen der Eingangsdaten: Was davon die Zahl verzerren kann und wie die App damit umgeht.")
    show_table(T.data_quality(issues, a), "quality", {"Anteil an den Tickets": "percent"}, "datenqualitaet")
    unest_rows, unest_total = T.unestimated_tickets(issues, a)
    if not any(r["Titel"] for r in unest_rows):
        unest_rows = [{k: v for k, v in r.items() if k != "Titel"} for r in unest_rows]
    if unest_total:
        st.markdown(f"**Tickets ohne Story Points** ({unest_total}" + (f", gezeigt die ersten {len(unest_rows)}" if unest_total > len(unest_rows) else "") + ")")
        show_table(unest_rows, "unest", None, "ohne-story-points")
with st.expander("📝 Zusammenfassung zum Kopieren (Markdown)"):
    st.caption("Für Confluence, Mail oder Chat: Gesamtfortschritt in allen drei Maßen, Umfang, Annahmen und die Tabelle der gewählten Ebene. Das Kopiersymbol oben rechts im Feld kopiert alles.")
    st.code(T.summary_markdown(issues, a, unit, as_of), language="markdown")

st.markdown("---")

# --- Kernfrage -----------------------------------------------------------------------------------------------------------------------------

st.markdown("## ❓ Kernfrage: Wie stark hängt die Zahl von den Annahmen ab?")
st.markdown("Der Gesamtfortschritt unter jedem der drei festen Status-Schemata, einmal mit Story Points und einmal nach Ticketanzahl gewichtet; alles andere wie eingestellt.")
rows = sensitivity(issues, settings)
st.plotly_chart(build_sensitivity(rows), width="stretch", key="chart_sens")
kind, text = verdict_sensitivity(rows)
getattr(st, kind)(text)

st.markdown("---")

# --- Erklärungen ---------------------------------------------------------------------------------------------------------------------------

with st.expander("🔧 Das Beispielprojekt"):
    st.markdown(
        """
**Die Daten sind erzeugt.** Das Beispielprojekt entsteht deterministisch aus der Epic-Zahl und dem Zufalls-Seed (links): Epics mit Stories, Bugs und Tasks (Story Points aus der Fibonacci-Skala,
ein Teil ungeschätzt), Sub-Tasks ohne Schätzung, Sprints, Komponenten, Labels, Releases, Teams, Bereiche und Prioritäten. Gleicher Seed, gleiches Projekt. Die Demo liest keine Jira-Datei und
verbindet sich nicht mit Jira; eigene Tickets kann sie nicht auswerten.

**Wie Ebenen entstehen.** Das Epic eines Tickets folgt der Elternkette bis zu einem Ticket vom Typ Epic. Sprint, Komponente und Release erbt ein Ticket ohne eigenen Wert vom
übergeordneten Ticket (Sub-Tasks). Bei mehreren Sprints zählt der letzte. Labels, Komponenten und Releases mit mehreren Werten teilen das Ticket gleichmäßig auf.

**Teilprojekt und Hierarchiegraph.** Die Auswahl „Teilprojekt“ setzt ein Ticket zur Wurzel: Gerechnet wird nur mit den Tickets der Zählebene, die dieses Ticket selbst oder (über beliebig viele Ebenen) darunter sind, z. B. eine Initiative, ein Epic oder eine Story mit ihren Sub-Tasks. Der Median für ungeschätzte Tickets und alle Kennzahlen, Tabellen, Diagramme, die Zusammenfassung und die Sensitivität beziehen sich dann auf diesen Teilbaum. Der Hierarchiegraph zeigt den Baum von links nach rechts; ein Knoten trägt die Summe der zählenden Tickets darunter. Bei mehr als 250 Knoten wird die tiefste Ebene zusammengefasst; ein Teilprojekt als Wurzel zeigt dann mehr Tiefe. Eltern-Verweise, die im Kreis laufen, werden je Ticket nur einmal gezählt.
"""
    )

with st.expander("📐 Mathematische Formulierung"):
    st.markdown(
        """
**Lesehilfe.** Gegeben sind die Tickets mit Status, Story Points und Zugehörigkeit zu Gruppen. Gesucht ist der Fortschritt einer Gruppe als Zahl zwischen 0 und 1.

| Symbol | Bedeutung |
|---|---|
| $i$ | ein Ticket der Zählebene (Atom) |
| $q_i$ | Story Points von $i$ (kann fehlen) |
| $w_i$ | Gewicht von $i$ |
| $c_i$ | Gutschrift von $i$ aus dem Status, zwischen 0 und 1 |
| $G$ | eine Gruppe, z. B. ein Epic oder ein Sprint |
| $s_{iG}$ | Anteil von $i$ an der Gruppe $G$ (1, bei $k$ Werten je $1/k$) |

Gewicht eines Tickets, mit $m$ als Median der geschätzten Tickets und $f$ als Ersatzwert der gewählten Regel (0, 1 oder $m$):
"""
    )
    st.markdown("$$w_i = \\begin{cases} q_i & \\text{falls } i \\text{ geschätzt} \\\\ f & \\text{sonst} \\end{cases}$$")
    st.markdown("Bei Gewichtung nach Ticketanzahl gilt $w_i = 1$. Fortschritt einer Gruppe:")
    st.markdown("$$P(G) = \\frac{\\sum_{i} s_{iG}\\, w_i\\, c_i}{\\sum_{i} s_{iG}\\, w_i}$$")
    st.markdown("Mit der Sub-Task-Option gilt für eine Story $i$ mit Sub-Tasks $S(i)$ und deren Gewichten $v_j$ (Story Points, falls alle gesetzt sind, sonst 1):")
    st.markdown("$$c_i = \\max\\left( c_i^{\\text{Status}},\\; \\frac{\\sum_{j \\in S(i)} v_j\\, c_j}{\\sum_{j \\in S(i)} v_j} \\right)$$")
    st.markdown("Teilprojekt mit Wurzel $r$: Es zählen nur die Tickets $i$ aus $T(r)$, der Menge von $r$ und allen Tickets, die über Eltern-Verweise unter $r$ hängen; alle Formeln gelten unverändert für diese Menge (auch der Median $m$).")
    st.markdown("Verlauf: Umfang $S(t)$ und Erledigtes $D(t)$ zum Stichtag $t$ mit Erstelldatum $e_i$ und Lösungsdatum $r_i$ der erledigten Tickets:")
    st.markdown("$$S(t) = \\sum_{i:\\, e_i \\le t} w_i \\qquad D(t) = \\sum_{i \\text{ erledigt}:\\, r_i \\le t} w_i$$")

with st.expander("🚧 Wo die Annahmen enden"):
    st.markdown(
        """
- **Die Status-Gewichte sind Annahmen, keine Messung.** „In Review zählt 80 %“ ist eine Verabredung; unter „Nur Done“ und „Workflow-gewichtet“ liegt dieselbe Realität bei anderen Zahlen
  (siehe Kernfrage). Wer ein Gewicht begründen will, braucht die Historie des eigenen Teams.
- **Story Points sind teamintern.** Zwischen Teams oder Projekten sind sie nicht vergleichbar; ein Gesamtwert über mehrere Teams mischt Maßstäbe.
- **Ungeschätzte Tickets verschieben die Zahl.** Jede der drei Regeln trifft eine Annahme; die Meldung oben zeigt, wie viele Tickets betroffen sind.
- **Der Verlauf kennt nur „erledigt“.** Ohne Statushistorie lässt sich nicht rekonstruieren, wann ein Ticket in Review ging; Umfangsänderungen (neue Tickets) sieht der Verlauf nur über das Erstelldatum.
- **Epics wiegen nur, was in ihnen steckt.** Ein Epic ohne Tickets oder mit nur ungeschätzten Tickets hat kein Gewicht und taucht in der Auswertung nicht als Fortschritt auf.
- **Keine Prognose.** Die Demo zeigt, wo das Projekt steht, nicht, wann es fertig wird.
"""
    )

st.markdown("---")
st.caption(
    "Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – "
    "Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). "
    "Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html)."
)
