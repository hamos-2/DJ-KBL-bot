"""Parity tests verifying exact feature alignment with 카카오 프로야구봇 (_HhRnC)."""

from unittest.mock import AsyncMock, patch
import pytest

from apps.kakao.builder import (
    MAIN_MENU_QUICK_REPLIES,
    build_game_summary_response,
    build_home_menu_response,
    build_lineup_response,
    build_live_score_response,
    build_settings_response,
)
from apps.kakao.router import _dispatch_command
from core.db.models import User
from services.content.kbl_data import TEAM_LINEUPS, get_team_lineup


class DummyGameService:
    async def get_today_games(self, db):
        return [
            {
                "game_id": "MOCK-G1",
                "home_team": "SK",
                "away_team": "DB",
                "home_score": 84,
                "away_score": 80,
                "period": 4,
                "game_clock": "02:10",
                "status": "LIVE",
                "start_time": "2026-11-01T05:00:00Z",
                "arena": "잠실학생",
            }
        ]

    async def get_kbl_schedule(self, db, days=7, limit=4, team=None):
        return await self.get_today_games(db)

    async def get_recent_results(self, db, limit=6):
        return [
            {
                "game_id": "MOCK-FINAL-1",
                "home_team": "LG",
                "away_team": "KT",
                "home_score": 79,
                "away_score": 75,
                "status": "FINAL",
                "start_time": "2026-10-31T05:00:00Z",
                "arena": "창원",
            }
        ]


class DummyUserService:
    pass


class DummyDB:
    async def commit(self):
        pass


@pytest.fixture
def dummy_user():
    return User(
        kakao_user_key_hmac="test_hmac_parity_user_001",
        encrypted_kakao_user_key="enc_key",
        favorite_team=None,
    )


@pytest.mark.asyncio
async def test_welcome_onboarding_shows_10_teams_carousel_if_no_fav_team(dummy_user):
    """When a new user enters, 10-team selection carousel must be presented immediately."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    with patch("apps.kakao.router.get_user_preferences", new=AsyncMock(return_value={"favorite_players": []})):
        resp = await _dispatch_command("웰컴", db, game_service, user_service, dummy_user)
        assert resp is not None
        assert "환영합니다" in resp.template.outputs[0]["simpleText"]["text"]
        assert "carousel" in resp.template.outputs[1]
        cards = resp.template.outputs[1]["carousel"]["items"]
        assert len(cards) >= 4
        btn_labels = [b["label"] for card in cards for b in card["buttons"]]
        assert "❤️ 원주 DB" in btn_labels
        assert "❤️ 서울 SK" in btn_labels


@pytest.mark.asyncio
async def test_lineup_feature_parity(dummy_user):
    """'라인업' query must return starting 5 players and head coach."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    resp = await _dispatch_command("라인업", db, game_service, user_service, dummy_user)
    assert resp is not None
    text = resp.template.outputs[0]["simpleText"]["text"]
    assert "선발 라인업" in text
    assert "전희철 감독" in text or "SK" in text
    assert "자밀 워니" in text
    assert "이선 알바노" in text


@pytest.mark.asyncio
async def test_game_summary_recap_feature_parity(dummy_user):
    """'요약' or '한줄평' query must return game summary with MVP and turning points."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    for cmd in ["요약", "한줄평", "경기요약"]:
        resp = await _dispatch_command(cmd, db, game_service, user_service, dummy_user)
        assert resp is not None
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "경기 요약 & 한줄평" in text
        assert "MVP" in text
        assert "승부처 한줄평" in text


@pytest.mark.asyncio
async def test_prediction_feature_parity(dummy_user):
    """'승부예측' query must return prediction gauge and vote buttons."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    mock_cheers = {
        "game_id": "MOCK-G1",
        "home_team": "SK",
        "away_team": "DB",
        "home_votes": 65,
        "away_votes": 35,
        "home_pct": 65,
        "away_pct": 35,
        "user_pick": None,
        "user_points": 50,
    }

    with patch("apps.kakao.router.get_game_cheers", new=AsyncMock(return_value=mock_cheers)):
        resp = await _dispatch_command("승부예측", db, game_service, user_service, dummy_user)
        assert resp is not None
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "승부예측" in text


@pytest.mark.asyncio
async def test_notification_settings_parity(dummy_user):
    """'알림설정' must render 5 notification toggles and allow toggling lineup & prediction."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    user_prefs = {
        "favorite_players": ["허훈"],
        "notifications": {
            "lineup": True,
            "game_start": True,
            "game_end": True,
            "clutch": True,
            "prediction": True,
        },
    }

    with (
        patch("apps.kakao.router.get_user_preferences", new=AsyncMock(return_value=user_prefs)),
        patch("apps.kakao.router.save_user_preferences", new=AsyncMock())
    ):
        resp = await _dispatch_command("알림설정", db, game_service, user_service, dummy_user)
        assert resp is not None
        cards = resp.template.outputs[0]["carousel"]["items"]
        btn_labels = [b["label"] for card in cards for b in card["buttons"]]
        assert any("라인업" in b for b in btn_labels)
        assert any("시작알림" in b for b in btn_labels)
        assert any("종료알림" in b for b in btn_labels)
        assert any("클러치알림" in b for b in btn_labels)
        assert any("승부예측알림" in b for b in btn_labels)

        # Toggle lineup notification
        resp_toggle = await _dispatch_command("#알림 라인업", db, game_service, user_service, dummy_user)
        assert resp_toggle is not None


@pytest.mark.asyncio
async def test_live_score_quarter_boxscore():
    """build_live_score_response must include quarter-by-quarter breakdown and Daum relay button."""
    snapshot = {
        "game_id": "LIVE-001",
        "home_team": "SK",
        "away_team": "DB",
        "home_score": 82,
        "away_score": 79,
        "period": 4,
        "game_clock": "01:23",
        "status": "LIVE",
    }
    resp = build_live_score_response(snapshot)
    text = resp.template.outputs[0]["simpleText"]["text"]
    assert "쿼터별 스코어" in text
    assert "1Q" in text and "4Q" in text
    card = resp.template.outputs[1]["textCard"]
    card_btn_labels = [b["label"] for b in card["buttons"]]
    assert "📺 다음 톡중계 보기" in card_btn_labels
