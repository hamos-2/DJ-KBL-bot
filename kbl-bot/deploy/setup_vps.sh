#!/usr/bin/env bash
# ==============================================================================
# KBL Bot — Ubuntu 22.04 / 24.04 LTS VPS Bootstrap Script
# Usage on fresh VPS:
#   chmod +x deploy/setup_vps.sh
#   sudo ./deploy/setup_vps.sh
# ==============================================================================
set -euo pipefail

echo "========================================================"
echo "🏀 KBL Bot VPS Initial Setup (Ubuntu + Docker + Swap)"
echo "========================================================"

# 1. Configure 2GB Swap (prevents OOM on $3.5~$5/mo 1GB RAM VPS instances)
if ! swapon --show | grep -q '/swapfile'; then
  echo "[1/4] Creating 2GB swapfile..."
  fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
  sysctl vm.swappiness=10
  echo 'vm.swappiness=10' > /etc/sysctl.d/99-kbl-swap.conf
  echo "✅ 2GB Swap enabled."
else
  echo "[1/4] Swap already active, skipping."
fi

# 2. Install Docker & Docker Compose v2
if ! command -v docker >/dev/null 2>&1; then
  echo "[2/4] Installing Docker Engine & Compose plugin..."
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg ufw openssl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  echo "✅ Docker installed."
else
  echo "[2/4] Docker already installed, skipping."
fi

# 3. Lock down UFW Firewall (Only SSH 22 open; Cloudflare Tunnel works outbound-only!)
echo "[3/4] Configuring UFW firewall (Inbound: SSH only)..."
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw --force enable
echo "✅ Firewall locked down (Zero web/DB ports exposed to public internet)."

# 4. Generate production .env with strong cryptographic secrets if missing
echo "[4/4] Generating production .env secrets..."
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"

PG_PASS="$(openssl rand -hex 16)"
MASTER_KEY="$(openssl rand -hex 32)"
HMAC_KEY="$(openssl rand -hex 32)"
SKILL_SECRET="$(openssl rand -hex 16)"

if [ ! -f "${ENV_FILE}" ]; then
  cat > "${ENV_FILE}" <<EOF
APP_ENV=production
APP_DEBUG=false
LOG_LEVEL=INFO

POSTGRES_DB=kbl_bot
POSTGRES_USER=kbl_user
POSTGRES_PASSWORD=${PG_PASS}

DATABASE_URL=postgresql+asyncpg://kbl_user:${PG_PASS}@postgres:5432/kbl_bot
REDIS_URL=redis://redis:6379/0

MASTER_ENCRYPTION_KEY=${MASTER_KEY}
HMAC_SECRET_KEY=${HMAC_KEY}

WORKER_LIVE_INTERVAL_SECONDS=5
WORKER_SCHEDULED_INTERVAL_SECONDS=60
WORKER_LOOKAHEAD_DAYS=60

PROVIDER_MODE=daum

KAKAO_SKILL_SECRET=${SKILL_SECRET}
CLOUDFLARE_TUNNEL_TOKEN=
EOF
  chmod 600 "${ENV_FILE}"
  echo "✅ Production .env created at ${ENV_FILE}"
else
  echo "ℹ️  ${ENV_FILE} already exists (preserved existing secrets)."
fi

echo ""
echo "========================================================"
echo "🎉 VPS Bootstrap Complete!"
echo "Next step:"
echo "  - Quick HTTPS test (no domain needed): ./deploy/deploy.sh --quick"
echo "  - Production Named Tunnel:             ./deploy/deploy.sh --prod"
echo "========================================================"
