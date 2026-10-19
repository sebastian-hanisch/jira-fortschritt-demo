"""Jira-Fortschritt: gewichtet über Status, Story Points und Ebenen - interaktive Fall-Demo
Sebastian Hanisch - Operations Research und Machine Learning

Lauffähig mit: streamlit run app.py
"""

import datetime as dt

import streamlit as st

import jira_algorithm as A
import jira_constants as C
import jira_import as J
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
from jira_visualization import build_burnup, build_heatmap, build_progress_bars, build_sensitivity, build_treemap

st.set_page_config(page_title="Jira-Fortschritt – Sebastian Hanisch", layout="wide")


@st.cache_data(show_spinner=False)
def _sample(n_epics, seed):
    return make_sample(n_epics, seed)


@st.cache_data(show_spinner=False)
def _parse_upload(name, data, points, sprint, epic_link):
    """Datei einlesen; Fehler als Text zurückgeben (st.cache_data legt Ausnahmen nicht ab)."""
    try:
        return J.read_file(name, data, J.parse_field_ids(points, sprint, epic_link)), ""
    except J.JiraImportError as exc:
        return None, str(exc)


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
wiegt mehr als eine mit 1, und ein Bericht über das ganze Projekt sieht anders aus als einer je **Epic**, Sprint oder Komponente. Diese Demo liest Tickets aus einer
**Jira-Datei** oder direkt über die **Jira-API**, rechnet den Fortschritt mit frei wählbaren **Status-Gewichten** und zeigt ihn über mehrere **Aggregationsebenen**.

Unten: die **Kernfrage** (wie stark hängt die Zahl von den Annahmen ab?) und die Expander **🔧 Datenquellen und Jira-Felder**, **📐 Mathematische Formulierung** und
**🚧 Wo die Annahmen enden**.
"""
)
st.caption("🔗 Die Adresszeile oben spiegelt Ihre aktuelle Konfiguration wider – einfach kopieren, um ein Szenario zu teilen.")

load_permalink_settings()
init_session_state_defaults()
st.session_state.setdefault("editor_version", 0)

with st.sidebar:
    sidebar_presets()  # Schnellstart oben, das aktive Preset ist hervorgehoben
    st.header("📥 Datenquelle")
    source = st.radio("Quelle", C.SOURCES, key="source", help="Beispieldaten sind erzeugt. Eine Datei oder die Jira-API lädt Ihre eigenen Tickets.")
    is_sample = source == C.SOURCE_SAMPLE
    n_epics = st.slider("Epics im Beispielprojekt", *bounds("n_epics"), key="n_epics", disabled=not is_sample, help="Nur für die Beispieldaten.")
    seed = st.number_input("Zufalls-Seed der Beispieldaten", *bounds("seed_input"), key="seed_input", step=1, disabled=not is_sample)
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
    st.button("🎲 Neues Beispielprojekt", width="stretch", on_click=randomize_seed, disabled=not is_sample)

sync_query_params({key: st.session_state[key] for key in SETTING_SPECS})

# --- Daten ---------------------------------------------------------------------------------------------------------------------------------

issues, report = (), None
st.markdown("## 📥 Daten")
if source == C.SOURCE_SAMPLE:
    issues = _sample(int(n_epics), int(seed))
    st.caption(f"Erzeugtes Beispielprojekt (Stichtag {C.SAMPLE_TODAY.strftime('%d.%m.%Y')}, Sprint {C.SAMPLE_CURRENT_SPRINT} läuft): "
               f"{len(issues)} Tickets. Die Beispieldatei lässt sich als CSV herunterladen, um das erwartete Format zu sehen.")
    st.download_button("⬇️ Beispiel als CSV", J.to_csv(issues), file_name="jira-beispiel.csv", mime="text/csv", key="sample_csv")
else:
    with st.expander("Jira-Felder (Story Points, Sprint, Epic-Link)", expanded=False):
        st.caption("Die Feld-IDs unterscheiden sich je Jira-Instanz. Sie werden für JSON-Dateien und die API gebraucht; CSV-Exporte tragen die Namen als Spaltenköpfe.")
        f_points = st.text_input("Story-Point-Felder (kommagetrennt)", C.DEFAULT_POINTS_FIELDS, key="f_points")
        f_sprint = st.text_input("Sprint-Feld", C.DEFAULT_SPRINT_FIELD, key="f_sprint")
        f_epic = st.text_input("Epic-Link-Feld (nur altes Jira)", C.DEFAULT_EPIC_LINK_FIELD, key="f_epic")
    if source == C.SOURCE_FILE:
        upload = st.file_uploader("Jira-Export (CSV) oder gespeicherte REST-Antwort (JSON)", type=["csv", "json"], key="upload")
        if upload is None:
            st.info("Bitte eine Datei wählen. In Jira: Vorgänge suchen → Exportieren → CSV (alle Felder). Ohne Datei zeigen die Beispieldaten, wie es aussieht.")
            st.stop()
        parsed, error = _parse_upload(upload.name, upload.getvalue(), f_points, f_sprint, f_epic)
        if parsed is None:
            st.error(error)
            st.stop()
        issues, report = parsed
        st.caption("Die Datei wird nur für diese Sitzung im Arbeitsspeicher gelesen.")
    else:
        st.caption("Zugangsdaten gehen nur für diese Sitzung direkt an Ihre Jira-Adresse. Sie werden nicht gespeichert und nicht in der Adresszeile geteilt. "
                   "Für echte Projekte besser lokal ausführen (siehe README).")
        flavor = st.radio("Jira-Typ", J.FLAVORS, key="api_flavor", horizontal=True)
        api_url = st.text_input("Adresse der Jira-Instanz", placeholder="https://firma.atlassian.net", key="api_url")
        if flavor == J.CLOUD:
            api_email = st.text_input("E-Mail-Adresse des Kontos", key="api_email")
            api_token = st.text_input("API-Token", type="password", key="api_token", help="Unter id.atlassian.com → Sicherheit → API-Token erzeugen.")
        else:
            api_email = ""
            api_token = st.text_input("Persönliches Zugriffstoken", type="password", key="api_token")
        api_jql = st.text_area("JQL-Abfrage", "project = ABC", key="api_jql", height=70, help="Die Suche muss eingegrenzt sein, z. B. auf ein Projekt.")
        if st.button("Tickets aus Jira laden", key="api_load"):
            try:
                import requests

                with st.spinner("Lade Tickets aus Jira ..."):
                    raw, truncated = J.fetch_issues(
                        api_url, flavor, api_jql, J.parse_field_ids(f_points, f_sprint, f_epic), requests.Session(),
                        auth=(api_email, api_token) if flavor == J.CLOUD else None, token=api_token)
                    loaded = J.issues_from_api(raw, J.parse_field_ids(f_points, f_sprint, f_epic))
                st.session_state["api_data"] = (loaded[0], loaded[1], truncated, dt.datetime.now().strftime("%d.%m.%Y %H:%M"))
            except J.JiraImportError as exc:
                st.session_state.pop("api_data", None)
                st.error(str(exc))
            except Exception as exc:      # Netzfehler: ohne Zugangsdaten melden
                st.session_state.pop("api_data", None)
                st.error(f"Verbindung zu Jira fehlgeschlagen ({type(exc).__name__}). Adresse und Netzwerk prüfen.")
        if "api_data" not in st.session_state:
            st.info("Noch nichts geladen. Adresse, Zugangsdaten und JQL eintragen und auf „Tickets aus Jira laden“ klicken.")
            st.stop()
        issues, report, truncated, loaded_at = st.session_state["api_data"]
        st.caption(f"Geladen am {loaded_at}: {len(issues)} Tickets.")
        if truncated:
            st.warning(f"Die Obergrenze von {C.MAX_IMPORT_ISSUES} Tickets wurde erreicht, Jira hätte mehr geliefert. Die JQL-Abfrage weiter eingrenzen.")

if not issues:
    st.warning("Die Quelle enthält keine Tickets.")
    st.stop()
if report is not None:
    for note in report.notes:
        st.warning(note)

# --- Status-Gewichte -----------------------------------------------------------------------------------------------------------------------

statuses = status_list(issues)
custom = tuple(st.session_state.get("custom_credits", ()))
credits_now = A.status_credits(statuses, scheme, custom)
with st.expander("⚖️ Gewichte je Status – Tabelle ansehen und ändern", expanded=False):
    st.caption(
        "Anteil der Arbeit, der bei diesem Status als getan gilt. Eine Änderung schaltet auf „Eigene Gewichte“. "
        "Die Kategorie stammt von Jira (oder wurde aus dem Statusnamen geraten) und bestimmt, was als „erledigt“ zählt.")
    version = st.session_state["editor_version"]
    base = tuple((s, credits_now[s]) for s, _ in statuses)
    st.data_editor(
        [{"Status": s, "Kategorie": C.CATEGORY_LABEL[cat], "Gewicht (%)": round(100 * credits_now[s], 1)} for s, cat in statuses],
        disabled=["Status", "Kategorie"], hide_index=True, key=f"credit_editor_{version}", on_change=_on_credit_edit, args=(version, base),
        column_config={"Gewicht (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=5, format="%.0f")})

# --- Ergebnis ------------------------------------------------------------------------------------------------------------------------------

unit = "SP" if weight_mode == C.WEIGHT_POINTS else "Tickets"
st.markdown("## 🎯 Ergebnis")
metrics_box = st.container()
view_left, view_right = st.columns(2)
with view_left:
    dimension = st.selectbox("Ebene", C.DIMENSIONS, key="dimension", help="Wonach die Tickets zusammengefasst werden. Tickets mit mehreren Werten (Labels, Komponenten) zählen anteilig.")
with view_right:
    dimension2 = st.selectbox("Zweite Ebene (Kreuztabelle)", C.DIMENSIONS_2, key="dimension2", help="Zeigt zusätzlich den Fortschritt je Kombination beider Ebenen.")

settings = Settings(scheme=scheme, custom=custom, weight_mode=weight_mode, unest_rule=unest_rule, count_level=count_level, blend=blend,
                    dimension=dimension, dimension2=dimension2)
a = analyse(issues, settings, C.SAMPLE_TODAY if source == C.SOURCE_SAMPLE else dt.date.today())

for problem in check_consistency(a):
    st.error(f"Interne Prüfung verletzt: {problem}")

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

st.markdown("### 📋 Zahlen je Gruppe")
table = [
    {dimension: lbl, f"Gewicht ({unit})": round(float(w), 2), "Fortschritt": None if p != p else round(float(p), 4), "Nur Done (Gewicht)": None if d != d else round(float(d), 4),
     "Tickets": round(float(n), 2), "ohne Story Points": round(float(u), 2)}
    for lbl, w, p, d, n, u in zip(a.stats.labels, a.stats.weight, a.stats.progress, a.stats.progress_done, a.stats.count, a.stats.unestimated)
]
st.dataframe(table, hide_index=True, width="stretch", column_config={"Fortschritt": st.column_config.NumberColumn(format="percent"),
                                                                       "Nur Done (Gewicht)": st.column_config.NumberColumn(format="percent")})
csv_lines = [";".join([dimension, f"Gewicht ({unit})", "Fortschritt", "Nur Done (Gewicht)", "Tickets", "ohne Story Points"])] + [
    ";".join(["" if v is None else (str(v).replace(".", ",") if isinstance(v, float) else str(v).replace(";", ",")) for v in row.values()]) for row in table]
st.download_button("⬇️ Tabelle als CSV", ("\n".join(csv_lines) + "\n").encode("utf-8-sig"), file_name="fortschritt-je-gruppe.csv", mime="text/csv", key="table_csv")

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

with st.expander("🔧 Datenquellen und Jira-Felder"):
    st.markdown(
        """
**CSV-Export.** In Jira unter *Vorgänge → Exportieren → CSV (alle Felder)*. Erkannt werden englische und deutsche Spaltenköpfe: *Issue key*, *Issue Type*, *Status*,
*Status Category*, *Custom field (Story Points)* bzw. *Story Point Estimate*, *Parent* oder *Epic Link* (als Schlüssel oder als Vorgangs-ID), *Sprint* (mehrere Spalten
möglich), *Component/s*, *Labels*, *Assignee*, *Fix versions*, *Created*, *Resolved*. Pflicht sind nur Schlüssel und Status; was fehlt, wird oben gemeldet.

**JSON.** Eine gespeicherte Antwort der REST-Suche (`{"issues": [...]}`). Die Felder stehen unter `fields`; Story Points, Sprint und Epic-Link liegen in Feldern
mit instanzabhängiger ID (`customfield_…`), die unter „Jira-Felder“ eintragbar sind.

**API.** Jira Cloud: `GET /rest/api/3/search/jql` mit Seitenmarke `nextPageToken`; Anmeldung mit E-Mail und API-Token. Server/Data Center: `GET /rest/api/2/search` mit
`startAt`; Anmeldung mit persönlichem Zugriffstoken. Die Felder werden ausdrücklich angefragt. Es werden höchstens 5000 Tickets geladen.

**Wie Ebenen entstehen.** Das Epic eines Tickets folgt der Elternkette bis zu einem Ticket vom Typ Epic. Sprint, Komponente und Release erbt ein Ticket ohne eigenen Wert vom
übergeordneten Ticket (Sub-Tasks). Bei mehreren Sprints zählt der letzte. Labels, Komponenten und Releases mit mehreren Werten teilen das Ticket gleichmäßig auf.
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
