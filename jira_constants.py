"""Konstanten: Regler-Grenzen, feste Annahmen, Farben und Presets."""

import datetime as dt

# --- Beispieldaten -------------------------------------------------------------------------------------------------------------------------
N_EPICS_MIN, N_EPICS_MAX, DEFAULT_N_EPICS = 2, 12, 6   # Epics im Beispielprojekt; bei 12 Epics rund 80 Stories plus Sub-Tasks, O(n) in allen Schritten
SWEEP_SEEDS = tuple(range(100000, 100010))   # feste Beispielprojekte für alle Messreihen: nie ein einzelner Seed als Befund
SEED_MAX, DEFAULT_SEED = 999999, 9        # gewählt, weil das Beispielprojekt damit alle Merkmale zeigt (übernommene Sprints, Sub-Tasks, ungeschätzte Tickets)
SAMPLE_START = dt.date(2026, 6, 1)    # Beginn von Sprint 1; Sprints dauern 14 Tage
SAMPLE_TODAY = dt.date(2026, 8, 17)   # fester Stichtag der Beispieldaten (mitten in Sprint 6), damit der Burn-up reproduzierbar ist
SAMPLE_SPRINTS, SAMPLE_CURRENT_SPRINT = 10, 6
STORY_POINT_SCALE = (1, 2, 3, 5, 8, 13)
STORY_POINT_PROBS = (0.15, 0.25, 0.25, 0.20, 0.10, 0.05)
EPIC_NAMES = (
    "Login und Konten", "Berichte", "Datenimport", "Benachrichtigungen", "Suche", "Rechteverwaltung",
    "Schnittstellen", "Leistung", "Mobile Ansicht", "Abrechnung", "Auditprotokoll", "Onboarding",
)
COMPONENTS = ("Frontend", "Backend", "Daten", "Infrastruktur")
LABELS = ("tech-schuld", "ux", "sicherheit", "quick-win")
ASSIGNEES = ("Person A", "Person B", "Person C", "Person D", "Person E")

# --- Jira-Import ---------------------------------------------------------------------------------------------------------------------------
MAX_IMPORT_ISSUES = 5000      # harte Obergrenze für eine Datei: alle Schritte sind O(n), das Diagramm-Budget ist darauf ausgelegt
REPO_URL = "https://github.com/sebastian-hanisch/jira-fortschritt-werkzeug"      # Open Source (MIT-Lizenz): Code und Anleitung zum lokalen Betrieb
MAX_UPLOAD_MB = 50            # Größe einer hochgeladenen Datei; gehört in .streamlit/config.toml als server.maxUploadSize (tests/test_app.py prüft die Übereinstimmung)
DEFAULT_POINTS_FIELDS = "customfield_10016, customfield_10026"   # Kandidaten für das Story-Point-Feld; je Jira-Instanz verschieden
DEFAULT_SPRINT_FIELD = "customfield_10020"
DEFAULT_EPIC_LINK_FIELD = "customfield_10014"                    # nur für Projekte mit altem „Epic Link“; sonst genügt das Feld parent

# --- Gewichte ------------------------------------------------------------------------------------------------------------------------------
CATEGORIES = ("new", "indeterminate", "done")
CATEGORY_LABEL = {"new": "To Do", "indeterminate": "In Arbeit", "done": "Erledigt"}
SCHEME_DONE, SCHEME_LINEAR, SCHEME_WORKFLOW, SCHEME_CUSTOM = "Nur Done (0 / 0 / 100)", "Linear (0 / 50 / 100)", "Workflow-gewichtet", "Eigene Gewichte"
SCHEMES = (SCHEME_DONE, SCHEME_LINEAR, SCHEME_WORKFLOW, SCHEME_CUSTOM)
SENSITIVITY_SCHEMES = (SCHEME_DONE, SCHEME_LINEAR, SCHEME_WORKFLOW)   # die drei festen Schemata der Sensitivitätsprüfung
CATEGORY_CREDIT_LINEAR = {"new": 0.0, "indeterminate": 0.5, "done": 1.0}
# Workflow-gewichtet: Anteil der Arbeit, der bei einem Status in Arbeit schon als getan gilt. Annahmen, keine Messung: Wer das Schema
# nutzt, ersetzt die Zahlen durch die Erfahrung des eigenen Teams (Eigene Gewichte).
WORKFLOW_KEYWORDS = (
    (("review", "prüfung", "pruefung"), 0.8),
    (("test", "qa", "abnahme", "verif"), 0.9),
    (("progress", "bearbeitung", "arbeit", "doing"), 0.4),
)

WEIGHT_POINTS, WEIGHT_COUNT = "Story Points", "Ticketanzahl"
WEIGHT_MODES = (WEIGHT_POINTS, WEIGHT_COUNT)
UNEST_IGNORE, UNEST_ONE, UNEST_MEDIAN = "nicht zählen", "als 1 Story Point", "Median der geschätzten Tickets"
UNEST_RULES = (UNEST_MEDIAN, UNEST_ONE, UNEST_IGNORE)
LEVEL_STORIES, LEVEL_SUBTASKS = "Stories, Tasks und Bugs", "Sub-Tasks"
COUNT_LEVELS = (LEVEL_STORIES, LEVEL_SUBTASKS)

DIM_ALL, DIM_EPIC, DIM_SPRINT, DIM_RELEASE, DIM_COMPONENT, DIM_LABEL, DIM_ASSIGNEE, DIM_TYPE, DIM_STATUS = (
    "Gesamtes Projekt", "Epic", "Sprint", "Release (Fix Version)", "Komponente", "Label", "Bearbeiter", "Ticket-Typ", "Status")
DIMENSIONS = (DIM_ALL, DIM_EPIC, DIM_SPRINT, DIM_RELEASE, DIM_COMPONENT, DIM_LABEL, DIM_ASSIGNEE, DIM_TYPE, DIM_STATUS)
DIM_NONE = "(keine zweite Ebene)"
DIMENSIONS_2 = (DIM_NONE,) + DIMENSIONS[1:]
DEFAULT_DIM, DEFAULT_DIM2 = DIM_EPIC, DIM_NONE

SOURCE_SAMPLE, SOURCE_FILE = "Beispieldaten", "Datei (CSV oder JSON)"
SOURCES = (SOURCE_SAMPLE, SOURCE_FILE)

BURNUP_STEP_DAYS = 7

# --- Farben --------------------------------------------------------------------------------------------------------------------------------
COLOR_DONE = "#2F6B65"
COLOR_PARTIAL = "#7FB5AE"
COLOR_OPEN = "rgba(150,150,150,0.45)"
COLOR_SCOPE = "#4c78a8"
COLOR_SCALE = [[0.0, "#c9534b"], [0.5, "#f2d57e"], [1.0, "#2F6B65"]]   # Fortschritt 0 % bis 100 %

DEFAULT_SCHEME, DEFAULT_WEIGHT_MODE, DEFAULT_UNEST, DEFAULT_LEVEL = SCHEME_LINEAR, WEIGHT_POINTS, UNEST_MEDIAN, LEVEL_STORIES

PRESETS = {
    "Standard: linear nach Status": {
        "scheme": SCHEME_LINEAR, "weight_mode": WEIGHT_POINTS, "unest_rule": UNEST_MEDIAN, "count_level": LEVEL_STORIES, "blend": False},
    "Streng: nur Done zählt": {
        "scheme": SCHEME_DONE, "weight_mode": WEIGHT_POINTS, "unest_rule": UNEST_MEDIAN, "count_level": LEVEL_STORIES, "blend": False},
    "Workflow-Stufen mit Sub-Tasks": {
        "scheme": SCHEME_WORKFLOW, "weight_mode": WEIGHT_POINTS, "unest_rule": UNEST_MEDIAN, "count_level": LEVEL_STORIES, "blend": True},
}
PRESET_HELP = {
    "Standard: linear nach Status": "To Do zählt 0 %, jeder Status in Arbeit 50 %, Done 100 %; gewichtet mit Story Points, ungeschätzte Tickets mit dem Median.",
    "Streng: nur Done zählt": "Nur erledigte Tickets bringen Fortschritt, angefangene Arbeit zählt 0 %. Der vorsichtigste Blick.",
    "Workflow-Stufen mit Sub-Tasks": "In Review 80 %, Testing 90 %, sonstige Arbeit 40 % (Annahmen); der Fortschritt einer Story folgt zusätzlich ihren Sub-Tasks.",
}
