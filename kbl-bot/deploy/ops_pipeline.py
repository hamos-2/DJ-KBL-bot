#!/usr/bin/env python3
"""
KBL Bot Unified Operations & Multi-Agent Verification Pipeline (Ops Pipeline).
Orchestrates SRE, Data Integrity, QA System Audit, and Growth Readiness in one unified run.
Can be executed locally (via SSH to VPS) or directly on the OCI production server.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")
DEFAULT_TARGET_URL = os.environ.get("KBL_API_URL", "http://localhost:8000/integrations/kakao/skills/today-games")
OCI_IP = os.environ.get("OCI_IP", "168.110.6.240")
SSH_KEY = os.environ.get("SSH_KEY", os.path.expanduser("~/Downloads/ssh-key-2026-10-31.key"))


def log_phase(title: str) -> None:
    sep = "=" * 70
    print(f"\n{sep}\n🎯 {title}\n{sep}")


def run_post(utterance: str, url: str = DEFAULT_TARGET_URL) -> tuple[dict, float]:
    payload = {
        "userRequest": {
            "user": {"id": "ops_pipeline_runner"},
            "utterance": utterance,
        },
        "action": {
            "name": "main_action",
            "params": {"utterance": utterance},
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "KBL-Ops-Pipeline/2.0"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=5.0) as resp:
        duration_ms = (time.perf_counter() - t0) * 1000
        return json.loads(resp.read().decode("utf-8")), duration_ms


def check_step(name: str, fn) -> bool:
    t0 = time.perf_counter()
    try:
        fn()
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  ✅ [PASS] {name} ({elapsed:.1f}ms)")
        return True
    except Exception as exc:
        elapsed = (time.perf_counter() - t0) * 1000
        print(f"  ❌ [FAIL] {name} ({elapsed:.1f}ms) -> {exc}")
        return False


def run_ops_pipeline(base_url: str = DEFAULT_TARGET_URL) -> int:
    started_at = datetime.now(_KST).strftime("%Y-%m-%d %H:%M:%S KST")
    print(f"🏀 KBL BOT MULTI-AGENT OPS PIPELINE STARTED AT {started_at}")
    print(f"🎯 Target Endpoint: {base_url}\n")

    results: dict[str, list[bool]] = {
        "SRE & Infra": [],
        "Data Integrity": [],
        "QA & UX Journeys": [],
        "Growth & Marketing": [],
    }

    # =========================================================================
    # Phase 1: SRE & Infra Guard
    # =========================================================================
    log_phase("PHASE 1: SRE & INFRASTRUCTURE HEALTH GUARD")

    def test_health_endpoint():
        res, ms = run_post("헬스체크", base_url)
        assert res.get("version") == "2.0"
        outs = res.get("template", {}).get("outputs", [])
        assert len(outs) >= 1
        assert ms < 500.0, f"SLA violated: {ms:.1f}ms >= 500ms"

    def test_http_200_guarantee():
        res, _ = run_post("알수없는비정상입력!@#$%", base_url)
        assert res.get("version") == "2.0"
        assert len(res.get("template", {}).get("outputs", [])) >= 1

    results["SRE & Infra"].append(check_step("Kakao 2.0 Health & Latency SLA (<500ms)", test_health_endpoint))
    results["SRE & Infra"].append(check_step("Always HTTP 200 Protocol Guard on edge inputs", test_http_200_guarantee))

    # =========================================================================
    # Phase 2: Data Integrity & Invariants Guard
    # =========================================================================
    log_phase("PHASE 2: KBL DATA & ROSTER INTEGRITY GUARD")

    def test_7_invariants_diagnostic():
        res, _ = run_post("#데이터정합성", base_url)
        text = res["template"]["outputs"][0]["simpleText"]["text"]
        assert "ALL INTEGRITY PASS" in text, f"Integrity failed: {text}"
        assert "은퇴 선수(함지훈) 격리: PASS" in text
        assert "김선형 선수 SK 격리 원칙: PASS" in text
        assert "구단별 선발 베스트 5" in text

    def test_season_rollover_active():
        res, _ = run_post("팀순위", base_url)
        c1 = res["template"]["outputs"][0]["listCard"]
        assert "KBL 순위" in c1["header"]["title"]
        assert "2026-27" in c1["header"]["title"] or "2026-2027" in c1["header"]["title"]

    def test_ghost_player_quarantine():
        res, _ = run_post("현대모비스 선수", base_url)
        text = str(res)
        assert "함지훈" not in text, "Retired player Ham Ji-hoon detected in active roster!"

    def test_kim_sun_hyung_quarantine():
        res, _ = run_post("SK 선수", base_url)
        text = str(res)
        assert "김선형" not in text, "Transfer player Kim Sun-hyung detected in SK roster!"

    results["Data Integrity"].append(check_step("7 Golden Invariants Roster Diagnostic", test_7_invariants_diagnostic))
    results["Data Integrity"].append(check_step("Season 2026-2027 Active Rollover Verification", test_season_rollover_active))
    results["Data Integrity"].append(check_step("Rule 3: Ham Ji-hoon (Retired) Quarantine", test_ghost_player_quarantine))
    results["Data Integrity"].append(check_step("Rule 4: Kim Sun-hyung (SK) Quarantine", test_kim_sun_hyung_quarantine))

    # =========================================================================
    # Phase 3: QA & UX Journey Audit
    # =========================================================================
    log_phase("PHASE 3: QA & MOBILE UX JOURNEY AUDIT")

    def test_lineup_single_carousel():
        res, _ = run_post("라인업", base_url)
        outputs = res.get("template", {}).get("outputs", [])
        assert len(outputs) == 1, f"Expected clean single bubble, got {len(outputs)}"
        assert "carousel" in outputs[0], "Lineup output must be basicCard carousel"
        qrs = res.get("template", {}).get("quickReplies", [])
        assert len(qrs) >= 5, "Contextual quick replies missing in lineup"

    def test_standings_playoff_badge():
        res, _ = run_post("팀순위", base_url)
        c2 = res["template"]["outputs"][1]["listCard"]
        assert "6강 PO 경쟁" in c2["header"]["title"]
        items_str = str(c2["items"])
        assert "[PO마지노선]" in items_str, "6th place playoff threshold tag missing"

    def test_10_clubs_direct_access():
        res, _ = run_post("구단별 선수", base_url)
        qrs = [q["label"] for q in res["template"]["quickReplies"]]
        assert len(qrs) == 10, f"Expected all 10 clubs, got {len(qrs)}: {qrs}"
        assert any("소노" in q for q in qrs), "Sono club missing from quick replies!"

    def test_dead_end_elimination():
        for cmd in ("#감독변경", "#트레이드", "#로스터동기화"):
            res, _ = run_post(cmd, base_url)
            qrs = res.get("template", {}).get("quickReplies", [])
            assert len(qrs) >= 5, f"Dead-end detected on admin command {cmd}"

    results["QA & UX Journeys"].append(check_step("P0 UX: Lineup Single Carousel & No Redundant Text", test_lineup_single_carousel))
    results["QA & UX Journeys"].append(check_step("P2 UX: KBL 6강 Playoff Race & Threshold Badges", test_standings_playoff_badge))
    results["QA & UX Journeys"].append(check_step("P2 UX: All 10 KBL Clubs in Player Quick Replies", test_10_clubs_direct_access))
    results["QA & UX Journeys"].append(check_step("P0 UX: Dead-End Elimination on Admin Commands", test_dead_end_elimination))

    # =========================================================================
    # Phase 4: Growth & Marketing Readiness
    # =========================================================================
    log_phase("PHASE 4: GROWTH & MARKETING READINESS")

    def test_prediction_gamification():
        res, _ = run_post("승부예측", base_url)
        assert len(res.get("template", {}).get("outputs", [])) >= 1
        qrs = [q["label"] for q in res.get("template", {}).get("quickReplies", [])]
        assert any("내 포인트" in q for q in qrs) or any("포인트" in q for q in qrs)

    def test_home_navigation_buttons():
        res, _ = run_post("처음으로", base_url)
        outs = res.get("template", {}).get("outputs", [])
        assert len(outs) >= 1

    results["Growth & Marketing"].append(check_step("Prediction & Points Gamification Funnel", test_prediction_gamification))
    results["Growth & Marketing"].append(check_step("Home Onboarding & Main Navigation Flow", test_home_navigation_buttons))

    # =========================================================================
    # Final Scorecard
    # =========================================================================
    log_phase("📊 FINAL MULTI-AGENT OPS SCORECARD")
    total_passed = 0
    total_checks = 0

    for domain, domain_results in results.items():
        domain_passed = sum(1 for r in domain_results if r)
        domain_total = len(domain_results)
        total_passed += domain_passed
        total_checks += domain_total
        status_icon = "🟢" if domain_passed == domain_total else "🔴"
        pct = (domain_passed / domain_total * 100) if domain_total else 0
        print(f"  {status_icon} {domain:22s} : {domain_passed}/{domain_total} ({pct:.1f}%)")

    overall_pct = (total_passed / total_checks * 100) if total_checks else 0
    print(f"\n{'='*70}")
    print(f"🏆 OVERALL OPS PIPELINE VERDICT: {total_passed}/{total_checks} PASSED ({overall_pct:.1f}%)")
    verdict = "🟢 ALL_HEALTHY_AND_VERIFIED" if total_passed == total_checks else "🔴 INCIDENT_DETECTED"
    print(f"🚦 SYSTEM STATUS: {verdict}")
    print(f"{'='*70}\n")

    return 0 if total_passed == total_checks else 1


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET_URL
    sys.exit(run_ops_pipeline(url))
