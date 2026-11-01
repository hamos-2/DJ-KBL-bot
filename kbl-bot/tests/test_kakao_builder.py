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
        """Custom user_message must appear in card output."""
        resp = build_error_response("커스텀 오류")
        assert resp.template.outputs[0]["textCard"]["description"] == "커스텀 오류"

    def test_default_message_is_korean(self) -> None:
        """Default error message must be non-empty Korean text."""
        resp = build_error_response()
        text = resp.template.outputs[0]["textCard"]["description"]
        assert len(text) > 0


class TestBuildTodayGamesResponse:
    """Tests for build_today_games_response()."""

    def test_empty_games_returns_response(self) -> None:
        """Empty game list must return a friendly card message."""
        resp = build_today_games_response([])
        assert isinstance(resp, KakaoSkillResponse)
        card = resp.template.outputs[0]["listCard"]
        assert "경기" in card["header"]["title"] or "경기" in card["items"][0]["title"]

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
        item = resp.template.outputs[0]["listCard"]["items"][0]
        assert "SK" in item["title"]
        assert "KT" in item["title"]
        assert "55" in item["title"]

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
        item = resp.template.outputs[0]["listCard"]["items"][0]
        assert "KCC" in item["title"]
        assert "vs" in item["title"]

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
        card = resp.template.outputs[0]["itemCard"]
        assert "4" in card["imageTitle"]["description"]
        assert "60" in card["imageTitle"]["title"]

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
        card = resp.template.outputs[0]["itemCard"]
        assert "⚠️" in card["imageTitle"]["description"]

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
        card = resp.template.outputs[0]["itemCard"]
        assert "종료" in card["head"]["title"] or "스코어" in card["imageTitle"]["description"]


class TestBuildHealthResponse:
    """Tests for build_health_response()."""

    def test_all_ok(self) -> None:
        """All systems healthy → response must contain ✅."""
        resp = build_health_response(db_ok=True, redis_ok=True, worker_running=True)
        text = resp.template.outputs[0]["textCard"]["description"]
        assert "✅" in text

    def test_partial_failure(self) -> None:
        """Partial failure → response must contain ❌."""
        resp = build_health_response(db_ok=True, redis_ok=False, worker_running=True)
        text = resp.template.outputs[0]["textCard"]["description"]
        assert "❌" in text

    def test_returns_skill_response(self) -> None:
        """Must always return a KakaoSkillResponse."""
        assert isinstance(
            build_health_response(False, False, False), KakaoSkillResponse
        )


class TestProBasketballBotFeatures:
    """Tests for the 10 core Pro Basketball Bot features (프로야구봇 KBL version)."""

    def test_all_10_quick_replies_present(self) -> None:
        """MAIN_MENU_QUICK_REPLIES must match 프로야구봇 (_HhRnC) core menus."""
        from apps.kakao.builder import MAIN_MENU_QUICK_REPLIES
        labels = [q.label for q in MAIN_MENU_QUICK_REPLIES]
        expected = [
            "오늘 경기", "실시간 점수", "승부예측", "라인업", "일정",
            "결과", "팀순위", "선수순위", "주요장면", "알림설정",
        ]
        assert labels == expected

    def test_team_standings_builder(self) -> None:
        """build_team_standings_response must render 10-team table cards and star favorite team."""
        from apps.kakao.builder import build_team_standings_response
        from services.content.kbl_data import compute_standings_from_games
        games = [
            {"home_team": "KT", "away_team": "LG", "home_score": 85, "away_score": 77, "status": "FINAL", "start_time": "2026-10-25T05:00:00Z"},
        ]
        standings = compute_standings_from_games(games)
        assert len(standings) == 10
        resp = build_team_standings_response(standings, favorite_team="KT")
        card1 = resp.template.outputs[0]["listCard"]
        assert "1위 ⭐KT" in card1["items"][0]["title"]
        assert len(resp.template.outputs) == 2  # 1-5위 and 6-10위 listCards

    def test_player_rankings_builder(self) -> None:
        """build_player_rankings_response must render leaderboards card and category buttons."""
        from apps.kakao.builder import build_player_rankings_response
        from services.content.kbl_data import get_default_player_rankings
        ranks = get_default_player_rankings()["pts"]
        resp = build_player_rankings_response(ranks, category="pts")
        card = resp.template.outputs[0]["listCard"]
        assert any("자밀 워니" in it["title"] for it in card["items"])
        assert "득점" in card["header"]["title"]

    def test_cheering_and_settings_builders(self) -> None:
        """build_cheering_response and build_settings_response must render interactive cards and buttons."""
        from apps.kakao.builder import build_cheering_response, build_settings_response
        cheer_resp = build_cheering_response(
            [{"game_id": "1", "home_team": "정관장", "away_team": "KT", "home_votes": 60, "away_votes": 40, "home_pct": 60, "away_pct": 40, "user_pick": "KT"}],
            notice="KT 응원 완료",
            user_points=20,
        )
        carousel = cheer_resp.template.outputs[0]["carousel"]
        assert any("정관장" in c["title"] for c in carousel["items"])
        assert "승부예측" in carousel["items"][0]["title"]

        set_main = build_settings_response("KT", ["허훈"], {"lineup": True, "game_start": True, "game_end": False, "clutch": False})
        carousel_items = set_main.template.outputs[0]["carousel"]["items"]
        btn_labels = [b["label"] for card in carousel_items for b in card["buttons"]]
        assert "❤️ 응원팀 변경" in btn_labels
        assert "시작알림 OFF" in btn_labels
        assert "종료알림 ON" in btn_labels
        assert "클러치알림 ON" in btn_labels
        qr_labels = [q.label for q in set_main.template.quickReplies]
        assert qr_labels == [
            "오늘 경기", "실시간 점수", "승부예측", "라인업", "일정",
            "결과", "팀순위", "선수순위", "주요장면", "알림설정",
        ]

        set_resp = build_settings_response("KT", ["허훈"], {"game_start": True}, submode="team_select")
        assert len(set_resp.template.quickReplies) == 10

    def test_lineup_and_game_summary_builders(self) -> None:
        """build_lineup_response and build_game_summary_response must format professional baseball bot equivalents."""
        from apps.kakao.builder import build_game_summary_response, build_lineup_response
        sample_games = [
            {
                "game_id": "G001",
                "home_team": "SK",
                "away_team": "DB",
                "home_score": 88,
                "away_score": 82,
                "status": "FINAL",
                "start_time": "2026-11-01T05:00:00Z",
                "arena": "잠실학생",
            }
        ]
        lineup_resp = build_lineup_response(sample_games, favorite_team="SK")
        l_carousel = lineup_resp.template.outputs[0]["carousel"]
        assert len(l_carousel["items"]) >= 1
        assert "이선 알바노" in l_carousel["items"][0]["description"]

        summary_resp = build_game_summary_response(sample_games, favorite_team="SK")
        s_card = summary_resp.template.outputs[0]["itemCard"]
        assert "경기 요약" in s_card["head"]["title"]
        assert "SK" in s_card["imageTitle"]["title"]

    def test_clean_single_bubble_on_results_news_highlights_standings(self) -> None:
        """All content builders must output clean visual cards with 10 fixed quickReplies."""
        from apps.kakao.builder import (
            build_game_results_response,
            build_highlights_response,
            build_my_schedule_response,
            build_news_response,
            build_team_standings_response,
        )
        sample_games = [
            {
                "game_id": "80109227",
                "home_team": "KT",
                "away_team": "LG",
                "home_score": 88,
                "away_score": 82,
                "status": "FINAL",
                "arena": "수원",
                "start_time": "2026-10-31T05:00:00Z",
            }
        ]
        for resp in [
            build_my_schedule_response(sample_games, sample_games, favorite_team="KT"),
            build_game_results_response(sample_games, favorite_team="KT"),
            build_news_response([{"title": "KT 승리", "url": "https://sports.daum.net/basketball"}], favorite_team="KT"),
            build_highlights_response([{"title": "하이라이트", "url": "https://search.daum.net/search?w=vclip&q=KBL+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8", "arena": "수원"}]),
            build_team_standings_response([{"rank": 1, "team": "KT", "wins": 5, "losses": 1, "wpct": 0.833, "gb": "0.0", "streak": "3연승"}], favorite_team="KT"),
        ]:
            assert "listCard" in resp.template.outputs[0]
            assert len(resp.template.quickReplies) == 10

    def test_team_specific_news_builder(self) -> None:
        """build_news_response must customize headline and advice when favorite_team is provided."""
        from apps.kakao.builder import build_news_response
        team_resp = build_news_response(
            [{"title": "DB 알바노 맹활약", "url": "https://sports.daum.net/basketball"}],
            favorite_team="DB",
        )
        card = team_resp.template.outputs[0]["listCard"]
        assert "원주 DB" in card["header"]["title"]
        assert "DB 알바노" in card["items"][0]["title"]

        generic_resp = build_news_response(
            [{"title": "KBL 전체 뉴스", "url": "https://sports.daum.net/basketball"}],
            favorite_team=None,
        )
        gen_card = generic_resp.template.outputs[0]["listCard"]
        assert "KBL 프로농구 최신 뉴스" in gen_card["header"]["title"]

    def test_team_specific_highlights_builder(self) -> None:
        """build_highlights_response must customize header and advice when favorite_team is provided."""
        from apps.kakao.builder import build_highlights_response
        team_resp = build_highlights_response(
            [{"title": "SK 워니 덩크슛", "url": "https://search.daum.net/search?w=vclip&q=SK+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8", "arena": "잠실"}],
            favorite_team="SK",
        )
        card = team_resp.template.outputs[0]["listCard"]
        assert "서울 SK" in card["header"]["title"]
        assert "SK 워니" in card["items"][0]["title"]

        gen_resp = build_highlights_response(
            [{"title": "전체 하이라이트", "url": "https://search.daum.net/search?w=vclip&q=KBL+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8", "arena": "수원"}],
            favorite_team=None,
        )
        gen_card = gen_resp.template.outputs[0]["listCard"]
        assert "KBL 프로농구 주요장면" in gen_card["header"]["title"]

    def test_custom_player_builders(self) -> None:
        """build_single_player_response and build_team_players_response must render toggle buttons."""
        from apps.kakao.builder import build_single_player_response, build_team_players_response
        from services.content.kbl_data import KBL_PLAYERS

        player = next(p for p in KBL_PLAYERS if p["name"] == "허훈")
        resp1 = build_single_player_response(player, is_favorite=False)
        card1 = resp1.template.outputs[0]["basicCard"]
        assert "허훈" in card1["title"]
        assert "부산 KCC" in card1["description"]
        btn1 = card1["buttons"][0]
        assert "등록" in btn1["label"]

        player_ksh = next(p for p in KBL_PLAYERS if p["name"] == "김선형")
        resp_ksh = build_single_player_response(player_ksh, is_favorite=False)
        assert "수원 KT" in resp_ksh.template.outputs[0]["basicCard"]["description"]

        resp2 = build_single_player_response(player, is_favorite=True)
        card2 = resp2.template.outputs[0]["basicCard"]
        btn2 = card2["buttons"][0]
        assert "해제" in btn2["label"]

        db_players = [p for p in KBL_PLAYERS if p["team"] == "DB"]
        team_resp = build_team_players_response("DB", db_players, fav_players=["이선 알바노"])
        card3 = team_resp.template.outputs[0]["listCard"]
        assert "원주 DB" in card3["header"]["title"]
        assert len(card3["buttons"]) >= 1

    def test_deterministic_seed_consistency(self) -> None:
        """_deterministic_seed must return identical values across calls."""
        from core.cache.redis import _deterministic_seed
        s1 = _deterministic_seed("80109227:KT")
        s2 = _deterministic_seed("80109227:KT")
        assert s1 == s2
        assert 45 <= s1 < 125

    def test_notice_builder(self) -> None:
        """build_notice_response must return listCard with channel announcements."""
        from apps.kakao.builder import build_notice_response
        resp = build_notice_response()
        assert resp.version == "2.0"
        card = resp.template.outputs[0]["listCard"]
        assert "KBL봇 채널 소식" in card["header"]["title"]
        assert len(card["items"]) >= 3
        assert len(resp.template.quickReplies) == 10



