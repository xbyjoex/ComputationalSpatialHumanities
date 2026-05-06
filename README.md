# Leipzig Open Data Platform

An authenticated, self-hosted dashboard for all 413 Leipzig open datasets — interactive map, statistics, correlations — deployed on a single VPS.

## Stack

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 + PostGIS 3.4 |
| ETL | Python 3.11 (httpx, psycopg3, shapely) |
| API | FastAPI + Uvicorn |
| Cache | Redis 7 |
| Frontend | React 18 + MapLibre GL + Recharts |
| Proxy | Nginx + Let's Encrypt |
| Runtime | Docker Compose |
| CI/CD | GitHub Actions → SSH deploy |
| Monitoring | Uptime Kuma |

## Project Structure

```
├── backend/          # FastAPI REST API (auth, map, stats, datasets)
├── etl/              # Nightly + live ETL pipeline
├── frontend/         # React SPA (map dashboard, stats, dataset browser)
├── sql/              # DB migrations and mart views
├── infrastructure/   # Docker Compose, Nginx, VPS scripts
└── dataset_contracts.json  # 398 dataset definitions (auto-classified)
```

## Dataset Coverage

- **398** datasets from opendata.leipzig.de + statistik.leipzig.de
- **18** live / near-realtime sources (Park+Ride, Radzählstellen, Verkehrseinschränkungen …)
- **380** nightly-refreshed sources (statistics, elections, demographics, environment …)
- **51** datasets with geospatial resources

## Quick Start (local dev)

```bash
# 1. Clone and copy env
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, SECRET_KEY

# 2. Start DB + Redis
docker compose -f infrastructure/docker-compose.yml up -d db redis

# 3. Run migrations (done automatically by ETL scheduler)
# Or manually: psql < sql/migrations/001_schemas_and_core.sql

# 4. Backend
cd backend && pip install -e . && uvicorn src.api.main:app --reload

# 5. Frontend
cd frontend && npm install && npm run dev

# 6. ETL (once to seed data)
cd etl && pip install -e . && python -m src.scheduler
```

## VPS Deployment

### First-time setup
```bash
# On VPS as root
curl -fsSL https://raw.githubusercontent.com/YOURUSER/YOURREPO/main/infrastructure/scripts/setup-vps.sh \
  | DOMAIN=yourdomain.com REPO_URL=https://github.com/... bash
```

### Manual deploy
```bash
cd /opt/leipzig-data
bash infrastructure/scripts/deploy.sh
```

### TLS certificate
```bash
# Initial certificate (stop nginx first if needed)
docker run --rm -p 80:80 certbot/certbot certonly \
  --standalone -d yourdomain.com --agree-tos -m you@email.com
```

### Git push → auto-deploy (CI/CD)
Set these GitHub Actions secrets:
- `VPS_HOST` — VPS IP address
- `VPS_USER` — deploy username (default: `deploy`)
- `VPS_SSH_KEY` — private SSH key for the deploy user

Push to `main` → lints → builds frontend → deploys via SSH.

## Memory Budget (4 GB VPS)

| Service | Target |
|---|---|
| PostgreSQL | 768 MB shared_buffers + 2 GB effective_cache |
| Redis | 128 MB max |
| Backend (2 workers) | ~200 MB |
| ETL scheduler | ~150 MB |
| Nginx | ~30 MB |
| OS overhead | ~600 MB |
| **Headroom** | ~1.1 GB |

## Backups

```bash
# Install cron on VPS (runs daily at 03:00)
echo "0 3 * * * /opt/leipzig-data/infrastructure/scripts/backup.sh" | crontab -
```

Backups are stored in `/opt/backups/leipzig/` and optionally uploaded to S3.
Retention: 14 days local.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Get access + refresh token |
| POST | `/api/auth/refresh` | Rotate refresh token |
| GET | `/api/auth/me` | Current user info |
| GET | `/api/datasets` | List all datasets |
| GET | `/api/datasets/status` | ETL run status per dataset |
| GET | `/api/map/features` | GeoJSON bbox query |
| GET | `/api/map/park-ride` | Live Park+Ride occupancy |
| GET | `/api/map/bicycle-counters` | Bicycle counter time series |
| GET | `/api/map/restrictions` | Active traffic restrictions |
| GET | `/api/map/admin-boundaries` | Admin boundary polygons |
| GET | `/api/stats/metrics` | Available metric names |
| GET | `/api/stats/timeseries` | Metric time series |
| GET | `/api/stats/correlation` | Pearson r + scatter data |
| GET | `/api/stats/choropleth` | GeoJSON choropleth layer |

All endpoints require `Authorization: Bearer <token>` except `/health` and `/ready`.
