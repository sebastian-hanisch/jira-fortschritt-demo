# Jira-Fortschritt: gewichtet über Status, Story Points und Ebenen – interaktive Streamlit-Demo

**[→ Demo live ausprobieren](https://sebastianhanisch-jira-fortschritt-demo.streamlit.app/)**

Fall-Demo auf der Website „Sebastian Hanisch – Operations Research und Machine Learning“ (Datenanalyse: Kennzahlen aus Ticketdaten und ihre Abhängigkeit von Annahmen). Die App rechnet an einem
**erzeugten Beispielprojekt** (Tickets mit Status, Story Points, Sprints, Teams und Hierarchie, wie ein Jira-Export sie liefert) einen **gewichteten Projektfortschritt**: Jeder Status zählt mit einem wählbaren
Anteil (To Do 0 %, in Arbeit 50 % oder eigene Werte, Done 100 %), jedes Ticket wiegt seine **Story Points** (oder 1), und das Ergebnis lässt sich über mehrere **Aggregationsebenen** zeigen: Gesamtprojekt, Epic,
Sprint, Release, Komponente, Label, Bearbeiter, Team, Bereich, Priorität, Ticket-Typ und Status, auf Wunsch zwei Ebenen als Kreuztabelle. Die Auswertung lässt sich auf ein **Teilprojekt** (ein Ticket als
Wurzel) beschränken, und ein **Hierarchiegraph** zeigt den Baum mit Gewicht und Fortschritt je Knoten. Dazu kommen eine **Zusammenfassung zum Kopieren** (Markdown), die **Ticketliste** des Beispielprojekts und sechs
**Tabellen** (je Gruppe, Status × Gruppe, Beitrag zum Fortschritt, Status-Übersicht, Erledigt je Monat, Datenqualität), jede als CSV ladbar. Die Demo liest keine Jira-Datei und verbindet sich nicht mit Jira.

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
Das Beispielprojekt hat die gewöhnlichen Status (Backlog, To Do, In Progress, In Review, Testing, Done).

## Methodik

- **Teilprojekt und Hierarchiegraph.** Ein Ticket mit Kindern lässt sich zur Wurzel wählen; dann zählen nur die Tickets der Zählebene im Teilbaum (die Wurzel selbst eingeschlossen), und alles Weitere (Median für Ungeschätztes, Kennzahlen, Tabellen, Zusammenfassung, Sensitivität) bezieht sich darauf. Die Wahl steht nicht in der Adresszeile. Der Graph zeichnet Projekt oder Teilprojekt von links nach rechts mit Knotengröße = Gewicht und Farbe = Fortschritt; ab 250 Knoten wird die tiefste Ebene zusammengefasst, Eltern-Verweise im Kreis zählen je Ticket einmal.
- **Aggregation.** Die Ebene ist ein Gruppenschlüssel je Ticket; Sub-Tasks erben Sprint, Komponente und Release vom übergeordneten Ticket, bei mehreren Sprints zählt der letzte.
  Die Summen laufen vektorisiert über `np.bincount`.
- **Beispielprojekt.** `jira_scenario.py` erzeugt aus Epic-Zahl und Zufalls-Seed deterministisch Epics mit Stories, Bugs, Tasks und Sub-Tasks (Story Points aus der Fibonacci-Skala, ein Teil ungeschätzt, Sprints mit übernommenen Tickets, Komponenten, Labels, Releases, Teams, Bereiche, Prioritäten) mit dem SplitMix64-Zufallsgenerator des Portfolios; die App zeigt jedes Ticket in einer Tabelle.
- **Tabellen.** `jira_tables.py` baut aus der Auswertung reine Zeilen: Status × Gruppe (Gewicht, Tickets oder angerechnetes Gewicht je Zelle, mit Summen), Beitrag je Gruppe in Prozentpunkten (die Beiträge summieren sich zum Gesamtfortschritt), Gewicht und Anrechnung je Status, erledigtes Gewicht je Kalendermonat und acht Prüfungen der Eingangsdaten (ohne Story Points, ohne Epic, ohne Sprint, erledigt ohne Lösungsdatum, Lösungsdatum vor Erstelldatum, erledigte Story mit offenen Sub-Tasks, uneinheitliche Statuskategorie) samt Liste der ungeschätzten Tickets.
- **Prüfung in der App.** `check_consistency` prüft bei jedem Lauf, dass Gruppengewichte und Ticketzahlen sich zum Gesamtwert summieren und kein Fortschritt außerhalb von 0 bis 100 %
  liegt und die Beiträge der Gruppen den Gesamtfortschritt ergeben; bei Verletzung zeigt die App einen Fehler statt einer stillen falschen Zahl.

## Befunde (gemessen, keine Behauptungen)

Das Beispielprojekt ist erzeugt (`jira_scenario.py`); die Zahlen zeigen den Mechanismus, keine Aussage über echte Projekte. Standardprojekt: 6 Epics, Zufalls-Seed 3, 78 Tickets
(davon 28 Sub-Tasks), also 44 Stories, Tasks und Bugs mit zusammen 177 Story Points (Median-Regel; 7 davon ungeschätzt). Der Seed ist so gewählt, dass alle Merkmale vorkommen
(übernommene Sprints, Sub-Tasks, ungeschätzte Tickets); er ist eine Beschreibung, kein Befund.

| Frage | Befund | Test |
|---|---|---|
| Wie weit ist das Standardprojekt je nach Voreinstellung? | Linear 54,0 %, streng (nur Done) 43,5 %, Workflow-Stufen mit Sub-Tasks 62,0 %; nur Done nach Ticketzahl 52,3 % | `test_default_progress_under_each_preset` |
| Wie groß ist die Spanne über die drei Schemata und die beiden Gewichtungen? | 43,5 % bis 68,0 %: 24,5 Prozentpunkte beim Standardprojekt | `test_default_sensitivity_range` |
| Ist das ein Zufall des Standardprojekts? | Über 10 feste Beispielprojekte liegt Linear im Median 7,2 Prozentpunkte über „nur Done“ (1,3 bis 11,5), und die Spanne über alle Annahmen beträgt im Median 17,0 Prozentpunkte (8,0 bis 19,3) | `test_linear_minus_only_done_over_the_fixed_projects`, `test_sensitivity_spread_over_the_fixed_projects` |
| Was bringt die Sub-Task-Option? | Beim Workflow-Schema hebt sie das Standardprojekt von 61,4 % auf 62,0 % | `test_blend_lifts_the_workflow_scheme_on_the_default_project` |

Dass „Linear“ über „nur Done“ liegt, folgt aus der Konstruktion (die Gutschriften sind nie kleiner); gemessen wird hier, **wie viel** das ausmacht. Welche der Zahlen die richtige ist,
beantwortet die Demo nicht: Das hängt davon ab, was berichtet werden soll (Lieferstand, Arbeitsstand oder Restaufwand).

## Ehrliche Grenzen

- **Die Status-Gewichte sind Annahmen, keine Messung.** Wer „In Review zählt 80 %“ begründen will, braucht die Historie des eigenen Teams.
- **Die Beispielzahlen gelten für das erzeugte Beispiel.** In echten Projekten kann die Spanne kleiner oder größer sein; die Demo zeigt, wie man sie für das eigene Projekt bestimmt.
- **Story Points sind teamintern.** Ein Gesamtwert über mehrere Teams mischt Maßstäbe.
- **Ungeschätzte Tickets verschieben die Zahl**, je nach Regel in eine andere Richtung; die App meldet, wie viele betroffen sind.
- **Der Verlauf kennt nur „erledigt“.** Eine Statushistorie (wann ging das Ticket in Review?) liegt in den gelesenen Feldern nicht vor.
- **Die Demo rechnet nur mit erzeugten Daten.** Ob die Zahlen eines echten Projekts ähnlich ausfallen, sagt sie nicht; sie zeigt, wie man die Abhängigkeit von den Annahmen für ein eigenes Projekt bestimmen würde.

## Verifikation

- **Kern:** jede Einheit (Status-Gutschrift, Gewichte, Sub-Task-Mischung, Gruppierung, Kreuzgruppen, Aggregation, Burn-up, Flächenbaum) gegen Handrechnung an der Mini-Instanz
  (`tests/conftest.py`).
- **Orakel:** `tests/test_oracle_jira_fortschritt.py` vergleicht den vektorisierten Kern in jeder Ebene gegen eine Schleifenfassung in exakter Bruchrechnung (`fractions`) auf erzeugten
  Projekten und prüft Eigenschaften: Skalierung der Story Points, Reihenfolge der Tickets, Monotonie der Gutschriften, Burn-up gegen direktes Zählen.
- **Beispielprojekt und Hierarchie:** Beispielprojekt gegen Handzählung (Zahl der Tickets, Eltern, Sprints), Teilbaum, Hierarchiegraph und Teilprojekt-Auswertung an einem handgebauten Baum, dazu ein unabhängiges Orakel für jede wählbare Wurzel (`tests/test_scope_graph.py`).
- **Zwischenspeicher und Netz:** Test, dass nur die Erzeugung des Beispielprojekts zwischengespeichert wird (`st.cache_data`) und dass weder eine Netzwerkbibliothek noch ein Eingabefeld für Zugangsdaten im Code steckt.
- **Tabellen und Zusammenfassung:** jede gegen Handrechnung an der Mini-Instanz, dazu Orakel in Bruchrechnung (Status × Gruppe in allen drei Kennzahlen, Beitrag, Status-Übersicht, Erledigt je Monat gegen direktes Zählen), Randfälle (leeres Projekt, kein Gewicht, Gewicht unter 1) und CSV-Format.
- **Verdikte** als reine Funktionen an handgesetzten Werten (Schwellen inklusive, jede Zahl im Text); **Randfälle** (leeres Projekt, ein und zwei Tickets, alles ungeschätzt, Gewicht 0).
- **Presets, Layout, Oberfläche:** AppTest-Rauchtest (jeder Button, jeder Regler am Minimum und Maximum, jede Option jeder Auswahl, Kombinationen der Ebenen, Eigene Gewichte, Teilprojekt, Ticketliste, Permalink), Schnellstart oben in der Seitenleiste mit hervorgehobenem aktivem Preset (`tests/test_layout.py`), Footer-Test, Laufzeit-Importe.
- **Zahlen im README** stehen in `tests/test_claims.py`.
- **Mutationstest:** Vollauf über alle Stellen von `jira_algorithm.py`, `jira_evaluation.py` und `jira_tables.py` (289 Stellen) (`tools/mutate_demo.py`, Stand `tests/mutation_state.json`): alle Mutanten gefangen bis auf sechs äquivalente (Toleranzgrenze der Ticketzählung in `check_consistency`, erst ab Millionen Tickets wirksam; zwei Randvergleiche der Zusammenfassung bei genau 40 Gruppen, wo beide Zweige dasselbe liefern; zwei Randwerte beim Aufbau des Hierarchiegraphen und eine Schleifengrenze der Baumsuche, die sich nie auswirken). Nicht gemutet: Beispielprojekt, Darstellung.

## Dateistruktur

| Datei | Zweck |
|---|---|
| `.github/workflows/tests.yml` | CI: Push, Pull Request, wöchentlicher Canary |
| `.gitignore` | venv, Caches, Streamlit-Secrets |
| `.streamlit/config.toml` | Streamlit-Einstellungen (keine Nutzungsstatistik) |
| `app.py` | Streamlit-App: Beispielprojekt, Status-Gewichte, Ergebnis, Ebenen, Teilprojekt, Hierarchiegraph, Kernfrage, Erklärungen |
| `jira_algorithm.py` | Kern: Gutschriften, Gewichte, Gruppierung, Aggregation, Burn-up, Flächenbaum |
| `jira_constants.py` | Regler-Grenzen, Gewichte-Schemata, Farben, Presets |
| `jira_evaluation.py` | `analyse`, Sensitivitätsprüfung, Verdikte, `check_consistency` |
| `jira_layout.py` | Fester Kopf (Stylesheet) |
| `jira_presets.py` | Permalink, Presets (Schnellstart in der Seitenleiste, aktives Preset hervorgehoben), Zufalls-Seed-Button |
| `jira_rng.py` | SplitMix64 (Portfolio-Konvention für Zufall), wortgleich aus `ab-test-demo` |
| `jira_tables.py` | Tabellen: Ticketliste, Status × Gruppe, Beitrag, Status-Übersicht, Erledigt je Monat, Datenqualität, CSV-Format |
| `jira_scenario.py` | Datenmodell `Issue` und erzeugtes Beispielprojekt |
| `jira_visualization.py` | Plotly-Abbildungen (Achsen gesperrt) |
| `requirements-dev.txt` | Laufzeit plus pytest |
| `requirements.txt` | Laufzeit-Bibliotheken (ungepinnt) |
| `tests/` | Mini-Instanz, Orakel, Teilprojekt und Graph, Verdikte, Randfälle, Presets, Layout, AppTest, Claims, Footer, Laufzeit-Importe |

## Bewusst nicht umgesetzt

- **Prognose** („wann ist das Projekt fertig?“): Das braucht ein Modell für Tempo und Umfangsänderungen und wäre eine eigene Demo.
- **Einlesen eigener Jira-Daten** (Datei-Upload oder Anbindung an die Jira-Schnittstelle): bewusst nicht Teil dieser Demo; sie rechnet nur mit dem erzeugten Beispielprojekt. Zugangsdaten und Ticketdaten
  gehören nicht in eine öffentlich gehostete Demo.
- **Statushistorie** (Changelog der Jira-Schnittstelle) für einen Burn-up mit Status-Gewichten: lässt sich nachrüsten, kostet aber einen Aufruf je Ticket.
- **PDF-Export**: Alle Tabellen lassen sich als CSV laden.
- **Mehrfach-Projekt-Ansichten.**

## Lokal ausführen

Die App läuft auch auf dem eigenen Rechner. Sie baut keine Verbindung ins Netz auf (kein Netzwerkcode, ein Test prüft das); installiert werden die Bibliotheken einmalig über `pip`. Voraussetzung: Python 3.12 oder neuer.

```bash
git clone https://github.com/sebastian-hanisch/jira-fortschritt-demo.git
cd jira-fortschritt-demo

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py --server.address localhost
```

Die App öffnet sich unter `http://localhost:8501`. Mit `--server.address localhost` hört sie nur auf dem eigenen Rechner; ohne diese Angabe ist sie standardmäßig auch im lokalen Netz erreichbar.

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Gebaut mit Streamlit, Plotly und NumPy.

---

Diese Demo ist Teil des Portfolios von [Sebastian Hanisch](https://sebastianhanisch.net) – Operations Research und Machine Learning ([Über mich](https://sebastianhanisch.net/ueber-mich.html)). Mehr zu den Demos: [Interaktive Demos](https://sebastianhanisch.net/demos.html).
