#!/usr/bin/env bash
# =============================================================================
# Nightly PostgreSQL backup script
# Install cron: 0 3 * * * /opt/leipzig-data/infrastructure/scripts/backup.sh
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leipzig-data}"
COMPOSE_FILE="$APP_DIR/infrastructure/docker-compose.yml"
BACKUP_DIR="${BACKUP_DIR:-/opt/backups/leipzig}"
RETENTION_DAYS=14

source "$APP_DIR/.env" 2>/dev/null || true

TS=$(date +%Y%m%d_%H%M%S)
FILENAME="leipzig_data_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "=== Backup: $TS ==="

# Dump via pg_dump inside the db container
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  | gzip > "$BACKUP_DIR/$FILENAME"

echo "Written: $BACKUP_DIR/$FILENAME ($(du -h "$BACKUP_DIR/$FILENAME" | cut -f1))"

# Prune old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
echo "Pruned backups older than $RETENTION_DAYS days"

# Optional: upload to S3 (requires AWS CLI and env vars)
if [ -n "${BACKUP_S3_BUCKET:-}" ]; then
  aws s3 cp "$BACKUP_DIR/$FILENAME" "s3://$BACKUP_S3_BUCKET/${BACKUP_S3_PREFIX:-backups}/$FILENAME"
  echo "Uploaded to S3"
fi

echo "=== Backup done ==="
