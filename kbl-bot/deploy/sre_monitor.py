#!/usr/bin/env python3
"""
KBL Bot SRE Monitoring & Health Diagnostic Tool.
Gathers real-time telemetry from OCI VPS, Docker containers, Daum API ingestion,
Redis, PostgreSQL, and public HTTPS Cloudflare Tunnel endpoints.
"""

import json
import os
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error

SSH_KEY = os.path.expanduser("/Users/dj/Downloads/ssh-key-2026-10-31.key")
SSH_USER_HOST = "ubuntu@168.110.6.240"
PUBLIC_BASE_URL = "https://activity-lexmark-insert-styles.trycloudflare.com"

# SSL context that works even in environments with corporate proxies/Zscaler
SSL_CTX = ssl._create_unverified_context()


def run_ssh(cmd: str) -> tuple[int, str]:
    """Execute a remote shell command on the OCI VPS via SSH."""
    if not os.path.exists(SSH_KEY):
        return -1, f"SSH key not found: {SSH_KEY}"
    full_cmd = [
        "ssh",
        "-i", SSH_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=5",
        SSH_USER_HOST,
        cmd,
    ]
    try:
        res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=15)
        return res.returncode, (res.stdout + res.stderr).strip()
    except subprocess.TimeoutExpired:
        return -1, "SSH command timed out (15s)"
    except Exception as e:
        return -1, str(e)


def check_http(url: str, method: str = "GET", data: dict | None = None) -> tuple[int, float, str]:
    """Perform an HTTP request and measure latency."""
    start = time.perf_counter()
    headers = {"User-Agent": "KBL-SRE-Monitor/1.0", "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=7, context=SSL_CTX) as resp:
            latency = (time.perf_counter() - start) * 1000
            content = resp.read().decode("utf-8", errors="replace")
            return resp.status, latency, content
    except urllib.error.HTTPError as e:
        latency = (time.perf_counter() - start) * 1000
        content = e.read().decode("utf-8", errors="replace")
        return e.code, latency, content
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return 0, latency, str(e)


def collect_metrics() -> dict:
    """Collect full telemetry suite."""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "infrastructure": {},
        "containers": {},
        "endpoints": {},
        "ingestion_worker": {},
        "redis_health": {},
        "db_health": {},
    }

    # 1. Endpoint Checks
    health_status, health_latency, _ = check_http(f"{PUBLIC_BASE_URL}/health")
    report["endpoints"]["health_probe"] = {
        "url": f"{PUBLIC_BASE_URL}/health",
        "status_code": health_status,
        "latency_ms": round(health_latency, 1),
        "ok": health_status == 200,
    }

    # Skill endpoint check (today-games)
    payload = {
        "userRequest": {"user": {"id": "sre_monitor_user"}, "utterance": "오늘 경기", "block": {"id": "sre", "name": "sre"}},
        "action": {"name": "today_games", "params": {}, "extra": {}},
        "contexts": [],
    }
    skill_status, skill_latency, skill_body = check_http(
        f"{PUBLIC_BASE_URL}/integrations/kakao/skills/today-games",
        method="POST",
        data=payload,
    )
    report["endpoints"]["kakao_skill"] = {
        "url": f"{PUBLIC_BASE_URL}/integrations/kakao/skills/today-games",
        "status_code": skill_status,
        "latency_ms": round(skill_latency, 1),
        "ok": skill_status == 200 and "version" in skill_body,
    }

    # 2. VPS System Metrics
    sys_cmd = "uptime; echo '---MEM---'; free -m; echo '---DISK---'; df -h /"
    code, out = run_ssh(sys_cmd)
    if code == 0:
        report["infrastructure"]["status"] = "CONNECTED"
        report["infrastructure"]["raw"] = out
    else:
        report["infrastructure"]["status"] = "UNREACHABLE"
        report["infrastructure"]["error"] = out

    # 3. Docker Container State
    dk_cmd = "sudo docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'"
    code, out = run_ssh(dk_cmd)
    if code == 0:
        containers = []
        for line in out.strip().split("\n"):
            if line:
                parts = line.split("\t")
                containers.append({
                    "name": parts[0],
                    "status": parts[1] if len(parts) > 1 else "",
                    "ports": parts[2] if len(parts) > 2 else "",
                })
        report["containers"]["list"] = containers
    else:
        report["containers"]["error"] = out

    # 4. Ingestion Worker Pulse & Error Log Scan
    log_cmd = "sudo docker logs --tail 30 kbl_api 2>&1"
    code, out = run_ssh(log_cmd)
    if code == 0:
        lines = out.strip().split("\n")
        recent_polls = [l for l in lines if "SPORTS_GAME" in l][-5:]
        error_lines = [l for l in lines if any(k in l.lower() for k in ["error", "traceback", "exception", "failed"])][-5:]
        report["ingestion_worker"]["recent_polls"] = recent_polls
        report["ingestion_worker"]["recent_errors"] = error_lines
        report["ingestion_worker"]["alive"] = len(recent_polls) > 0
    else:
        report["ingestion_worker"]["error"] = out

    # 5. Redis Stats
    redis_cmd = "sudo docker exec kbl_redis redis-cli info memory"
    code, out = run_ssh(redis_cmd)
    if code == 0:
        mem_info = {}
        for line in out.split("\n"):
            if ":" in line:
                k, v = line.strip().split(":", 1)
                mem_info[k] = v
        report["redis_health"]["used_memory_human"] = mem_info.get("used_memory_human", "N/A")
        report["redis_health"]["maxmemory_human"] = mem_info.get("maxmemory_human", "N/A")
        report["redis_health"]["ok"] = True
    else:
        report["redis_health"]["ok"] = False
        report["redis_health"]["error"] = out

    # 6. PostgreSQL Stats
    pg_cmd = "sudo docker exec kbl_postgres psql -U kbl_user -d kbl_bot -t -A -c \"SELECT count(*) FROM games; SELECT count(*) FROM users; SELECT count(*) FROM pg_stat_activity; SELECT pg_size_pretty(pg_database_size('kbl_bot'));\""
    code, out = run_ssh(pg_cmd)
    if code == 0:
        parts = [p.strip() for p in out.strip().split("\n") if p.strip()]
        if len(parts) >= 4:
            report["db_health"] = {
                "ok": True,
                "game_count": int(parts[0]),
                "user_count": int(parts[1]),
                "active_connections": int(parts[2]),
                "database_size": parts[3],
            }
        else:
            report["db_health"] = {"ok": True, "raw": out}
    else:
        report["db_health"] = {"ok": False, "error": out}

    # 7. OCI Always Free Cost Guard & Budget Defense
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from oci_cost_guard import collect_oci_cost_metrics
        report["oci_cost_guard"] = collect_oci_cost_metrics()
    except Exception as exc:
        report["oci_cost_guard"] = {"ok": False, "error": str(exc)}

    return report


def main():
    report = collect_metrics()
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
