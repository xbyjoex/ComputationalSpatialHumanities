#!/usr/bin/env bash
# =============================================================================
# VPS first-time setup script
# Run as root on a fresh Ubuntu 22.04/24.04 Hostinger VPS
# Usage: curl -fsSL https://raw.githubusercontent.com/YOURREPO/main/infrastructure/scripts/setup-vps.sh | bash
# =============================================================================
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
REPO_URL="${REPO_URL:-https://github.com/YOURUSER/YOURREPO.git}"
APP_DIR="${APP_DIR:-/opt/leipzig-data}"

echo "=== Leipzig Open Data VPS Setup ==="

# ── System packages ───────────────────────────────────────────────────────────
apt-get update && apt-get upgrade -y
apt-get install -y --no-install-recommends \
  curl git ufw fail2ban unattended-upgrades \
  ca-certificates gnupg lsb-release

# ── Docker ────────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable docker
systemctl start docker

# ── Deploy user ───────────────────────────────────────────────────────────────
if ! id "$DEPLOY_USER" &>/dev/null; then
  useradd -m -s /bin/bash "$DEPLOY_USER"
  usermod -aG docker "$DEPLOY_USER"
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:/usr/bin/docker,/usr/local/bin/docker" >> /etc/sudoers.d/deploy
  mkdir -p /home/"$DEPLOY_USER"/.ssh
  # Paste your public key here or set via environment
  # echo "ssh-ed25519 AAAA..." >> /home/"$DEPLOY_USER"/.ssh/authorized_keys
  chmod 700 /home/"$DEPLOY_USER"/.ssh
  chown -R "$DEPLOY_USER":"$DEPLOY_USER" /home/"$DEPLOY_USER"/.ssh
fi

# ── Firewall ──────────────────────────────────────────────────────────────────
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── Fail2ban ──────────────────────────────────────────────────────────────────
cat > /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled = true
maxretry = 5
bantime = 3600

[nginx-http-auth]
enabled = true
maxretry = 10
bantime = 600
EOF
systemctl enable fail2ban
systemctl restart fail2ban

# ── Auto security updates ─────────────────────────────────────────────────────
dpkg-reconfigure -f noninteractive unattended-upgrades

# ── Clone repo ────────────────────────────────────────────────────────────────
mkdir -p "$APP_DIR"
chown "$DEPLOY_USER":"$DEPLOY_USER" "$APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo -u "$DEPLOY_USER" git clone "$REPO_URL" "$APP_DIR"
fi

# ── .env file ─────────────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo ""
  echo "⚠  Edit $APP_DIR/.env with your secrets before continuing!"
  echo "   Then run: cd $APP_DIR && docker compose -f infrastructure/docker-compose.yml up -d --build"
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Add SSH public key to /home/$DEPLOY_USER/.ssh/authorized_keys"
echo "  2. Edit $APP_DIR/.env (copy from .env.example, fill in passwords + Telegram tokens)"
echo "  3. Generate self-signed TLS cert: bash $APP_DIR/infrastructure/scripts/generate-selfsigned.sh"
echo "  4. Start all services: cd $APP_DIR && docker compose -f infrastructure/docker-compose.yml up -d --build"
