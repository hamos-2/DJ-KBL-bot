"""Unit and integration tests for DaumSportsDataProvider, MatchupQuery parser, and Kakao Rule 3."""

from datetime import date
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.kakao.builder import build_matchup_search_response
from main import app
from services.provider.daum import DaumSportsDataProvider
from services.search.parser import (
    MatchupQuery,
    normalize_team_name,
    parse_matchup_query,
)


class TestSearchParser:
    """Tests for KBL team normalization and '#KT vs LG' query parsing."""

    def test_normalize_daum_team_names(self) -> None:
        """Daum Sports full/short team names must normalize to canonical KBL codes."""
        assert normalize_team_name("수원 KT 소닉붐") == "KT"
        assert normalize_team_name("창원 LG 세이커스") == "LG"
        assert normalize_team_name("안양 정관장 레드부스터스") == "정관장"
        assert normalize_team_name("고양 소노 스카이거너스") == "소노"
        assert normalize_team_name("울산 현대모비스") == "현대모비스"
        assert normalize_team_name("대구 한국가스공사") == "한국가스공사"

    def test_parse_hashtag_vs_query(self) -> None:
        """'#KT vs LG' must parse into head-to-head MatchupQuery(team_a='KT', team_b='LG')."""
        q = parse_matchup_query("#KT vs LG")
        assert q is not None
        assert q.team_a == "KT"
        assert q.team_b == "LG"
        assert q.is_head_to_head is True

    def test_parse_compact_korean_query(self) -> None:
        """Compact Korean query without spaces around vs must still parse both teams."""
        q = parse_matchup_query("#정관장vs소노 경기일정")
        assert q is not None
        assert q.team_a == "정관장"
        assert q.team_b == "소노"
        assert q.is_head_to_head is True

    def test_parse_single_team_query(self) -> None:
        """Single team hashtag query '#모비스' must parse with team_b=None."""
        q = parse_matchup_query("#모비스")
        assert q is not None
        assert q.team_a == "현대모비스"
        assert q.team_b is None
        assert q.is_head_to_head is False

    def test_parse_unknown_query_returns_none(self) -> None:
        """Unrelated text with no KBL team names must return None."""
        assert parse_matchup_query("오늘 날씨 어때") is None
        assert parse_matchup_query("") is None


class TestDaumSportsProviderMocked:
    """Tests for DaumSportsDataProvider 3-tier fallback and canonical mapping."""

    @pytest.mark.asyncio
    async def test_canonical_conversion_from_arms_api(self) -> None:
        """Tier 1 ARMS API payload must convert cleanly to canonical game format."""
        sample_arms_payload: dict[str, Any] = {
            "code": 200,
            "document": {
                "list": [
                    {
                        "gameId": 80109251,
                        "startDate": "20261115",
                        "startTime": "1630",
                        "periodType": "BEFORE",
                        "gameStatus": "BEFORE",
                        "field": {"shortNameKo": "창원체육관"},
                        "home": {
                            "result": None,
                            "team": {"shortNameKo": "창원 LG"},
                        },
                        "away": {
                            "result": None,
                            "team": {"shortNameKo": "수원 KT"},
                        },
                        "gameUrl": "https://sports.daum.net/match/80109251",
                    }
                ]
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=sample_arms_payload)

        transport = httpx.MockTransport(handler)
        provider = DaumSportsDataProvider(transport=transport)
        games = await provider.get_schedule(date(2026, 11, 15))

        assert len(games) == 1
        g = games[0]
        assert g["game_id"] == "80109251"
        assert g["home_team"] == "LG"
        assert g["away_team"] == "KT"
        assert g["status"] == "SCHEDULED"
        assert g["arena"] == "창원체육관"
        assert g["game_url"] == "https://sports.daum.net/match/80109251"

    @pytest.mark.asyncio
    async def test_tier1_failure_falls_back_to_tier2_hermes(self) -> None:
        """When Tier 1 ARMS fails (500), provider must fall back to Tier 2 Hermes API."""
        hermes_payload: dict[str, Any] = {
            "list": [
                {
                    "gameId": 80109217,
                    "startDate": "20261025",
                    "startTime": "1400",
                    "periodType": "END",
                    "gameStatus": "END",
                    "field": {"shortNameKo": "잠실학생체육관"},
                    "home": {"result": "79", "team": {"shortNameKo": "서울 SK"}},
                    "away": {"result": "75", "team": {"shortNameKo": "수원 KT"}},
                }
            ]
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if "SPORTS_GAME_LIST" in str(request.url):
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(200, json=hermes_payload)

        transport = httpx.MockTransport(handler)
        provider = DaumSportsDataProvider(transport=transport)

        games = await provider.get_schedule(date(2026, 10, 25))
        assert len(games) == 1
        assert games[0]["game_id"] == "80109217"
        assert games[0]["status"] == "FINAL"
        assert games[0]["home_score"] == 79
        assert games[0]["away_score"] == 75

    @pytest.mark.asyncio
    async def test_tier3_daum_portal_search_extracts_match_id(self) -> None:
        """Tier 3 search must extract sports.daum.net/match/{id} from HTML and fetch the game."""
        fake_html = '<html><body><a href="https://sports.daum.net/match/80109251">KT vs LG</a></body></html>'
        fake_game_doc = {
            "code": 200,
            "document": {
                "gameId": 80109251,
                "startDate": "20261115",
                "startTime": "1630",
                "gameStatus": "BEFORE",
                "field": {"shortNameKo": "창원체육관"},
                "home": {"result": None, "team": {"shortNameKo": "창원 LG"}},
                "away": {"result": None, "team": {"shortNameKo": "수원 KT"}},
            },
        }

        def handler(request: httpx.Request) -> httpx.Response:
            if "search.daum.net" in str(request.url):
                return httpx.Response(200, text=fake_html)
            return httpx.Response(200, json=fake_game_doc)

        transport = httpx.MockTransport(handler)
        provider = DaumSportsDataProvider(transport=transport)

        results = await provider.search_matchup_via_daum_portal("KT", "LG")
        assert len(results) == 1
        assert results[0]["game_id"] == "80109251"
        assert {results[0]["home_team"], results[0]["away_team"]} == {"KT", "LG"}

    @pytest.mark.asyncio
    async def test_daum_search_standings_and_player_rankings_parsing(self) -> None:
        """Daum Search portal HTML must be parsed into 10-team standings and 5 player leaderboards."""
        from services.provider.daum import parse_daum_standings_and_rankings

        fake_standings_html = """
        <table>
            <tr><th>순위</th><th>경기</th><th>승</th><th>패</th><th>승차</th><th>승률</th></tr>
            <tr><td>1   서울 삼성</td><td>9</td><td>9</td><td>0</td><td>0.0</td><td>1.0</td></tr>
            <tr><td>2   서울 SK</td><td>5</td><td>4</td><td>1</td><td>3.0</td><td>0.8</td></tr>
            <tr><td>3   안양 정관장</td><td>10</td><td>6</td><td>4</td><td>3.5</td><td>0.6</td></tr>
            <tr><td>4   대구 한국가스공사</td><td>10</td><td>5</td><td>5</td><td>4.5</td><td>0.5</td></tr>
            <tr><td>4   원주 DB</td><td>10</td><td>5</td><td>5</td><td>4.5</td><td>0.5</td></tr>
            <tr><td>6   창원 LG</td><td>9</td><td>4</td><td>5</td><td>5.0</td><td>0.444</td></tr>
            <tr><td>7   고양 소노</td><td>10</td><td>4</td><td>6</td><td>5.5</td><td>0.4</td></tr>
            <tr><td>7   수원 KT</td><td>10</td><td>4</td><td>6</td><td>5.5</td><td>0.4</td></tr>
            <tr><td>9   울산 현대모비스</td><td>10</td><td>3</td><td>7</td><td>6.5</td><td>0.3</td></tr>
            <tr><td>10   부산 KCC</td><td>11</td><td>3</td><td>8</td><td>7.0</td><td>0.273</td></tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr>
                <td><strong class="rank_num">1</strong><span class="txt_ellip">케렘 칸터</span><span class="team_name txt_ellip">서울 삼성</span></td>
                <td>26.8</td><td>2.7</td><td>0.3</td><td>10.7</td><td>1.0</td>
            </tr>
            <tr>
                <td><strong class="rank_num">2</strong><span class="txt_ellip">패리스 배스</span><span class="team_name txt_ellip">수원 KT</span></td>
                <td>26.3</td><td>4.2</td><td>1.0</td><td>9.7</td><td>0.9</td>
            </tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr>
                <td><strong class="rank_num">1</strong><span class="txt_ellip">허훈</span><span class="team_name txt_ellip">부산 KCC</span></td>
                <td>15.5</td><td>8.5</td><td>0.0</td><td>2.7</td><td>0.6</td>
            </tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr>
                <td><strong class="rank_num">1</strong><span class="txt_ellip">다리우스 베즐리</span><span class="team_name txt_ellip">울산 현대모비스</span></td>
                <td>21.6</td><td>4.3</td><td>2.0</td><td>9.9</td><td>1.6</td>
            </tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr>
                <td><strong class="rank_num">1</strong><span class="txt_ellip">아셈 마레이</span><span class="team_name txt_ellip">창원 LG</span></td>
                <td>15.1</td><td>6.8</td><td>0.2</td><td>14.2</td><td>0.8</td>
            </tr>
            <tr>
                <td><strong class="rank_num">3</strong><span class="txt_ellip">존 무니</span><span class="team_name txt_ellip"></span></td>
                <td>20.6</td><td>3.6</td><td>0.7</td><td>12.9</td><td>1.1</td>
            </tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr>
                <td><strong class="rank_num">1</strong><span class="txt_ellip">안영준</span><span class="team_name txt_ellip">서울 SK</span></td>
                <td>17.8</td><td>3.6</td><td>0.6</td><td>5.2</td><td>3.2</td>
            </tr>
        </table>
        """

        standings, player_ranks = parse_daum_standings_and_rankings(fake_standings_html)
        assert len(standings) == 10
        assert standings[0]["team"] == "삼성"
        assert standings[0]["rank"] == 1
        assert standings[0]["wins"] == 9
        assert standings[0]["losses"] == 0
        assert standings[0]["wpct"] == 1.0

        assert len(player_ranks["pts"]) == 2
        assert player_ranks["pts"][0]["name"] == "케렘 칸터"
        assert player_ranks["pts"][0]["team"] == "삼성"
        assert player_ranks["pts"][0]["value"] == 26.8

        assert player_ranks["ast"][0]["name"] == "허훈"
        assert player_ranks["ast"][0]["team"] == "KCC"
        assert player_ranks["ast"][0]["value"] == 8.5

        assert player_ranks["blk"][0]["name"] == "다리우스 베즐리"
        assert player_ranks["blk"][0]["value"] == 2.0

        assert player_ranks["reb"][0]["name"] == "아셈 마레이"
        assert player_ranks["reb"][0]["value"] == 14.2
        # Verify John Mooney fallback team mapping
        assert player_ranks["reb"][1]["name"] == "존 무니"
        assert player_ranks["reb"][1]["team"] == "정관장"

        assert player_ranks["stl"][0]["name"] == "안영준"
        assert player_ranks["stl"][0]["value"] == 3.2

    @pytest.mark.asyncio
    async def test_daum_provider_get_standings_and_rankings(self) -> None:
        """Provider get_standings and get_player_rankings must fetch via Daum search portal."""
        fake_search_html = """
        <table>
            <tr><th>순위</th><th>경기</th><th>승</th><th>패</th><th>승차</th><th>승률</th></tr>
            <tr><td>1 서울 삼성</td><td>9</td><td>9</td><td>0</td><td>0.0</td><td>1.0</td></tr>
            <tr><td>2 서울 SK</td><td>5</td><td>4</td><td>1</td><td>3.0</td><td>0.8</td></tr>
            <tr><td>3 안양 정관장</td><td>10</td><td>6</td><td>4</td><td>3.5</td><td>0.6</td></tr>
            <tr><td>4 대구 한국가스공사</td><td>10</td><td>5</td><td>5</td><td>4.5</td><td>0.5</td></tr>
            <tr><td>4 원주 DB</td><td>10</td><td>5</td><td>5</td><td>4.5</td><td>0.5</td></tr>
            <tr><td>6 창원 LG</td><td>9</td><td>4</td><td>5</td><td>5.0</td><td>0.444</td></tr>
            <tr><td>7 고양 소노</td><td>10</td><td>4</td><td>6</td><td>5.5</td><td>0.4</td></tr>
            <tr><td>7 수원 KT</td><td>10</td><td>4</td><td>6</td><td>5.5</td><td>0.4</td></tr>
            <tr><td>9 울산 현대모비스</td><td>10</td><td>3</td><td>7</td><td>6.5</td><td>0.3</td></tr>
            <tr><td>10 부산 KCC</td><td>11</td><td>3</td><td>8</td><td>7.0</td><td>0.273</td></tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr><td><strong class="rank_num">1</strong><span class="txt_ellip">케렘 칸터</span><span class="team_name txt_ellip">삼성</span></td><td>26.8</td><td>2.7</td><td>0.3</td><td>10.7</td><td>1.0</td></tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr><td><strong class="rank_num">1</strong><span class="txt_ellip">허훈</span><span class="team_name txt_ellip">KCC</span></td><td>15.5</td><td>8.5</td><td>0.0</td><td>2.7</td><td>0.6</td></tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr><td><strong class="rank_num">1</strong><span class="txt_ellip">다리우스 베즐리</span><span class="team_name txt_ellip">현대모비스</span></td><td>21.6</td><td>4.3</td><td>2.0</td><td>9.9</td><td>1.6</td></tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr><td><strong class="rank_num">1</strong><span class="txt_ellip">아셈 마레이</span><span class="team_name txt_ellip">LG</span></td><td>15.1</td><td>6.8</td><td>0.2</td><td>14.2</td><td>0.8</td></tr>
        </table>
        <table>
            <tr><th>순위</th><th>득점</th><th>도움</th><th>블록슛</th><th>리바운드</th><th>스틸</th></tr>
            <tr><td><strong class="rank_num">1</strong><span class="txt_ellip">안영준</span><span class="team_name txt_ellip">SK</span></td><td>17.8</td><td>3.6</td><td>0.6</td><td>5.2</td><td>3.2</td></tr>
        </table>
        """
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=fake_search_html)

        transport = httpx.MockTransport(handler)
        provider = DaumSportsDataProvider(transport=transport)

        standings = await provider.get_standings("2026-27")
        assert len(standings) == 10
        assert standings[0]["team"] == "삼성"
        assert standings[0]["rank"] == 1

        rankings = await provider.get_player_rankings()
        assert "pts" in rankings
        assert rankings["pts"][0]["name"] == "케렘 칸터"
        assert rankings["ast"][0]["name"] == "허훈"


class TestMatchupBuilderAndKakaoRule3:
    """Tests for matchup response builder and Kakao Always-200 validation guard."""

    def test_build_matchup_search_response_formats_game(self) -> None:
        """Matchup response must include team names, arena, KST date/time, and Daum URL."""
        query = MatchupQuery(raw_query="#KT vs LG", team_a="KT", team_b="LG")
        games = [
            {
                "game_id": "80109251",
                "home_team": "LG",
                "away_team": "KT",
                "status": "SCHEDULED",
                "arena": "창원체육관",
                "game_url": "https://sports.daum.net/match/80109251",
                "start_time": "2026-11-15T07:30:00+00:00",  # 16:30 KST
            }
        ]
        resp = build_matchup_search_response(query, games)
        card = resp.template.outputs[0]["listCard"]
        assert "KT vs LG" in card["header"]["title"]
        assert len(card["items"]) == 1
        assert "창원" in card["items"][0]["description"]
        assert "https://sports.daum.net/match/80109251" in card["items"][0]["link"]["web"]

    def test_kakao_validation_error_returns_http_200(self) -> None:
        """Invalid Kakao Skill payload must still return HTTP 200 OK (Rule 3)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/integrations/kakao/skills/today-games",
            json={"invalid_payload": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["version"] == "2.0"
        assert "outputs" in body["template"]

    @pytest.mark.asyncio
    async def test_worker_transition_to_final_triggers_cache_invalidation(self) -> None:
        """When IngestionWorker detects a game transitioning to FINAL, standings/rankings cache is invalidated."""
        from unittest.mock import AsyncMock, patch
        from services.ingestion.worker import IngestionWorker

        mock_provider = AsyncMock()
        worker = IngestionWorker(provider=mock_provider, persist_db=False)
        worker._last_status["TEST-G01"] = "LIVE"

        with patch("services.ingestion.worker.invalidate_standings_and_rankings_cache", new_callable=AsyncMock) as mock_invalidate:
            await worker._detect_transition("TEST-G01", {"status": "FINAL", "home_team": "SK", "away_team": "KT"})
            mock_invalidate.assert_awaited_once()
            assert worker._last_status["TEST-G01"] == "FINAL"


class TestSeasonAwareSearch:
    """Verify that search queries prioritize the 2026-2027 season and automatically adapt."""

    @pytest.mark.asyncio
    async def test_search_queries_include_season_prefix(self) -> None:
        """Search requests to Daum must include the full 4-digit season string (2026-2027)."""
        requested_queries: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            q = request.url.params.get("q", "")
            requested_queries.append(q)
            # Minimal HTML with 10 standings to satisfy parser
            dummy_html = "<table><tr><th>순위</th><th>경기</th><th>승</th><th>패</th><th>승차</th><th>승률</th></tr>"
            for i in range(1, 11):
                dummy_html += f"<tr><td>{i} 팀{i}</td><td>10</td><td>5</td><td>5</td><td>0.0</td><td>0.500</td></tr>"
            dummy_html += "</table>"
            return httpx.Response(200, text=dummy_html)

        transport = httpx.MockTransport(handler)
        provider = DaumSportsDataProvider(transport=transport)

        # 1. Standings search without season argument -> must search "2026-2027 KBL 순위"
        standings = await provider.get_standings()
        assert len(standings) == 10
        assert any("2026-2027 KBL 순위" in q for q in requested_queries)
        assert standings[0]["season"] == "2026-27"

        # 2. Player rankings search -> must search "2026-2027 KBL 순위"
        requested_queries.clear()
        await provider.get_player_rankings()
        assert any("2026-2027 KBL 순위" in q for q in requested_queries)

        # 3. News search -> must search "2026-2027 KBL 프로농구"
        requested_queries.clear()
        await provider.get_news()
        assert any("2026-2027 KBL 프로농구" in q for q in requested_queries)

        # 4. Club news search -> must search "2026-2027 프로농구 SK"
        requested_queries.clear()
        await provider.get_news(team="SK")
        assert any("2026-2027 프로농구 SK" in q for q in requested_queries)
