# Architektur-Dokumentation — Leipzig Open Data Platform

## Was ist das Projekt?

Ein **Leipzig Open Data Dashboard** — eine selbst-gehostete Web-Plattform, die 398 Datensätze von `opendata.leipzig.de` und `statistik.leipzig.de` lädt, speichert und auf einer interaktiven Karte visualisiert. Uni-Projekt im Rahmen von "Computational Spatial Humanities".

---

## Überblick: Die 7 Services

```
Internet
    │
    ▼ :80 (HTTP→HTTPS-Redirect) / :443 (HTTPS, Let's Encrypt)
┌─────────────────────────────────────────────────────┐
│                     nginx                           │
│           (Reverse Proxy + Rate Limiting)           │
└──────────────┬───────────────────┬──────────────────┘
               │ /api/*            │ /*
               ▼                   ▼
        ┌──────────┐         ┌──────────┐
        │ backend  │         │ frontend │
        │ FastAPI  │         │  nginx   │
        │  :8000   │         │  :80     │
        └─────┬────┘         └──────────┘
              │ async SQL          (statische React-
              │ + Redis            Build-Dateien)
         ┌────┴────┐
         │         │
         ▼         ▼
  ┌──────────┐  ┌──────────┐
  │    db    │  │  redis   │
  │Postgres  │  │  Cache   │
  │+PostGIS  │  │  128 MB  │
  └────▲─────┘  └──────────┘
       │
  ┌────┴─────┐
  │   etl    │  ← schreibt nur in die DB, kein Netzwerk zum Backend
  │ Scheduler│
  └──────────┘

  ┌──────────┐   ┌─────────────┐
  │ certbot  │   │ uptime-kuma │
  │TLS renew │   │  Monitoring │
  └──────────┘   └─────────────┘
```

---

## Jeder Service im Detail

### `db` — PostgreSQL 16 + PostGIS 3.4
- Einzige persistente Datenquelle; alle anderen Services sind zustandslos
- Port `5432` nur auf `127.0.0.1` exposed — nicht von außen erreichbar
- RAM-optimiert: `shared_buffers=768MB`, `work_mem=8MB`, max 50 Connections
- Volume: `db_data` (persistiert Datenbankdateien)
- Healthcheck: `pg_isready` — Backend und ETL warten darauf, bevor sie starten

### `redis` — Redis 7
- Reiner Query-Cache für das Backend (`@cached(ttl=N)` Decorator)
- LRU-Eviction bei 128 MB Limit — kein persistenter Zustand nötig
- Nur intern erreichbar (kein exposed Port)

### `backend` — FastAPI
- Startet erst wenn `db` **und** `redis` healthy sind (`depends_on: condition: service_healthy`)
- Kommuniziert mit `db` via `POSTGRES_HOST=db` und mit `redis` via `REDIS_URL=redis://redis:6379/0`
- Port `8000` nur intern exposed — Nginx leitet `/api/*` dorthin weiter

### `etl` — ETL-Scheduler
- Startet erst wenn `db` healthy ist
- Hat **kein Netzwerk zum Backend** — schreibt direkt in die DB
- Liest `dataset_contracts.json` und `sql/` als Read-only Volumes ein
- Läuft dauerhaft: `python -m src.scheduler` (nightly 02:00 UTC + alle 5 min für Live-Daten)
- Logs landen im Volume `etl_logs`

### `frontend` — React SPA (nginx)
- Multi-Stage Dockerfile: Stage 1 = `npm run build`, Stage 2 = nginx serviert statische Dateien
- Port `80` nur intern — Nginx leitet alle anderen Requests (`/*`) dorthin weiter
- Kein direkter DB-Zugriff — kommuniziert nur über `/api/*` mit dem Backend

### `nginx` — Reverse Proxy
- Einziger Service mit öffentlichen Ports: `:80` (HTTP-Redirect) und `:443` (HTTPS)
- Routing-Regeln:
  - `/api/auth/*` → Backend, Rate-Limit **5 req/min** (Brute-Force-Schutz)
  - `/api/*` → Backend, Rate-Limit **30 req/min**
  - `/*` → Frontend (SPA-Fallback auf `index.html`)
- Gzip-Komprimierung für JSON, JavaScript, GeoJSON
- Security-Headers: `X-Frame-Options DENY`, CSP, `nosniff`, HSTS
- TLS via Let's Encrypt — Zertifikat liegt in `infrastructure/certbot/conf/` (Bind-Mount)
- Domain: `auerbachs-auge.tech`

### `certbot` — TLS-Renewal
- Prüft alle 12h ob Renewal nötig (`certbot renew --quiet`)
- Teilt Bind-Mount-Verzeichnisse mit nginx: `infrastructure/certbot/conf/` (Zertifikate) und `infrastructure/certbot/www/` (ACME-Challenges)
- Erstzertifikat einmalig per `certbot-init.sh` ausstellen (vor dem ersten `docker compose up`)

### `uptime-kuma` — Monitoring
- Port `3001` nur auf `127.0.0.1` — nur per SSH-Tunnel erreichbar, nicht öffentlich
- Überwacht alle Services via HTTP-Healthchecks + optionalem Webhook

---

## Startup-Reihenfolge (durch `depends_on`)

```
db (healthy)
    ├── redis (healthy)
    │       └── backend (healthy)
    │                   └── nginx (startet)
    └── etl (startet sofort nach db)

frontend (startet unabhängig)
    └── nginx (wartet auch auf frontend)

certbot / uptime-kuma: komplett unabhängig
```

---

## Datenpipeline: Von Quelle bis Browser

```
1. opendata.leipzig.de / statistik.leipzig.de
        ↓  httpx + tenacity (Retry mit Exponential Backoff)
2. ETL Extractor  (GeoJSON / CSV / JSON)
        ↓  Rohdaten + Audit-Log
3. raw_ingest Schema  (PostgreSQL)
        ↓  Normalisierung + Upsert
4. core Schema  (park_ride, bicycle_counts, geo_features, statistics…)
        ↓  Nach ETL-Lauf: REFRESH MATERIALIZED VIEW CONCURRENTLY
5. mart Schema  (park_ride_latest, bicycle_daily, active_restrictions…)
        ↓  Async psycopg3 Query
6. FastAPI Backend  → Redis Cache (60–3600s TTL)
        ↓  JSON / GeoJSON Response
7. Nginx  (/api/*)
        ↓  Axios + React Query (Polling je nach Layer)
8. MapLibre GL Karte im Browser
```

Die API liest **nie** direkt aus `core` — immer nur aus den materialisierten `mart`-Views. Das garantiert schnelle, konsistente Reads auch während laufender ETL-Runs.

---

## Datenbankschema (PostgreSQL 16 + PostGIS 3.4)

```
raw_ingest   ← ETL-Audit-Log + Rohdaten (Backup für Fehleranalyse)
staging      ← Zwischenschicht (aktuell kaum genutzt)
core         ← Normalisierte Domänen-Tabellen
mart         ← Materialisierte Views (API-Reads, CONCURRENTLY refreshed)
auth         ← Users + Refresh-Tokens (SHA-256 gehasht, 30 Tage TTL)
```

Migrations werden in `public.schema_migrations` getrackt und beim ETL-Start automatisch angewendet (`etl/src/db.py:run_migrations()`).

---

## ETL-Pipeline im Detail

**Zentrale Konfigurationsdatei:** `dataset_contracts.json` im Root — definiert alle 398 Datensätze.

```
dataset_contracts.json
    │
    ▼
scheduler.py  ─── nightly 02:00 UTC ──► run_nightly() ─► alle 398 Datensätze
                                                          + mart.refresh_all()
              ─── alle 5 Minuten ──────► run_live()    ─► 18 Live-Datensätze
                                                          + mart.refresh_live()
                         │
                         ▼
                    pipeline.py  (run_dataset pro Datensatz)
                         │
              ┌──────────┼──────────────────────────┐
              ▼          ▼                           ▼
     GeoJsonExtractor  CsvExtractor      StatistikApiExtractor
              │          │                           │
              └──────────┴───────────────────────────┘
                                    │
                         loaders/postgres.py
                                    │
              ┌──────────┬──────────┬──────────┬─────────────────┐
              ▼          ▼          ▼           ▼                 ▼
        park_ride   bicycle     traffic    geo_features      statistics
                    _counts   _restrictions
```

**Dispatch-Logik** in `pipeline.py`: Name-Matching auf den Datensatz-Titel (z.B. `"park-ride"` im Namen → `upsert_park_ride()`). Unbekannte Formate landen als Rohpayload in `raw_ingest.payloads`.

---

## Backend API — Endpoints

```
POST   /api/auth/login           ← JWT-Login (kein Auth nötig)
POST   /api/auth/refresh         ← Access Token erneuern
GET    /api/auth/me              ← eigenes Profil

GET    /api/datasets             ← alle 398 Datensätze + ETL-Status

GET    /api/map/features         ← GeoJSON (Bbox-Filter, max 2000 Features)
GET    /api/map/park-ride        ← Live P+R-Belegung (Cache 60s)
GET    /api/map/bicycle-counters ← Zählstellen + Zeitreihe (Cache 120s)
GET    /api/map/restrictions     ← Aktive Verkehrseinschränkungen (Cache 120s)
GET    /api/map/admin-boundaries ← Verwaltungsgrenzen (Cache 3600s)

GET    /api/stats/*              ← Metriken, Zeitreihen, Korrelation, Choropleth

GET    /health                   ← Health-Check (ungeschützt)
GET    /ready                    ← Readiness-Check (ungeschützt)
```

**Auth:** Access Token JWT (60 min) + Refresh Token SHA-256 in DB (30 Tage). Alle `/api/*` außer `/auth/login` brauchen `Authorization: Bearer <token>`.

---

## Frontend-Architektur

```
App.tsx
├── /login  → LoginPage  (JWT-Formular, Zustand in authStore)
└── /*      → RequireAuth (Redirect auf /login wenn kein Token)
                └── DashboardPage
                    ├── /          → MapView    (MapLibre GL, Layer-Polling)
                    ├── /stats     → StatsPanel (Recharts Zeitreihen + Pearson)
                    └── /datasets  → DatasetList (alle 398 + ETL-Status)
```

**State:** Zustand — `authStore` (Token), `mapStore` (aktive Layer, Choropleth-Metrik, Jahr)

**Polling-Intervalle (React Query):**
| Layer | Intervall |
|---|---|
| Park+Ride | 60s |
| Verkehrseinschränkungen | 120s |
| Fahrrad-Zählstellen | 300s |
| Admin-Grenzen | 3600s |

**Karte:** MapLibre GL via `@vis.gl/react-maplibre`, CartoDB Dark Matter als Basemap, Zentrierung Leipzig (12.3731, 51.3397).

---

## HTTPS-Setup

Erstzertifikat ausstellen (einmalig, vor dem ersten `docker compose up`):

```bash
export CERTBOT_EMAIL=deine@email.com
bash /opt/leipzig-data/infrastructure/scripts/certbot-init.sh
```

Das Script stoppt laufende Container, startet einen temporären Certbot-Container auf Port 80 (standalone), stellt das Let's Encrypt-Zertifikat aus und legt es in `infrastructure/certbot/conf/` ab.

Danach erneuert der `certbot`-Service das Zertifikat automatisch alle 12h (nur wenn Ablauf < 30 Tage). Let's Encrypt-Zertifikate laufen nach 90 Tagen ab.

**Nginx-Routing:**
- `HTTP :80` → ACME-Challenge-Pfad durchlassen, alles andere → 301 auf `HTTPS :443`
- `HTTPS :443` → TLS terminiert (Let's Encrypt), dann Proxy zu backend/frontend

---

## Telegram-Benachrichtigungen

Der ETL-Scheduler sendet automatisch Benachrichtigungen:

| Ereignis | Nachricht |
|---|---|
| Nightly ETL gestartet | Anzahl Datensätze |
| Nightly ETL abgeschlossen | Erfolg / Fehler / Übersprungen |
| Nightly ETL >10% Fehler | Warnung mit Anzahl Fehlern |
| Mart-Refresh fehlgeschlagen | Fehlermeldung |
| Live-Refresh Mart-Fehler | Fehlermeldung |

Konfiguration in `.env`: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`.

**Bot einrichten:**
1. Bei [@BotFather](https://t.me/BotFather) `/newbot` → Token kopieren
2. Bot anschreiben, dann `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id` kopieren
3. Beide Werte in `.env` eintragen

---

## CI/CD Pipeline

```
git push → main
    │
    ▼ GitHub Actions (.github/workflows/deploy.yml)
    ├── PR: lint + npm run build (Validation)
    └── Push to main:
            SSH zum VPS
            └── infrastructure/scripts/deploy.sh
                    ├── git reset --hard origin/main
                    ├── docker compose build backend etl frontend
                    ├── docker compose up -d --remove-orphans
                    ├── Warte auf Backend-Health (/health)
                    └── docker image prune -f
```

**Required Secrets:** `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_SSH_PORT`

---

## Infrastruktur-Übersicht

| Service | Image | Port (extern) | Port (intern) |
|---|---|---|---|
| db | postgis/postgis:16-3.4-alpine | 127.0.0.1:5432 | 5432 |
| redis | redis:7-alpine | — | 6379 |
| backend | custom (FastAPI) | — | 8000 |
| etl | custom (Python) | — | — |
| frontend | custom (React+nginx) | — | 80 |
| nginx | nginx:alpine | 0.0.0.0:80, 0.0.0.0:443 | — |
| certbot | certbot/certbot | — | — |
| uptime-kuma | louislam/uptime-kuma:1 | 127.0.0.1:3001 | 3001 |
