#!/usr/bin/env bash
# ==============================================================================
# KBL Bot — One-Command Deployment Script (Cloudflare Tunnel + Docker Compose)
# Usage:
#   ./deploy/deploy.sh --quick   # Instant *.trycloudflare.com HTTPS URL (no domain needed)
#   ./deploy/deploy.sh --prod    # Production Cloudflare Zero Trust Tunnel (uses CLOUDFLARE_TUNNEL_TOKEN)
# ==============================================================================
set -euo pipefail

MODE="${1:---quick}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

if [ ! -f ".env" ]; then
  echo "❌ .env file not found. Run ./deploy/setup_vps.sh or copy .env.example to .env first."
  exit 1
fi

if [ "${MODE}" = "--prod" ]; then
  TUNNEL_TOKEN="$(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' .env | cut -d'=' -f2- | tr -d '[:space:]')"
  if [ -z "${TUNNEL_TOKEN}" ]; then
    echo "❌ CLOUDFLARE_TUNNEL_TOKEN is empty in .env!"
    echo "   Set CLOUDFLARE_TUNNEL_TOKEN=<your_token> in .env or use './deploy/deploy.sh --quick' first."
    exit 1
  fi
  echo "🚀 Starting KBL Bot Stack + Production Cloudflare Tunnel..."
  docker compose --profile prod up -d --build
  echo ""
  echo "✅ Production stack is up!"
  docker compose ps
  exit 0
fi

echo "🚀 Starting KBL Bot Stack + Cloudflare Quick Tunnel (*.trycloudflare.com)..."
docker compose --profile quick up -d --build

echo "⏳ Waiting for Cloudflare Quick Tunnel HTTPS URL..."
TUNNEL_URL=""
for _ in $(seq 1 20); do
  TUNNEL_URL="$(docker logs kbl_cloudflared_quick 2>&1 | grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' | head -n 1 || true)"
  if [ -n "${TUNNEL_URL}" ]; then
    break
  fi
  sleep 2
done

echo ""
echo "========================================================================"
if [ -n "${TUNNEL_URL}" ]; then
  echo "✅ Cloudflare HTTPS Tunnel Ready: ${TUNNEL_URL}"
  echo ""
  echo "📌 Kakao i OpenBuilder에 아래 Skill URL을 그대로 등록하세요:"
  echo "  1) 오늘 경기 조회 : ${TUNNEL_URL}/integrations/kakao/skills/today-games"
  echo "  2) 매치업 검색    : ${TUNNEL_URL}/integrations/kakao/skills/match-search"
  echo "  3) 실시간 스코어  : ${TUNNEL_URL}/integrations/kakao/skills/live-score"
  echo "  4) 시스템 헬스    : ${TUNNEL_URL}/integrations/kakao/skills/health"
else
  echo "⚠️  Tunnel URL을 아직 가져오지 못했습니다. 아래 명령어로 확인하세요:"
  echo "   docker logs kbl_cloudflared_quick"
fi
echo "========================================================================"
