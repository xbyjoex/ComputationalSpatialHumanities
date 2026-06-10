# Datensatz-Analyse & Lagebild-Konzept

> Vollständige Bestandsaufnahme aller 398 registrierten Leipzig-Datensätze, erhoben
> direkt auf der Produktions-Datenbank (VPS, `leipzig-data-db-1`) am 2026-06-10.
> Ziel: Grundlage, um Quellen-, Ebenen- und Metrik-Auswahl im Lagebild neu zu bauen
> und jeden Datensatz einzeln einzuordnen (kartierbar? live-sinnvoll? wie laden? wie
> visualisieren?). Rohinventar liegt unter `.inventory/`.

---

## 1. Kernbefunde (TL;DR)

| Fakt | Zahl | Bedeutung |
|------|------|-----------|
| Registrierte Datensätze | **398** | `core.datasets` |
| …mit echten Daten in Kerntabellen | **152** (38 %) | Rest ist im UI faktisch unsichtbar |
| …**ohne** Kerndaten | **246** (62 %) | extrahiert, aber nicht geladen oder fehlgeschlagen |
| Geo-Features (kartierbar) | **29** Datensätze / 4,17 Mio Zeilen | dominiert von Baumkataster (3,59 Mio) |
| Statistik (Zeit/Verteilung) | **122** Datensätze / 5.925 Zeilen | nur **19** davon auf Ortsteil-Ebene kartierbar |
| Verkehrseinschränkungen | **1** Datensatz / 30.999 (21.314 aktiv) | echter Live-Layer |
| Wahlergebnisse | **0** Zeilen | `election_results` leer, obwohl Domäne + Router existieren |

### Die vier großen Lücken

1. **174 statistik.leipzig.de-Datensätze werden erfolgreich geholt, aber mit 0 Zeilen
   geladen.** Der Melt/Loader erkennt ihr Layout nicht. Das ist der mit Abstand größte
   Hebel: von ~296 statistik-Datensätzen sind nur 122 (41 %) sichtbar.
2. **Live-Punktfeeds laden nicht.** Park+Ride-Belegung, Radzählstellen (genau die
   Beispiele aus dem Auftrag) werden extrahiert (`rows_extracted` > 0), aber nie nach
   `geo_features` geschrieben (`rows_loaded` = 0). Das Roh-Payload enthält nur
   `{"count": 7}` statt der Features → Extraktor-/Loader-Bug für diese Quellen.
3. **36 opendata-Downloads scheitern mit „Connection reset by peer".** Darunter fast
   alle **Wahlergebnis-CSVs** (Bundestag/Landtag/Stadtrat/Europa, Ortsteil-/Wahlbezirks-/
   Stadtergebnis) und Vornamensstatistik 2015–2019/2025.
4. **Datenqualität auch bei geladenen Statistiken mangelhaft.** Metriknamen wie
   `Unnamed: 10`, Ortsteile als „Metrik" statt als Raumdimension (Lebenserwartung),
   Punkt-Datensätze (Öffentliche Toiletten mit `lat`/`long`) als Ortsteil-Statistik
   fehlgeladen, Wahljahre auf „1994" kollabiert. Eine rohe Metrik-Dropdown-Liste ist
   damit unbrauchbar — **eine kuratierte Whitelist ist Pflicht.**

### Warum die aktuelle Ebenenkontrolle nicht funktioniert

Die heutige `LayerPanel.tsx` bietet 5 Layer: `park_ride`, `bicycle`, `restrictions`,
`choropleth`, `geo_features`.

- **`park_ride` und `bicycle` haben keine Daten** (tote Layer, Default-aktiv ist sogar
  `park_ride`).
- **`choropleth`** zieht rohe `metric_name`s (inkl. Müll wie `Unnamed: 10`, `lat`,
  `Straßenschlüssel`) und funktioniert real nur für ~5 saubere Ortsteil-Indikatoren.
- **`geo_features`** lässt **beliebige** Quellen frei kombinieren, ohne Semantik — daher
  die berechtigte Kritik „man kann random Features sinnlos verknüpfen".
- **105 stadtweite Statistik-Datensätze** (Zeitreihen ohne Ortsteilbezug) lassen sich
  **gar nicht** auf der Karte zeigen.

---

## 2. Wo die Daten wirklich liegen (Speicher-Realität)

Der `feature/data-unification`-Branch hat Geodaten in **einen** Layer zusammengeführt.
Die alten Domänen-Tabellen sind **leer** und nur noch Legacy:

| Tabelle | Zeilen | Status |
|---------|-------:|--------|
| `core.geo_features` | 4.175.146 | **aktiv** — vereinheitlichter Geo-Layer (MVT/Vector Tiles) |
| `core.statistics` | 5.925 | **aktiv** — Long-Format Zeit/Verteilung |
| `core.traffic_restrictions` | 30.999 | **aktiv** — separate Tabelle, Live |
| `core.election_results` | 0 | leer (Domäne ungenutzt) |
| `core.park_ride_occupancy` | 0 | leer (Legacy) |
| `core.bicycle_counts` | 0 | leer (Legacy) |
| `core.transit_stops` / `transit_routes` | 0 | leer (Legacy) |
| `raw_ingest.payloads` | 376 | speichert **nur** `{"count": N}`, **nicht** die Rohdaten |

**Konsequenz:** Für die 246 ungeladenen Datensätze liegen keine Rohdaten gepuffert
vor — sie müssen aus der Quelle neu geholt werden, sobald ein passender Loader existiert.

### Geo-Modell: Zeit steckt schon teils im Layer
`geo_features` hat eine `properties`-JSONB-Spalte und eine `year`-Spalte. Manche
Datensätze nutzen das bereits als **Zeitreihe im Geo-Layer**: NO2-Monatsmittel hat
**36 Punkte je Station** (Jan 2021–Dez 2023, ein Punkt pro Monat). Das ist das Muster,
mit dem sich „Zeitdaten auf der Karte" sauber abbilden lassen (gleicher Ort, viele
Zeitstempel → Zeit-Slider + animierter Verlauf).

---

## 3. Systematischer Datensatz-Katalog

### 3.1 Geo-Datensätze (29) — direkt kartierbar

Spalten: Geometrie · Zeit/Live · zentrale Attribute (aus `properties`) · Visualisierungs-Idee.

| Datensatz | Geom | n | Inhalt / wichtige Attribute | Visualisierung |
|-----------|------|--:|------------------------------|----------------|
| **Baumkataster** | Point | 3,59 Mio | Gattung, Baumhöhe, Kronen-Ø (`kr_durchm`), Stammumfang, Pflanzjahr, `gefaellt_am`, `letzte_bewaesserung`, Ortsteil | Cluster→Punkte; Heatmap Baumdichte; Kronenfläche als Kühl-Proxy |
| **Straßennetz** (live) | MultiLineString | 271k | Straßenname, Klasse, Baulast, Länge, Stadtbezirk | Liniennetz, Basis für Routing/Joins |
| **Knotenpunkte Straßennetz** | Point | 206k | Knoten-IDs, Gültigkeit | Kreuzungsdichte |
| **Verkehrszeichen** | Point | 82k | sehr reich: Zeichen-Typ/Kategorie, Aufstellung, Richtung, Segment | gefilterte Schilder (z. B. Tempo, Halteverbot) |
| **LVB-Fahrplandaten** (live) | Point | 5.299 | GTFS-Haltestellen (`stop_id`, `stop_name`) | ÖPNV-Haltestellen-Layer |
| **Digitale Stadtgrundkarte (DSGK)** | Point | 5.212 | Vermessungspunkte, Höhen | Referenz/Geodäsie (Spezialfall) |
| **Luftreinhalteplan-Prognose Straße 2025** | (Multi)LineString | 3.397 | **NO2, PM10 je Straßenabschnitt**, Länge | Linien-Choroplethe Schadstoff |
| **Bodenrichtwerte 2022/23/24** (Familie) | Polygon | je ~1,2k | **`brw` Bodenwert €/m²**, Nutzungsart, Fläche, GFZ | Flächen-Choroplethe Bodenwert + Jahr |
| **Weihnachtsmarkt-Stände 2023/24/25** (Familie) | (Multi)Polygon | je ~400 | Marktart, Firma, Angebot | saisonaler Punkt/Flächen-Layer |
| **Wahlbezirks-Geometrien** (BTW21/25, LTW24, EuW/SRW24, OBM20, Briefwahl) | (Multi)Polygon | 194–414 | `wbz`, teils EWO/Wähler/Wahlberechtigte | **Träger für Wahl-Choroplethen** (sobald Ergebnisse geladen) |
| **NO2-Monatsmittel Passivsammler** | (Multi)Point | 406 | Station, **`mmw`**, `date_month` (36/Station) | **Zeit-Slider an Stationen**, Verlaufskurve |
| **NO2-Jahresmittel Passivsammler** | Point | 34 | Station, **`jmw`**, Jahr | jährliche Stations-Werte |
| **Luftreinhaltemaßnahmen** | Point | 11 | Maßnahme, Status, Ziel, Fotos | Maßnahmen-Marker |
| **Statistische Bezirke / Ortsteile / Stadtbezirke** | Polygon | 310/63/10 | Verwaltungsgrenzen | **Choroplethen-Geometrie** (Join-Basis) |
| **Stadt-/Land-/Bundestags-Wahlkreise** | Polygon | 2–10 | Wahlkreis-IDs | Wahlkreis-Overlay |
| **Potentielle Superblocks (Eggimann)** | Polygon | 171 | `area`, `b_type` | Stadtplanungs-Overlay |

> Auffällig fehlend in `geo_features`, obwohl Geo: **Park+Ride**, **Radzählstellen**,
> **Landschaftsschutzgebiete** (SHP, fehlgeschlagen), **3D-Stadtmodell LoD2** (SHP, 0
> geladen), **Defibrillator-Standorte** (als Statistik fehlgeladen). → Abschnitt 3.5.

### 3.2 Statistik auf Ortsteil-Ebene — kartierbar als Choroplethe

Real existieren 4.229 Ortsteil-Zeilen über 19 Datensätze / 43 Metriken. **Davon sind
die meisten unbrauchbar** (Adress-/Straßenverzeichnisse, Wahl-Rohformat, Punkt-Daten).
Saubere Choroplethen-Kandidaten:

| Datensatz | brauchbare Metrik(en) | Eignung |
|-----------|------------------------|---------|
| Kindertageseinrichtungen (Träger) | Kinder gesamt/Jungen/Mädchen, Einrichtungen | ✅ Choroplethe |
| Versorgungsgrad Kita-Plätze | Versorgungsgrad Krippe/Kindergarten | ✅ Choroplethe |
| Relative Entwicklung Einwohnerzahl | Ewo 2018/2022, Prognose-Varianten | ✅ Choroplethe + Trend |
| Zu-/Wegzüge ukrainischer Personen | Alter/Geschlecht/Wohndauer (Dimensionen) | ⚠️ erst entpivotieren |
| Stadtbezirksbudget | Betrag in EUR | ⚠️ Beschluss-IDs mischen rein |

> **Fehlklassifiziert** (sollten NICHT als Ortsteil-Metrik erscheinen): „Öffentliche
> Toiletten" (`lat`/`long`/`utm` als Metrik → eigentlich Punkte), „… Straßenabschnitts-
> verzeichnis" (Adressregister), „Ergebnisse *wahl seit 1994" (Partei-ID als Dimension,
> Jahr auf 1994 kollabiert). → in der neuen Metrik-Whitelist ausblenden.

### 3.3 Stadtweite Statistik (City-Ebene) — 105 Datensätze, **nicht** kartierbar

1.632 Zeilen, 403 „Metriken", **kein** `spatial_code`. Das sind die Daten, die der
Auftrag „auch ohne Geolocation sinnvoll auf der Karte / im Lagebild zeigen" meint.
Charakter: entweder **Zeitreihen** (eine Kennzahl über Jahre) oder **Verteilungen**
(viele Kategorien, ein Stichjahr).

Reichhaltige, gut nutzbare Beispiele:

| Datensatz | Form | Metriken | Idee |
|-----------|------|---------:|------|
| Probleme aus Bürgersicht (Jahres) | Zeitreihe | 24 (Armut, Baustellen, Freizeit…) | Themen-Verlauf, Small Multiples |
| Personalkennzahlen Stadtverwaltung | Snapshot | 24 | KPI-Kacheln |
| Lebenserwartung | Zeitreihe 1998–2021 | (Teilräume) | Linien-Chart |
| Energie- & CO2-Bilanz 2011 | Verteilung | 14 (⚠️ `Unnamed`-Header) | nach Fix: Sektor-Balken |
| Unfälle mit Radbeteiligung | Snapshot | 20 (IstRad, IstPKW…) | Beteiligungs-Balken |
| Bevölkerungsvorausschätzung 2023 | Zeitreihe 2023–2040 | 3 | Prognose-Fächer |
| Wanderungssaldo n. Herkunft/Ziel | Verteilung | 5–9 | Sankey/Flow |
| LWB-Angebots-/Bestandsmieten n. Baualter | Zeitreihe 2012–2022 | 8/9 | Mieten-Trend |
| LeipzigGiesst gegossene Liter (Familie 2021–2025) | Zeitreihe | 8 | Jahresbalken, Bezug zu Baumkataster |
| Vornamensstatistik (Familie 2014–2024) | Verteilung | 2 | Top-Namen je Jahr |

### 3.4 Live-Layer: Verkehrseinschränkungen
`core.traffic_restrictions`, 1 Datensatz, 30.999 Einträge (21.314 aktuell gültig),
MultiPolygon, mit `valid_from`/`valid_until`. **Funktioniert**, echter Live-Mehrwert
(Baustellen/Sperrungen). Alle 5 Min aktualisiert.

### 3.5 Ungenutzt, aber wiederherstellbar (246)

| Gruppe | n | Quelle/Status | Recovery-Aufwand |
|--------|--:|---------------|------------------|
| **statistik-Datensätze, 0 geladen** | 174 | statistik · success | mittel — Melt/Loader-Layout erweitern; größter Hebel |
| **opendata-Downloads fehlgeschlagen** | 36 | opendata · „Connection reset" | klein–mittel — Retry/Timeout/Format (XLSX, SHP) |
| **Geo/JSON success, 0 geladen** | 16 | u. a. Park+Ride×3, Radverkehr×3, 3D-LoD2, OParl×3, Liegenschaften | klein (Live-Feeds) bis groß (3D) |
| **nie ingestiert** | 16 | keine Resource-URL | meist nicht behebbar (Metadaten-Dubletten) |

**Konkret enthalten und wertvoll** (Auswahl):
- **Park+Ride: Standorte + Aktuelle Belegung + Historie 30 Tage** (GeoJSON, live) → Loader-Fix = sofort Live-Parkplatzkarte.
- **Radzählstellen: Standorte + Gesamtanzahl/Tag** (GeoJSON, live) → Loader-Fix = Live-Radverkehr.
- **Wahlergebnisse 2021–2024** (CSV, opendata, fehlgeschlagen) → füllt `election_results`, aktiviert Wahl-Choroplethen.
- **Landschaftsschutzgebiete** (SHP) → Umwelt-Flächenlayer.
- **OParl-Ratsinformationssystem** (Organisationen/Sitzungen/Vorlagen, JSON) → Politik-Kontext, kein Geo.
- **Abfallentsorgung, Schulen, Gästezahlen, Bürgerumfrage-Module** (statistik) → Zeitreihen.

---

## 4. Datenqualitäts-Befunde (vor der UI zu beheben oder zu filtern)

1. **Müll-Metriknamen** (`Unnamed: 1…14`) bei fehlerhaftem Header-Parsing (Energie/CO2-Bilanz).
2. **Raumdimension als Metrik** (Lebenserwartung: „Grünau", „Innenstadtrand" sind Teilräume, keine Kennzahlen).
3. **Punkt-Datensätze als Statistik fehlgeladen** (Öffentliche Toiletten, Defibrillatoren, Bibliotheks-/Haltestellen-Koordinaten → gehören als Punkte in `geo_features`).
4. **Identifikatoren als Metrik** (`Straßenschlüssel`, `Hausnummer`, `Partei_ID_StatAmtLE`, `lat`/`long`).
5. **Jahr kollabiert** (alle „seit 1994"-Wahldatensätze zeigen Jahr 1994).
6. **Indikatoren-Katalog deckt nur ~20 %** der real geladenen Metriken ab (97 von 477). Der Katalog ist groß (1.407 Indikatoren), passt aber schlecht zu den tatsächlich vorhandenen Spalten.

→ **Designprinzip:** Die Metrik-/Quellenauswahl darf nur **kuratierte, validierte**
Einträge zeigen. Roh-`metric_name` niemals direkt ins UI.

---

## 5. Live vs. Nightly — was wirklich „live" gehört

16 Datensätze sind als `schedule=live` markiert, aber nur wenige sind **fachlich** live:

| Wirklich live-sinnvoll | Begründung |
|------------------------|------------|
| **Park+Ride Belegung** | Freie Plätze ändern sich minütlich (derzeit Loader-Bug) |
| **Verkehrseinschränkungen** | Baustellen/Sperrungen, zeitlich gültig (funktioniert) |
| **Radzählstellen (Tageswerte)** | tagesaktuell sinnvoll, nicht minütlich |

**Mis-getaggt als live** (eigentlich nightly/statisch): Straßennetz, LVB-GTFS (statischer
Fahrplan, keine Echtzeit-Positionen), „Probleme aus Bürgersicht", „Adressen", „Hort"-
Zahlen. → Diese aus dem 5-Minuten-Takt nehmen (spart Last) und korrekt als nightly führen.

**ÖPNV-Echtzeit fehlt komplett:** GTFS liefert nur den Soll-Fahrplan. Für „Live-ÖPNV"
bräuchte es GTFS-Realtime (LVB), das (noch) nicht angebunden ist.

---

## 6. Analyse- & Visualisierungskonzepte

Statt freier Beliebig-Kombination: **kuratierte „Lagebilder" (Use-Case-Presets)**, die
fachlich sinnvolle Layer bündeln und gezielte Cross-Analysen erlauben.

### Lagebild A — „Mobilität & Ankommen" (live)
**Layer:** Park+Ride-Belegung (Punkte, Farbe = freie Plätze) · LVB-Haltestellen · Rad-
zählstellen (Tagesaufkommen) · Verkehrseinschränkungen (Flächen) · Straßennetz (Basis).
**Analyse:** „Wie komme ich in die Stadt?" Intermodaler Vergleich. Statistik-Kontext:
Unfälle mit Radbeteiligung (Jahresverlauf). **Cross:** Park+Ride-Auslastung ↔ nahe
Radzählstellen-Aufkommen ↔ aktive Sperrungen im Korridor.
*(Voraussetzung: Park+Ride- und Rad-Loader-Fix.)*

### Lagebild B — „Stadtklima & Hitze"
**Layer:** Baumkataster (Heatmap Baumdichte, Kronen-Ø als Kühl-Proxy) · NO2-Stationen
(Zeit-Slider) · Luftreinhalteplan NO2/PM10 je Straße (Linien-Choroplethe) · LeipzigGiesst
(Gießwasser, Kontext-Chart).
**Analyse:** Wo wenig Baumkronen **und** hohe NO2-Belastung? **Cross (statistisch wertvoll):**
Baumdichte je Ortsteil vs. NO2-Jahresmittel; Baum-/Versiegelungsgrad vs. Bodenrichtwert.
Bivariate Choroplethe (2-Variablen-Farbschema) als Highlight.

### Lagebild C — „Wahlen & Politik"
**Layer:** Wahlbezirks-Geometrien (2020–2025) + Ergebnisse als Partei-Choroplethe.
**Analyse:** Parteistärke je Wahlbezirk; **Swing-Map** (Differenz zweier Wahlen);
Wahlbeteiligung. **Cross:** Wahlergebnis vs. Sozialindikatoren (Einwohnerentwicklung,
Kita-Versorgung) auf Ortsteilebene.
*(Voraussetzung: Wahl-CSV-Loader-Fix → `election_results` füllen.)*

### Lagebild D — „Bevölkerung & Soziales"
**Layer:** Ortsteil-Choropleth mit Zeit-Slider (Einwohnerentwicklung, Kita-Versorgung,
Lebenserwartung). **Kontext-Dock (city-level, nicht-geo):** Bevölkerungsvorausschätzung
(Prognose-Fächer), Geburtenziffer, Wanderungssaldo (Sankey).
**Analyse:** Wachstum/Schrumpfung je Ortsteil; Versorgungslücken Kita.

### Lagebild E — „Wohnen & Boden"
**Layer:** Bodenrichtwerte-Flächen (€/m², Jahr-Slider 2022–2024) · Superblocks-Overlay.
**Kontext:** LWB-Mieten (Zeitreihe). **Cross:** Bodenwert ↔ Baumdichte ↔ Wahlergebnis.

### Querschnitt: nicht-geolokalisierte Daten intelligent zeigen
Drei Darstellungsmodi, automatisch nach Datenform gewählt:
1. **Ortsteil/Stadtbezirk vorhanden →** Choroplethe (Zeit-Slider, wenn mehrere Jahre).
2. **Nur Stadtebene, Zeitreihe →** **Kontext-Dock** (andockbares Panel) mit Sparkline/
   Linien-Chart; optional als ein Marker auf dem Stadtzentrum, der das Dock öffnet.
3. **Nur Stadtebene, Verteilung (Kategorien) →** Small-Multiples/Treemap/Balken im Dock.

Der Kniff: Die Auswahl **kennt die Granularität** jedes Indikators und bietet nur
sinnvolle Darstellungen an — keine „Choroplethe" für eine reine Stadt-Zeitreihe.

---

## 7. Vorschlag: Neues Lagebild-UI (zur Abstimmung)

**Leitidee — zwei getrennte Achsen statt einer flachen Layer-Liste:**

- **WAS** (Inhalt): thematisch gruppierter Katalog über den Indikatoren-/Themen-Baum
  (Mobilität, Umwelt, Bevölkerung, Wahlen, Wohnen…). Jeder Eintrag zeigt Badges:
  `Geo` / `Ortsteil` / `Stadt` / `Zeitreihe` / `Live`, Zeitumfang und Datenstand.
- **WIE** (Darstellung): wird aus der Datenform **automatisch** abgeleitet (Punkt/Cluster,
  Linie, Flächen-Choroplethe, Heatmap, Zeit-Slider, Kontext-Chart). Nur kompatible
  Optionen sind wählbar.

**Kernkomponenten:**
1. **Lagebild-Presets** (Abschnitt 6) als Ein-Klick-Einstieg — kuratiert, fachlich sinnvoll.
2. **Katalog-Browser** mit Themen-Gruppen + Suche + Badges; nur Datensätze **mit** Daten,
   kuratierte Metrik-Whitelist (kein roher `metric_name`).
3. **Kompatibilitäts-Regeln:** Korrelation/Bivariat nur zwischen Metriken **gleicher**
   Raumeinheit; keine sinnlosen Kombinationen mehr.
4. **Kontext-Dock** für nicht-geo Statistik (Charts statt erzwungener Geometrie).
5. **Zeit-Achse** global: Slider, der Choroplethen, Geo-`year` und Zeit-im-Geo (NO2)
   gleichzeitig steuert.

**Vor dem Bauen offen (Abschnitt für Rücksprache):** Umfang (nur UI-Redesign auf
vorhandenen Daten vs. zusätzlich Loader-Fixes für Park+Ride/Rad/Wahlen), und ob die
Presets oder der freie Katalog der primäre Einstieg sein sollen.

---

## Anhang — Rohinventar
- `.inventory/geo.txt` — 29 Geo-Datensätze (Geometrie, Anzahl, Feature-Typ, Jahre)
- `.inventory/geo_props.txt` — Property-Keys je Geo-Datensatz
- `.inventory/stats.txt` — 122 Statistik-Datensätze (Metriken, Raumeinheit, Jahre)
- `.inventory/nodata_full.txt` — 246 ungeladene Datensätze (Quelle, Status, Format)
</content>
</invoke>
