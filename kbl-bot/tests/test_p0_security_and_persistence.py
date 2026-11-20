"""Unit tests for P0 admin allowlist guard, DB durability fallbacks, and FINAL auto-settlement."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.kakao.router import _dispatch_command, _is_admin_operator
from core.config import get_settings
from services.user.persistence import settle_game_predictions_chunked


def test_admin_operator_guard_fail_closed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """In production, roster mutation commands deny non-allowlisted users by default."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USER_HMACS", "")
    get_settings.cache_clear()
    try:
        assert _is_admin_operator("random_user_hmac") is False
        monkeypatch.setenv("ADMIN_USER_HMACS", "admin_hmac_1, admin_hmac_2")
        get_settings.cache_clear()
        assert _is_admin_operator("random_user_hmac") is False
        assert _is_admin_operator("admin_hmac_2") is True
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dispatch_blocks_unauthorized_roster_commands_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#감독변경 / #트레이드 / #로스터동기화 are blocked for non-admins in production."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ADMIN_USER_HMACS", "only_admin_hmac")
    get_settings.cache_clear()
    try:
        db = AsyncMock()
        game_svc = MagicMock()
        user_svc = MagicMock()
        user = SimpleNamespace(kakao_user_key_hmac="intruder_hmac", favorite_team="SK")

        for cmd in ("#감독변경 SK 홍길동", "#트레이드 김선형 SK", "#로스터동기화"):
            resp = await _dispatch_command(cmd, db, game_svc, user_svc, user)
            assert resp is not None
            text = resp.template.outputs[0]["simpleText"]["text"]
            assert "운영자 권한이 필요한 명령입니다" in text
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_settle_game_predictions_chunked_processes_batches_cleanly() -> None:
    """FINAL transition settles PredictionVote rows in bounded chunks and updates points/streak."""
    v1 = SimpleNamespace(user_hmac="u_win", game_id="80109999", selected_team="SK", settled=False, is_hit=None, points_awarded=0)
    v2 = SimpleNamespace(user_hmac="u_lose", game_id="80109999", selected_team="KT", settled=False, is_hit=None, points_awarded=0)

    call_count = {"n": 0}

    class _FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return SimpleNamespace(all=lambda: self._rows)

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, stmt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _FakeResult([v1, v2])
            if call_count["n"] in (2, 3):  # pg_insert upserts
                return MagicMock()
            return _FakeResult([])

        async def commit(self):
            return None

    with (
        patch("services.user.persistence.settle_prediction_hit", new=AsyncMock(side_effect=[(True, 60), (False, 10)])) as mock_hit,
        patch("services.user.persistence.update_user_streak", new=AsyncMock(side_effect=[(3, 30), (0, 0)])) as mock_stk,
    ):
        settled = await settle_game_predictions_chunked(
            {"game_id": "80109999", "home_team": "SK", "away_team": "KT", "home_score": 85, "away_score": 78, "status": "FINAL"},
            chunk_size=50,
            session_factory=lambda: _FakeSession(),
        )

    assert settled == 2
    assert v1.settled is True and v1.is_hit is True and v1.points_awarded == 80
    assert v2.settled is True and v2.is_hit is False and v2.points_awarded == 0
    assert mock_hit.await_count == 2
    assert mock_stk.await_count == 2
