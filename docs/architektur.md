# Architektur & Datenverarbeitung

> Wie Daten von `opendata.leipzig.de` / `statistik.leipzig.de` bis ins Lagebild
> fließen — Dienste, Pipeline, Speicherschichten, Verarbeitung. Diagramme sind
> Mermaid (rendern auf GitHub und in den meisten Markdown-Viewern).
> Stand: 2026-06. Ergänzt `datensatz-analyse.md` (Inhalt der Datensätze).

---

## 1. Systemüberblick

Ein VPS (4 GB RAM), alle Dienste in Docker Compose hinter einem TLS-Nginx.

```mermaid
flowchart LR
  subgraph quellen["Externe Quellen"]
    OD["opendata.leipzig.de<br/>CKAN/DCAT · CSV/GeoJSON/SHP"]
    ST["statistik.leipzig.de<br/>JSON-API · wide-by-year"]
    GD["geodienste.leipzig.de<br/>WFS · Park+Ride / Rad live"]
  end

  subgraph vps["VPS · Docker Compose"]
    direction TB
    ETL["etl<br/>Scheduler + Pipeline"]
    DB[("db<br/>PostgreSQL 16 + PostGIS")]
    RED[("redis<br/>Cache")]
    BE["backend<br/>FastAPI · async psycopg3"]
    FE["frontend<br/>React + MapLibre"]
    NGINX["nginx<br/>TLS-Proxy :8080/8443"]
    KUMA["uptime-kuma<br/>Monitoring"]
  end

  USER(["Browser<br/>auth. Nutzer"])

  OD --> ETL
  ST --> ETL
  GD --> ETL
  ETL -->|"upsert"| DB
  ETL -->|"tiles:version bump"| RED
  BE <-->|"SQL"| DB
  BE <-->|"Tile-/Query-Cache"| RED
  FE -->|"REST + Vector Tiles<br/>Bearer JWT"| BE
  NGINX --- FE
  NGINX --- BE
  USER -->|"HTTPS"| NGINX
  KUMA -.->|"health"| BE
```

| Dienst | Port | Rolle |
|--------|------|-------|
| `db` | 5432 | PostgreSQL 16 + PostGIS 3.4 — alle 5 Schemata |
| `redis` | 6379 | Tile-Cache + Query-Cache, invalidiert via `tiles:version` |
| `backend` | 8000 | FastAPI, JWT-Auth, MVT-Tiles, Statistik-Endpunkte |
| `etl` | — | APScheduler: nightly 02:00 UTC + live alle 5 min |
| `frontend` | 80 | Vite-Build, MapLibre-Lagebild |
| `nginx` | 8080/8443 | TLS-Terminierung, Reverse-Proxy |
| `uptime-kuma` | 3001 | Verfügbarkeits-Monitoring |

---

## 2. Datenfluss end-to-end

Der rote Faden: **Extraktion → Roh-Audit → typ-spezifische Transformation →
Upsert in Kerntabellen → materialisierte Sichten → API → Karte.**

```mermaid
flowchart TD
  SRC["Quelle<br/>(URL aus dataset_contracts.json)"]

  SRC --> HEAD{"HEAD / ETag<br/>geändert?"}
  HEAD -->|"304 / gleicher ETag"| SKIP["status = skipped<br/>(kein Body-Download)"]
  HEAD -->|"geändert / kein ETag"| EXT["Extraktor<br/>(httpx HTTP/1.1 + tenacity-Retry)"]

  EXT --> DISP{"_dispatch()<br/>nach Typ/Format/URL"}

  DISP -->|"Wahl-Datensatz"| ELEC["elections-Domäne<br/>D/F/E-Spalten → Parteien"]
  DISP -->|"Park+Ride / Rad WFS"| GEOLIVE["GeoJSON + CRS→WGS84<br/>(reproject 25833)"]
  DISP -->|"GeoJSON / SHP / GTFS"| GEO["Geo-Features"]
  DISP -->|"Baustellen WFS"| TR["Traffic-Restrictions"]
  DISP -->|"statistik-API CSV/JSON"| MELT["melt_values / melt_kdvalues<br/>wide-by-year → long"]
  DISP -->|"CSV/XLSX/XML Fallback"| STATG["generische Statistik"]
  DISP -->|"unbekannt"| RAWONLY["nur Roh-Zusammenfassung<br/>(0 Kernzeilen)"]

  ELEC --> CORE_E[("core.election_results")]
  GEOLIVE --> CORE_G
  GEO --> CORE_G[("core.geo_features")]
  TR --> CORE_TR[("core.traffic_restrictions")]
  MELT --> CORE_S[("core.statistics")]
  STATG --> CORE_S

  EXT -.->|"{count: N} + checksum"| RAW[("raw_ingest.payloads<br/>+ etl_runs Audit")]
  DISP -.-> RAW

  CORE_E & CORE_G & CORE_TR & CORE_S --> REFRESH["mart.refresh_all()<br/>/ refresh_live()"]
  REFRESH --> MART[("mart.*<br/>statistics_latest,<br/>active_restrictions,<br/>dataset_status …")]
  REFRESH --> BUMP["tiles:version++<br/>(Redis-Cache invalidieren)"]

  MART --> API["FastAPI-Router"]
  CORE_G --> TILES["tiles_router<br/>ST_AsMVT"]
  API --> FE["Frontend / Lagebild"]
  TILES --> FE
```

**Wichtig zur Roh-Schicht:** `raw_ingest.payloads` speichert nur eine
`{"count": N}`-Zusammenfassung + Checksumme zur Änderungserkennung — **nicht**
die Rohdaten. Extrahierte Daten fließen direkt Extraktor → Loader → Core. Ein
ungeladener Datensatz muss daher aus der Quelle neu geholt werden.

---

## 3. Dispatch-Entscheidungsbaum (`etl/src/pipeline.py`)

Die Reihenfolge ist bewusst: **kuratierte semantische Domänen schlagen
Format-Heuristiken.** Erster Treffer gewinnt.

```mermaid
flowchart TD
  A["run_dataset(contract)"] --> B{"URL vorhanden?"}
  B -->|nein| Z1["skipped"]
  B -->|ja| C{"Format in SKIP<br/>(PDF/XLS)?"}
  C -->|ja| Z2["skipped"]
  C -->|nein| D["_dispatch()"]

  D --> E{"elections.route_for(id)?"}
  E -->|ja| R_E["run_election_dataset()<br/>→ core.election_results"]
  E -->|nein| F{"URL ~ pr_anlage_belegung<br/>_lastrecord?"}
  F -->|ja| R_PRL["geo_features<br/>feature_type=park_ride<br/>(Live-Snapshot, dedup=site)"]
  F -->|nein| G{"URL ~ _zeitreihe?"}
  G -->|ja| R_PRH["geo_features<br/>feature_type=park_ride_history<br/>(Zeit-in-Geo)"]
  G -->|nein| H{"name ~ radverkehr /<br/>dauerzaehlstell?"}
  H -->|ja| R_RAD["geo_features<br/>bicycle_count / bicycle_station<br/>(reproject 25833→4326)"]
  H -->|nein| I{"name ~ verkehrsraum /<br/>baustell?"}
  I -->|ja| R_TR["core.traffic_restrictions"]
  I -->|nein| J{"Format?"}

  J -->|GTFS| R_GTFS["geo_features (gtfs_stop)"]
  J -->|SHP/GPKG| R_SHP["geo_features"]
  J -->|ZIP| R_ZIP["entpacken → GeoJSON/CSV/SHP"]
  J -->|XLSX/ODS/XML| R_XLS["core.statistics"]
  J -->|GeoJSON/WFS| R_GEO["geo_features"]
  J -->|"CSV/JSON @ statistik-API"| R_MELT["melt → core.statistics"]
  J -->|CSV| R_CSV["core.statistics (Fallback)"]
  J -->|sonst| R_RAW["nur Roh-Zusammenfassung"]
```

---

## 4. Speicherschichten (5 Schemata)

```mermaid
flowchart LR
  subgraph raw["raw_ingest"]
    P["payloads<br/>(count + checksum)"]
    RU["etl_runs<br/>(Audit)"]
    CL["change_log"]
    CK["dataset_checksums<br/>(ETag/Last-Modified)"]
  end
  subgraph stg["staging"]
    NORM["Zwischen-Normalisierung"]
  end
  subgraph core["core (normalisiert)"]
    DS["datasets<br/>(+ family_id, categories)"]
    GF["geo_features<br/>4,17 Mio · jsonb props · year"]
    STAT["statistics<br/>long: metric × Periode × Raum"]
    ER["election_results"]
    TRr["traffic_restrictions"]
    AB["admin_boundaries<br/>+ spatial_aliases"]
    IND["indicators<br/>+ indicator_metrics"]
  end
  subgraph mart["mart (Lesesichten)"]
    SL["statistics_latest"]
    AR["active_restrictions"]
    BD["bicycle_daily"]
    DST["dataset_status"]
  end
  subgraph auth["auth"]
    U["users"]
    RT["refresh_tokens"]
  end

  raw --> core
  stg --> core
  core --> mart
```

Die **Verarbeitungsschritte** je Schema:

1. **`raw_ingest`** — Änderungserkennung (ETag/Last-Modified → 304-Skip), Lauf-Audit,
   Checksummen. Quelle der Wahrheit für „lief, mit welchem Status".
2. **`staging`** — leichte Zwischen-Normalisierung (bei Bedarf).
3. **`core`** — die normalisierten Domänentabellen. Räumliche Schlüssel werden über
   `core.resolve_spatial_key()` aus `spatial_aliases` zum kanonischen `spatial_code`
   aufgelöst (Join-Basis für Choroplethen).
4. **`mart`** — `CONCURRENTLY` refreshte materialisierte Sichten für schnelle Reads.
5. **`auth`** — Nutzer + gehashte Refresh-Tokens.

---

## 5. Drei Verarbeitungspfade im Detail

### 5a. Statistik-Melt (statistik.leipzig.de)
Die API liefert **wide-by-year** (Kennziffer × Jahr/Quartal/Schuljahr) bzw.
**kdvalues** (Gebiet × Sachmerkmal). `statistik_transform.py` schmilzt sie in
Long-Records, bevor `upsert_statistics` schreibt.

```mermaid
flowchart LR
  W["wide:<br/>Kennziffer | 2019 | 2020 | 2021"] --> M["melt_values()"]
  M --> L["long:<br/>(metric, period_year, value)"]
  L --> RES["resolve_spatial_key()<br/>Ortsteil-Name → code"]
  RES --> US["upsert_statistics<br/>uq (dataset,period,unit,key,metric)"]
  US --> S[("core.statistics")]
```

### 5b. Vereinheitlichter Geo-Layer + Vector Tiles
Alle Geo-Quellen liegen in **einer** Tabelle; der MVT-Layer rendert sie
zoomabhängig (Cluster → Einzelpunkte). Park+Ride/Rad wurden hierher umgeleitet.

```mermaid
flowchart LR
  GJ["GeoJSON/WFS/SHP"] --> RP["CRS→WGS84<br/>(GeoJsonExtractor)"]
  RP --> SH["shapely → WKT<br/>ST_Force2D"]
  SH --> UG["upsert_geo_features<br/>dedup (dataset_id, dedup_key)"]
  UG --> GF[("core.geo_features")]
  GF --> MVT["tiles_router<br/>ST_AsMVT(z/x/y)"]
  MVT --> RC{"Redis<br/>tiles:version"}
  RC -->|hit| FE["MapLibre"]
  RC -->|miss| MVT
```

### 5c. Wahl-Domäne (Offene Wahldaten)
Spaltenstandard A/B/C/D/E/F + `D{i}`/`F{i}` je Partei in amtlicher Reihenfolge;
Partei-Mapping aus `election_definitions.json` (verifiziert gegen die Named-Shares
der statistik-API).

```mermaid
flowchart LR
  CSV["Wahl-CSV<br/>D/F/E-Spalten"] --> DEF["election_definitions.json<br/>Spalte i → Partei"]
  DEF --> PARSE["run_election_dataset()<br/>je Gebiet × Partei"]
  PARSE --> RES["resolve_spatial_key()<br/>Wahlbezirk/Ortsteil → code"]
  RES --> ER[("core.election_results")]
  ER --> CH["elections_router<br/>Partei-Choroplethe"]
```

---

## 6. Scheduling: nightly vs. live

```mermaid
sequenceDiagram
  participant S as Scheduler
  participant P as Pipeline
  participant DB as PostgreSQL
  participant R as Redis
  Note over S: Startup
  S->>DB: seed admin_boundaries
  S->>DB: sync categories / families / elections / indicators
  Note over S: nightly · 02:00 UTC (alle 382)
  S->>P: run_dataset(contract) je Datensatz
  P->>DB: HEAD/ETag → ggf. skip
  P->>DB: extract → transform → upsert
  S->>DB: mart.refresh_all() CONCURRENTLY
  S->>R: tiles:version++
  Note over S: live · alle 5 min (16 Quellen)
  S->>P: nur live-Datensätze (z. B. Park+Ride-Belegung, Baustellen)
  P->>DB: upsert (Snapshot überschreibt)
  S->>DB: mart.refresh_live()
  S->>R: tiles:version++
```

**Fachlich wirklich live:** Park+Ride-Belegung (minütlich relevant),
Verkehrseinschränkungen. Radzählungen sind tagesaktuell. Übrige als „live"
markierte Quellen sind statisch/jährlich und gehören in den nightly-Takt.

---

## 7. Backend-API → Lagebild

```mermaid
flowchart TD
  subgraph api["FastAPI-Router (/api, Bearer JWT)"]
    AUTH["auth_router"]
    DSR["datasets<br/>/catalog · /categories · /{id}/profile"]
    MAP["map_router<br/>/restrictions · /admin-boundaries"]
    STATS["stats_router<br/>/metrics · /choropleth · /timeseries · /correlation"]
    TILES["tiles_router<br/>/map/tiles/{z}/{x}/{y}.pbf"]
    ELR["elections_router"]
    INDR["indicators_router"]
  end

  subgraph fe["Frontend (React + Zustand mapStore)"]
    CAT["CatalogPanel<br/>Themen-Leiste + Badges + Presets"]
    DOCK["ContextDock<br/>nicht-geo Statistik als Charts"]
    MV["MapView (MapLibre)"]
  end

  DSR -->|"/datasets/catalog"| CAT
  CAT -->|"geo → dataset_ids"| TILES
  CAT -->|"choropleth → metric"| STATS
  CAT -->|"city → dock"| DOCK
  DOCK -->|"/stats/timeseries"| STATS
  TILES --> MV
  STATS --> MV
  MAP --> MV
```

### `/datasets/catalog` — der Knoten der neuen UI
Ein Pass über alle vier Stores liefert je logischem Datensatz (Familien
kollabiert), **welche Darstellungen** er trägt:

| Feld | Bedeutung |
|------|-----------|
| `kind` | `geo` \| `choropleth` \| `timeseries` \| `distribution` |
| `badges` | `Live` / `Geo` / `Ortsteil` / `Stadt` / `Zeitreihe` |
| `geometry` | `point` / `line` / `area` (Styling) |
| `theme` | primäre Kategorie (Themen-Baum) |
| `traffic` | Sonderpfad: Live-Layer statt Tiles |

Daraus baut `CatalogPanel` den Themen-Baum; die Auswahl bietet **nur sinnvolle**
Darstellungen an (keine Choroplethe für eine reine Stadt-Zeitreihe, Korrelation
nur bei gleicher Raumeinheit).

---

## 8. Schlüsseldateien

| Datei | Rolle |
|-------|-------|
| `dataset_contracts.json` | Quelle der Wahrheit: 398 Datensätze (URL, Format, Schedule) |
| `dataset_families.json` | Jahr-Varianten-Familien + Loader-Hints |
| `election_definitions.json` | Spalte→Partei je Wahl (verifiziert) |
| `indicator_catalog.json` | kanonischer Indikatoren-Katalog (Metrik-Whitelist) |
| `etl/src/scheduler.py` | Einstieg + Scheduling (nightly/live) |
| `etl/src/pipeline.py` | Dispatch je Datensatz |
| `etl/src/extractors/base.py` | HTTP-Client (HTTP/1.1, Retry auf TransportError) |
| `etl/src/extractors/geojson_extractor.py` | GeoJSON + CRS-Reprojektion |
| `etl/src/extractors/statistik_transform.py` | wide→long Melt |
| `etl/src/domains/elections.py` | Wahl-Semantik → election_results |
| `etl/src/loaders/postgres.py` | alle Upserts |
| `backend/src/api/routers/datasets.py` | u. a. `/catalog` |
| `backend/src/api/routers/tiles_router.py` | ST_AsMVT Vector Tiles |
| `frontend/src/components/CatalogPanel.tsx` | Themen-Leiste |
| `frontend/src/components/ContextDock.tsx` | Kontext-Charts |
| `sql/migrations/001_…` / `002_…` | Schema + Mart-Sichten |
