#!/usr/bin/env bash
# =============================================================================
# Erstzertifikat via Let's Encrypt ausstellen.
# Einmalig auf dem VPS ausführen, BEVOR nginx mit HTTPS-Config gestartet wird.
#
# Voraussetzungen:
#   1. DNS-Eintrag für DOMAIN zeigt auf diese Server-IP
#   2. Port 80 ist von außen erreichbar (für ACME-Challenge)
#   3. DOMAIN und CERTBOT_EMAIL sind gesetzt (in .env oder als Umgebungsvariablen)
#
# Verwendung:
#   export DOMAIN=yourdomain.com
#   export CERTBOT_EMAIL=your@email.com
#   bash infrastructure/scripts/certbot-init.sh
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leipzig-data}"
COMPOSE_FILE="$APP_DIR/infrastructure/docker-compose.yml"

DOMAIN="${DOMAIN:?Bitte DOMAIN setzen, z.B.: export DOMAIN=yourdomain.com}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:?Bitte CERTBOT_EMAIL setzen, z.B.: export CERTBOT_EMAIL=you@example.com}"

echo "=== Certbot Init: $DOMAIN ==="

# 1. nginx temporär mit HTTP-only-Config starten (für ACME-Challenge)
#    Dafür muss in app.conf der HTTPS-Block noch NICHT aktiv sein,
#    oder nginx läuft noch nicht — dann direkt weiter zu Schritt 2.
if ! docker compose -f "$COMPOSE_FILE" ps nginx | grep -q "Up"; then
  echo "Nginx läuft nicht — starte temporär für ACME-Challenge..."
  # Starte nur nginx im HTTP-Modus (HTTPS-Block verursacht Fehler ohne Zertifikat)
  # Einfachste Lösung: kurze temp-config ohne SSL-Block
  docker run --rm -d --name nginx-tmp \
    -p 80:80 \
    -v "$APP_DIR/infrastructure/certbot/www:/var/www/certbot" \
    nginx:alpine sh -c "mkdir -p /var/www/certbot && nginx -g 'daemon off;'"
  TEMP_NGINX=true
else
  TEMP_NGINX=false
fi

# 2. Zertifikat ausstellen
echo "Stelle Zertifikat für $DOMAIN aus..."
docker run --rm \
  -v "$APP_DIR/infrastructure/certbot/conf:/etc/letsencrypt" \
  -v "$APP_DIR/infrastructure/certbot/www:/var/www/certbot" \
  certbot/certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

# 3. Temp-nginx aufräumen
if [ "$TEMP_NGINX" = "true" ]; then
  docker stop nginx-tmp 2>/dev/null || true
fi

echo ""
echo "=== Zertifikat erfolgreich ausgestellt ==="
echo ""
echo "Nächste Schritte:"
echo "  1. In infrastructure/nginx/conf.d/app.conf alle 'yourdomain.com' durch '$DOMAIN' ersetzen"
echo "  2. docker compose -f $COMPOSE_FILE up -d nginx"
echo ""
echo "Zertifikat liegt in: /etc/letsencrypt/live/$DOMAIN/"
echo "Certbot erneuert automatisch alle 12h (im certbot-Container)."
