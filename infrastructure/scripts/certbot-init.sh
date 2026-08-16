#!/usr/bin/env bash
# =============================================================================
# Let's Encrypt Erstzertifikat ausstellen für auerbachs-auge.tech
# Einmalig auf dem VPS ausführen, BEVOR docker compose up gestartet wird.
#
# Voraussetzungen:
#   - DNS A-Record für auerbachs-auge.tech zeigt auf diese VPS-IP
#   - Port 80 ist von außen erreichbar
#   - CERTBOT_EMAIL ist gesetzt
#
# Verwendung:
#   export CERTBOT_EMAIL=deine@email.com
#   bash infrastructure/scripts/certbot-init.sh
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leipzig-data}"
COMPOSE_FILE="$APP_DIR/infrastructure/docker-compose.yml"
DOMAIN="auerbachs-auge.tech"
CERTBOT_EMAIL="${CERTBOT_EMAIL:?Bitte setzen: export CERTBOT_EMAIL=deine@email.com}"
CERTBOT_CONF="$APP_DIR/infrastructure/certbot/conf"
CERTBOT_WWW="$APP_DIR/infrastructure/certbot/www"

echo "=== Certbot Init: $DOMAIN ==="

# Verzeichnisse anlegen
mkdir -p "$CERTBOT_CONF" "$CERTBOT_WWW"

# Laufende Container stoppen (Port 80 freigeben)
echo "Stoppe laufende Container..."
docker compose --project-directory "$APP_DIR" -f "$COMPOSE_FILE" down 2>/dev/null || true

# Zertifikat via standalone ausstellen (certbot hört selbst auf Port 80)
echo "Stelle Zertifikat aus..."
docker run --rm \
  -p 80:80 \
  -v "$CERTBOT_CONF:/etc/letsencrypt" \
  -v "$CERTBOT_WWW:/var/www/certbot" \
  certbot/certbot certonly \
    --standalone \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    -d "$DOMAIN"

# Erneuerung auf webroot umstellen.
#
# Der Bootstrap oben MUSS standalone sein: nginx startet ohne vorhandenes
# Zertifikat nicht, kann die ACME-Challenge also noch nicht ausliefern. Certbot
# speichert die verwendete Methode aber dauerhaft in der Renewal-Config — und
# standalone scheitert ab dann bei jeder Erneuerung, weil nginx Port 80 belegt.
# Genau so lief das Zertifikat am 2026-08-09 unbemerkt ab: certbot versuchte es
# alle 12h, bekam von nginx eine 404 auf den Challenge-Pfad und gab auf.
#
# nginx liefert /.well-known/acme-challenge/ aus /var/www/certbot aus, sobald es
# läuft. Ab der ersten Erneuerung ist webroot also die richtige Methode.
RENEWAL_CONF="$CERTBOT_CONF/renewal/$DOMAIN.conf"
if grep -q '^authenticator = standalone' "$RENEWAL_CONF" 2>/dev/null; then
  echo "Stelle Erneuerungsmethode auf webroot um..."
  sed -i \
    -e 's|^authenticator = standalone|authenticator = webroot\nwebroot_path = /var/www/certbot,|' \
    "$RENEWAL_CONF"
  grep -q '^\[\[webroot_map\]\]' "$RENEWAL_CONF" || echo '[[webroot_map]]' >> "$RENEWAL_CONF"
fi

echo ""
echo "=== Zertifikat erfolgreich ausgestellt ==="
echo "Gültig bis: $(openssl x509 -noout -enddate -in "$CERTBOT_CONF/live/$DOMAIN/fullchain.pem")"
echo ""
echo "Jetzt starten:"
echo "  cd $APP_DIR && docker compose --project-directory $APP_DIR -f infrastructure/docker-compose.yml up -d --build"
