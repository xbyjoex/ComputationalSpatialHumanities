# Deployment-Anleitung — Leipzig Open Data Platform

Schritt-für-Schritt-Guide vom leeren VPS bis zur laufenden Plattform.

---

## Voraussetzungen

- VPS mit Ubuntu 22.04 oder 24.04 (min. 4 GB RAM, 20 GB Disk)
- GitHub-Account mit diesem Repository
- Telegram-Account

Domain: **auerbachs-auge.tech** (Hostinger). TLS via Let's Encrypt — vollständiges, von Browsern akzeptiertes Zertifikat, automatisches Renewal.

---

## Schritt 1 — Telegram Bot einrichten

Du brauchst zwei Werte: **Bot-Token** und **Chat-ID**.

### Bot-Token holen

1. In Telegram [@BotFather](https://t.me/BotFather) anschreiben
2. `/newbot` senden
3. Name eingeben (z.B. `Leipzig ETL Bot`)
4. Username eingeben (muss auf `bot` enden, z.B. `LeipzigETLBot`)
5. BotFather gibt dir einen Token: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
   → Das ist dein `TELEGRAM_BOT_TOKEN`

### Chat-ID holen

1. Deinen neuen Bot anschreiben (einfach `/start` senden)
2. Im Browser aufrufen:
   ```
   https://api.telegram.org/bot<DEIN_TOKEN>/getUpdates
   ```
3. In der JSON-Antwort: `result[0].message.chat.id`
   → Das ist deine `TELEGRAM_CHAT_ID` (z.B. `987654321`)

---

## Schritt 2 — VPS einrichten

Per SSH als Root einloggen:

```bash
ssh root@<VPS-IP>
```

Setup-Script ausführen:

```bash
export DEPLOY_USER=deploy
export REPO_URL=https://github.com/DEIN-GITHUB-USER/DEIN-REPO.git
export APP_DIR=/opt/leipzig-data

curl -fsSL https://raw.githubusercontent.com/DEIN-GITHUB-USER/DEIN-REPO/main/infrastructure/scripts/setup-vps.sh | bash
```

Das Script installiert: Docker, UFW (Firewall), Fail2ban, klont das Repository nach `/opt/leipzig-data`.

---

## Schritt 3 — `.env` befüllen

Auf dem VPS:

```bash
cd /opt/leipzig-data
cp .env.example .env
nano .env
```

Alle Variablen im Überblick:

### Datenbank

```env
POSTGRES_HOST=db                    # Container-Name, nicht ändern
POSTGRES_PORT=5432                  # nicht ändern
POSTGRES_DB=leipzig_data            # Datenbankname, kann bleiben
POSTGRES_USER=leipzig               # DB-Benutzer, kann bleiben
POSTGRES_PASSWORD=STARKES_PASSWORT  # ← ÄNDERN: min. 20 Zeichen, zufällig
```

Passwort generieren:
```bash
openssl rand -base64 32
```

### Backend / Auth

```env
SECRET_KEY=ZUFAELLIGER_STRING       # ← ÄNDERN: für JWT-Signierung
JWT_ALGORITHM=HS256                 # nicht ändern
JWT_EXPIRE_MINUTES=60               # Access Token Laufzeit
REFRESH_TOKEN_EXPIRE_DAYS=30        # Refresh Token Laufzeit
```

Secret Key generieren:
```bash
openssl rand -hex 32
```

### CORS

```env
ALLOWED_ORIGINS=https://auerbachs-auge.tech  # bereits korrekt gesetzt
```

### Leipzig Open Data API

```env
LEIPZIG_API_BASE=https://opendata.leipzig.de/api/3   # nicht ändern
LEIPZIG_STAT_API_BASE=https://statistik.leipzig.de/opendata/api  # nicht ändern
```

### ETL-Verhalten

```env
ETL_NIGHTLY_CRON=0 2 * * *          # Uhrzeit des Nightly-Runs (02:00 UTC)
ETL_LIVE_INTERVAL_SECONDS=300       # Live-Refresh alle 5 Minuten
ETL_REQUEST_TIMEOUT_SECONDS=60      # HTTP-Timeout pro Request
ETL_MAX_RETRIES=3                   # Retry-Versuche bei Fehler
ETL_BACKOFF_FACTOR=2.0              # Exponentieller Backoff-Faktor
```

### Redis

```env
REDIS_URL=redis://redis:6379/0      # nicht ändern
```

### Telegram

```env
TELEGRAM_BOT_TOKEN=123456:ABC...    # ← aus Schritt 1
TELEGRAM_CHAT_ID=987654321          # ← aus Schritt 1
```

### Monitoring (optional)

```env
UPTIME_KUMA_PUSH_URL=               # optional, Uptime Kuma Webhook
```

### Backup (optional)

```env
BACKUP_S3_BUCKET=                   # optional, S3-Bucket für Backups
BACKUP_S3_PREFIX=leipzig-data-backups
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
```

---

## Schritt 4 — DNS-A-Record setzen (einmalig)

Im **Hostinger-Panel** unter DNS-Verwaltung für `auerbachs-auge.tech`:

```
Typ:   A
Name:  @
Wert:  <VPS-IP>
TTL:   300
```

Propagation abwarten (5–30 min), dann prüfen:
```bash
nslookup auerbachs-auge.tech
```

## Schritt 5 — Let's Encrypt Zertifikat ausstellen (einmalig)

```bash
export CERTBOT_EMAIL=deine@email.com
bash /opt/leipzig-data/infrastructure/scripts/certbot-init.sh
```

Das Script stoppt laufende Container, stellt das Zertifikat via Certbot standalone aus und legt es in `infrastructure/certbot/conf/` ab. Der `certbot`-Service erneuert es danach automatisch alle 12h.

---

## Schritt 6 — Ersten Start durchführen

```bash
cd /opt/leipzig-data

docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml up -d --build
```

Services hochfahren dauert beim ersten Start 2–5 Minuten (Images bauen). Status prüfen:

```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml ps
```

Alle Services sollten `Up (healthy)` zeigen. Logs prüfen:

```bash
# Alle Services
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs -f

# Einzelner Service
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs -f etl
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs -f backend
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs -f nginx
```

---

## Schritt 7 — GitHub Actions Secrets konfigurieren

Damit CI/CD bei jedem Push auf `main` automatisch deployed, braucht GitHub Zugriff auf den VPS.

### SSH-Key für den Deploy-User erstellen (auf dem VPS):

```bash
# Als deploy-User einloggen
su - deploy

# SSH-Key generieren (ohne Passphrase!)
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/github_deploy -N ""

# Public Key zum authorized_keys hinzufügen
cat ~/.ssh/github_deploy.pub >> ~/.ssh/authorized_keys

# Private Key anzeigen — diesen in GitHub einfügen
cat ~/.ssh/github_deploy
```

### Secrets in GitHub eintragen:

Gehe zu: `GitHub → Repository → Settings → Secrets and variables → Actions → New repository secret`

| Secret-Name | Wert | Wo herkommt er |
|---|---|---|
| `VPS_HOST` | `123.45.67.89` | IP-Adresse deines VPS |
| `VPS_USER` | `deploy` | Deploy-User auf dem VPS |
| `VPS_SSH_KEY` | `-----BEGIN OPENSSH...` | Gesamter Inhalt von `~/.ssh/github_deploy` (Private Key) |
| `VPS_SSH_PORT` | `22` | SSH-Port (meist 22) |

### GitHub Environment anlegen:

Gehe zu: `GitHub → Repository → Settings → Environments → New environment`

- Name: `production`
- Optional: Required reviewers für Schutz vor ungewollten Deploys

---

## Schritt 8 — Ersten Admin-User anlegen

Nach dem Start muss einmalig ein User in der Datenbank angelegt werden:

```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec db \
  psql -U leipzig -d leipzig_data -c \
  "INSERT INTO auth.users (username, password_hash)
   VALUES ('admin', crypt('DEIN_PASSWORT', gen_salt('bf', 12)))"
```

Alternativ mit Python im Backend-Container:

```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec backend python -c "
from src.api.auth import hash_password
import psycopg, os
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    conn.execute(
        'INSERT INTO auth.users (username, password_hash) VALUES (%s, %s)',
        ('admin', hash_password('DEIN_PASSWORT'))
    )
    conn.commit()
print('User erstellt')
"
```

---

## Schritt 9 — Alles verifizieren

```bash
# HTTP → HTTPS Redirect?
curl -I http://auerbachs-auge.tech
# → 301 Moved Permanently

# HTTPS antwortet?
curl https://auerbachs-auge.tech/health
# → {"status":"ok"}

# ETL läuft?
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs etl | tail -20

# Zertifikat gültig bis?
openssl s_client -connect auerbachs-auge.tech:443 -servername auerbachs-auge.tech < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Telegram testen:

1. Bot anschreiben: `help` → Befehlsübersicht erscheint
2. `status` → "✅ Idle" erscheint
3. `etl-live` → Live-Refresh startet, Bestätigung kommt

---

## Normaler Deployment-Ablauf (nach Setup)

Nach dem initialen Setup läuft alles automatisch:

```
git push → main
    │
    ▼ GitHub Actions (automatisch)
    lint + build prüfen
    SSH zum VPS → deploy.sh
        git pull
        docker compose build
        docker compose up -d
        health check
    ▼
    fertig in ~3 Minuten
```

Manuell deployen (auf dem VPS):
```bash
cd /opt/leipzig-data
bash infrastructure/scripts/deploy.sh
```

---

## Häufige Probleme

### nginx startet nicht
```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs nginx
# Häufigste Ursache: Zertifikat fehlt noch → certbot-init.sh erneut ausführen
# Prüfen ob Cert-Dateien vorhanden sind:
ls -la /opt/leipzig-data/infrastructure/certbot/conf/live/auerbachs-auge.tech/
```

### ETL schlägt fehl
```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs etl | grep FAIL
# Einzelnen Datensatz testen:
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec etl \
  python -c "from src.pipeline import run_dataset; run_dataset({...})"
```

### Telegram-Bot antwortet nicht
```bash
# Prüfen ob polling läuft:
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml logs etl | grep telegram
# Token/Chat-ID in .env prüfen
# Sicherstellen dass du mit dem Bot geschrieben hast (nicht an dich selbst)
```

### Disk voll / Mart-Refresh schlägt fehl mit `No space left on device`

Die Datenbank ist zu groß geworden. Erste Diagnose — größte Tabellen anzeigen:

```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec db psql -U leipzig -d leipzig_data -c "SELECT schemaname||'.'||relname AS table, pg_size_pretty(pg_total_relation_size(relid)) AS size FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15"
```

Ab Migration 005/006 erledigen die Migrations Dedup + Retention + `VACUUM FULL` einmalig. Wiederholte Retention erfolgt nachts in `scheduler.run_nightly` (Park+Ride 30d, Bicycle 365d, etl_runs 90d). Wenn die Disk trotzdem wächst, prüfe `raw_ingest.payloads` (sollte ≤ 1 Zeile pro `dataset_id` enthalten) und ob neue Loader-Aufrufe `ON CONFLICT` korrekt nutzen.

Manueller Notlauf (falls Disk akut voll und Migrations noch nicht durch sind):

```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec db psql -U leipzig -d leipzig_data -c "DELETE FROM raw_ingest.payloads WHERE ingested_at < NOW() - INTERVAL '1 day'; VACUUM FULL raw_ingest.payloads;"
```

### Datenbank-Migration fehlgeschlagen
```bash
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec db \
  psql -U leipzig -d leipzig_data -c "SELECT * FROM public.schema_migrations"
# Manuell ausführen:
docker compose --project-directory /opt/leipzig-data -f infrastructure/docker-compose.yml exec db \
  psql -U leipzig -d leipzig_data -f /docker-entrypoint-initdb.d/001_schemas_and_core.sql
```

---

## Backup manuell ausführen

```bash
bash /opt/leipzig-data/infrastructure/scripts/backup.sh
# Dumps landen in /opt/backups/
```

Automatisches tägliches Backup (03:00 Uhr) per Cron einrichten:
```bash
echo "0 3 * * * /opt/leipzig-data/infrastructure/scripts/backup.sh" | crontab -
```
