"""
QA Edge Case & Reliability Test Suite for KBL Bot.
Verifies:
1. Kakao Skill 2.0 1,000-char boundary safety in build_lineup_response.
2. Daum Provider 2.5s timeout SLA compliance.
3. DB Session rollback invocation on endpoint failure.
4. SRE Watchdog 30-min alert cooldown and auto-recovery logic.
5. SRE Mailer multi-recipient comma parsing.
"""

import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.kakao.builder import build_lineup_response
from apps.kakao.router import today_games
from apps.kakao.schemas import KakaoAction, KakaoSkillPayload, KakaoUser, KakaoUserRequest
from core.exceptions import ProviderError
from deploy.sre_mailer import send_sre_email
from deploy.sre_watchdog import (
    STATE_FILE,
    evaluate_anomalies,
    load_alert_state,
    run_watchdog_check,
    save_alert_state,
)
from services.provider.daum import DaumSportsDataProvider


class TestKakaoProtocolBoundaries:
    """Tests for Kakao OpenBuilder protocol constraints and boundaries."""

    def test_lineup_text_1000_char_boundary(self) -> None:
        """simpleText.text must never exceed 1,000 characters even with lengthy rosters."""
        # Create 5 games with verbose names to stress-test string length
        games = []
        for i in range(5):
            games.append({
                "game_id": f"TEST_GAME_{i}",
                "home_team": f"홈구단길고긴이름테스트_{i}",
                "away_team": f"원정구단길고긴이름테스트_{i}",
                "status": "SCHEDULED",
                "start_time": "2026-11-01T19:00:00+09:00",
                "home_score": None,
                "away_score": None,
            })

        resp = build_lineup_response(games)
        simple_text = resp.template.outputs[1]["simpleText"]["text"]

        assert len(simple_text) <= 1000, f"simpleText exceeded 1000 chars: {len(simple_text)}"
        assert isinstance(resp.template.outputs[0]["carousel"]["items"], list)
        assert len(resp.template.outputs[0]["carousel"]["items"]) <= 10


class TestProviderSLACompliance:
    """Tests for Daum Sports Provider timeout SLA."""

    def test_daum_provider_timeout_sla(self) -> None:
        """Daum provider default timeout must be <= 3.0 seconds to safely meet Kakao 5s SLA."""
        provider = DaumSportsDataProvider()
        assert provider._timeout <= 3.0
        assert provider._timeout == 2.5


class TestRouterTransactionRollback:
    """Tests for DB session rollback on endpoint failure."""

    @pytest.mark.asyncio
    async def test_today_games_calls_rollback_on_domain_error(self) -> None:
        """When GameService raises KBLBotError, db.rollback() must be awaited before returning 200."""
        mock_db = AsyncMock()
        mock_game_service = MagicMock()
        mock_game_service.get_today_games = AsyncMock(side_effect=ProviderError("Daum API Down"))

        mock_user_service = MagicMock()
        mock_user = MagicMock()
        mock_user.kakao_user_key_hmac = "test_hmac"
        mock_user.favorite_team = "KT"
        mock_user_service.get_or_create = AsyncMock(return_value=(mock_user, False))

        payload = KakaoSkillPayload(
            userRequest=KakaoUserRequest(user=KakaoUser(id="user_test_123")),
            action=KakaoAction(name="today-games", params={}, extra={}),
        )

        with patch("apps.kakao.router._verify_skill_secret", return_value=True):
            resp = await today_games(
                payload=payload,
                db=mock_db,
                game_service=mock_game_service,
                user_service=mock_user_service,
                x_kakao_skill_secret=None,
            )

        assert resp.status_code == 200
        mock_db.rollback.assert_awaited_once()


class TestSREWatchdogCooldownAndRecovery:
    """Tests for SRE Watchdog alert cooldown and recovery mechanics."""

    def test_alert_state_cooldown_and_recovery(self) -> None:
        """Watchdog must dispatch once, suppress during cooldown, and send recovery on clear."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            with patch("deploy.sre_watchdog.STATE_FILE", temp_path):
                # Mock anomaly telemetry
                anomalous_metrics = {
                    "containers": {"list": []},  # all containers missing -> CRITICAL
                    "endpoints": {},
                    "oci_cost_guard": {},
                }
                healthy_metrics = {
                    "containers": {"list": [
                        {"name": "kbl_api", "status": "Up 2 hours"},
                        {"name": "kbl_postgres", "status": "Up 2 hours"},
                        {"name": "kbl_redis", "status": "Up 2 hours"},
                        {"name": "kbl_cloudflared_quick", "status": "Up 2 hours"},
                    ]},
                    "endpoints": {
                        "health_probe": {"ok": True, "status_code": 200},
                        "kakao_skill": {"ok": True, "status_code": 200, "latency_ms": 320},
                    },
                    "oci_cost_guard": {
                        "status": "HEALTHY",
                        "checks": {
                            "shapes": {"status": "PASS"},
                            "storage_quota": {"status": "PASS", "local_disk_use_percent": 22},
                            "egress_quota": {"status": "PASS"},
                        },
                    },
                }

                # 1. First run with anomaly -> ALERT_DISPATCHED
                with patch("deploy.sre_watchdog.collect_metrics", return_value=anomalous_metrics), \
                     patch("deploy.sre_watchdog.send_sre_email", return_value=(True, "sent")):
                    res1 = run_watchdog_check()
                    assert res1["action"] == "ALERT_DISPATCHED"

                # 2. Second run with same anomaly immediately -> COOLDOWN_SUPPRESSED
                with patch("deploy.sre_watchdog.collect_metrics", return_value=anomalous_metrics), \
                     patch("deploy.sre_watchdog.send_sre_email", return_value=(True, "sent")):
                    res2 = run_watchdog_check()
                    assert res2["action"] == "COOLDOWN_SUPPRESSED"

                # 3. Third run with healthy metrics -> RECOVERY_DISPATCHED
                with patch("deploy.sre_watchdog.collect_metrics", return_value=healthy_metrics), \
                     patch("deploy.sre_watchdog.send_sre_email", return_value=(True, "sent")):
                    res3 = run_watchdog_check()
                    assert res3["action"] == "RECOVERY_DISPATCHED"

                # 4. Fourth run when already healthy -> ALL_HEALTHY
                with patch("deploy.sre_watchdog.collect_metrics", return_value=healthy_metrics):
                    res4 = run_watchdog_check()
                    assert res4["action"] == "ALL_HEALTHY"
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestSREMailerMultipleRecipients:
    """Tests for SRE Mailer multi-recipient handling."""

    def test_multiple_recipients_parsing(self) -> None:
        """Comma-separated email_to should be parsed into individual recipients list."""
        with patch("deploy.sre_mailer.smtplib.SMTP") as mock_smtp:
            instance = MagicMock()
            mock_smtp.return_value.__enter__.return_value = instance

            config = {
                "email_to": "admin1@test.com, admin2@test.com",
                "email_from": "KBL Alert <alert@kbl.com>",
                "smtp_user": "alert@kbl.com",
                "smtp_pass": "testpass1234",
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 587,
            }

            with patch("deploy.sre_mailer.get_mail_config", return_value=config):
                ok, msg = send_sre_email(
                    severity="WARNING",
                    title="Test Warning",
                    incident_details=[{"component": "test", "metric": "test"}],
                    telemetry_summary={"cpu": 10},
                    recovery_commands=["echo 1"],
                )

                assert ok is True
                assert "이메일 발송 성공" in msg
                # Verify sendmail was called with list of 2 recipients
                call_args = instance.sendmail.call_args[0]
                recipients = call_args[1]
                assert recipients == ["admin1@test.com", "admin2@test.com"]
