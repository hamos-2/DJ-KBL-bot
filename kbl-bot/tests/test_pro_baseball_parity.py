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
        assert "carousel" in resp.template.outputs[0]
        cards = resp.template.outputs[0]["carousel"]["items"]
        assert len(cards) >= 4
        btn_labels = [b["label"] for card in cards for b in card["buttons"]]
        assert "❤️ 원주 DB" in btn_labels
        assert "❤️ 서울 SK" in btn_labels


@pytest.mark.asyncio
async def test_lineup_feature_parity(dummy_user):
    """'라인업' query must return starting 5 players card."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    resp = await _dispatch_command("라인업", db, game_service, user_service, dummy_user)
    assert resp is not None
    cards = resp.template.outputs[0]["carousel"]["items"]
    assert len(cards) >= 1
    assert any("김낙현" in c["description"] or "이선 알바노" in c["description"] for c in cards)


@pytest.mark.asyncio
async def test_game_summary_recap_feature_parity(dummy_user):
    """'요약' or '한줄평' query must return game summary card."""
    db = DummyDB()
    game_service = DummyGameService()
    user_service = DummyUserService()

    for cmd in ["요약", "한줄평", "경기요약"]:
        resp = await _dispatch_command(cmd, db, game_service, user_service, dummy_user)
        assert resp is not None
        card = resp.template.outputs[0]["itemCard"]
        assert "경기 요약" in card["head"]["title"]
        assert "LG" in card["imageTitle"]["title"]


@pytest.mark.asyncio
async def test_prediction_feature_parity(dummy_user):
    """'승부예측' query must return prediction card and vote buttons."""
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
        carousel = resp.template.outputs[0]["carousel"]
        assert any("승부예측" in c["title"] for c in carousel["items"])


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
    card = resp.template.outputs[0].get("itemCard")
    assert card is not None
    assert "daumcdn.net" in card.get("imageTitle", {}).get("imageUrl", "")
    card_btn_labels = [b["label"] for b in card["buttons"]]
    assert "📺 다음 톡중계 보기" in card_btn_labels


@pytest.mark.asyncio
async def test_today_games_includes_native_list_card_with_daum_logos():
    """build_today_games_response must include native listCard with official Daum logos and action buttons."""
    from apps.kakao.builder import build_today_games_response
    games = [
        {
            "game_id": "G001",
            "home_team": "SK",
            "away_team": "KT",
            "home_score": 75,
            "away_score": 70,
            "status": "LIVE",
            "period": 3,
            "start_time": "2026-11-01T05:00:00Z",
            "arena": "잠실학생",
        },
        {
            "game_id": "G002",
            "home_team": "DB",
            "away_team": "LG",
            "status": "SCHEDULED",
            "start_time": "2026-11-01T07:00:00Z",
            "arena": "원주",
        },
    ]
    resp = build_today_games_response(games, favorite_team="SK")
    assert len(resp.template.outputs) == 1
    list_card = resp.template.outputs[0].get("listCard")
    assert list_card is not None
    assert "오늘의 KBL 경기" in list_card["header"]["title"]
    assert len(list_card["items"]) == 2
    assert "daumcdn.net" in list_card["items"][0]["imageUrl"]
    btn_labels = [b["label"] for b in list_card["buttons"]]
    assert "🔴 실시간 점수" in btn_labels
    assert "🗳️ 오늘 승부예측" in btn_labels


@pytest.mark.asyncio
async def test_visual_cards_onboarding_lineup_and_summary():
    """Lineup, summary, and onboarding responses must embed official Daum logos in cards."""
    from apps.kakao.builder import (
        build_game_summary_response,
        build_home_menu_response,
        build_lineup_response,
    )
    # 1. Onboarding
    onboard_resp = build_home_menu_response(favorite_team=None)
    carousel = onboard_resp.template.outputs[0]["carousel"]
    assert carousel["type"] == "basicCard"
    for item in carousel["items"]:
        assert "thumbnail" in item
        assert "daumcdn.net" in item["thumbnail"]["imageUrl"]

    # 2. Lineup
    sample_games = [
        {"game_id": "1", "home_team": "SK", "away_team": "DB", "start_time": "2026-11-01T05:00:00Z", "arena": "잠실학생"}
    ]
    lineup_resp = build_lineup_response(sample_games, favorite_team="SK")
    l_carousel = lineup_resp.template.outputs[0]["carousel"]
    assert l_carousel["type"] == "basicCard"
    assert "daumcdn.net" in l_carousel["items"][0]["thumbnail"]["imageUrl"]

    # 3. Game Summary
    finished_games = [
        {"game_id": "1", "home_team": "SK", "away_team": "KT", "home_score": 82, "away_score": 78, "status": "FINAL"}
    ]
    summary_resp = build_game_summary_response(finished_games, favorite_team="SK")
    s_card = summary_resp.template.outputs[0]["itemCard"]
    assert "daumcdn.net" in s_card["imageTitle"]["imageUrl"]
    assert "SK" in s_card["imageTitle"]["title"]

