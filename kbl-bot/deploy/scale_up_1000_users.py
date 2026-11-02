#!/usr/bin/env python3
"""
KBL Bot — 1,000 Concurrent Users Infrastructure Scaling & Readiness Kit.

IMPORTANT:
- By default, this script runs in DRY-RUN (`--check`) mode and DOES NOT modify
  the running production server.
- When you are ready to apply the 1,000-user high-concurrency tuning in the future,
  run with `--apply` or `--generate-ingress`.

Usage:
  # 1. Dry-run readiness check (Default — no changes made)
  python3 deploy/scale_up_1000_users.py --check

  # 2. Generate Cloudflare Named Tunnel & Caddy HTTPS configs for >200 concurrency
  python3 deploy/scale_up_1000_users.py --generate-ingress --domain bot.example.com

  # 3. Apply high-concurrency DB pool & Uvicorn uvloop tuning locally (when ready)
  python3 deploy/scale_up_1000_users.py --apply

  # 4. Run async concurrency benchmark against local or remote endpoint
  python3 deploy/scale_up_1000_users.py --benchmark --concurrency 200 --url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

ROOT_DIR = Path(__file__).resolve().parent.parent
SESSION_FILE = ROOT_DIR / "core" / "db" / "session.py"
DOCKERFILE = ROOT_DIR / "Dockerfile"
INGRESS_DIR = ROOT_DIR / "deploy" / "ingress_ready"


def check_readiness() -> dict[str, str]:
    """Inspect current local codebase configuration without modifying any files."""
    status: dict[str, str] = {}

    if SESSION_FILE.exists():
        text = SESSION_FILE.read_text(encoding="utf-8")
        if "pool_size=25" in text and "max_overflow=50" in text:
            status["db_pool"] = "SCALED (pool_size=25, max_overflow=50, max=75)"
        else:
            status["db_pool"] = "BASELINE (pool_size=10, max_overflow=20, max=30) -> Ready to upgrade"
        if "session.new or session.dirty or session.deleted" in text:
            status["db_commit_guard"] = "OPTIMIZED (Read-only requests skip commit)"
        else:
            status["db_commit_guard"] = "BASELINE (Commits on every session) -> Ready to optimize"
    else:
        status["db_pool"] = "MISSING core/db/session.py"

    if DOCKERFILE.exists():
        d_text = DOCKERFILE.read_text(encoding="utf-8")
        if "uvloop" in d_text and "httptools" in d_text:
            status["uvicorn_loop"] = "OPTIMIZED (uvloop + httptools + backlog 2048)"
        else:
            status["uvicorn_loop"] = "BASELINE (standard uvicorn) -> Ready to upgrade"
    else:
        status["uvicorn_loop"] = "MISSING Dockerfile"

    status["ingress_configs"] = (
        "GENERATED in deploy/ingress_ready/"
        if INGRESS_DIR.exists()
        else "NOT YET GENERATED (Run with --generate-ingress)"
    )
    return status


def generate_ingress_configs(domain: str = "kblbot.example.com") -> None:
    """
    Generate ready-to-use Cloudflare Named Tunnel and Caddy reverse-proxy configs
    to remove the 200-concurrent-request limit of trycloudflare.com Quick Tunnels.
    """
    INGRESS_DIR.mkdir(parents=True, exist_ok=True)

    cf_config = f"""# Cloudflare Named Tunnel Configuration (Removes 200 concurrent request cap)
# 1. Login: cloudflared tunnel login
# 2. Create: cloudflared tunnel create kbl-prod-tunnel
# 3. Route DNS: cloudflared tunnel route dns kbl-prod-tunnel {domain}
# 4. Run: cloudflared tunnel --config deploy/ingress_ready/cloudflared_config.yml run

tunnel: kbl-prod-tunnel
credentials-file: /etc/cloudflared/kbl-prod-tunnel.json

ingress:
  - hostname: {domain}
    service: http://kbl_api:8000
    originRequest:
      connectTimeout: 5s
      keepAliveConnections: 1000
      keepAliveTimeout: 90s
      http2Origin: true
  - service: http_status:404
"""
    (INGRESS_DIR / "cloudflared_config.yml").write_text(cf_config, encoding="utf-8")

    caddyfile = f"""# Caddyfile — Direct OCI Public IP (168.110.6.240) HTTPS Reverse Proxy (Zero Cloudflare limits)
# Usage: docker run -d --name kbl_caddy --network host -v $PWD/deploy/ingress_ready/Caddyfile:/etc/caddy/Caddyfile caddy:2-alpine

{domain} {{
    encode zstd gzip
    reverse_proxy 127.0.0.1:8000 {{
        transport http {{
            keepalive 90s
            keepalive_idle_conns 1000
        }}
    }}
}}
"""
    (INGRESS_DIR / "Caddyfile").write_text(caddyfile, encoding="utf-8")

    postgres_tuning = """-- PostgreSQL High-Concurrency Tuning (Run inside kbl_postgres when scaling to 1,000+ users)
ALTER SYSTEM SET max_connections = '200';
ALTER SYSTEM SET shared_buffers = '128MB';
ALTER SYSTEM SET effective_cache_size = '384MB';
ALTER SYSTEM SET work_mem = '4MB';
-- Requires container restart: sudo docker restart kbl_postgres
"""
    (INGRESS_DIR / "postgres_1000_users.sql").write_text(postgres_tuning, encoding="utf-8")


def apply_code_tuning() -> None:
    """
    Apply DB connection pool expansion, read-only commit skip, and Uvicorn uvloop flags
    to local files when the operator is ready to scale.
    """
    if SESSION_FILE.exists():
        text = SESSION_FILE.read_text(encoding="utf-8")
        text = text.replace(
            "pool_size=10,\n            max_overflow=20,",
            "pool_size=25,\n            max_overflow=50,",
        )
        old_commit = """        try:
            yield session
            await session.commit()"""
        new_commit = """        try:
            yield session
            if session.new or session.dirty or session.deleted:
                await session.commit()"""
        text = text.replace(old_commit, new_commit)
        SESSION_FILE.write_text(text, encoding="utf-8")
        print("[APPLIED] Updated core/db/session.py (pool_size=25, max_overflow=50, conditional commit)")

    if DOCKERFILE.exists():
        d_text = DOCKERFILE.read_text(encoding="utf-8")
        old_cmd = 'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'
        new_cmd = (
            'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", '
            '"--loop", "uvloop", "--http", "httptools", "--backlog", "2048", "--limit-concurrency", "1000"]'
        )
        if old_cmd in d_text:
            d_text = d_text.replace(old_cmd, new_cmd)
            DOCKERFILE.write_text(d_text, encoding="utf-8")
            print("[APPLIED] Updated Dockerfile with uvloop, httptools, backlog=2048, limit-concurrency=1000")


async def run_benchmark(base_url: str, concurrency: int) -> None:
    """Simulate concurrent Kakao Skill 2.0 requests and report latency percentiles."""
    url = f"{base_url.rstrip('/')}/integrations/kakao/skills/match-search"
    utterances = ["오늘 경기", "팀순위", "선수순위", "관심선수", "DB 라인업", "정관장 라인업", "일정"]
    latencies: list[float] = []
    errors = 0

    limits = httpx.Limits(max_connections=concurrency + 50, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(limits=limits, timeout=10.0, verify=False) as client:
        async def _worker(idx: int) -> None:
            nonlocal errors
            utt = utterances[idx % len(utterances)]
            payload = {
                "userRequest": {
                    "user": {"id": f"bench_user_{idx % 200}"},
                    "utterance": utt,
                },
                "action": {"name": "매치업검색", "params": {}},
            }
            t0 = time.perf_counter()
            try:
                resp = await client.post(url, json=payload)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if resp.status_code == 200:
                    latencies.append(elapsed_ms)
                else:
                    errors += 1
            except Exception:
                errors += 1

        print(f"🚀 Running {concurrency} concurrent Kakao Skill requests against {url} ...")
        t_start = time.perf_counter()
        await asyncio.gather(*(_worker(i) for i in range(concurrency)))
        total_sec = time.perf_counter() - t_start

    latencies.sort()
    n = len(latencies)
    if n == 0:
        print(f"❌ All {concurrency} requests failed.")
        return

    p50 = latencies[int(n * 0.50)]
    p95 = latencies[int(n * 0.95)]
    p99 = latencies[min(n - 1, int(n * 0.99))]
    rps = concurrency / total_sec if total_sec > 0 else 0.0
    print("=" * 68)
    print(f"📊 CONCURRENCY BENCHMARK REPORT ({concurrency} Simultaneous Requests)")
    print("=" * 68)
    print(f"• Success / Total : {n} / {concurrency} (Errors: {errors})")
    print(f"• Total Wall Time : {total_sec:.3f} s ({rps:.1f} req/s)")
    print(f"• Latency p50     : {p50:.1f} ms")
    print(f"• Latency p95     : {p95:.1f} ms")
    print(f"• Latency p99     : {p99:.1f} ms (Kakao SLA Limit: 5,000 ms)")
    print(f"• SLA Verdict     : {'🟢 PASS (< 5,000ms)' if p99 < 5000 and errors == 0 else '🟡 NEEDS SCALING'}")
    print("=" * 68)


def main() -> None:
    parser = argparse.ArgumentParser(description="KBL Bot 1,000-User Scaling Readiness Tool")
    parser.add_argument("--check", action="store_true", help="Check current scaling readiness (Dry-run)")
    parser.add_argument("--generate-ingress", action="store_true", help="Generate Named Tunnel & Caddy configs")
    parser.add_argument("--domain", type=str, default="kblbot.example.com", help="Domain for Named Tunnel / Caddy")
    parser.add_argument("--apply", action="store_true", help="Apply high-concurrency tuning to local codebase")
    parser.add_argument("--benchmark", action="store_true", help="Run concurrent load test")
    parser.add_argument("--concurrency", type=int, default=100, help="Concurrent requests for benchmark")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="Target base URL for benchmark")
    args = parser.parse_args()

    if args.generate_ingress:
        generate_ingress_configs(args.domain)
        print(f"✅ Generated ingress & PostgreSQL tuning files in {INGRESS_DIR}")

    if args.apply:
        apply_code_tuning()

    if args.benchmark:
        asyncio.run(run_benchmark(args.url, args.concurrency))
        return

    status = check_readiness()
    print("=" * 68)
    print("🛡️  KBL BOT — 1,000 CONCURRENT USERS SCALING READINESS STATUS")
    print("=" * 68)
    for k, v in status.items():
        print(f"• {k:18s}: {v}")
    print("=" * 68)
    print("💡 No live production changes were made. See deploy/INFRA_SCALING_PLAYBOOK.md for 1-click execution.")


if __name__ == "__main__":
    main()
