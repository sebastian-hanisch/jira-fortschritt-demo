# Jira-Fortschritt: gewichtet über Status, Story Points und Ebenen – Streamlit-Demo

Fall-Demo für die Website „Sebastian Hanisch – Operations Research und Machine Learning“ (`demos.html`). Die App liest Tickets aus einer **Jira-Datei** (CSV-Export oder
gespeicherte REST-Antwort) oder direkt über die **Jira-API** und rechnet daraus einen **gewichteten Projektfortschritt**: Jeder Status zählt mit einem wählbaren Anteil
(To Do 0 %, in Arbeit 50 % oder eigene Werte, Done 100 %), jedes Ticket wiegt seine **Story Points** (oder 1), und das Ergebnis lässt sich über mehrere
**Aggregationsebenen** zeigen: Gesamtprojekt, Epic, Sprint, Release, Komponente, Label, Bearbeiter, Ticket-Typ und Status, auf Wunsch zwei Ebenen als Kreuztabelle.
Dazu kommen sechs **Tabellen** (je Gruppe, Status × Gruppe, Beitrag zum Fortschritt, Status-Übersicht, Erledigt je Monat, Datenqualität), jede als CSV ladbar. Ohne eigene Daten zeigt ein erzeugtes Beispielprojekt, wie es aussieht.

## Warum dieses Problem

„Wie weit ist das Projekt?“ hat keine eindeutige Antwort. Zählt ein Ticket in Review schon halb, ganz oder gar nicht? Wiegt eine Story mit 13 Story Points so viel wie
dreizehn mit einem Punkt? Und was ist mit Tickets ohne Schätzung? Jede Dashboard-Zahl beantwortet diese Fragen still mit. Die Demo macht die Antworten zu Reglern und
fragt als **Kernfrage**: Wie stark hängt die Zahl von diesen Annahmen ab?

## Modell

Ein *Atom* ist ein Ticket der gewählten Zählebene (Stories, Tasks und Bugs, oder Sub-Tasks). Es hat ein Gewicht `w` (Story Points; fehlen sie, entscheidet die Regel
„nicht zählen“, „als 1 Story Point“ oder „Median der geschätzten Tickets“) und eine Gutschrift `c` zwischen 0 und 1 aus seinem Status. Der Fortschritt einer Gruppe `G` ist

    P(G) = Σ s·w·c / Σ s·w

mit `s` als Anteil des Tickets an der Gruppe (bei mehreren Labels oder Komponenten gleichmäßig verteilt, damit nichts doppelt zählt). Mit der Sub-Task-Option gilt für
eine Story zusätzlich: Ihre Gutschrift ist mindestens so hoch wie der Fortschritt ihrer Sub-Tasks. Details, Symboltabelle und der Verlauf (Burn-up) stehen im 📐-Expander der App.

Die drei festen Status-Schemata: **Nur Done** (0 % / 0 % / 100 %), **Linear** (0 % / 50 % / 100 %) und **Workflow-gewichtet** (In Review 80 %, Testing 90 %, sonstige Arbeit
40 %; Annahmen, die jedes Team durch eigene Werte ersetzen sollte). **Eigene Gewichte** entstehen, sobald die Tabelle in der App geändert wird.

## Methodik

- **Einlesen.** CSV (englische und deutsche Spaltenköpfe, Komma oder Semikolon, Elternverweis als Schlüssel oder ID, mehrfach vorkommende Spalten für Sprint, Labels,
  Komponenten), JSON (REST-Antwort) und die REST-API: Jira Cloud über `GET /rest/api/3/search/jql` mit Seitenmarke, Server/Data Center über `GET /rest/api/2/search`
  mit `startAt`. Was beim Einlesen fehlt oder nicht lesbar ist, meldet die App vor der ersten Zahl. Höchstens 5000 Tickets.
- **Aggregation.** Die Ebene ist ein Gruppenschlüssel je Ticket; Sub-Tasks erben Sprint, Komponente und Release vom übergeordneten Ticket, bei mehreren Sprints zählt der letzte.
  Die Summen laufen vektorisiert über `np.bincount`.
- **Tabellen.** `jira_tables.py` baut aus der Auswertung reine Zeilen: Status × Gruppe (Gewicht, Tickets oder angerechnetes Gewicht je Zelle, mit Summen), Beitrag je Gruppe in Prozentpunkten (die Beiträge summieren sich zum Gesamtfortschritt), Gewicht und Anrechnung je Status, erledigtes Gewicht je Kalendermonat und acht Prüfungen der Eingangsdaten (ohne Story Points, ohne Epic, ohne Sprint, erledigt ohne Lösungsdatum, Lösungsdatum vor Erstelldatum, erledigte Story mit offenen Sub-Tasks, uneinheitliche Statuskategorie) samt Liste der ungeschätzten Tickets.
- **Prüfung in der App.** `check_consistency` prüft bei jedem Lauf, dass Gruppengewichte und Ticketzahlen sich zum Gesamtwert summieren und kein Fortschritt außerhalb von 0 bis 100 %
  liegt und die Beiträge der Gruppen den Gesamtfortschritt ergeben; bei Verletzung zeigt die App einen Fehler statt einer stillen falschen Zahl.

## Befunde (gemessen, keine Behauptungen)

Das Beispielprojekt ist erzeugt (`jira_scenario.py`); die Zahlen zeigen den Mechanismus, keine Aussage über echte Projekte. Standardprojekt: 6 Epics, Zufalls-Seed 9, 88 Tickets
(davon 32 Sub-Tasks), also 50 Stories, Tasks und Bugs mit zusammen 211 Story Points (Median-Regel; 6 davon ungeschätzt). Der Seed ist so gewählt, dass alle Merkmale vorkommen
(übernommene Sprints, Sub-Tasks, ungeschätzte Tickets); er ist eine Beschreibung, kein Befund.

| Frage | Befund | Test |
|---|---|---|
| Wie weit ist das Standardprojekt je nach Voreinstellung? | Linear 48,1 %, streng (nur Done) 37,4 %, Workflow-Stufen mit Sub-Tasks 56,4 %; nur Done nach Ticketzahl 40,0 % | `test_default_progress_under_each_preset` |
| Wie groß ist die Spanne über die drei Schemata und die beiden Gewichtungen? | 37,4 % bis 54,4 %: 16,9 Prozentpunkte beim Standardprojekt | `test_default_sensitivity_range` |
| Ist das ein Zufall des Standardprojekts? | Über 10 feste Beispielprojekte liegt Linear im Median 6,9 Prozentpunkte über „nur Done“ (4,2 bis 10,2), und die Spanne über alle Annahmen beträgt im Median 13,9 Prozentpunkte (8,8 bis 18,4) | `test_linear_minus_only_done_over_the_fixed_projects`, `test_sensitivity_spread_over_the_fixed_projects` |
| Was bringt die Sub-Task-Option? | Beim Workflow-Schema hebt sie das Standardprojekt von 54,4 % auf 56,4 % | `test_blend_lifts_the_workflow_scheme_on_the_default_project` |

Dass „Linear“ über „nur Done“ liegt, folgt aus der Konstruktion (die Gutschriften sind nie kleiner); gemessen wird hier, **wie viel** das ausmacht. Welche der Zahlen die richtige ist,
beantwortet die Demo nicht: Das hängt davon ab, was berichtet werden soll (Lieferstand, Arbeitsstand oder Restaufwand).

## Ehrliche Grenzen

- **Die Status-Gewichte sind Annahmen, keine Messung.** Wer „In Review zählt 80 %“ begründen will, braucht die Historie des eigenen Teams.
- **Die Beispielzahlen gelten für das erzeugte Beispiel.** In echten Projekten kann die Spanne kleiner oder größer sein; die Demo zeigt, wie man sie für das eigene Projekt bestimmt.
- **Story Points sind teamintern.** Ein Gesamtwert über mehrere Teams mischt Maßstäbe.
- **Ungeschätzte Tickets verschieben die Zahl**, je nach Regel in eine andere Richtung; die App meldet, wie viele betroffen sind.
- **Der Verlauf kennt nur „erledigt“.** Eine Statushistorie (wann ging das Ticket in Review?) liegt in den gelesenen Feldern nicht vor.
- **Die API-Anbindung ist nur gegen eine Nachbildung der Schnittstelle getestet**, nicht gegen eine echte Jira-Instanz. Feld-IDs für Story Points, Sprint und Epic-Link sind je Instanz
  verschieden und einstellbar; bei Abweichungen meldet die App, welches Feld leer blieb.
- **Zugangsdaten.** Sie gehen nur für die Sitzung an die angegebene https-Adresse und werden weder gespeichert noch geteilt. Auf einer öffentlich gehosteten App läuft das über den Server
  der App; für echte Projektdaten besser lokal ausführen (siehe unten).

## Verifikation

- **Kern:** jede Einheit (Status-Gutschrift, Gewichte, Sub-Task-Mischung, Gruppierung, Kreuzgruppen, Aggregation, Burn-up, Flächenbaum) gegen Handrechnung an der Mini-Instanz
  (`tests/conftest.py`).
- **Orakel:** `tests/test_oracle_jira_fortschritt.py` vergleicht den vektorisierten Kern in jeder Ebene gegen eine Schleifenfassung in exakter Bruchrechnung (`fractions`) auf erzeugten
  Projekten und prüft Eigenschaften: Skalierung der Story Points, Reihenfolge der Tickets, Monotonie der Gutschriften, Burn-up gegen direktes Zählen.
- **Einlesen:** CSV (englisch, deutsch, Semikolon, cp1252, ID-Eltern, fehlende Spalten, unlesbare Werte), JSON, Rundlauf Beispiel → CSV → Beispiel; API mit einer Nachbildung, die die
  Seitenlogik (Seitenmarke bzw. `startAt`, `maxResults`) wirklich umsetzt; Zugangsdaten dürfen in keiner Fehlermeldung vorkommen.
- **Tabellen:** jede gegen Handrechnung an der Mini-Instanz, dazu Orakel in Bruchrechnung (Status × Gruppe in allen drei Kennzahlen, Beitrag, Status-Übersicht, Erledigt je Monat gegen direktes Zählen), Randfälle (leeres Projekt, kein Gewicht, Gewicht unter 1) und CSV-Format.
- **Verdikte** als reine Funktionen an handgesetzten Werten (Schwellen inklusive, jede Zahl im Text); **Randfälle** (leeres Projekt, ein und zwei Tickets, alles ungeschätzt, Gewicht 0).
- **Presets, Layout, Oberfläche:** AppTest-Rauchtest (jeder Button, jeder Regler am Minimum und Maximum, jede Option jeder Auswahl, Kombinationen der Ebenen, Datei- und API-Pfad, Eigene
  Gewichte, Permalink), Schnellstart oben in der Seitenleiste mit hervorgehobenem aktivem Preset (`tests/test_layout.py`), Footer-Test, Laufzeit-Importe.
- **Zahlen im README** stehen in `tests/test_claims.py`.
- **Mutationstest:** Vollauf über alle Stellen von `jira_algorithm.py`, `jira_evaluation.py` und `jira_tables.py` (`tools/mutate_demo.py`, Stand `tests/mutation_state.json`): alle Mutanten gefangen bis auf einen äquivalenten (Toleranzgrenze der Ticketzählung in `check_consistency`, erst ab Millionen Tickets wirksam). Nicht gemutet: Einlesen, Beispielprojekt, Darstellung.
- **Nicht gemacht:** ein Test gegen eine echte Jira-Instanz.

## Dateistruktur

| Datei | Zweck |
|---|---|
| `.github/workflows/tests.yml` | CI: Push, Pull Request, wöchentlicher Canary |
| `.gitignore` | venv, Caches, Streamlit-Secrets |
| `.streamlit/config.toml` | Streamlit-Einstellungen (keine Nutzungsstatistik) |
| `app.py` | Streamlit-App: Datenquelle, Status-Gewichte, Ergebnis, Ebenen, Kernfrage, Erklärungen |
| `jira_algorithm.py` | Kern: Gutschriften, Gewichte, Gruppierung, Aggregation, Burn-up, Flächenbaum |
| `jira_constants.py` | Regler-Grenzen, Gewichte-Schemata, Farben, Presets |
| `jira_evaluation.py` | `analyse`, Sensitivitätsprüfung, Verdikte, `check_consistency` |
| `jira_import.py` | CSV, JSON und REST-API zu `Issue`; Beispiel-CSV |
| `jira_layout.py` | Fester Kopf (Stylesheet) |
| `jira_presets.py` | Permalink, Presets (Schnellstart in der Seitenleiste, aktives Preset hervorgehoben), Zufalls-Seed-Button |
| `jira_rng.py` | SplitMix64 (Portfolio-Konvention für Zufall), wortgleich aus `ab-test-demo` |
| `jira_tables.py` | Tabellen: Status × Gruppe, Beitrag, Status-Übersicht, Erledigt je Monat, Datenqualität, CSV-Format |
| `jira_scenario.py` | Datenmodell `Issue` und erzeugtes Beispielprojekt |
| `jira_visualization.py` | Plotly-Abbildungen (Achsen gesperrt) |
| `requirements-dev.txt` | Laufzeit plus pytest |
| `requirements.txt` | Laufzeit-Bibliotheken (ungepinnt) |
| `tests/` | Mini-Instanz, Orakel, Import, Verdikte, Randfälle, Presets, Layout, AppTest, Claims, Footer, Laufzeit-Importe |

## Bewusst nicht umgesetzt

- **Prognose** („wann ist das Projekt fertig?“): Das braucht ein Modell für Tempo und Umfangsänderungen und wäre eine eigene Demo.
- **Statushistorie** (Changelog der API) für einen Burn-up mit Status-Gewichten: lässt sich nachrüsten, kostet aber einen Aufruf je Ticket.
- **PDF-Export**: Alle Tabellen lassen sich als CSV laden.
- **Speichern der Zugangsdaten** und Mehrfach-Projekt-Ansichten.

## Lokal ausführen

Für echte Projektdaten lokal ausführen, damit Tickets und Zugangsdaten den eigenen Rechner nicht verlassen (außer zur Jira-Adresse selbst). Python 3.12 oder neuer.

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Gebaut mit Streamlit, Plotly, NumPy und Requests.

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html).
