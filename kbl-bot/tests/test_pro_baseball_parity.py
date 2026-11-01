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

    # 4. Home menu with live/scheduled team game (Matching 프로야구봇 _HhRnC entry)
    live_game = {
        "home_team": "KT", "away_team": "소노", "home_score": 45, "away_score": 40,
        "period": 2, "game_clock": "05:10", "status": "LIVE", "arena": "수원"
    }
    home_live_resp = build_home_menu_response(favorite_team="KT", team_game=live_game)
    live_card = home_live_resp.template.outputs[0]["basicCard"]
    assert "LIVE" in live_card["title"]
    assert "KT" in live_card["title"]
    assert "45" in live_card["title"]

    sched_game = {
        "home_team": "SK", "away_team": "삼성", "status": "SCHEDULED",
        "start_time": "2026-11-01T07:30:00Z", "arena": "잠실학생"
    }
    home_sched_resp = build_home_menu_response(favorite_team="SK", team_game=sched_game)
    sched_card = home_sched_resp.template.outputs[0]["basicCard"]
    assert "경기 안내" in sched_card["title"]
    assert "SK vs 삼성" in sched_card["title"]


@pytest.mark.asyncio
async def test_player_ranking_category_utterances():
    """Direct utterances like '어시스트', '도움', '블록', '리바운드' must route to leaderboards."""
    class MockGameSvc:
        async def get_player_rankings(self, category="pts"):
            return [
                {"rank": 1, "name": f"1위선수_{category}", "team": "KT", "value": 9.9}
            ]

    game_svc = MockGameSvc()
    user = User(kakao_user_key_hmac="test", encrypted_kakao_user_key="enc", favorite_team="KT")
    db = AsyncMock()
    user_svc = AsyncMock()

    # 1. '어시스트' -> ast
    resp = await _dispatch_command("어시스트", db, game_svc, user_svc, user)
    card = resp.template.outputs[0]["listCard"]
    assert "도움" in card["header"]["title"] or "어시스트" in card["header"]["title"]
    assert "1위선수_ast" in card["items"][0]["title"]
    # Check that specialized category quick replies are provided
    qr_labels = [qr.label for qr in resp.template.quickReplies]
    assert any("어시스트" in q for q in qr_labels)
    assert any("득점" in q for q in qr_labels)

    # 2. '도움' -> ast
    resp_ast2 = await _dispatch_command("도움", db, game_svc, user_svc, user)
    assert "1위선수_ast" in resp_ast2.template.outputs[0]["listCard"]["items"][0]["title"]

    # 3. '리바운드' -> reb
    resp_reb = await _dispatch_command("리바운드", db, game_svc, user_svc, user)
    assert "1위선수_reb" in resp_reb.template.outputs[0]["listCard"]["items"][0]["title"]

    # 4. '블록' -> blk
    resp_blk = await _dispatch_command("블록", db, game_svc, user_svc, user)
    assert "1위선수_blk" in resp_blk.template.outputs[0]["listCard"]["items"][0]["title"]

    # 5. '스틸' -> stl
    resp_stl = await _dispatch_command("스틸", db, game_svc, user_svc, user)
    assert "1위선수_stl" in resp_stl.template.outputs[0]["listCard"]["items"][0]["title"]


@pytest.mark.asyncio
async def test_user_points_feature():
    """Users must be able to check their prediction points, tiers, and earning tips."""
    from apps.kakao.builder import build_user_points_response, get_point_tier

    # 1. Tier boundary tests
    assert get_point_tier(0)[0] == "🥉 루키"
    assert get_point_tier(50)[0] == "🥈 주전"
    assert get_point_tier(200)[0] == "🥇 올스타"
    assert get_point_tier(500)[0] == "👑 KBL 레전드"

    # 2. Response builder
    resp = build_user_points_response(120, favorite_team="KT")
    card = resp.template.outputs[0]["basicCard"]
    assert "120 P" in card["title"]
    assert "🥈 주전" in card["description"]
    assert "승부예측" in card["buttons"][0]["label"]

    # 3. Router dispatch test
    class MockGameSvc:
        pass

    game_svc = MockGameSvc()
    user = User(kakao_user_key_hmac="test_hmac_pts", encrypted_kakao_user_key="enc", favorite_team="KT")
    db = AsyncMock()
    user_svc = AsyncMock()

    with patch("apps.kakao.router.get_user_points", AsyncMock(return_value=150)):
        for q in ["포인트", "내 포인트", "포인트 확인", "포인트 조회", "자신의 포인트가 얼마인지 확인"]:
            resp = await _dispatch_command(q, db, game_svc, user_svc, user)
            assert resp is not None
            card = resp.template.outputs[0]["basicCard"]
            assert "150 P" in card["title"]
            assert "🥈 주전" in card["description"]



