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
        """MAIN_MENU_QUICK_REPLIES must match 프로야구봇 (_HhRnC) core menus with visual icons."""
        from apps.kakao.builder import MAIN_MENU_QUICK_REPLIES
        labels = [q.label for q in MAIN_MENU_QUICK_REPLIES]
        expected = [
            "🏀 오늘 경기", "🔴 실시간 점수", "🗳️ 승부예측", "📋 라인업", "⭐ 관심선수",
            "📅 일정", "📰 최신 뉴스", "🎬 주요장면", "🏆 팀순위", "⚙️ 설정",
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
        assert any(("코피 코번" in it["title"] or "게이지 프림" in it["title"] or "이정현" in it["title"]) for it in card["items"])
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
            "🏀 오늘 경기", "🔴 실시간 점수", "🗳️ 승부예측", "📋 라인업", "⭐ 관심선수",
            "📅 일정", "📰 최신 뉴스", "🎬 주요장면", "🏆 팀순위", "⚙️ 설정",
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
        assert "DB" in card["header"]["title"]
        assert "DB 알바노" in card["items"][0]["title"]

        generic_resp = build_news_response(
            [{"title": "KBL 전체 뉴스", "url": "https://sports.daum.net/basketball"}],
            favorite_team=None,
        )
        gen_card = generic_resp.template.outputs[0]["listCard"]
        assert "KBL" in gen_card["header"]["title"]

        # Test Page 1, Page 2, and Multi-page cycling (🔄 새로운 뉴스)
        sample_15_news = [{"title": f"기사 {i}", "url": f"https://sports.daum.net/{i}"} for i in range(15)]
        p1 = build_news_response(sample_15_news, favorite_team="KT", page=1)
        p1_card = p1.template.outputs[0]["listCard"]
        assert len(p1_card["items"]) == 5
        assert p1_card["items"][0]["title"] == "기사 0"
        assert "새로운 뉴스" in p1_card["buttons"][0]["label"]
        assert "새로운 뉴스 2" in p1_card["buttons"][0]["messageText"]

        p2 = build_news_response(sample_15_news, favorite_team="KT", page=2)
        p2_card = p2.template.outputs[0]["listCard"]
        assert len(p2_card["items"]) == 5
        assert p2_card["items"][0]["title"] == "기사 5"
        assert "더보기" in p2_card["header"]["title"]
        assert "새로운 뉴스" in p2_card["buttons"][0]["label"]
        assert "새로운 뉴스 3" in p2_card["buttons"][0]["messageText"]

        p3 = build_news_response(sample_15_news, favorite_team="KT", page=3)
        p3_card = p3.template.outputs[0]["listCard"]
        assert len(p3_card["items"]) == 5
        assert p3_card["items"][0]["title"] == "기사 10"
        assert p3_card["buttons"][0]["label"] == "최신 뉴스로"

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
        daum_btn = next(b for b in gen_card["buttons"] if "다음 KBL 영상관" in b["label"])
        assert "search.daum.net/search?w=vclip" in daum_btn["webLinkUrl"]
        assert "sports.daum.net/video/kbl" not in daum_btn["webLinkUrl"]

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

        player_hw = next(p for p in KBL_PLAYERS if p["name"] == "허웅")
        resp_hw = build_single_player_response(player_hw, is_favorite=False)
        assert "부산 KCC" in resp_hw.template.outputs[0]["basicCard"]["description"]

        resp2 = build_single_player_response(player, is_favorite=True)
        card2 = resp2.template.outputs[0]["basicCard"]
        btn2 = card2["buttons"][0]
        assert "해제" in btn2["label"]

        db_players = [p for p in KBL_PLAYERS if p["team"] == "DB"]
        team_resp = build_team_players_response("DB", db_players, fav_players=["이선 알바노"])
        card3 = team_resp.template.outputs[0]["listCard"]
        assert "원주 DB" in card3["header"]["title"]
        assert len(card3["buttons"]) >= 1
        assert any("다른 구단" in b["label"] for b in card3["buttons"])
        # Second output is 1-tap registration carousel for Best 5
        assert len(team_resp.template.outputs) == 2
        reg_cards = team_resp.template.outputs[1]["carousel"]["items"]
        assert len(reg_cards) == 2
        assert "Best 5" in reg_cards[0]["title"]
        all_reg_btns = [b["label"] for c in reg_cards for b in c["buttons"]]
        assert any("알바노" in b for b in all_reg_btns)

    def test_team_players_menu_and_10_clubs_selection(self) -> None:
        """Verify 10-team player selection menu and quick replies."""
        from apps.kakao.builder import build_team_players_menu_response, build_favorite_players_response

        # 1. 10-team carousel menu
        menu_resp = build_team_players_menu_response()
        assert menu_resp.version == "2.0"
        cards = menu_resp.template.outputs[0]["carousel"]["items"]
        assert len(cards) == 4
        all_buttons = [btn["messageText"] for card in cards for btn in card["buttons"]]
        for t in ["SK", "KT", "DB", "KCC", "LG", "정관장", "소노", "삼성"]:
            assert any(t in b for b in all_buttons), f"Team {t} missing from player menu buttons"
        assert len(menu_resp.template.quickReplies) == 10

        # 2. Favorite players response carousel contains 10-team browsing cards and stays <= 5 cards (< 30,720B Kakao bubble limit)
        fav_resp = build_favorite_players_response(fav_players=["김선형"], favorite_team="KT")
        assert fav_resp.version == "2.0"
        fav_cards = fav_resp.template.outputs[1]["carousel"]["items"]
        assert len(fav_cards) <= 5, f"Carousel has {len(fav_cards)} cards, exceeding Kakao 30KB bubble limit!"
        fav_card_titles = [c["title"] for c in fav_cards]
        assert any("수도권" in t for t in fav_card_titles)
        assert any("경기·강원" in t for t in fav_card_titles)
        assert any("영남권" in t for t in fav_card_titles)

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

    def test_team_news_menu_and_other_teams_navigation(self) -> None:
        """Verify '다른팀 뉴스' carousel menu and quick replies for all 10 teams."""
        from apps.kakao.builder import build_news_response, build_team_news_menu_response

        # 1. build_team_news_menu_response
        menu_resp = build_team_news_menu_response()
        assert menu_resp.version == "2.0"
        carousel = menu_resp.template.outputs[0]["carousel"]
        assert carousel["type"] == "basicCard"
        assert len(carousel["items"]) == 4  # 수도권, 경기강원, 영남, 대구/전체
        assert len(menu_resp.template.quickReplies) == 10

        # Verify buttons across all cards cover teams
        all_btn_labels = [
            btn["label"]
            for card in carousel["items"]
            for btn in card["buttons"]
        ]
        assert any("SK" in label for label in all_btn_labels)
        assert any("KT" in label for label in all_btn_labels)
        assert any("DB" in label for label in all_btn_labels)
        assert any("LG" in label for label in all_btn_labels)
        assert any("모비스" in label for label in all_btn_labels)
        assert any("한국가스공사" in label for label in all_btn_labels)
        assert any("KBL 전체" in label for label in all_btn_labels)

        # 2. build_news_response has "다른팀 뉴스" action button & quick replies
        news_resp = build_news_response(
            [{"title": "뉴스 기사", "url": "https://sports.daum.net"}],
            favorite_team="KT",
        )
        news_card = news_resp.template.outputs[0]["listCard"]
        assert any("다른팀 뉴스" in btn["label"] for btn in news_card["buttons"])
        qr_labels = [qr.label for qr in news_resp.template.quickReplies]
        assert any("다른팀 뉴스" in l for l in qr_labels)
        assert any("전체 뉴스" in l for l in qr_labels)
        assert len(news_resp.template.quickReplies) == 10

    def test_favorite_players_tab_and_builder_options(self) -> None:
        """Verify dedicated '관심선수' tab in MAIN_MENU_QUICK_REPLIES and favorite players response."""
        from apps.kakao.builder import (
            FAVORITE_PLAYERS_QUICK_REPLIES,
            MAIN_MENU_QUICK_REPLIES,
            build_favorite_players_response,
            build_home_menu_response,
        )

        # 1. '관심선수' is in MAIN_MENU_QUICK_REPLIES at position 5
        assert "관심선수" in MAIN_MENU_QUICK_REPLIES[4].label
        assert MAIN_MENU_QUICK_REPLIES[4].messageText == "관심선수"

        # 2. build_home_menu_response includes carousel with game card and news card
        home_resp = build_home_menu_response(favorite_team="KT")
        carousel_items = (
            home_resp.template.outputs[0]["carousel"]["items"]
            if "carousel" in home_resp.template.outputs[0]
            else [home_resp.template.outputs[0]["basicCard"]]
        )
        assert len(carousel_items) >= 2
        home_card = carousel_items[0]
        news_card = carousel_items[1]
        btn_labels = [btn["label"] for btn in home_card["buttons"]]
        assert any("관심선수" in l for l in btn_labels)
        news_btn_labels = [btn["label"] for btn in news_card["buttons"]]
        assert any("뉴스" in l for l in news_btn_labels)

        # 3. build_favorite_players_response includes FAVORITE_PLAYERS_QUICK_REPLIES and carousel options
        fav_resp = build_favorite_players_response(
            fav_players=["허훈"], favorite_team="KT"
        )
        assert len(fav_resp.template.quickReplies) == 10
        fav_qr_labels = [qr.label for qr in fav_resp.template.quickReplies]
        assert "⭐ 내 관심선수" in fav_qr_labels
        assert any("선수" in l for l in fav_qr_labels)

        # Check carousel cards (including team roster shortcuts)
        carousel = fav_resp.template.outputs[1]["carousel"]
        c_titles = [c["title"] for c in carousel["items"]]
        assert any("응원팀 선수" in t for t in c_titles)
        assert any("구단별 선수" in t for t in c_titles)

    def test_all_10_teams_rosters_and_best5_up_to_date(self) -> None:
        """Verify that all 10 teams' Best 5 and rosters are up to date and retired players (e.g. 함지훈) are excluded."""
        from services.content.kbl_data import KBL_PLAYERS, TEAM_LINEUPS

        # 1. Ham Ji-hoon must NEVER be in any active player roster or starters
        all_player_names = [p["name"] for p in KBL_PLAYERS]
        assert "함지훈" not in all_player_names, "Retired player 함지훈 must not be in active player roster!"

        mobis_lineup = TEAM_LINEUPS.get("현대모비스", {})
        mobis_starters = mobis_lineup.get("starters", [])
        mobis_starter_names = [s["name"] for s in mobis_starters]
        assert "함지훈" not in mobis_starter_names, "Retired player 함지훈 must not be in Hyundai Mobis starters!"
        assert "이승현" in mobis_starter_names, "이승현 should be in Mobis starters!"
        assert mobis_lineup.get("head_coach") == "양동근", "양동근 should be Hyundai Mobis head coach!"

        # 2. Verify all 10 teams have exactly 5 starters, foreign players, and Asian quota
        all_10_teams = ["SK", "DB", "KT", "LG", "정관장", "KCC", "한국가스공사", "현대모비스", "소노", "삼성"]
        for team in all_10_teams:
            assert team in TEAM_LINEUPS, f"Team {team} missing from TEAM_LINEUPS"
            info = TEAM_LINEUPS[team]
            assert len(info["starters"]) == 5, f"{team} must have exactly 5 starters"
            assert info.get("head_coach"), f"{team} must have a valid head coach"
            assert info.get("foreign_players"), f"{team} must have foreign players listed"
            assert info.get("asian_quota"), f"{team} must have Asian quota player listed"

        # 3. Verify 2026-2027 Season (as of 2026-11-02) official head coaches
        assert TEAM_LINEUPS["소노"]["head_coach"] == "손창환"
        assert TEAM_LINEUPS["삼성"]["head_coach"] == "김상식"
        assert TEAM_LINEUPS["정관장"]["head_coach"] == "유도훈"
        assert TEAM_LINEUPS["KCC"]["head_coach"] == "이상민"
        assert TEAM_LINEUPS["DB"]["head_coach"] == "이규섭"
        assert TEAM_LINEUPS["KT"]["head_coach"] == "문경은"
        assert TEAM_LINEUPS["SK"]["head_coach"] == "전희철"
        assert TEAM_LINEUPS["LG"]["head_coach"] == "조상현"
        assert TEAM_LINEUPS["한국가스공사"]["head_coach"] == "강혁"
        assert TEAM_LINEUPS["현대모비스"]["head_coach"] == "양동근"

        # 4. Verify 2026-2027 real-world rosters across clubs
        # DB: Albano, Kang Sang-jae, Ellenson
        db_starters = [s["name"] for s in TEAM_LINEUPS["DB"]["starters"]]
        assert "이선 알바노" in db_starters
        assert "강상재" in db_starters
        assert "헨리 엘런슨" in db_starters

        # KT: Kim Sun-hyung, Oczon, Bass, Ha Yoon-gi
        kt_starters = [s["name"] for s in TEAM_LINEUPS["KT"]["starters"]]
        assert "김선형" in kt_starters
        assert "패리스 배스" in kt_starters
        assert "하윤기" in kt_starters

        # KCC: Heo Hoon & Heo Woong brother backcourt, Shawn Long, Jang Jae-seok
        kcc_starters = [s["name"] for s in TEAM_LINEUPS["KCC"]["starters"]]
        assert "허훈" in kcc_starters
        assert "허웅" in kcc_starters
        assert "숀 롱" in kcc_starters
        assert "장재석" in kcc_starters

        # 삼성: Lee Kwan-hee, Justin Gutang, Kerem Kanter
        samsung_starters = [s["name"] for s in TEAM_LINEUPS["삼성"]["starters"]]
        assert "이관희" in samsung_starters
        assert "케렘 칸터" in samsung_starters
        assert "저스틴 구탕" in samsung_starters

        # 한국가스공사: Belangel, Aluma, Kim Jun-il
        kogas_starters = [s["name"] for s in TEAM_LINEUPS["한국가스공사"]["starters"]]
        assert "샘조세프 벨란겔" in kogas_starters
        assert "케베 알루마" in kogas_starters

        # SK: Kim Sun-hyung must NOT be in SK starters; Kim Nak-hyun & Jameel Warney are in SK starters
        sk_starters = [s["name"] for s in TEAM_LINEUPS["SK"]["starters"]]
        assert "김선형" not in sk_starters
        assert "김낙현" in sk_starters
        assert "자밀 워니" in sk_starters

    def test_viral_share_buttons_on_cards(self) -> None:
        """Verify Kakao Skill 2.0 viral share buttons (action: 'share') on prediction/points, player, and lineup cards."""
        from apps.kakao.builder import (
            build_lineup_response,
            build_prediction_results_response,
            build_single_player_response,
            build_user_points_response,
        )

        # 1. User points card -> [📤 내 적중률 자랑하기]
        pts_resp = build_user_points_response(150, favorite_team="KT")
        pts_btns = pts_resp.template.outputs[0]["basicCard"]["buttons"]
        assert any(b.get("action") == "share" and b.get("label") == "📤 내 적중률 자랑하기" for b in pts_btns)

        # 2. Prediction results card -> [📤 내 적중률 자랑하기]
        pred_resp = build_prediction_results_response(
            results=[{
                "game_id": "80109231",
                "home_team": "한국가스공사",
                "away_team": "정관장",
                "user_pick": "정관장",
                "status": "FINAL",
                "score_text": "한국가스공사 71 : 77 정관장",
                "outcome_badge": "🎉 적중 성공!",
                "points_note": "+50P",
            }],
            stats={"hits": 1, "misses": 0, "pending": 0, "total": 1, "hit_rate": 100},
            user_points=200,
            favorite_team="정관장",
        )
        pred_cards = pred_resp.template.outputs[0]["carousel"]["items"]
        for c in pred_cards:
            assert any(b.get("action") == "share" and b.get("label") == "📤 내 적중률 자랑하기" for b in c["buttons"])

        # 3. Single player card -> [📤 선수 스탯 공유하기]
        player_resp = build_single_player_response(
            {"name": "이선 알바노", "team": "DB", "pos": "G", "no": "3", "pts": 15.8, "reb": 2.9, "ast": 6.4},
            is_favorite=True,
        )
        player_btns = player_resp.template.outputs[0]["basicCard"]["buttons"]
        assert any(b.get("action") == "share" and b.get("label") == "📤 선수 스탯 공유하기" for b in player_btns)

        # 4. Lineup card -> [📤 라인업 공유하기]
        lineup_resp = build_lineup_response([], favorite_team="DB", target_team="DB")
        lineup_cards = lineup_resp.template.outputs[0]["carousel"]["items"]
        assert any(b.get("action") == "share" and b.get("label") == "📤 라인업 공유하기" for b in lineup_cards[0]["buttons"])

        # 5. Game summary & witty commentary card -> [📤 한줄평 공유하기]
        from apps.kakao.builder import build_game_summary_response
        sample_games = [
            {
                "game_id": "80109231",
                "home_team": "한국가스공사",
                "away_team": "정관장",
                "home_score": 71,
                "away_score": 77,
                "status": "FINAL",
            }
        ]
        summary_win = build_game_summary_response(sample_games, target_team="정관장")
        item_card = summary_win.template.outputs[0]["itemCard"]
        commentary_card = summary_win.template.outputs[1]["basicCard"]
        assert "정관장 경기 요약" in item_card["head"]["title"]
        assert any(b.get("action") == "share" and b.get("label") == "📤 한줄평 공유하기" for b in item_card["buttons"])
        assert "촌철살인 한줄평" in commentary_card["title"]
        assert "정관장 시점 촌철살인 한줄평" in commentary_card["description"]
        assert any(b.get("action") == "share" and b.get("label") == "📤 한줄평 공유하기" for b in commentary_card["buttons"])

        # Losing team perspective ("가스공사 요약")
        summary_lose = build_game_summary_response(sample_games, target_team="한국가스공사")
        lose_commentary = summary_lose.template.outputs[1]["basicCard"]
        assert "한국가스공사 시점 촌철살인 한줄평" in lose_commentary["description"]

        # Team without recent finished game in list ("DB 요약")
        summary_fallback = build_game_summary_response(sample_games, target_team="DB")
        fb_item = summary_fallback.template.outputs[0]["itemCard"]
        fb_commentary = summary_fallback.template.outputs[1]["basicCard"]
        assert "DB 경기 요약" in fb_item["head"]["title"]
        assert "DB 촌철살인 한줄평" in fb_commentary["title"]
        assert any(b.get("action") == "share" and b.get("label") == "📤 한줄평 공유하기" for b in fb_commentary["buttons"])

        # 6. Lineup 2-column visual board image (matching Daum ?tab=lineup)
        from services.content.lineup_board import (
            get_baseline_starters_with_photos,
            render_lineup_board_png,
        )

        lineup_board_resp = build_lineup_response(
            sample_games,
            favorite_team="정관장",
            target_team="정관장",
            base_url="https://activity-lexmark-insert-styles.trycloudflare.com",
        )
        assert len(lineup_board_resp.template.outputs) == 1
        board_cards = lineup_board_resp.template.outputs[0]["carousel"]["items"]
        assert len(board_cards) == 1
        assert board_cards[0]["thumbnail"]["fixedRatio"] is True
        assert "/integrations/kakao/skills/lineup-image/team/" in board_cards[0]["thumbnail"]["imageUrl"]

        png_bytes = render_lineup_board_png(
            "한국가스공사",
            "정관장",
            get_baseline_starters_with_photos("한국가스공사"),
            get_baseline_starters_with_photos("정관장"),
        )
        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(png_bytes) > 5000



