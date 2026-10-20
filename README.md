# Jira-Fortschritt: gewichtet über Status, Story Points und Ebenen – Streamlit-Werkzeug

Werkzeug auf der Website „Sebastian Hanisch – Operations Research und Machine Learning“. Die App liest Tickets aus einer **Jira-Datei** (CSV-Export oder
gespeicherte REST-Antwort als JSON) und rechnet daraus einen **gewichteten Projektfortschritt**: Jeder Status zählt mit einem wählbaren Anteil
(To Do 0 %, in Arbeit 50 % oder eigene Werte, Done 100 %), jedes Ticket wiegt seine **Story Points** (oder 1), und das Ergebnis lässt sich über mehrere
**Aggregationsebenen** zeigen: Gesamtprojekt, Epic, Sprint, Release, Komponente, Label, Bearbeiter, Ticket-Typ und Status, auf Wunsch zwei Ebenen als Kreuztabelle.
Das Werkzeug ist **Open Source** (MIT-Lizenz) und lässt sich selbst betreiben; für vertrauliche Daten ist der lokale Betrieb der empfohlene Weg (Abschnitt „Lokal ausführen“). Dazu kommen eine **Zusammenfassung zum Kopieren** (Markdown) und sechs **Tabellen** (je Gruppe, Status × Gruppe, Beitrag zum Fortschritt, Status-Übersicht, Erledigt je Monat, Datenqualität), jede als CSV ladbar. Ohne eigene Daten zeigt ein erzeugtes Beispielprojekt, wie es aussieht.

## Warum dieses Problem

„Wie weit ist das Projekt?“ hat keine eindeutige Antwort. Zählt ein Ticket in Review schon halb, ganz oder gar nicht? Wiegt eine Story mit 13 Story Points so viel wie
dreizehn mit einem Punkt? Und was ist mit Tickets ohne Schätzung? Jede Dashboard-Zahl beantwortet diese Fragen still mit. Das Werkzeug macht die Antworten zu Reglern und
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
  Komponenten) und JSON (gespeicherte Antwort der Jira-REST-Suche mit einstellbaren Feld-IDs). Beispieldateien in beiden Formaten lassen sich in der App
  herunterladen; die App erklärt auch, wie man die JSON-Datei gewinnt (Feldliste der Suche, Seitengröße). Was beim Einlesen fehlt oder nicht lesbar ist, meldet die App vor der ersten Zahl. Höchstens 5000 Tickets.
- **Datenschutz im Werkzeug.** Kein `st.cache_data` für hochgeladene Daten (nur das erzeugte Beispiel wird zwischengespeichert), keine Anbindung an die Jira-Schnittstelle und kein
  Eingabefeld für Zugangsdaten, Obergrenzen für Dateigröße (50 MB, `server.maxUploadSize`) und Ticketzahl, Hinweis vor dem Hochladen, die Rohdatei wird nach dem Einlesen nicht gehalten
  (neues Upload-Feld, Knopf „Daten jetzt löschen“), Titel (außer Epics) und Bearbeiternamen beim Laden verwerfbar, Fehlermeldungen nennen nur den Fehlertyp, und die Ausnahmemeldungen
  stehen nicht im Protokoll der App (Streamlit schreibt sie sonst samt Meldung hinein, Versuch siehe Verifikation).
- **Einlesen im Alltag.** Deutsche Datumsformate („19/Okt/26 15:45“, „19/Mär/26 3:45 nachm.“) werden gelesen; ein Erkennungsbericht zeigt, welche Spalte bzw. welches Feld wofür erkannt wurde
  und bei wie vielen Tickets ein Wert steht.
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
beantwortet das Werkzeug nicht: Das hängt davon ab, was berichtet werden soll (Lieferstand, Arbeitsstand oder Restaufwand).

## Ehrliche Grenzen

- **Die Status-Gewichte sind Annahmen, keine Messung.** Wer „In Review zählt 80 %“ begründen will, braucht die Historie des eigenen Teams.
- **Die Beispielzahlen gelten für das erzeugte Beispiel.** In echten Projekten kann die Spanne kleiner oder größer sein; das Werkzeug zeigt, wie man sie für das eigene Projekt bestimmt.
- **Story Points sind teamintern.** Ein Gesamtwert über mehrere Teams mischt Maßstäbe.
- **Ungeschätzte Tickets verschieben die Zahl**, je nach Regel in eine andere Richtung; die App meldet, wie viele betroffen sind.
- **Der Verlauf kennt nur „erledigt“.** Eine Statushistorie (wann ging das Ticket in Review?) liegt in den gelesenen Feldern nicht vor.
- **Das JSON-Format ist nur gegen die Beispieldatei und nachgebaute Antworten getestet**, nicht gegen eine echte Jira-Instanz. Feld-IDs für Story Points, Sprint und Epic-Link sind je
  Instanz verschieden und einstellbar; bei Abweichungen meldet die App, welches Feld leer blieb.
- **Hochgeladene Dateien liegen für die Sitzung auf dem Server der Plattform** (Streamlit Community Cloud, USA), im Arbeitsspeicher. Das Werkzeug speichert und cached sie nicht,
  behält nach dem Einlesen nur die berechnungsrelevanten Felder und verwirft auf Wunsch die Titel (außer Epics) und ersetzt die Namen der Bearbeiter durch Nummern. Das schützt Anzeige,
  Tabellen und Zusammenfassung, aber die Datei hat den Server beim Hochladen schon erreicht, und die Plattform kann sie bis zum Sitzungsende im Speicher halten. Keine vertraulichen
  Daten ohne Freigabe hochladen, Spalten wie Beschreibung und Kommentare vorher löschen; für sensible Projekte lokal ausführen (siehe unten).
- **Das Datenschutz-Verhalten ist nur gegen die eigene Testsuite geprüft**, nicht gegen die Server der Plattform: Dass der Filter für Ausnahmemeldungen im Protokoll greift, zeigte ein Versuch
  mit einer eigens fehlschlagenden App lokal; auf der Cloud selbst habe ich es nicht überprüft.

## Verifikation

- **Kern:** jede Einheit (Status-Gutschrift, Gewichte, Sub-Task-Mischung, Gruppierung, Kreuzgruppen, Aggregation, Burn-up, Flächenbaum) gegen Handrechnung an der Mini-Instanz
  (`tests/conftest.py`).
- **Orakel:** `tests/test_oracle_jira_fortschritt.py` vergleicht den vektorisierten Kern in jeder Ebene gegen eine Schleifenfassung in exakter Bruchrechnung (`fractions`) auf erzeugten
  Projekten und prüft Eigenschaften: Skalierung der Story Points, Reihenfolge der Tickets, Monotonie der Gutschriften, Burn-up gegen direktes Zählen.
- **Einlesen:** CSV (englisch, deutsch, Semikolon, cp1252, ID-Eltern, fehlende Spalten, unlesbare Werte), JSON (Felder, Feld-IDs, Sub-Task-Kennzeichen, alte Sprint-Schreibweise), Rundlauf Beispiel → CSV bzw. JSON → Beispiel in beiden Formaten, Umbenennung der Bearbeiter.
- **Datenschutz:** Test, dass nur die Erzeugung des Beispielprojekts zwischengespeichert wird (`st.cache_data`), nie hochgeladene Daten, und dass weder eine Netzwerkbibliothek noch ein Eingabefeld für Zugangsdaten im Code steckt.
- **Datenschutz:** der Filter für das Protokoll (Meldung ersetzt, Typ und Aufrufstationen bleiben), der Wächter (nur der Fehlertyp erscheint), der Upload-Lebenslauf, die Obergrenze in der
  Serverkonfiguration; zusätzlich ein Versuch mit einer absichtlich fehlschlagenden App: ohne Filter steht die Meldung im Protokoll, mit Filter nicht.
- **Tabellen und Zusammenfassung:** jede gegen Handrechnung an der Mini-Instanz, dazu Orakel in Bruchrechnung (Status × Gruppe in allen drei Kennzahlen, Beitrag, Status-Übersicht, Erledigt je Monat gegen direktes Zählen), Randfälle (leeres Projekt, kein Gewicht, Gewicht unter 1) und CSV-Format.
- **Verdikte** als reine Funktionen an handgesetzten Werten (Schwellen inklusive, jede Zahl im Text); **Randfälle** (leeres Projekt, ein und zwei Tickets, alles ungeschätzt, Gewicht 0).
- **Presets, Layout, Oberfläche:** AppTest-Rauchtest (jeder Button, jeder Regler am Minimum und Maximum, jede Option jeder Auswahl, Kombinationen der Ebenen, Datei-Pfad mit CSV und JSON, Eigene
  Gewichte, Permalink), Schnellstart oben in der Seitenleiste mit hervorgehobenem aktivem Preset (`tests/test_layout.py`), Footer-Test, Laufzeit-Importe.
- **Zahlen im README** stehen in `tests/test_claims.py`.
- **Mutationstest:** Vollauf über alle Stellen von `jira_algorithm.py`, `jira_evaluation.py` und `jira_tables.py` (235 Stellen) (`tools/mutate_demo.py`, Stand `tests/mutation_state.json`): alle Mutanten gefangen bis auf drei äquivalente (Toleranzgrenze der Ticketzählung in `check_consistency`, erst ab Millionen Tickets wirksam; zwei Randvergleiche der Zusammenfassung bei genau 40 Gruppen, wo beide Zweige dasselbe liefern). Nicht gemutet: Einlesen, Beispielprojekt, Darstellung.
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
| `jira_import.py` | CSV und JSON zu `Issue`; Beispieldateien als CSV und JSON; Namen der Bearbeiter durch Nummern ersetzen |
| `jira_layout.py` | Fester Kopf (Stylesheet) |
| `jira_presets.py` | Permalink, Presets (Schnellstart in der Seitenleiste, aktives Preset hervorgehoben), Zufalls-Seed-Button |
| `jira_privacy.py` | Filter, der Ausnahmemeldungen aus dem Protokoll der App entfernt (Typ und Aufrufstationen bleiben) |
| `jira_rng.py` | SplitMix64 (Portfolio-Konvention für Zufall), wortgleich aus `ab-test-demo` |
| `jira_tables.py` | Tabellen: Status × Gruppe, Beitrag, Status-Übersicht, Erledigt je Monat, Datenqualität, CSV-Format |
| `jira_scenario.py` | Datenmodell `Issue` und erzeugtes Beispielprojekt |
| `jira_visualization.py` | Plotly-Abbildungen (Achsen gesperrt) |
| `requirements-dev.txt` | Laufzeit plus pytest |
| `requirements.txt` | Laufzeit-Bibliotheken (ungepinnt) |
| `tests/` | Mini-Instanz, Orakel, Import, Verdikte, Randfälle, Presets, Layout, AppTest, Claims, Footer, Laufzeit-Importe |

## Bewusst nicht umgesetzt

- **Prognose** („wann ist das Projekt fertig?“): Das braucht ein Modell für Tempo und Umfangsänderungen und wäre ein eigenes Werkzeug.
- **Anbindung an die Jira-Schnittstelle:** bewusst entfernt (die erste Fassung hatte sie, Commit `09a66cb`). Zugangsdaten und Ticketdaten sollen nur als Datei durch eine öffentlich
  gehostete App gehen, nie als Anmeldung an einer fremden Jira-Adresse.
- **Statushistorie** (Changelog der Jira-Schnittstelle) für einen Burn-up mit Status-Gewichten: lässt sich nachrüsten, kostet aber einen Aufruf je Ticket.
- **PDF-Export**: Alle Tabellen lassen sich als CSV laden.
- **Mehrfach-Projekt-Ansichten.**

## Lizenz

MIT-Lizenz (Text in `LICENSE`): Der Code darf kopiert, verändert, weitergegeben, selbst gehostet (auch intern in einem Unternehmen) und kommerziell genutzt werden, solange der Urheberrechtsvermerk
und der Lizenztext mitgeführt werden. Gewährleistung und Haftung sind ausgeschlossen. Die verwendeten Bibliotheken (Streamlit: Apache-2.0, Plotly: MIT, NumPy: BSD-3-Clause) liegen nicht im
Repository, sondern werden installiert und stehen unter ihren eigenen Lizenzen. Die erzeugten Beispieldaten sind frei erfunden.

## Lokal ausführen

Für echte Projektdaten ist das der empfohlene Weg: Die Tickets bleiben auf dem eigenen Rechner, es gibt weder einen Upload an einen fremden Server noch ein Protokoll bei einem Anbieter. Das Werkzeug selbst baut
keine Verbindung ins Netz auf (kein Netzwerkcode, ein Test prüft das); installiert werden die Bibliotheken einmalig über `pip`. Voraussetzung: Python 3.12 oder neuer.

```bash
git clone https://github.com/sebastian-hanisch/jira-fortschritt-werkzeug.git
cd jira-fortschritt-werkzeug

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py --server.address localhost
```

Die App öffnet sich unter `http://localhost:8501`. Mit `--server.address localhost` hört sie nur auf dem eigenen Rechner; ohne diese Angabe ist sie standardmäßig auch im lokalen Netz erreichbar. Für den Betrieb
im Unternehmen (eigener Server, interne Adresse) gilt dasselbe Vorgehen; dann bleibt die Datei im eigenen Netz. Der Upload-Hinweis in der App und die Obergrenzen (50 MB, 5000 Tickets) gelten auch dort.

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Gebaut mit Streamlit, Plotly und NumPy.

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html).
