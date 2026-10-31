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
        text = resp.template.outputs[0]["simpleText"]["text"]
        assert "KT vs LG" in text
        assert "창원체육관" in text
        assert "11/15(일) 16:30" in text
        assert "https://sports.daum.net/match/80109251" in text

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
