# Politisches-Spektrum-Karte für Wahlergebnisse — Design

**Datum:** 2026-07-07 · **Status:** freigegeben (Architektur-Ansatz A, Parteiregel „BT-Sitzordnung inkl. Historie“)

## Ziel

Wahlergebnisse auf der Karte als **Links-Rechts-Farbkodierung** darstellen: je linker ein
Gebiet wählt, desto röter; je rechter, desto blauer. Die Links-Rechts-Definition folgt der
**Sitzordnung im Bundestag**. Beim Hovern über ein Gebiet erscheint ein **Pie-Chart** mit der
vollständigen Parteiverteilung. Die Darstellung muss auf **allen** Wahlergebnis-Datensätzen
funktionieren — den 5 modernen „Offene Wahldaten“-Wahlen ebenso wie den kleinräumigen
historischen Reihen ab 1994.

## Ist-Zustand (Befunde vom 2026-07-07)

- `core.election_results` ist auf dem VPS **leer**: Die Wahl-CSVs wurden früher einmal über den
  generischen CSV-Pfad nach `core.statistics` geladen, dabei wurde ihr ETag in
  `raw_ingest.dataset_checksums` gespeichert. `sync_elections()` löschte später die
  Alt-Statistikzeilen, der Checksum-Cache blieb — seitdem überspringt `etl/src/pipeline.py:102`
  alle Wahl-Datensätze nächtlich mit „unchanged (304)“, die Zieltabelle füllt sich nie.
- `core.statistics` enthält die kleinräumigen statistik.leipzig.de-Reihen: Metriken
  „Stimmenanteile {Partei}“ + „Wahlbeteiligung“ je **Ortsteil** für Bundestagswahlen
  (1994–2025), Europa-/Landtags-/Stadtratswahlen (1994–2024) und Oberbürgermeisterwahlen
  (1994–2020, parteigelabelt).
- Parteinamen sind quellenübergreifend uneinheitlich („DIE LINKE“ / „DIe Linke“ / „Die Linke“,
  „GRÜNE“ / „Grüne“).
- Frontend: Elections werden nur über den generischen Ein-Metrik-Choropleth sichtbar
  (Blauverlauf, eine Partei zur Zeit). `/elections/{id}/choropleth` (Backend) ist ungenutzt.
  Hover ändert nur den Cursor; Popups gibt es nur per Klick. Recharts ist vorhanden
  (BarChart in `ElectionResultsPanel.tsx`), PieChart noch nicht.

## Architektur (Ansatz A: Backend-Spectrum-API)

```
party_registry.json ──sync──▶ core.parties ─────────┐
election_definitions.json ──▶ core.election_sources ┤
                                                    ▼
core.election_results ┐                mart.election_party_shares
core.statistics ──────┴──(Alias-Join)──▶ (MatView, nightly refresh)
                                                    ▼
                              GET /api/elections/spectrum (GeoJSON)
                              GET /api/elections/spectrum/options
                                                    ▼
                    Frontend: Wahlen-Control + Spektrum-Layer + Hover-Pie
```

## 1. Partei-Register: `party_registry.json` (Root, kuratierte Config)

Eine Partei pro Eintrag: `key` (kanonisch), `name` (Anzeige), `position` (Links-Rechts,
`null` = nicht kodiert), `color` (Pie/Legende), `aliases` (alle beobachteten Schreibweisen).

**Regel:** Aufgenommen mit Position wird, wer je eine Sitzposition im Bundestag hatte;
Reihenfolge = aktuelle bzw. letzte Sitzordnung, Abstände kuratiert:

| key | name | position | color | aliases (case-insensitive gematcht) |
|---|---|---|---|---|
| linke | Die Linke | −1.00 | `#c45ab3` | DIE LINKE, DIe Linke, Die Linke, LINKE, PDS |
| bsw | BSW | −0.75 | `#9d8cff` | BSW, Bündnis Sahra Wagenknecht |
| gruene | Grüne | −0.45 | `#3dd68c` | GRÜNE, Grüne, BÜNDNIS 90/DIE GRÜNEN |
| spd | SPD | −0.25 | `#ff6e5e` | SPD |
| fdp | FDP | +0.25 | `#e8d553` | FDP |
| cdu | CDU | +0.60 | `#5d7a8d` | CDU |
| afd | AfD | +1.00 | `#53b9e8` | AfD |
| _(ohne Position)_ | Die PARTEI, Freie Wähler, Piraten, NPD, Volt, … | `null` | grau | jeweilige Schreibvarianten |

Herleitung der Reihenfolge: 21. Bundestag von links nach rechts Linke → Grüne → SPD → Union
→ AfD; FDP (bis 2025) saß zwischen SPD/Grünen und Union; BSW saß im 20. Bundestag als Gruppe
ganz links neben der Linken. Die konkreten Zahlenwerte sind bewusst Config, nicht Code —
Anpassung ohne Deploy der Logik.

Farben: übernehmen die bestehenden `PARTY_COLORS` aus `ElectionResultsPanel.tsx` (die
Konstante dort wird durch das Register ersetzt, geliefert über die API).

**Matching:** Eingangsname → `strip()`, Präfix „Stimmenanteile “ entfernen (Statistik-Pfad),
casefold, Lookup in Alias-Map. Kein Treffer → Partei bleibt ungemappt („Sonstige“).

**Sync:** `etl/src/scheduler.py` erhält `sync_parties()` (Startup + nightly, wie die anderen
`sync_*`): Upsert nach `core.parties`, Löschen entfernter Keys.

## 2. Datenmodell — Migration `sql/migrations/016_election_spectrum.sql`

```sql
CREATE TABLE core.parties (
    key       TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    position  REAL,              -- NULL = nicht im Links-Rechts-Score
    color     TEXT NOT NULL,
    aliases   TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE core.election_sources (   -- kleinräumig-Datensatz → Wahltyp
    dataset_id    TEXT PRIMARY KEY REFERENCES core.datasets(id),
    election_type TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'kleinraeumig'
);

CREATE TABLE core.party_aliases (      -- normalisierte Alias-Lookup (aus aliases[])
    alias_norm TEXT PRIMARY KEY,       -- lower(trim(alias))
    party_key  TEXT NOT NULL REFERENCES core.parties(key) ON DELETE CASCADE
);
```

Befüllung `core.election_sources` über neuen Abschnitt in `election_definitions.json`
(gesynct in `sync_elections()`):

```json
"kleinraeumig_sources": {
  "cbd82a0a-a6e7-45c4-a69a-00e69552fbb4": "bundestagswahl",
  "1da7d611-5f59-41b6-b62c-5032f9883acf": "europawahl",
  "2b2f9e42-4c85-470d-a9f3-7e163d23ddb7": "landtagswahl",
  "dd2024f3-7095-43a2-8817-1ebf9dbbe6a8": "stadtratswahl",
  "8540fb95-9df3-4c2d-aacc-00ee1510d136": "oberbuergermeisterwahl"
}
```

### `mart.election_party_shares` (Materialized View)

Einheitliches Format: `(election_type, year, level, spatial_code, gebiet_name, party_key,
party_name, share_pct, votes, turnout_pct, source)`.

- **Quelle A — `core.election_results`** (moderne Wahlen, `source='results'`):
  `share_pct = zweitstimmen * 100.0 / NULLIF(gueltige_zweit, 0)`. Per Loader-Konvention
  (`etl/src/domains/elections.py`) enthält `zweitstimmen`/`gueltige_zweit` bei allen
  `vote_mode`s die maßgebliche Parteistimme (erst_zweit: F-Spalten; single: D; kommunal:
  E-Summen) — die Formel gilt also einheitlich. `turnout_pct = waehler*100.0/wahlberechtigte`.
  Nur Zeilen mit `spatial_code IS NOT NULL` (Stadt-Ebene/Briefwahl bleiben draußen).
  `election_type`/`year` via Join auf `core.elections`. Partei-Zuordnung: Alias-Join auf
  `core.parties`; ungemappte behalten `party_key = NULL` und den Rohnamen. Zeilen mit dem
  transparenten Platzhalter-Namen `Liste {i}` werden als ungemappt geführt (Sonstige).
- **Quelle B — `core.statistics`** (`source='statistik'`): Datensätze aus
  `core.election_sources`; `metric_name LIKE 'Stimmenanteile %'` → Parteiname = Suffix,
  `share_pct = metric_value`, `votes = NULL`; `turnout_pct` aus der Metrik „Wahlbeteiligung“
  desselben (dataset, spatial_code, period_year). `level = spatial_unit`, `year = period_year`.
- **Kollisionsregel:** Kombinationen `(election_type, year, level)`, die Quelle A liefert,
  werden aus Quelle B ausgeschlossen (`NOT EXISTS`) — exakte Stimmenzahlen schlagen
  Prozent-Reihen; kleinräumig füllt ausschließlich die Historie auf.
- Refresh: in `mart.refresh_all()` aufnehmen (`002_materialized_views.sql`-Muster,
  UNIQUE INDEX für `REFRESH CONCURRENTLY`).

## 3. Backend — `backend/src/api/routers/elections_router.py`

### `GET /elections/spectrum?election_type=&year=&level=`

Antwort: GeoJSON-FeatureCollection. Geometrie-Join wie beim bestehenden Choropleth
(`core.admin_boundaries`, `boundary_type = level`, `boundary_year = 0 OR = year` für
versionierte Wahlbezirks-Geometrien). Properties je Feature:

```json
{
  "gebiet_code": "…", "name": "Volkmarsdorf",
  "score": -0.42,
  "coverage_pct": 91.3,
  "turnout_pct": 78.1,
  "parties": [
    {"key": "linke", "name": "Die Linke", "share": 31.2, "color": "#c45ab3"},
    {"key": null,   "name": "Sonstige",  "share": 8.7,  "color": "#6b7683"}
  ]
}
```

- **Score:** `score = Σ(position_i · share_i) / Σ(share_i)` über alle Parteien mit Position;
  `coverage_pct = Σ(share_i)` derselben Parteien. Gebiete mit `coverage_pct = 0` → `score: null`.
- `parties`: gemappte Parteien einzeln (absteigend nach `share`), alle ungemappten zu einem
  „Sonstige“-Eintrag aggregiert (grau, ans Ende sortiert).
- Berechnung in einer reinen Python-Funktion (`compute_spectrum(rows) -> score, coverage`),
  damit sie unit-testbar ist; SQL liefert nur die Share-Zeilen + Geometrien.
- Caching: `@cached(ttl=3600)` wie die übrigen Election-Endpoints.

### `GET /elections/spectrum/options`

Verfügbare Kombinationen für den Picker, aus der MatView aggregiert:

```json
[{"election_type": "bundestagswahl", "title": "Bundestagswahl",
  "years": [{"year": 2025, "levels": ["wahlbezirk", "ortsteil"]}, …]}, …]
```

Zusätzlich liefert der Endpoint die Registerdaten (Positionen/Farben/Domain) für Legende und
Tooltip, damit das Frontend keine Parteikonstanten mehr hartkodiert.

## 4. Frontend

### State & Steuerung

- `mapStore`: Layer-Key `"elections"` in `activeLayers`; neuer Slice
  `electionSelection: {electionType, year, level} | null` + Setter.
- Neues `ElectionsControl` im `CatalogPanel` (analog `ChoroplethControl`): drei Selects
  (Wahltyp → Jahr → Ebene), Optionen aus `/elections/spectrum/options` (React Query,
  `staleTime` hoch). Nur existierende Kombinationen wählbar; Wechsel des Wahltyps setzt
  Jahr/Ebene auf die jüngste verfügbare Kombination.
- Der bestehende generische Statistik-Choropleth bleibt unverändert bestehen.

### Karten-Layer (`MapView.tsx`)

- GeoJSON-Source `elections-spectrum` (ein Fetch pro Auswahl, React Query).
- Fill-Layer: divergierende Skala über `["get", "score"]`:
  `interpolate(linear): −D → #e5484d (rot), 0 → #3a4048 (neutral, passend zur dunklen Karte),
  +D → #3b82f6 (blau)` mit **fester Domain-Konstante `D = 0.5`** (eine zentrale Konstante;
  Werte werden geclampt). Feste Domain ⇒ Farben sind über Wahljahre und Wahltypen hinweg
  vergleichbar. `score == null` → ungefärbt (transparente Füllung über `case`-Expression).
- Line-Layer für Umrisse; Hover-Highlight über `feature-state` (setFeatureState bei
  `onMouseMove`, `generateId: true` auf der Source).
- Legende (kleine fixe Box, sichtbar solange der Layer aktiv ist): Farbbalken rot↔blau,
  Beschriftung „politisch links ↔ rechts (Sitzordnung Bundestag)“ + Hinweis auf Abdeckung.

### Hover-Tooltip (`ElectionSpectrumTooltip.tsx`)

- Leichtgewichtiger, cursor-folgender `div` (absolut positioniert über der Map, `pointer-events:
  none`) — kein MapLibre-Popup. Anzeige bei `onMouseMove` über `elections-fill`, weg bei Leave.
- Inhalt: Gebietsname, Score-Badge (Zahl + Farbe), **Recharts `PieChart`** (~140 px) mit der
  `parties`-Verteilung in Parteifarben, daneben/darunter Top-Parteien mit Prozentwerten,
  Fußzeile „Wahlbeteiligung X % · Y % der Stimmen im Score“.
- MapLibre serialisiert verschachtelte Properties als JSON-String → `JSON.parse` der
  `parties`-Property, memoisiert je `gebiet_code`.
- Touch-Geräte (kein Hover): Klick auf ein Gebiet öffnet denselben Inhalt als Popup
  (bestehender Klick-Popup-Pfad).

## 5. Schritt 0 — Daten-Fix (Voraussetzung, vor allem anderen)

1. **Code-Guard** in `etl/src/pipeline.py`: Bei Datensätzen mit Elections-Route wird der
   304-/ETag-Skip nur genommen, wenn `core.election_results` für diese `dataset_id` bereits
   Zeilen enthält (billiger `EXISTS`-Check). Verhindert die Skip-Endlosschleife strukturell.
2. **Einmalig auf dem VPS** (nach Deploy des Guards reicht auch das allein, der Guard erzwingt
   den Reload): `DELETE FROM raw_ingest.dataset_checksums WHERE dataset_id IN (<die 15
   Wahl-Datensatz-IDs aus election_definitions.json>);` und den nightly Lauf abwarten oder den
   Scheduler-Container neu starten.
3. Verifikation: `SELECT election_id, level, count(*) FROM core.election_results GROUP BY 1,2;`
   — erwartet: Zeilen für alle 5 Wahlen auf allen konfigurierten Ebenen.

## 6. Randfälle

- **Gebiete ohne Daten / ohne Score:** ungefärbt, Tooltip zeigt „keine Daten“.
- **Briefwahlbezirke & Stadt-Ebene:** haben `spatial_code IS NULL` → erreichen die View/Karte
  nicht (wie heute beim Choropleth).
- **OBM-Wahlen:** kleinräumig parteigelabelt → laufen ohne Sonderfall mit; die
  Kandidaten-City-Datensätze (1./2. Wahlgang) sind nicht kartierbar und bleiben außen vor.
- **Ungemappte/neue Parteinamen:** landen automatisch in „Sonstige“; `coverage_pct` macht
  sichtbar, wie viel der Score erfasst. Neue Parteien = ein Eintrag in `party_registry.json`.
- **Wahlbezirks-Geometrien:** je Wahljahr versioniert (`boundary_year`) — der Geometrie-Join
  übernimmt das bestehende Muster aus `election_choropleth`.
- **PDS/Linke-Kontinuität:** Alias „PDS“ → `linke`; historische Reihen führen ohnehin
  durchgängig das Label „DIE LINKE“/„DIe Linke“.

## 7. Tests & Verifikation

- **pytest (backend):** `compute_spectrum` (Score, Coverage, leere/teilgemappte Verteilungen),
  Alias-Normalisierung (alle beobachteten Schreibweisen aus beiden Quellen).
- **SQL-Smoke:** nach Migration + Refresh: View liefert Zeilen je Wahltyp; Kollisionsregel
  (btw2025/ortsteil kommt aus `results`, btw2017 aus `statistik`).
- **Frontend:** `npm run lint`, `npm run build`; manuell: Wahltyp-/Jahr-/Ebenen-Wechsel,
  Hover-Pie, Legende, Touch-Fallback.
- **Ende-zu-Ende auf dem VPS:** nach Daten-Fix und Deploy alle 5 modernen Wahlen +
  mindestens eine historische (z. B. BTW 2005) auf der Karte prüfen.

## Out of Scope (bewusst)

- Erst-/Zweitstimmen-Umschalter (Basis ist die Parteistimme; Erststimmen später möglich, die
  Daten liegen in `core.election_results` bereits vor).
- Wahlkreis-Ebene (Geodaten vorhanden, aber nur 2 Wahlkreise — kartografisch uninteressant).
- Zeit-Animation/Slider über Wahljahre (Jahr-Select reicht; Animation wäre ein Folgeprojekt).
- Einbindung von Jugendparlaments-/Migrantenbeiratswahl (nicht parteiförmig kodierbar).
