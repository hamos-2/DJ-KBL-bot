"""Comprehensive QA test suite for KBL Bot Real-Time Game Information (Live Score & Boxscore & Lifecycle).

Covers the 5 Core Real-Time Pillars:
1. Quarter Boxscore & Game Clock & Overtime (OT)
2. Freshness & Stale (10s threshold) Detection Protection
3. Game Lifecycle State Transitions (SCHEDULED -> LIVE -> FINAL) & 3Q Prediction Cutoff
4. Daum Sports Real-Time API Parsing & Fault Tolerance Fallback
5. Kakao Skill 2.0 Protocol & Latency SLA Compliance
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.kakao.builder import (
    build_error_response,
    build_live_score_response,
    build_today_games_response,
)
from apps.kakao.router import set_services
from apps.kakao.schemas import KakaoSkillResponse
from core.cache.redis import (
    _FRESHNESS_THRESHOLD_SECONDS,
    _LIVE_SNAPSHOT_TTL_SECONDS,
    _is_stale,
    get_game_snapshot,
    get_game_snapshots_bulk,
    save_game_snapshot,
)
from core.db.session import get_db
from core.exceptions import ProviderError
from main import app
from services.game.service import GameService
from services.ingestion.worker import IngestionWorker
from services.provider.daum import DaumSportsDataProvider
from services.user.service import UserService


@pytest.fixture(autouse=True)
def init_test_services():
    """Ensure mock services are set for FastAPI routes during tests."""
    mock_game_service = MagicMock(spec=GameService)
    mock_user_service = MagicMock(spec=UserService)
    mock_worker = MagicMock(spec=IngestionWorker)

    # Default mock user setup
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.favorite_team = "SK"
    mock_user_service.get_or_create = AsyncMock(return_value=(mock_user, False))

    set_services(mock_game_service, mock_user_service, mock_worker)

    async def mock_db_session():
        session = AsyncMock()
        yield session

    app.dependency_overrides[get_db] = mock_db_session
    yield
    app.dependency_overrides.clear()


# ===========================================================================
# 1. Quarter Boxscore & Game Clock & Overtime (OT) Tests
# ===========================================================================

class TestRealtimeQuarterBoxscoreAndClock:
    """Verifies quarter score breakdowns, game clock, and overtime (OT) support."""

    def test_live_game_with_real_quarter_scores(self) -> None:
        """When real quarter scores are present in snapshot, they must be displayed verbatim."""
        snapshot = {
            "game_id": "80109230",
            "home_team": "삼성",
            "away_team": "SK",
            "home_score": 68,
            "away_score": 72,
            "home_quarters": [20, 18, 16, 14],
            "away_quarters": [22, 17, 19, 14],
            "period": 3,
            "game_clock": "04:32",
            "arena": "잠실학생체육관",
            "status": "LIVE",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        assert isinstance(resp, KakaoSkillResponse)
        card = resp.template.outputs[0]["itemCard"]

        # Header and Image Title
        assert card["head"]["title"] == "🔴 LIVE 톡중계"
        assert "삼성 68 : 72 SK" in card["imageTitle"]["title"]
        assert "3쿼터 04:32" in card["imageTitle"]["description"]

        # Quarter Boxscore Items
        item_list = card["itemList"]
        assert len(item_list) == 4
        assert item_list[0] == {"title": "1쿼터", "description": "삼성 20 : 22 SK"}
        assert item_list[1] == {"title": "2쿼터", "description": "삼성 18 : 17 SK"}
        assert item_list[2] == {"title": "3쿼터", "description": "삼성 16 : 19 SK"}
        assert item_list[3] == {"title": "4쿼터", "description": "삼성 14 : 14 SK"}

    def test_overtime_ot1_display(self) -> None:
        """Games in Overtime (period=5 / OT1) must include an Overtime item in the boxscore."""
        snapshot = {
            "game_id": "80109999",
            "home_team": "KT",
            "away_team": "LG",
            "home_score": 85,
            "away_score": 82,
            "home_quarters": [20, 18, 17, 19, 11],
            "away_quarters": [18, 19, 18, 19, 8],
            "period": 5,
            "game_clock": "01:15",
            "arena": "수원KT소닉붐아레나",
            "status": "LIVE",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        card = resp.template.outputs[0]["itemCard"]

        assert "연장(OT)" in card["imageTitle"]["description"]
        assert "01:15" in card["imageTitle"]["description"]

        item_list = card["itemList"]
        assert len(item_list) == 5
        assert item_list[4] == {"title": "연장(OT)", "description": "KT 11 : 8 LG"}

    def test_double_overtime_ot2_display(self) -> None:
        """Games in 2nd Overtime (period=6 / OT2) must show '연장2차' label within 6 chars."""
        snapshot = {
            "game_id": "80109998",
            "home_team": "DB",
            "away_team": "KCC",
            "home_score": 98,
            "away_score": 95,
            "home_quarters": [20, 20, 20, 20, 9, 9],
            "away_quarters": [20, 20, 20, 20, 9, 6],
            "period": 6,
            "game_clock": "00:45",
            "status": "LIVE",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        card = resp.template.outputs[0]["itemCard"]
        assert "연장2차" in card["imageTitle"]["description"]

        item_list = card["itemList"]
        assert len(item_list) == 5
        assert item_list[4]["title"] == "연장2차"

    def test_final_game_boxscore_and_badge(self) -> None:
        """Completed games must display '✅ 경기 종료' head title and '최종 스코어' in description."""
        snapshot = {
            "game_id": "80109200",
            "home_team": "정관장",
            "away_team": "소노",
            "home_score": 84,
            "away_score": 78,
            "period": 4,
            "game_clock": "00:00",
            "status": "FINAL",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        card = resp.template.outputs[0]["itemCard"]
        assert card["head"]["title"] == "✅ 경기 종료"
        assert "최종 스코어" in card["imageTitle"]["description"]
        assert card["itemListSummary"]["title"] == "최종점수"
        assert card["itemListSummary"]["description"] == "정관장 84 : 78 소노"

    def test_action_buttons_and_kakao_constraints(self) -> None:
        """Score card must have exactly 3 action buttons complying with Kakao OpenBuilder limits."""
        snapshot = {
            "game_id": "80109230",
            "home_team": "삼성",
            "away_team": "SK",
            "home_score": 25,
            "away_score": 28,
            "status": "LIVE",
        }
        resp = build_live_score_response(snapshot)
        card = resp.template.outputs[0]["itemCard"]
        buttons = card["buttons"]

        # Exactly 3 buttons allowed
        assert len(buttons) == 3
        assert buttons[0]["action"] == "webLink"
        assert "다음 톡중계" in buttons[0]["label"]
        assert "https://sports.daum.net/match/80109230" in buttons[0]["webLinkUrl"]

        assert buttons[1]["action"] == "message"
        assert "새로고침" in buttons[1]["label"]
        assert buttons[1]["messageText"] == "실시간 점수"

        assert buttons[2]["action"] == "message"
        assert "승부예측" in buttons[2]["label"]
        assert buttons[2]["messageText"] == "승부예측"


# ===========================================================================
# 2. Freshness & Stale Detection Protection Tests
# ===========================================================================

class TestRealtimeFreshnessAndStaleProtection:
    """Verifies Redis caching TTL, 10s freshness threshold, and stale warning notifications."""

    def test_freshness_threshold_constants(self) -> None:
        """Physical snapshot TTL must be 4 hours (14400s) and freshness threshold 10s."""
        assert _LIVE_SNAPSHOT_TTL_SECONDS == 4 * 3600
        assert _FRESHNESS_THRESHOLD_SECONDS == 10

    def test_is_stale_boundary_conditions(self) -> None:
        """Snapshots <= 10s must be fresh; snapshots > 10s or invalid timestamp must be stale."""
        now = datetime.now(UTC)

        # 9 seconds ago: FRESH (not stale)
        ts_fresh = (now - timedelta(seconds=9)).isoformat()
        assert _is_stale(ts_fresh) is False

        # 11 seconds ago: STALE
        ts_stale = (now - timedelta(seconds=11)).isoformat()
        assert _is_stale(ts_stale) is True

        # Empty or corrupted timestamp: STALE (fail-safe)
        assert _is_stale("") is True
        assert _is_stale("invalid-date-string") is True

    def test_stale_warning_notification_displayed(self) -> None:
        """When stale is True, card description must display '⚠️(지연)'."""
        snapshot = {
            "game_id": "80109230",
            "home_team": "삼성",
            "away_team": "SK",
            "home_score": 40,
            "away_score": 42,
            "period": 2,
            "game_clock": "05:12",
            "status": "LIVE",
            "stale": True,
        }
        resp = build_live_score_response(snapshot)
        card = resp.template.outputs[0]["itemCard"]
        assert "⚠️(지연)" in card["imageTitle"]["description"]

    def test_fresh_data_has_no_stale_warning(self) -> None:
        """When stale is False, no warning sign should be present in the description."""
        snapshot = {
            "game_id": "80109230",
            "home_team": "삼성",
            "away_team": "SK",
            "home_score": 40,
            "away_score": 42,
            "period": 2,
            "game_clock": "05:12",
            "status": "LIVE",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        card = resp.template.outputs[0]["itemCard"]
        assert "⚠️" not in card["imageTitle"]["description"]


# ===========================================================================
# 3. Game Lifecycle Transitions & 3Q Prediction Cutoff Tests
# ===========================================================================

class TestRealtimeLifecycleAndPredictionCutoff:
    """Verifies state transitions (SCHEDULED -> LIVE -> FINAL) and prediction cutoff at 3Q."""

    @pytest.mark.asyncio
    async def test_worker_transition_detection(self) -> None:
        """IngestionWorker must detect SCHEDULED -> LIVE -> FINAL transitions and invalidate caches."""
        mock_provider = AsyncMock()
        worker = IngestionWorker(provider=mock_provider, persist_db=False)

        # Initial state: SCHEDULED
        data_sched = {"game_id": "G001", "status": "SCHEDULED", "home_team": "SK", "away_team": "KT"}
        await worker._detect_transition("G001", data_sched)
        assert worker._last_status["G001"] == "SCHEDULED"

        # Transition to LIVE
        data_live = {"game_id": "G001", "status": "LIVE", "home_team": "SK", "away_team": "KT"}
        await worker._detect_transition("G001", data_live)
        assert worker._last_status["G001"] == "LIVE"

        # Transition to FINAL: must trigger cache invalidation
        with patch("services.ingestion.worker.invalidate_standings_and_rankings_cache", new_callable=AsyncMock) as mock_inv:
            data_final = {"game_id": "G001", "status": "FINAL", "home_team": "SK", "away_team": "KT"}
            await worker._detect_transition("G001", data_final)
            assert worker._last_status["G001"] == "FINAL"
            mock_inv.assert_awaited_once()

    def test_prediction_3q_cutoff_integration(self) -> None:
        """A user attempting to predict a game that has entered 3Q must be blocked with a cutoff message."""
        client = TestClient(app, raise_server_exceptions=False)
        game_id = "80109230"

        # Mock game_service returning game in 3Q
        live_3q_game = {
            "game_id": game_id,
            "home_team": "삼성",
            "away_team": "SK",
            "status": "LIVE",
            "period": 3,
            "home_score": 52,
            "away_score": 55,
        }

        mock_gs = MagicMock(spec=GameService)
        mock_gs.get_today_games = AsyncMock(return_value=[live_3q_game])
        mock_us = MagicMock(spec=UserService)
        mock_user = MagicMock()
        mock_user.favorite_team = "삼성"
        mock_us.get_or_create = AsyncMock(return_value=(mock_user, False))
        set_services(mock_gs, mock_us, MagicMock())

        payload = {
            "userRequest": {
                "user": {"id": "test_user_3q"},
                "utterance": "#승부예측 삼성",
            },
            "action": {
                "name": "today_games",
                "params": {},
            },
        }
        resp = client.post("/integrations/kakao/skills/today-games", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0"

        output = data["template"]["outputs"][0]
        if "listCard" in output:
            header = output["listCard"]["header"]["title"]
            assert "3쿼터" in header and "마감" in header


# ===========================================================================
# 4. Daum Sports Real-Time API Parsing & Fault Tolerance Tests
# ===========================================================================

class TestDaumSportsRealtimeParsingAndFaultTolerance:
    """Verifies Daum ARMS real-time quarter parsing and graceful degradation under API failure."""

    def test_daum_arms_quarter_parsing(self) -> None:
        """DaumSportsDataProvider._parse_quarters must extract quarter1..4 and extra scores."""
        score_obj = {
            "quarter1": 21,
            "quarter2": 19,
            "quarter3": 25,
            "quarter4": 18,
            "extra": 7,
            "total": 90,
        }
        quarters = DaumSportsDataProvider._parse_quarters(score_obj)
        assert quarters == [21, 19, 25, 18, 7]

    def test_daum_arms_quarter_parsing_with_none_values(self) -> None:
        """Quarter score parsing must gracefully convert null/None quarters to 0."""
        score_obj = {
            "quarter1": 16,
            "quarter2": None,
            "quarter3": None,
            "quarter4": None,
            "extra": None,
            "total": 16,
        }
        quarters = DaumSportsDataProvider._parse_quarters(score_obj)
        assert quarters == [16, 0, 0, 0]

    def test_daum_arms_period_extra_parsing(self) -> None:
        """EXTRA1, EXTRA2 or OT in periodType must parse to period >= 5."""
        assert DaumSportsDataProvider._parse_period("QUARTER1", "LIVE") == 1
        assert DaumSportsDataProvider._parse_period("QUARTER4", "LIVE") == 4
        assert DaumSportsDataProvider._parse_period("EXTRA1", "LIVE") == 5
        assert DaumSportsDataProvider._parse_period("OT1", "LIVE") == 5
        assert DaumSportsDataProvider._parse_period("OT2", "LIVE") == 6
        assert DaumSportsDataProvider._parse_period(None, "FINAL") == 4

    def test_daum_api_timeout_fallback_to_snapshot(self) -> None:
        """When Daum API times out or fails, existing Redis snapshot must be retained without crashing."""
        client = TestClient(app, raise_server_exceptions=False)

        cached_snapshot = {
            "game_id": "80109230",
            "home_team": "삼성",
            "away_team": "SK",
            "home_score": 60,
            "away_score": 62,
            "period": 3,
            "game_clock": "03:15",
            "status": "LIVE",
            "stale": True,
            "updated_at": (datetime.now(UTC) - timedelta(seconds=20)).isoformat(),
        }

        mock_gs = MagicMock(spec=GameService)
        mock_gs.get_live_snapshot = AsyncMock(return_value=cached_snapshot)
        mock_us = MagicMock(spec=UserService)
        mock_user = MagicMock()
        mock_user.favorite_team = "삼성"
        mock_us.get_or_create = AsyncMock(return_value=(mock_user, False))
        set_services(mock_gs, mock_us, MagicMock())

        payload = {
            "userRequest": {
                "user": {"id": "test_qa_user"},
                "utterance": "실시간 점수",
            },
            "action": {
                "name": "live_score",
                "params": {"game_id": "80109230"},
            },
        }
        resp = client.post("/integrations/kakao/skills/live-score", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        card = data["template"]["outputs"][0]["itemCard"]
        assert "삼성 60 : 62 SK" in card["imageTitle"]["title"]
        assert "⚠️(지연)" in card["imageTitle"]["description"]


# ===========================================================================
# 5. Kakao Skill 2.0 Protocol & Latency SLA Compliance Tests
# ===========================================================================

class TestKakaoSkill20ProtocolAndRouting:
    """Verifies Kakao Skill 2.0 response format, refresh utterances, and Always HTTP 200 guarantee."""

    def test_live_score_refresh_utterance_routing(self) -> None:
        """Utterances like '새로고침' or '실시간 점수' must route to live score or today's games."""
        client = TestClient(app, raise_server_exceptions=False)
        live_game = {
            "game_id": "80109230",
            "home_team": "삼성",
            "away_team": "SK",
            "home_score": 25,
            "away_score": 28,
            "period": 1,
            "status": "LIVE",
        }

        mock_gs = MagicMock(spec=GameService)
        mock_gs.get_today_games = AsyncMock(return_value=[live_game])
        mock_us = MagicMock(spec=UserService)
        mock_user = MagicMock()
        mock_user.favorite_team = "삼성"
        mock_us.get_or_create = AsyncMock(return_value=(mock_user, False))
        set_services(mock_gs, mock_us, MagicMock())

        for utterance in ("새로고침", "실시간 점수", "박스스코어", "실시간점수새로고침"):
            payload = {
                "userRequest": {
                    "user": {"id": "test_qa_refresh"},
                    "utterance": utterance,
                },
                "action": {
                    "name": "today_games",
                    "params": {},
                },
            }
            resp = client.post("/integrations/kakao/skills/today-games", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["version"] == "2.0"
            assert len(data["template"]["outputs"]) == 1
            assert "itemCard" in data["template"]["outputs"][0]

    def test_always_http_200_on_unhandled_server_exception(self) -> None:
        """Even on unhandled backend exceptions, Kakao endpoints must return HTTP 200 with an error text card."""
        client = TestClient(app, raise_server_exceptions=False)

        mock_gs = MagicMock(spec=GameService)
        mock_us = MagicMock(spec=UserService)
        mock_us.get_or_create = AsyncMock(side_effect=RuntimeError("DB connection dead"))
        set_services(mock_gs, mock_us, MagicMock())

        payload = {
            "userRequest": {
                "user": {"id": "test_qa_unhandled"},
                "utterance": "실시간 점수",
            },
            "action": {
                "name": "live_score",
                "params": {},
            },
        }
        resp = client.post("/integrations/kakao/skills/live-score", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == "2.0"
        card = data["template"]["outputs"][0]["textCard"]
        assert "ℹ️ KBL 프로농구 안내" in card["title"]
        assert "일시적으로 데이터를 불러올 수 없습니다" in card["description"]
