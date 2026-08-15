# Design-Spec — Abschlusspaper „Computational Spatial Humanities"

**Datum:** 2026-08-15
**Autoren:** Jonas Paul (Text), Lucas Berger (Review)
**Format:** IEEE Conference (IEEEtran), **max. 6 Seiten**, Sprache **Englisch**
**Gegenstand:** auerbachs-auge.tech — Leipzig Open Data Platform

---

## 1. Kernthese

> **Veröffentlichung ist noch keine Transparenz.** Transparenz ist keine Eigenschaft
> publizierter Daten, sondern der Infrastruktur, die sie vergleichbar macht.

Leipzig publiziert 398 Datensätze aus 37 Ämtern und erfüllt damit jeden Maßstab
gängiger Open-Data-Politik. Wir haben versucht, alle zu benutzen. Die Differenz
zwischen „publiziert" und „nutzbar" ist messbar — und wir haben sie gemessen.

Der technische Teil ist damit **Beweismittel, nicht Beiwerk**: Jede
Engineering-Entscheidung ist die Antwort auf eine benannte Hürde.

### Normative Haltung

Die liberale These (Transparenz → mündige Bürger → evidenzbasierte Entscheidungen)
wird **vertreten**, nicht relativiert — aber an der Gegenposition gehärtet:

- **Gurstein-Filter:** Fünf handgepflegte Register, ~300 Metriknormalisierungen und
  eine Raum-Alias-Tabelle sind die Hürde, an der nicht-technische Bürger scheitern.
  Wir haben sie beziffert.
- **Kostenargument (Originalbeitrag):** Wir *wollten* maximale Offenheit und konnten
  sie uns nicht leisten. Login-Schranke und kuratierte Whitelist sind
  **Kapazitätsentscheidungen** (4 GB VPS, kein Budget für Missbrauchsschutz;
  ungefilterte Rohmetriken führen in die Irre) — **keine** Gatekeeping-Entscheidungen.
  Kapazität ist ungleich verteilt. Wer Interpretation bezahlen kann, entscheidet,
  was transparent ist. Wir sind selbst der Beleg.
- **Folgerung:** Die Interpretationsschicht gehört in die öffentliche Infrastruktur,
  nicht ins Ehrenamt. Städte sollten an Benutzbarkeit gemessen werden, nicht an der
  Datensatzzahl.

---

## 2. Aufbau

Rechnung für IEEE-Zweispalter, 10 pt, Richtwert ~900 Wörter/Seite Text:

```
6,0 Seiten gesamt
− 1,2 Seiten  4 Abbildungen + 2 Tabellen
− 0,5 Seiten  Referenzen (~20 Einträge)
─────────────
= 4,3 Seiten Fließtext  ≈  3.900 Wörter
```

**Operativ ist die Wortzahl, nicht die Seitenzahl.** Die Wortbudgets unten summieren
sich auf 3.980 — das ist bewusst knapp über dem Ziel, damit beim Kürzen Substanz
bleibt. Wer über 4.200 Wörter kommt, muss nach der Kürzungsreihenfolge in Abschnitt 9
streichen, nicht überall gleichmäßig verdünnen.

**Epigraph** (vor Abschnitt I):
> „Denn was man schwarz auf weiß besitzt, / Kann man getrost nach Hause tragen."
> — Goethe, *Faust I*, V. 1966 f.

Englische Übersetzung im Fließtext oder Fußnote; Originalvers stehen lassen.

### I. Introduction — ~500 W.

- Leipzig: 398 Datensätze, 13 Kategorien, 37 Ämter → nach Politikmaßstab transparent.
- Wendung: Wir haben versucht, alle zu benutzen. Publikation und Benutzbarkeit sind
  zwei verschiedene Leistungen.
- Thesensatz (s. o.).
- Namenserklärung: *Auerbachs Keller* — Schauplatz in Goethes *Faust I*, real in
  Leipzig; *Auge* = Sichtbarmachung.
- **Contributions** (IEEE-Konvention, vier Punkte):
  1. Produktivplattform, die das gesamte Portal (398 Datensätze, zwei heterogene
     Quellen) in *ein* räumlich und zeitlich verknüpfbares Modell überführt.
  2. Empirische Taxonomie der Reibungen zwischen publiziert und nutzbar, mit
     Vorher/Nachher-Messung.
  3. Durchgerechnete räumliche Fallstudie samt der methodischen Leitplanken, die sie
     erfordert — inklusive MAUP-Demonstration an eigenen Daten.
  4. Argument über die Infrastrukturkosten von Transparenz, belegt an den eigenen
     Beschränkungen.

### II. Background and Related Work — ~450 W.

- Open-Data-Politik und Transparenzversprechen — **kurz** (2–3 Sätze).
- Gegenliteratur: Gurstein (empowering the empowered), Kitchin et al. (urban
  indicators/dashboards), Mattern (*Mission Control*, Dashboard-Kritik — trifft uns
  selbst, deshalb unverzichtbar).
- Drucker als konzeptueller Anker: *capta*.
- Räumliche Methodik **hier** einführen, damit Abschnitt V sie nur noch anwendet:
  Tobler (First Law), Openshaw (MAUP: Skalen- und Zonierungsproblem),
  Robinson (ökologischer Fehlschluss).
- **Lückenaussage:** Leipzigs eigene 15 Portal-Anwendungen bedienen je einen
  Datensatz oder ein Thema. Keine verknüpft über das Portal hinweg.

### III. The Data Landscape and Its Frictions — ~600 W. + **Tabelle I**

Zuerst fair sein (kostet nichts, kauft Glaubwürdigkeit): gute Zugänglichkeit,
maschinenlesbare Formate, Aktualisierung bis täglich, reiche Metadaten,
funktionierende Kontaktwege. Zwei Quellen mit unterschiedlichen Paradigmen:
`opendata.leipzig.de` (CKAN/DCAT) und `statistik.leipzig.de` (Wide-by-Year-API).

**Tabelle I — Taxonomie der Reibung.** Spalten: *Reibungstyp · konkretes Beispiel ·
Umfang · Kosten*.

| # | Reibungstyp | Beispiel | Umfang |
|---|---|---|---|
| 1 | Formatheterogenität | CSV mit wechselnden Trennzeichen/Encodings, GeoJSON, JSON, XLSX, SHP | portalweit |
| 2 | Strukturheterogenität | Wide-by-Year (Kennziffer × Jahr/Quartal/Schuljahr; Gebiet × Sachmerkmal), erfordert Melt | 174 Datensätze luden anfangs 0 Zeilen |
| 3 | Raumbezugsheterogenität | Ortsteilname vs. -nummer vs. Wahlbezirk vs. lat/long vs. gar nichts | kein gemeinsamer Schlüssel |
| 4 | Zeitheterogenität | täglich bis nie; als `live` getaggte statische Daten (GTFS-Sollfahrplan, Straßennetz) | 16 als live markiert, 3 fachlich live |
| 5 | Semantische Opazität | `Unnamed: 10`, `25 bis unter 55 ahre`, Identifikatoren als Metrik, Raumeinheiten als Metrik, Wahljahr auf 1994 kollabiert | 1.351 „Metriken" auf Stadtebene |
| 6 | Entitätsfragmentierung | ein Phänomen über Jahre zersplittert (Vornamen 2014–2025, BTW 2021/2025) | die Zahl 398 überzeichnet die Zahl distinkter Phänomene |

**Schlusssatz des Abschnitts (wichtig):** Keine dieser Reibungen verletzt eine
Open-Data-Richtlinie. Alle sind konform. Genau das ist der Punkt — Konformität wird
bei der *Veröffentlichung* gemessen, nicht bei der *Nutzung*.

### IV. System Design — ~750 W. + **Abb. 1**

- Anforderung direkt aus III abgeleitet: *eine* Raumachse, *eine* Zeitachse,
  *ein* Semantikregister.
- Pipeline: `raw_ingest → staging → core → mart` (materialisierte Sichten,
  CONCURRENTLY refreshed).
- **Die fünf kuratierten Register als Kernbeitrag** — explizit als *Handarbeit*
  ausweisen, denn das ist die Interpretationsleistung, die „maschinenlesbar" nicht
  mitliefert:
  `dataset_contracts.json` (398 Einträge: Schedule, beste Resource, Format, has_geo) ·
  `dataset_families.json` (Jahresvarianten → logische Datensätze + Loader-Hints) ·
  `dataset_categories.json` (CKAN-Gruppen + statistik `kategorie_nr`) ·
  `election_definitions.json` (Spalte→Partei je Wahl, gegen die benannten Anteile der
  statistik-API verifiziert) · `indicator_catalog.json` (kanonisches Indikatorregister).
- **Eigener Absatz zur Raumauflösung** — wichtigste Einzelentscheidung des Systems:
  `core.spatial_aliases` → `core.resolve_spatial_key()` → kanonischer `spatial_code`
  → Join auf `core.admin_boundaries` (63 Ortsteile, 10 Stadtbezirke, 819 Wahlbezirke).
- Auslieferung: PostGIS `ST_AsMVT` Vector Tiles mit Per-Tile-Redis-Cache
  (Invalidierung über `tiles:version`), FastAPI (async psycopg3), React 18 +
  MapLibre GL.
- **Betriebsfenster hier setzen**, damit Abschnitt VI damit argumentieren kann:
  ein 4-GB-VPS, Docker Compose, nightly 02:00 UTC + 5-Minuten-Live-Schleife.

### V. Results — ~700 W. + **Tabelle II** + **Abb. 2, 3, 4**

**A. Abdeckung** (Tabelle II, Vorher/Nachher — Daten s. Abschnitt 5 dieser Spec).

Der entscheidende Satz: **Das Portal hat sich zwischen den beiden Messpunkten nicht
verändert.** Die Differenz ist keine Datenverbesserung, sondern die Menge an
Interpretationsarbeit, die nötig war. *Das* ist die Messung der Reibung.

Zwei Rückgänge **ehrlich als Korrektur ausweisen**, nicht verschweigen:
`geo_features` 4.175.146 → 489.011 und `traffic_restrictions` 30.999 → 1.421 sind
Deduplizierung (volatile WFS-Properties erzeugten Dubletten je Lauf) plus
Retention — also Qualitätsgewinn, nicht Datenverlust.

**B. Fallstudie** (Methodik s. Abschnitt 3 dieser Spec).

**C. Leitplanken als Systemeigenschaft** — implementiert, nicht bloß gefordert:
Korrelation nur bei identischer Raumeinheit und identischem Jahr; kuratierte
Metrik-Whitelist (roher `metric_name` erreicht nie das UI); ökologischer Fehlschluss
(Robinson) explizit benannt; **MAUP an eigenen Daten vorgeführt** (Abschnitt 4).

### VI. Discussion: Transparency and Its Infrastructure — ~650 W.

Erntet, was III–V gesät haben. Vier Bewegungen:

1. **Arbeitsargument** — die bezifferte Hürde (Register, Normalisierungen,
   Alias-Tabelle). Gursteins Filter ist genau das.
2. **Kostenargument** — s. Abschnitt 1. Login und Whitelist als Kapazitätsfolge.
3. **Konkrete Empfehlungen an publizierende Städte:** stabile Raumschlüssel über
   Datensätze hinweg · Long-Format statt Wide-by-Year · maschinenlesbare
   Indikatordefinitionen · ein Datensatz je Phänomen mit Jahresdimension.
4. **Gegen Dashboard-Solutionismus** (Mattern): Ein Dashboard erzeugt keine mündigen
   Bürger. Es senkt genau eine Hürde. Das offen zu sagen belegt, dass wir die eigene
   These kritisch halten — und macht sie stärker, nicht schwächer.

Positiver Schluss: Nüchterne Datenlage *und* die Leitplanken, sie zu lesen. Beides
sind Engineering-Fragen.

### VII. Limitations and Future Work — ~200 W.

Login-Schranke · 48 von 398 Datensätzen weiterhin ohne Daten · kein GTFS-Realtime ·
n = 63 bzw. n = 10 · Korrelation ≠ Kausalität · nur eine Stadt (Städtevergleich als
Ausblick) · Barrierefreiheit offen · Abhängigkeit von der Verfügbarkeit des Portals.

### VIII. Conclusion — ~130 W. · References — ~20 Einträge, ~0,5 S.

---

## 3. Fallstudie — Methodik

**Wahl: Europawahl 2024 (`ew2024`).** Begründung: die **einzige** Wahl im Bestand mit
nativen Ergebnissen auf **beiden** Ebenen — Ortsteil (2.142 Zeilen / 63 Gebiete) und
Stadtbezirk (340 Zeilen / 10 Gebiete). Nur damit ist die MAUP-Demonstration ohne
selbst aggregierte Wahlergebnisse möglich. Zusätzlich politisch weniger aufgeladen
als LTW/BTW, was der Lesart als Methodendemonstration entgegenkommt.

**Jahr: 2024** für Wahl *und* Indikatoren (Indikatoren decken 2020–2025 ab).

**Parteien: mehrere berichten, nicht eine.** Sonst liest sich das Paper als politische
Aussage statt als Methodendemonstration — und unterläuft damit die eigene
Leitplanken-Argumentation. Vorschlag: die vier bis fünf stimmstärksten Listen.

**Indikatoren — nur aus summierbaren Zählgrößen bilden**, dann auf jeder Ebene neu
normalisieren. Das vermeidet Gewichtungsfehler bei der Aggregation:

| Indikator | Konstruktion |
|---|---|
| Arbeitslosenanteil | `Arbeitslose insgesamt` / `Einwohner insgesamt` |
| Ausländeranteil | `Ausländer` / `Einwohner insgesamt` |
| Alleinerziehendenanteil | `Alleinerziehende insgesamt` / `Familien insgesamt` |

> **Nicht** die fertigen Quoten (`Ausländeranteil`, `Altenquote`, `Durchschnittsalter`,
> `Einwohnerdichte`) für die MAUP-Demo verwenden — sie sind Raten und ließen sich nur
> bevölkerungsgewichtet aggregieren. Für die reine Ortsteil-Korrelation sind sie
> zulässig, für den Ebenenvergleich nicht.

**Statistik:** Pearson r, R², p-Wert. Darstellung als kleine Matrix
(Parteien × Indikatoren) im Text plus **ein** Scatter als Abbildung.

**Zu verifizieren vor der Auswertung** (offene Implementierungsfragen):

- In welcher Spalte liegen die Europawahl-Stimmen — `zweitstimmen`/`gueltige_zweit`
  oder `erststimmen`/`gueltige_erst`? Die EuW kennt nur eine Stimme.
- Was zählt `55 Jahre und älter` (Ø 118,7) und `25 bis unter 55 ahre` (Ø 468)
  tatsächlich? Für Einwohner-Altersgruppen bei Ø 12.052 Einwohnern je Ortsteil sind
  die Werte zu klein — vermutlich **Arbeitslose nach Altersgruppe**. Vor jeder
  Verwendung klären. (Nebenbei ein perfektes Belegbeispiel für Reibungstyp 5.)

---

## 4. MAUP-Demonstration

Dieselbe Korrelation (eine Partei × ein Indikator) auf zwei Aggregationsebenen:

- **Ortsteil:** n = 63
- **Stadtbezirk:** n = 10

Wahlergebnisse liegen für `ew2024` auf beiden Ebenen **nativ** vor. Die
Sozialindikatoren liegen **nur** auf Ortsteilebene vor (`core.statistics.spatial_unit`
kennt nur `ortsteil`, `city`, `custom` — **kein** `stadtbezirk`) und müssen aggregiert
werden. Das ist gedeckt: `core.admin_boundaries` hat `parent_code` für **alle 63
Ortsteile**, verweisend auf **10 Stadtbezirke**.

Aggregation: Zählgrößen je Stadtbezirk summieren, Anteil danach neu bilden.

Berichtet wird Δr zwischen den Ebenen. Erwartung nach Openshaws Skaleneffekt: |r|
steigt bei gröberer Aggregation. Der Verlust an statistischer Aussagekraft bei n = 10
ist dabei nicht Schwäche, sondern **Teil des Arguments** — dieselben Daten, andere
Zonierung, anderes Ergebnis.

---

## 5. Datenstand (verifiziert)

Alle Zahlen direkt aus der Produktionsdatenbank (`leipzig-data-db-1`, VPS) erhoben.

**Basislinie 2026-06-10** — aus `docs/datensatz-analyse.md`
**Messpunkt 2026-08-15** — aus Live-Abfragen dieser Session

| Kennzahl | 2026-06-10 | 2026-08-15 |
|---|---:|---:|
| Registrierte Datensätze | 398 | 398 |
| …mit Daten in Kerntabellen | 152 (38 %) | **350 (88 %)** |
| Statistikzeilen | 5.925 | **377.083** |
| Statistik-Datensätze | 122 | **299** |
| Wahlergebniszeilen | 0 | **79.553** |
| Geo-Datensätze | 29 | **35** |
| Geo-Feature-Zeilen | 4.175.146 | 489.011 *(dedupliziert)* |
| Verkehrseinschränkungen | 30.999 | 1.421 *(dedupliziert + Retention)* |

**Analysefläche Ortsteilebene (2026-08-15):** 341.945 Zeilen · 67 Datensätze ·
300 Metriken · 305.037 Zeilen mit aufgelöstem `spatial_code` · 63 Ortsteile ·
Jahre 2020–2025.

**Stadtebene:** 34.839 Zeilen · 233 Datensätze · 1.351 „Metriken" · **0** mit
`spatial_code` — der Beleg für Reibungstyp 5.

**Wahlen im Bestand:** `btw2021`, `btw2025`, `ew2024`, `ltw2024`, `srw2024`.
Auf Ortsteilebene: alle außer `btw2025`. Auf Stadtbezirksebene: **nur** `ew2024`.

**Verwaltungsgrenzen:** 63 Ortsteile (alle mit `parent_code`) · 10 Stadtbezirke ·
819 Wahlbezirke.

---

## 6. Abbildungen und Tabellen

Budget: **4 Abbildungen + 2 Tabellen.**

| Element | Inhalt | Quelle |
|---|---|---|
| Abb. 1 | Systemarchitektur, 7 Services + Datenfluss | Neu zeichnen nach `docs/ARCHITECTURE.md` |
| Abb. 2 | Choroplethe: Parteianteil je Ortsteil | Screenshot der Plattform oder matplotlib aus DB |
| Abb. 3 | Korrelations-Scatter mit Trendlinie und R² | matplotlib, Vektor-PDF |
| Abb. 4 | MAUP-Zweipanel: n = 63 vs. n = 10 | matplotlib; bei Platznot in Abb. 3 falten |
| Tab. I | Taxonomie der Reibung (6 Zeilen) | Abschnitt III |
| Tab. II | Abdeckung vorher/nachher | Abschnitt 5 dieser Spec |

Alle Abbildungen als **Vektor-PDF** für LaTeX. Vor dem Schreiben von Chart-Code die
`dataviz`-Skill laden (Farbwahl, Achsen, Lesbarkeit in Graustufen — IEEE-Drucke sind
oft schwarzweiß).

---

## 7. Zitat-Ökonomie

Vier Zitate mit klarer Arbeitsteilung statt eines dekorativen:

| Stelle | Zitat | Funktion |
|---|---|---|
| Epigraph | Goethe, *Faust I*, V. 1966 f. | Verbindet Projektnamen und These: Besitz ≠ Verständnis |
| Abschn. II | Drucker: „data are capta, taken not given" | Konzeptueller Anker der Datenkritik |
| Abschn. V | Tobler, First Law of Geography | Rechtfertigt räumliche Korrelation als Methode |
| Abschn. VI | Gurstein: „empowering the empowered" | Gegenposition, an der die These gehärtet wird |

### Literaturverzeichnis — verifiziert am 2026-08-15

Alle Angaben per Websuche gegen die Verlagsseiten geprüft:

1. **Drucker, J. (2011).** Humanities Approaches to Graphical Display.
   *Digital Humanities Quarterly* 5(1).
   Wörtlich: „data are capta, taken not given, constructed as an interpretation of the
   phenomenal world, not inherent in it."
2. **Gurstein, M. B. (2011).** Open data: Empowering the empowered or effective data
   use for everyone? *First Monday* 16(2). DOI 10.5210/fm.v16i2.3316
3. **Tobler, W. R. (1970).** A Computer Movie Simulating Urban Growth in the Detroit
   Region. *Economic Geography* 46, 234–240. DOI 10.2307/143141
   *(Taylor & Francis führt den Band als 46/sup1; gängige Zitierweise 46(2). Eine
   Variante wählen und konsistent halten.)*
4. **Openshaw, S. (1984).** The Modifiable Areal Unit Problem. *CATMOG* 38.
   Geo Books, Norwich. Skalen- und Zonierungsproblem.
5. **Robinson, W. S. (1950).** Ecological Correlations and the Behavior of
   Individuals. *American Sociological Review* 15(3), 351–357. DOI 10.2307/2087176
6. **Mattern, S. (2015).** Mission Control: A History of the Urban Dashboard.
   *Places Journal*, März 2015. DOI 10.22269/150309
7. **Kitchin, R., Lauriault, T. P., & McArdle, G. (2015).** Knowing and governing
   cities through urban indicators, city benchmarking and real-time dashboards.
   *Regional Studies, Regional Science* 2(1), 6–28.
   DOI 10.1080/21681376.2014.983149
8. **Goethe, J. W. (1808).** *Faust. Der Tragödie erster Teil.* V. 1966 f.,
   Studierzimmer II (Schülerszene), gesprochen vom Schüler.
   Kanonischer Wortlaut beginnt mit „Denn".

Verbleibend zu ergänzen (noch nicht geprüft): EU Open Data Directive (2019/1024),
deutsches Open-Data-Gesetz, CKAN/DCAT-Referenz, MapLibre/PostGIS-Referenzen sowie
2–4 weitere DH-/Critical-Data-Studies-Titel nach Bedarf. **Jede neue Quelle vor
Aufnahme prüfen — nicht aus dem Gedächtnis zitieren.**

---

## 8. Werkzeuge und Arbeitsweise

**Lokal verfügbar (geprüft):** TeXLive 2025 (`pdflatex`, `xelatex`, `latexmk`),
`pandoc`, Python mit matplotlib 3.10.9 / pandas 3.0.3 / numpy 2.4.6.
Kein Overleaf nötig.

**Verzeichnisvorschlag:**

```
paper/
├── main.tex              # IEEEtran
├── refs.bib
├── figures/              # Vektor-PDFs
└── analysis/             # Abfragen + Auswertung, reproduzierbar
```

**Datenzugriff:** `ssh -i ~/.ssh/leipzig_deploy deploy@auerbachs-auge.tech`
→ `docker exec leipzig-data-db-1 psql -U leipzig -d leipzig_data`

**Arbeitsreihenfolge:**

1. **Analyse** — Abfragen und Auswertung als reproduzierbares Skript, nicht als
   Ad-hoc-Kommandos. Aggregations- und Korrelationsfunktionen als reine Funktionen
   mit ein bis zwei Tests gegen handgerechnete Werte. Zahlen im Paper dürfen nur aus
   diesem Skript stammen.
2. **Abbildungen** — `dataviz`-Skill vor dem ersten Chart. Vektor-PDF.
3. **Text** — IEEEtran, abschnittsweise in der Reihenfolge III → IV → V → VI → II → I
   → VII → VIII. Einleitung zuletzt, wenn die Befunde feststehen.
4. **Review** — Lucas liest das Ganze; Analyse-Code separat prüfen lassen.

---

## 9. Risiken und offene Punkte

| Risiko | Umgang |
|---|---|
| **Seitenüberlauf.** Der Entwurf ist für 6 Seiten ambitioniert. | Kürzungsreihenfolge festlegen: zuerst Abb. 4 in Abb. 3 falten, dann Abschnitt II straffen, dann Tabelle I auf vier Zeilen. Abschnitte V und VI **nicht** kürzen — sie tragen das Paper. |
| **EuW-Stimmenspalte unklar.** | Vor der Auswertung verifizieren (Abschnitt 3). |
| **Semantik von `55 Jahre und älter` unklar.** | Vor Verwendung klären; taugt sonst als Negativbeispiel statt als Indikator. |
| **n = 10 bei der MAUP-Demo.** | Kein Mangel, sondern Teil des Arguments — explizit so schreiben, nicht wegerklären. |
| **Politische Lesart der Fallstudie.** | Mehrere Parteien berichten, Methodendemonstration in den Vordergrund. |
| **Zahlen veralten.** | Messpunkt mit Datum benennen („Stand 15. August 2026"), nicht als zeitlos darstellen. |

## 10. Nicht im Scope

Keine Kausalanalyse · keine Mehrstädtevergleiche · keine neuen Plattform-Features
für das Paper · keine Behebung der 48 verbleibenden ungeladenen Datensätze ·
keine Öffnung der Login-Schranke.
