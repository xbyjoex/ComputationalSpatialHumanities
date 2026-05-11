#!/usr/bin/env bash
# =============================================================================
# Self-signed TLS-Zertifikat generieren (gültig 10 Jahre).
# Einmalig auf dem VPS ausführen.
#
# Verwendung:
#   bash infrastructure/scripts/generate-selfsigned.sh
# =============================================================================
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/leipzig-data}"
CERTS_DIR="$APP_DIR/infrastructure/nginx/certs"

mkdir -p "$CERTS_DIR"

# VPS-IP automatisch ermitteln (oder manuell überschreiben)
VPS_IP="${VPS_IP:-$(curl -s https://api.ipify.org)}"

echo "=== Generiere self-signed Zertifikat für IP: $VPS_IP ==="

openssl req -x509 -nodes \
  -days 3650 \
  -newkey rsa:2048 \
  -keyout "$CERTS_DIR/privkey.pem" \
  -out   "$CERTS_DIR/fullchain.pem" \
  -subj  "/CN=$VPS_IP/O=Leipzig Open Data/C=DE" \
  -addext "subjectAltName=IP:$VPS_IP"

chmod 600 "$CERTS_DIR/privkey.pem"
chmod 644 "$CERTS_DIR/fullchain.pem"

echo ""
echo "=== Fertig ==="
echo "Zertifikat: $CERTS_DIR/fullchain.pem"
echo "Key:        $CERTS_DIR/privkey.pem"
echo "Gültig bis: $(openssl x509 -noout -enddate -in "$CERTS_DIR/fullchain.pem")"
echo ""
echo "Browser-Warnung beim ersten Aufruf ist normal — einmalig 'Trotzdem fortfahren' klicken."
