"""Unit tests for Kakao response builder functions."""

import pytest
from apps.kakao.builder import (
    build_error_response,
    build_health_response,
    build_live_score_response,
    build_simple_response,
    build_today_games_response,
)
from apps.kakao.schemas import KakaoSkillResponse, QuickReply


class TestBuildSimpleResponse:
    """Tests for build_simple_response()."""

    def test_returns_skill_response(self) -> None:
        """Must return a KakaoSkillResponse instance."""
        resp = build_simple_response("테스트")
        assert isinstance(resp, KakaoSkillResponse)

    def test_version_is_two(self) -> None:
        """version field must be '2.0'."""
        resp = build_simple_response("hi")
        assert resp.version == "2.0"

    def test_text_in_outputs(self) -> None:
        """The text must appear in the first output's simpleText."""
        resp = build_simple_response("안녕하세요")
        assert resp.template.outputs[0]["simpleText"]["text"] == "안녕하세요"

    def test_no_quick_replies_by_default(self) -> None:
        """No quick_replies arg → empty quickReplies list."""
        resp = build_simple_response("hi")
        assert resp.template.quickReplies == []

    def test_with_quick_replies(self) -> None:
        """Provided quick_replies must appear in the response."""
        qr = [QuickReply(label="테스트", messageText="테스트")]
        resp = build_simple_response("hi", quick_replies=qr)
        assert len(resp.template.quickReplies) == 1
        assert resp.template.quickReplies[0].label == "테스트"


class TestBuildErrorResponse:
    """Tests for build_error_response()."""

    def test_returns_skill_response(self) -> None:
        """Must return a KakaoSkillResponse."""
        assert isinstance(build_error_response(), KakaoSkillResponse)

    def test_contains_quick_replies(self) -> None:
        """Error response must include at least one quick-reply."""
        resp = build_error_response()
        assert len(resp.template.quickReplies) >= 1

    def test_custom_message(self) -> None:
        """Custom user_message must appear in simpleText output."""
        resp = build_error_response("커스텀 오류")
        assert resp.template.outputs[0]["simpleText"]["text"] == "커스텀 오류"

    def test_default_message_is_korean(self) -> None:
        """Default error message must be non-empty Korean text."""
        resp = build_error_response()
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert len(text) > 0


class TestBuildTodayGamesResponse:
    """Tests for build_today_games_response()."""

    def test_empty_games_returns_response(self) -> None:
        """Empty game list must return a friendly message."""
        resp = build_today_games_response([])
        assert isinstance(resp, KakaoSkillResponse)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "경기" in text

    def test_live_game_in_output(self) -> None:
        """LIVE game status must be reflected in output text."""
        games = [{
            "game_id": "G001",
            "home_team": "SK",
            "away_team": "KT",
            "home_score": 55,
            "away_score": 48,
            "period": 3,
            "game_clock": "05:30",
            "status": "LIVE",
            "start_time": "2026-10-19T05:00:00+00:00",
            "stale": False,
        }]
        resp = build_today_games_response(games)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "SK" in text
        assert "KT" in text
        assert "55" in text

    def test_scheduled_game_shows_time(self) -> None:
        """SCHEDULED game must show vs and a time string."""
        games = [{
            "game_id": "G002",
            "home_team": "KCC",
            "away_team": "삼성",
            "home_score": None,
            "away_score": None,
            "period": None,
            "game_clock": None,
            "status": "SCHEDULED",
            "start_time": "2026-10-19T10:00:00+00:00",
        }]
        resp = build_today_games_response(games)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "KCC" in text
        assert "vs" in text

    def test_has_quick_replies(self) -> None:
        """Response must include quick replies."""
        games = [{
            "game_id": "G003",
            "home_team": "LG",
            "away_team": "현대모비스",
            "home_score": 98,
            "away_score": 91,
            "period": 4,
            "game_clock": "00:00",
            "status": "FINAL",
            "start_time": "2026-10-19T05:00:00+00:00",
        }]
        resp = build_today_games_response(games)
        assert len(resp.template.quickReplies) >= 1


class TestBuildLiveScoreResponse:
    """Tests for build_live_score_response()."""

    def test_live_status_shows_period(self) -> None:
        """LIVE snapshot must show period and clock in output."""
        snapshot = {
            "game_id": "G001",
            "status": "LIVE",
            "home_team": "SK",
            "away_team": "KT",
            "home_score": 60,
            "away_score": 57,
            "period": 4,
            "game_clock": "02:10",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "4" in text  # period
        assert "60" in text

    def test_stale_shows_warning(self) -> None:
        """stale=True must include a warning mark in the text."""
        snapshot = {
            "status": "LIVE",
            "home_team": "SK",
            "away_team": "KT",
            "home_score": 50,
            "away_score": 45,
            "period": 2,
            "game_clock": "08:00",
            "stale": True,
        }
        resp = build_live_score_response(snapshot)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "⚠️" in text

    def test_final_status(self) -> None:
        """FINAL snapshot must mention 종료."""
        snapshot = {
            "status": "FINAL",
            "home_team": "LG",
            "away_team": "모비스",
            "home_score": 98,
            "away_score": 91,
            "period": 4,
            "game_clock": "00:00",
            "stale": False,
        }
        resp = build_live_score_response(snapshot)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "종료" in text


class TestBuildHealthResponse:
    """Tests for build_health_response()."""

    def test_all_ok(self) -> None:
        """All systems healthy → response must contain ✅."""
        resp = build_health_response(db_ok=True, redis_ok=True, worker_running=True)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "✅" in text

    def test_partial_failure(self) -> None:
        """Partial failure → response must contain ❌."""
        resp = build_health_response(db_ok=True, redis_ok=False, worker_running=True)
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "❌" in text

    def test_returns_skill_response(self) -> None:
        """Must always return a KakaoSkillResponse."""
        assert isinstance(
            build_health_response(False, False, False), KakaoSkillResponse
        )


class TestProBasketballBotFeatures:
    """Tests for the 10 core Pro Basketball Bot features (프로야구봇 KBL version)."""

    def test_all_10_quick_replies_present(self) -> None:
        """MAIN_MENU_QUICK_REPLIES must include all 10 core menus."""
        from apps.kakao.builder import MAIN_MENU_QUICK_REPLIES
        labels = [q.label for q in MAIN_MENU_QUICK_REPLIES]
        expected = [
            "일정", "KBL 일정", "결과", "뉴스", "주요장면",
            "관심선수", "팀순위", "선수순위", "응원하기", "설정",
        ]
        assert labels == expected

    def test_team_standings_builder(self) -> None:
        """build_team_standings_response must render 10-team table and star favorite team."""
        from apps.kakao.builder import build_team_standings_response
        from services.content.kbl_data import compute_standings_from_games
        games = [
            {"home_team": "KT", "away_team": "LG", "home_score": 85, "away_score": 77, "status": "FINAL", "start_time": "2026-10-25T05:00:00Z"},
        ]
        standings = compute_standings_from_games(games)
        assert len(standings) == 10
        resp = build_team_standings_response(standings, favorite_team="KT")
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "1위 ⭐KT" in text

    def test_player_rankings_builder(self) -> None:
        """build_player_rankings_response must render leaderboards and category quick-replies."""
        from apps.kakao.builder import build_player_rankings_response
        from services.content.kbl_data import get_default_player_rankings
        ranks = get_default_player_rankings()["pts"]
        resp = build_player_rankings_response(ranks, category="pts")
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "자밀 워니" in text
        assert "득점(PTS)" in text

    def test_cheering_and_settings_builders(self) -> None:
        """build_cheering_response and build_settings_response must render interactive buttons."""
        from apps.kakao.builder import build_cheering_response, build_settings_response
        cheer_resp = build_cheering_response(
            [{"game_id": "1", "home_team": "정관장", "away_team": "KT", "home_votes": 60, "away_votes": 40, "home_pct": 60, "away_pct": 40, "user_pick": "KT"}],
            notice="KT 응원 완료",
            user_points=20,
        )
        assert "정관장 60%" in cheer_resp.template.outputs[0]["simpleText"]["text"]

        set_resp = build_settings_response("KT", ["허훈"], {"game_start": True}, submode="team_select")
        assert len(set_resp.template.quickReplies) == 10

