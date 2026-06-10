#!/usr/bin/env bash
# =============================================================================
# Deployment script — runs on VPS via SSH from CI/CD or manually
# Usage: ./infrastructure/scripts/deploy.sh
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leipzig-data}"
COMPOSE_FILE="$APP_DIR/infrastructure/docker-compose.yml"
COMPOSE="docker compose --project-directory $APP_DIR -f $COMPOSE_FILE"

echo "=== Deploy: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

cd "$APP_DIR"

# Pull latest code
git fetch origin main
git reset --hard origin/main

# Rebuild and restart changed services only
$COMPOSE build --pull --no-cache backend etl frontend
$COMPOSE up -d --remove-orphans

# Wait for backend health
echo "Waiting for backend health …"
for i in $(seq 1 30); do
  if $COMPOSE exec -T backend curl -sf http://localhost:8000/health &>/dev/null; then
    echo "Backend healthy"
    break
  fi
  sleep 2
done

# Nginx config is bind-mounted read-only — reload to pick up changes
$COMPOSE exec -T nginx nginx -s reload || true

# Prune old images and build cache (builds run with --no-cache, so the
# BuildKit cache is never read — only written. Without pruning it grows
# by the full build size on every deploy.)
docker image prune -f
docker builder prune -af

echo "=== Deploy done ==="
