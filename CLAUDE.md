# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A self-hosted authenticated web dashboard ingesting, storing, and visualizing **398 Leipzig open datasets** from `opendata.leipzig.de` and `statistik.leipzig.de`. Features include an interactive MapLibre map, statistical time series, Pearson correlations, and choropleth layers for urban data (Park+Ride occupancy, bicycle counters, traffic restrictions, election results, demographics).

University project for "Computational Spatial Humanities".

## Development Commands

### Local Development (without Docker)

```bash
# Start only infrastructure services
docker compose -f infrastructure/docker-compose.yml up -d db redis

# Backend (FastAPI, port 8000)
cd backend && pip install -e . && uvicorn src.api.main:app --reload

# Frontend (Vite, port 5173)
cd frontend && npm install && npm run dev

# ETL (seeds data on first run, then runs on schedule)
cd etl && pip install -e . && python -m src.scheduler
```

### Full Stack via Docker Compose

```bash
docker compose -f infrastructure/docker-compose.yml up -d
```

Services: `db` (5432), `redis` (6379), `backend` (8000), `etl`, `frontend` (80), `nginx` (8080/8443), `uptime-kuma` (3001).

### Frontend Scripts

```bash
cd frontend
npm run dev      # Vite HMR dev server
npm run build    # TypeScript compile + production build
npm run lint     # ESLint on src/
npm run preview  # Serve production build locally
```

### Python (backend & etl)

Both packages use `pyproject.toml`. Install in editable mode with `pip install -e .`. Python 3.11+ required.

### Database Migrations

Migrations live in `sql/migrations/` and are auto-applied by the ETL scheduler on startup via `etl/src/db.py:run_migrations()`. To apply manually:

```bash
psql -U leipzig -d leipzig_data < sql/migrations/001_schemas_and_core.sql
psql -U leipzig -d leipzig_data < sql/migrations/002_materialized_views.sql
```

### Environment Setup

```bash
cp .env.example .env
# Set at minimum: POSTGRES_PASSWORD and SECRET_KEY
```

## Architecture

### Data Flow

```
opendata.leipzig.de / statistik.leipzig.de
    → etl/src/extractors/ (httpx + tenacity retry)
    → PostgreSQL raw_ingest schema
    → etl/src/loaders/postgres.py (upsert into core schema)
    → mart materialized views (refreshed after each ETL run)
    → backend/src/api/routers/ (FastAPI, async psycopg3)
    → frontend/src/api/ (React Query + Axios)
```

Geo features are served as **vector tiles** (`/api/map/tiles/{z}/{x}/{y}.pbf`,
PostGIS `ST_AsMVT` over `core.geo_features`, per-tile Redis cache invalidated
via `tiles:version` bump after the nightly run). Statistics with
Ortsteil/Stadtbezirk/Wahlbezirk reference join `core.admin_boundaries` via the
canonical `spatial_code` (resolved by `core.resolve_spatial_key()` from
`core.spatial_aliases`); boundaries are seeded by `etl/src/boundaries.py`.

### Database Schema (PostgreSQL 16 + PostGIS 3.4)

Five schemas with clear separation of concerns:
- **`raw_ingest`** — ETL audit log + raw payloads
- **`staging`** — intermediate normalization
- **`core`** — normalized domain tables (park_ride, bicycle_counts, traffic_restrictions, geo_features, statistics)
- **`mart`** — materialized views for fast API reads; refreshed via `mart.refresh_all()` / `mart.refresh_live()` CONCURRENTLY
- **`auth`** — users + refresh tokens

Schema migrations are tracked in `public.schema_migrations`.

### ETL Package (`etl/`)

**`dataset_contracts.json`** (root) is the single source of truth for all 398 datasets — each entry defines `id`, `title`, `schedule` (nightly vs. live), `best_resource` (URL + format), and `has_geo`.

**`dataset_families.json`** (root) merges year-variant datasets (e.g. Bundestagswahl 2021 + 2025, Vornamenstatistik 2014–2025) into one logical dataset with a year dimension (`family_id` on `core.datasets`, `year` on rows). `dataset_hints` overrides loader heuristics per dataset (`spatial_key_column`, `skip_columns`). Re-draft with `etl/scripts/generate_dataset_families.py`, then review manually.

**Curated configs (root, each with a generator in `etl/scripts/` and a `sync_*` on scheduler startup):**
- `dataset_categories.json` — thematic categories mirroring the opendata.leipzig.de CKAN/DCAT groups (+`sonstiges`), enriched via family inheritance and the statistik `kategorie_nr` mapping → `core.dataset_categories` + `categories TEXT[]`
- `election_definitions.json` — column→party mapping per election for the 'Offene Wahldaten' CSVs (D/F/E columns), verified against the named shares of the statistik API → semantic domain `etl/src/domains/elections.py` loads `core.election_results` (consulted FIRST in dispatch)
- `indicator_catalog.json` — canonical indicator registry (name/unit/topic, incl. topic 'Demografie') over the statistik metrics → `core.indicators` + `core.indicator_metrics`; powers `/stats/metrics?grouped=true`

**statistik.leipzig.de ingestion**: the API serves wide-by-year layouts — `etl/src/extractors/statistik_transform.py` melts values (Kennziffer × Jahr/Quartal/Schuljahr columns) and kdvalues (Gebiet × Sachmerkmal) into long records before `upsert_statistics`.

- `src/scheduler.py` — entry point; runs nightly (02:00 UTC) for all datasets, every 5 min for 18 live sources; seeds admin boundaries + syncs families on startup and each nightly run
- `src/pipeline.py` — dispatches per dataset to typed extractors and loaders
- `src/boundaries.py` — seeds `core.admin_boundaries` (Ortsteile, Stadtbezirke, Wahlbezirke 2021/2025) and resolves raw spatial keys to canonical codes
- `src/extractors/` — `GeoJsonExtractor`, `CsvExtractor` (delimiter sniffing), `JsonExtractor` (statistik API), all extending `HttpExtractor`
- `src/loaders/postgres.py` — all upsert functions keyed by dataset type

### Backend Package (`backend/`)

FastAPI with async psycopg3 pool + Redis cache.

- `src/api/main.py` — app entry point, lifespan, middleware, router registration
- `src/api/auth.py` — JWT (python-jose, 60-min access tokens) + bcrypt; refresh tokens SHA-256 hashed and stored in DB (30-day TTL)
- `src/api/routers/` — `auth_router`, `datasets` (incl. `/categories`, `/by-slug/{slug}`, `/{id}/profile` data profiler), `map_router`, `stats_router`, `tiles_router` (MVT vector tiles + per-feature detail), `elections_router`, `indicators_router`
- `src/api/profiling.py` — generic per-dataset column profiles + width_bucket histograms, cached per data generation (`tiles_version`)
- All data endpoints require `Authorization: Bearer <token>`; unprotected: `GET /health`, `GET /ready`
- Uses `orjson` (`ORJSONResponse`) for fast JSON serialization

### Frontend (`frontend/`)

React 18 SPA with Vite + TypeScript.

- **Routing**: `App.tsx` → `/login` (LoginPage) or `/*` guarded by `RequireAuth` → `DashboardPage` with nested routes (`/` map, `/stats`, `/datasets` Themenkatalog → `/datasets/c/:categoryId` → `/datasets/d/:slug`; `/datasets/register` technical registry; UUID URLs redirect to slugs)
- **State**: Zustand — `authStore` (access token, login/logout), `mapStore` (active layers, choropleth metric, selected year, spatial unit)
- **Data fetching**: React Query with per-layer polling (Park+Ride: 60s, restrictions: 120s, bicycle: 300s)
- **Map**: MapLibre GL via `@vis.gl/react-maplibre`, CartoDB dark-matter base, centered on Leipzig (12.3731, 51.3397)
- **UI**: Tailwind CSS + Radix UI primitives + Lucide icons + Recharts

### Infrastructure

- Single VPS (4 GB RAM), all services in Docker Compose
- Nginx TLS-terminating reverse proxy; TLS via Certbot / Let's Encrypt
- CI/CD: GitHub Actions — lint + build on PRs, SSH deploy on push to `main` (secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_SSH_PORT`)
- Deploy script: `infrastructure/scripts/deploy.sh` (git pull + docker compose build + up)

## Key Files

| File | Purpose |
|------|---------|
| `dataset_contracts.json` | Source of truth for all 398 datasets |
| `dataset_families.json` | Year-variant dataset families + loader hints |
| `etl/src/scheduler.py` | ETL entry point and scheduling |
| `etl/src/pipeline.py` | Per-dataset dispatch to extractors/loaders |
| `etl/src/boundaries.py` | Admin-boundary seeding + spatial-code resolution |
| `backend/src/api/routers/tiles_router.py` | Vector tiles (ST_AsMVT) for the unified geo layer |
| `backend/src/api/main.py` | FastAPI app setup |
| `backend/src/api/auth.py` | Auth logic (JWT + bcrypt) |
| `sql/migrations/001_schemas_and_core.sql` | Full DB schema |
| `sql/migrations/002_materialized_views.sql` | Mart views + refresh functions |
| `infrastructure/docker-compose.yml` | All service definitions |
| `.env.example` | All required environment variables with docs |
