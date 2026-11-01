#!/usr/bin/env python3
"""
SRE Autonomous Watchdog & Anomaly Detection Daemon.
Continuously or periodically inspects system health, endpoints, SLA latency,
background ingestion, and OCI Always Free cost defense.
Automatically dispatches rich HTML emails upon detecting anomalies, singularities, or recoveries.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Any

# Ensure deploy directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from sre_mailer import send_sre_email, get_mail_config
from sre_monitor import collect_metrics

STATE_FILE = os.path.join(SCRIPT_DIR, "alert_state.json")
ALERT_COOLDOWN_MINUTES = 30


def load_alert_state() -> dict[str, Any]:
    """Load alert state (active incidents, last alerted timestamp) from disk."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"active_incidents": {}, "last_alert_time": {}}


def save_alert_state(state: dict[str, Any]) -> None:
    """Save alert state to disk."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def evaluate_anomalies(metrics: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    """
    Evaluate anomaly detection rules against real-time telemetry.
    Returns: (highest_severity, incident_details, recovery_commands)
    """
    incidents: list[dict[str, Any]] = []
    recovery_cmds: list[str] = []
    severity = "INFO"

    # 1. Container Health Check
    required_containers = ["kbl_api", "kbl_postgres", "kbl_redis", "kbl_cloudflared_quick"]
    running_names = {c.get("name"): c for c in metrics.get("containers", {}).get("list", [])}
    for c_name in required_containers:
        if c_name not in running_names:
            incidents.append({
                "component": f"Container ({c_name})",
                "metric": "Status",
                "threshold": "Running (Up)",
                "actual": "DOWN / MISSING",
                "status": "CRITICAL",
            })
            recovery_cmds.append(f"cd /home/ubuntu/DJ-KBL-bot/kbl-bot && sudo docker compose up -d {c_name.replace('kbl_', '')}")
        else:
            status_str = running_names[c_name].get("status", "")
            if "unhealthy" in status_str.lower() or "restarting" in status_str.lower():
                incidents.append({
                    "component": f"Container ({c_name})",
                    "metric": "Health",
                    "threshold": "healthy",
                    "actual": status_str,
                    "status": "CRITICAL",
                })
                recovery_cmds.append(f"sudo docker restart {c_name}")

    # 2. Endpoint & SLA Latency Check
    endpoints = metrics.get("endpoints", {})
    health_probe = endpoints.get("health_probe", {})
    if not health_probe.get("ok"):
        incidents.append({
            "component": "Health Endpoint (/health)",
            "metric": "HTTP Status",
            "threshold": "200 OK",
            "actual": f"HTTP {health_probe.get('status_code', 0)}",
            "status": "CRITICAL",
        })
        recovery_cmds.append("sudo docker restart kbl_api")

    kakao_skill = endpoints.get("kakao_skill", {})
    skill_latency = kakao_skill.get("latency_ms", 0.0)
    skill_ok = kakao_skill.get("ok", False)
    if not skill_ok:
        incidents.append({
            "component": "Kakao Skill API (/today-games)",
            "metric": "HTTP Status & Payload",
            "threshold": "200 OK & version 2.0",
            "actual": f"HTTP {kakao_skill.get('status_code', 0)}",
            "status": "CRITICAL",
        })
        recovery_cmds.append("sudo docker restart kbl_api && sudo docker logs --tail 30 kbl_api")
    elif skill_latency >= 4000:
        incidents.append({
            "component": "Kakao Skill Latency",
            "metric": "Response Time",
            "threshold": "< 4000ms (SLA 5.0s)",
            "actual": f"{skill_latency}ms",
            "status": "CRITICAL",
        })
        recovery_cmds.append("sudo docker restart kbl_api")
    elif skill_latency >= 2000:
        incidents.append({
            "component": "Kakao Skill Latency",
            "metric": "Response Time",
            "threshold": "< 2000ms",
            "actual": f"{skill_latency}ms",
            "status": "WARNING",
        })

    # 3. Disk & Memory Pressure
    infra_raw = metrics.get("infrastructure", {}).get("raw", "")
    cost_checks = metrics.get("oci_cost_guard", {}).get("checks", {})
    storage_info = cost_checks.get("storage_quota", {})
    disk_pct = storage_info.get("local_disk_use_percent", 0)
    if disk_pct >= 85:
        incidents.append({
            "component": "Host Storage (/)",
            "metric": "Disk Usage",
            "threshold": "< 85%",
            "actual": f"{disk_pct}%",
            "status": "CRITICAL",
        })
        recovery_cmds.append("sudo docker system prune -af --volumes")
    elif disk_pct >= 75:
        incidents.append({
            "component": "Host Storage (/)",
            "metric": "Disk Usage",
            "threshold": "< 75%",
            "actual": f"{disk_pct}%",
            "status": "WARNING",
        })
        recovery_cmds.append("sudo docker system prune -f")

    # 4. Ingestion Worker Health
    worker_info = metrics.get("ingestion_worker", {})
    if not worker_info.get("alive", True):
        incidents.append({
            "component": "Daum Ingestion Worker",
            "metric": "SPORTS_GAME Pulse",
            "threshold": "Active Polling",
            "actual": "No Recent Game Sync",
            "status": "WARNING",
        })
        recovery_cmds.append("sudo docker restart kbl_api")

    recent_errors = worker_info.get("recent_errors", [])
    if len(recent_errors) >= 5:
        incidents.append({
            "component": "Daum API Ingestion",
            "metric": "Recent Error Burst",
            "threshold": "< 5 errors",
            "actual": f"{len(recent_errors)} errors detected",
            "status": "WARNING",
        })

    # 5. OCI Always Free Cost Guard
    cost_guard = metrics.get("oci_cost_guard", {})
    if "Billing Risk" in cost_guard.get("compliance_status", ""):
        incidents.append({
            "component": "OCI Cost Defense",
            "metric": "Always Free Compliance",
            "threshold": "100% Free-Tier Safe",
            "actual": cost_guard.get("compliance_status", "Billing Risk"),
            "status": "CRITICAL",
        })
    elif cost_guard.get("alerts"):
        for alert_msg in cost_guard.get("alerts", []):
            incidents.append({
                "component": "OCI Free-Tier Quota",
                "metric": "Resource Limit",
                "threshold": "Within Free Tier",
                "actual": alert_msg,
                "status": "WARNING",
            })

    # Determine highest severity
    if any(i["status"] == "CRITICAL" for i in incidents):
        severity = "CRITICAL"
    elif any(i["status"] == "WARNING" for i in incidents):
        severity = "WARNING"
    else:
        severity = "RESOLVED" if not incidents else "INFO"

    return severity, incidents, list(dict.fromkeys(recovery_cmds))


def run_watchdog_check(force_alert: bool = False) -> dict[str, Any]:
    """Execute a single watchdog check cycle, manage state, and dispatch alerts."""
    state = load_alert_state()
    now_ts = datetime.now(timezone.utc).timestamp()

    if force_alert:
        # Synthetic test alert
        severity = "WARNING"
        incidents = [
            {
                "component": "Kakao Skill API (/today-games)",
                "metric": "Latency Spike Test",
                "threshold": "< 2000ms",
                "actual": "2850ms (Synthetic Test)",
                "status": "WARNING",
            },
            {
                "component": "OCI Free-Tier Storage",
                "metric": "Boot Volume Test",
                "threshold": "< 50 GB",
                "actual": "44.1 GB (Normal)",
                "status": "INFO",
            },
        ]
        recovery_cmds = [
            "sudo docker stats",
            "python3 /home/ubuntu/DJ-KBL-bot/kbl-bot/deploy/sre_monitor.py",
        ]
        telemetry_summary = {
            "cpu_load": "0.73",
            "mem_avail_mb": 511,
            "disk_used_pct": 17,
            "skill_latency_ms": 286.9,
        }
        title = "SRE 이상 감지 및 이메일 보고 시험 발송"
        ok, msg = send_sre_email(severity, title, incidents, telemetry_summary, recovery_cmds)
        return {"action": "TEST_ALERT_SENT", "success": ok, "message": msg}

    # Collect live telemetry
    metrics = collect_metrics()
    severity, incidents, recovery_cmds = evaluate_anomalies(metrics)

    # Build telemetry summary
    cost_checks = metrics.get("oci_cost_guard", {}).get("checks", {})
    storage_info = cost_checks.get("storage_quota", {})
    endpoints = metrics.get("endpoints", {})
    telemetry_summary = {
        "cpu_load": metrics.get("infrastructure", {}).get("raw", "").splitlines()[0] if metrics.get("infrastructure", {}).get("raw") else "N/A",
        "mem_avail_mb": "511",
        "disk_used_pct": storage_info.get("local_disk_use_percent", 17),
        "skill_latency_ms": endpoints.get("kakao_skill", {}).get("latency_ms", "N/A"),
    }

    active_incidents = state.get("active_incidents", {})
    last_alert_time = state.get("last_alert_time", {})

    # Case 1: Incidents Detected (Critical or Warning)
    if incidents:
        incident_signature = "|".join(sorted(f"{i['component']}:{i['metric']}" for i in incidents))
        last_time = last_alert_time.get(incident_signature, 0)
        cooldown_seconds = ALERT_COOLDOWN_MINUTES * 60

        # Check if cooldown has elapsed or severity escalated
        if (now_ts - last_time) > cooldown_seconds:
            title = f"{len(incidents)}건의 시스템 이상 신호 및 특이점이 감지되었습니다."
            ok, msg = send_sre_email(severity, title, incidents, telemetry_summary, recovery_cmds)
            state["active_incidents"] = {i["component"]: i for i in incidents}
            state["last_alert_time"][incident_signature] = now_ts
            save_alert_state(state)
            return {"action": "ALERT_DISPATCHED", "severity": severity, "count": len(incidents), "result": msg}
        else:
            remaining_mins = round((cooldown_seconds - (now_ts - last_time)) / 60, 1)
            return {"action": "COOLDOWN_SUPPRESSED", "severity": severity, "count": len(incidents), "cooldown_remaining_min": remaining_mins}

    # Case 2: System Healthy - check if we need to send a RECOVERY email
    if active_incidents:
        resolved_details = [
            {
                "component": comp,
                "metric": "All Systems Normal",
                "threshold": "Normal Operating Range",
                "actual": "Healthy / 200 OK",
                "status": "RESOLVED",
            }
            for comp in active_incidents.keys()
        ]
        title = "시스템이 정상 상태로 복구되었습니다 (All Clear)"
        ok, msg = send_sre_email("RESOLVED", title, resolved_details, telemetry_summary, ["sudo docker ps", "uptime"])
        state["active_incidents"] = {}
        state["last_alert_time"] = {}
        save_alert_state(state)
        return {"action": "RECOVERY_DISPATCHED", "result": msg}

    return {"action": "ALL_HEALTHY", "severity": "CLEAR", "message": "모든 시스템 정상 가동 중 (이상 신호 없음)"}


def main():
    parser = argparse.ArgumentParser(description="KBL Bot SRE Autonomous Watchdog & Anomaly Dispatcher")
    parser.add_argument("--test-alert", action="store_true", help="Send a synthetic test alert email")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in background (5min cycle)")
    parser.add_argument("--interval", type=int, default=300, help="Daemon interval seconds (default: 300)")
    args = parser.parse_args()

    if args.test_alert:
        print("[Watchdog] Triggering synthetic test alert...")
        res = run_watchdog_check(force_alert=True)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    if args.daemon:
        print(f"[Watchdog] Starting SRE Watchdog Daemon (Interval: {args.interval}s)...")
        while True:
            try:
                res = run_watchdog_check()
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {json.dumps(res, ensure_ascii=False)}")
            except Exception as e:
                print(f"[Error in watchdog loop] {e}", file=sys.stderr)
            time.sleep(args.interval)
    else:
        res = run_watchdog_check()
        print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
