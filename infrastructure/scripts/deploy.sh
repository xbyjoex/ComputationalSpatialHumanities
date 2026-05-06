#!/usr/bin/env bash
# =============================================================================
# Deployment script — runs on VPS via SSH from CI/CD or manually
# Usage: ./infrastructure/scripts/deploy.sh
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leipzig-data}"
COMPOSE_FILE="$APP_DIR/infrastructure/docker-compose.yml"

echo "=== Deploy: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

cd "$APP_DIR"

# Pull latest code
git fetch origin main
git reset --hard origin/main

# Rebuild and restart changed services only
docker compose -f "$COMPOSE_FILE" build --pull --no-cache backend etl frontend
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Wait for backend health
echo "Waiting for backend health …"
for i in $(seq 1 30); do
  if docker compose -f "$COMPOSE_FILE" exec -T backend \
       curl -sf http://localhost:8000/health &>/dev/null; then
    echo "Backend healthy"
    break
  fi
  sleep 2
done

# Prune old images
docker image prune -f

echo "=== Deploy done ==="
