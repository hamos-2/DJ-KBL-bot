"""Daum Sports KBL data provider with 3-tier fallback (ARMS API -> Hermes API -> Daum Search)."""

import re
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from core.exceptions import ProviderError
from core.logging import get_logger
from services.provider.interface import SportsDataProvider
from services.search.parser import normalize_team_name

logger = get_logger("provider.daum")

_KST = ZoneInfo("Asia/Seoul")

_DAUM_ARMS_BASE = "https://sports.daum.net/api/arms"
_DAUM_HERMES_BASE = "https://sports.daum.net/api/hermes"
_DAUM_SEARCH_URL = "https://search.daum.net/search"

_DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Referer": "https://sports.daum.net/schedule/kbl",
    "Accept": "application/json, text/plain, */*",
}

# Map Daum gameStatus values to internal canonical statuses
_DAUM_STATUS_MAP: dict[str, str] = {
    "BEFORE": "SCHEDULED",
    "DELAY": "SCHEDULED",
    "POSTPONE": "SCHEDULED",
    "CANCEL": "FINAL",
    "ING": "LIVE",
    "LIVE": "LIVE",
    "PLAY": "LIVE",
    "END": "FINAL",
    "FINAL": "FINAL",
}


class DaumSportsDataProvider(SportsDataProvider):
    """
    Fetches KBL schedule, live scores, and standings from Daum Sports.

    Implements a 3-tier fallback strategy:
        1. Tier 1: Daum Sports ARMS JSON API (``/api/arms/SPORTS_GAME_LIST``, ``SPORTS_GAME``)
        2. Tier 2: Daum Sports Hermes JSON API (``/api/hermes/game/list.json``)
        3. Tier 3: Daum Portal Search HTML parsing (``search.daum.net`` match ID extraction)
    """

    def __init__(
        self,
        timeout_seconds: float = 6.0,
        verify_ssl: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Initialise DaumSportsDataProvider.

        Args:
            timeout_seconds: HTTP request timeout in seconds.
            verify_ssl: Whether to verify TLS certificates (False avoids macOS local issuer issues).
            transport: Optional custom httpx.AsyncBaseTransport (for unit testing).
        """
        self._timeout = timeout_seconds
        self._verify_ssl = verify_ssl
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return a shared, connection-pooled httpx.AsyncClient configured with Daum headers."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                timeout=self._timeout,
                verify=self._verify_ssl,
                follow_redirects=True,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the shared HTTP client if open."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_schedule(
        self, for_date: date, team_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return KBL games scheduled on *for_date*.

        Args:
            for_date: Calendar date in KST.
            team_id: Optional canonical team filter (e.g. ``"KT"``).

        Returns:
            List of canonical game dicts.
        """
        return await self.get_schedule_range(for_date, for_date, team_id=team_id)

    async def get_schedule_range(
        self, start_date: date, end_date: date, team_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Fetch KBL games between *start_date* and *end_date* using Tier 1 -> Tier 2 fallback.

        Args:
            start_date: Inclusive start date (KST).
            end_date: Inclusive end date (KST).
            team_id: Optional canonical team filter.

        Returns:
            List of canonical game dicts sorted by start_time.
        """
        from_str = start_date.strftime("%Y%m%d")
        to_str = end_date.strftime("%Y%m%d")

        raw_list: list[dict[str, Any]] | None = None

        # Tier 1: Daum Sports ARMS API
        try:
            raw_list = await self._fetch_arms_game_list(from_str, to_str)
        except Exception as exc:
            logger.warning(
                "Tier 1 (Daum ARMS) schedule fetch failed, falling back to Tier 2 (Hermes)",
                from_date=from_str,
                to_date=to_str,
                error=str(exc),
            )

        # Tier 2: Daum Sports Hermes API
        if raw_list is None:
            try:
                raw_list = await self._fetch_hermes_game_list(from_str, to_str)
            except Exception as exc:
                logger.error(
                    "Tier 2 (Daum Hermes) schedule fetch failed",
                    from_date=from_str,
                    to_date=to_str,
                    error=str(exc),
                )
                raise ProviderError(f"Daum Sports schedule fetch failed: {exc}") from exc

        games = [self._to_canonical_game(item) for item in raw_list]
        if team_id:
            norm_team = normalize_team_name(team_id)
            games = [
                g for g in games if norm_team in (g["home_team"], g["away_team"])
            ]
        return games

    async def get_game(self, game_id: str) -> dict[str, Any]:
        """
        Fetch a single game by Daum *game_id* via ``/api/arms/SPORTS_GAME``.

        Args:
            game_id: Daum numeric gameId string (e.g. ``"80109251"``).

        Returns:
            Canonical game dict.
        """
        url = f"{_DAUM_ARMS_BASE}/SPORTS_GAME"
        params = {"gameId": str(game_id)}

        client = self._get_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"Failed to fetch game {game_id} from Daum: {exc}") from exc

        doc = (payload or {}).get("document")
        if not doc or not doc.get("gameId"):
            raise ProviderError(f"Game not found on Daum Sports: {game_id}")

        return self._to_canonical_game(doc)

    async def get_live_score(self, game_id: str) -> dict[str, Any]:
        """
        Return the latest live score for *game_id* from Daum Sports.

        Args:
            game_id: Daum numeric gameId string.

        Returns:
            Canonical live score dict.
        """
        return await self.get_game(game_id)

    async def get_standings(self, season: str) -> list[dict[str, Any]]:
        """
        Fetch KBL team standings from Daum Sports ``SPORTS_TEAM_RANK``.

        Args:
            season: Season key such as ``"20262027"`` or ``"2025-26"``.

        Returns:
            List of canonical standing dicts sorted by rank.
        """
        season_key = self._normalize_season_key(season)
        url = f"{_DAUM_ARMS_BASE}/SPORTS_TEAM_RANK"
        params = {"leagueCode": "kbl", "seasonKey": season_key}

        client = self._get_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            raise ProviderError(f"Failed to fetch standings from Daum: {exc}") from exc

        raw_list = ((payload or {}).get("document") or {}).get("list") or []
        standings: list[dict[str, Any]] = []
        for idx, item in enumerate(raw_list):
            rank_info = item.get("rank") or {}
            team_name = item.get("shortNameKo") or item.get("nameKo") or "?"
            standings.append(
                {
                    "rank": int(rank_info.get("rank") or (idx + 1)),
                    "team": normalize_team_name(team_name),
                    "wins": int(rank_info.get("win") or 0),
                    "losses": int(rank_info.get("loss") or 0),
                    "wpct": float(rank_info.get("wpct") or 0.0),
                    "gb": str(rank_info.get("gb") or "0.0"),
                    "streak": str(rank_info.get("streak") or "-"),
                    "season": season_key,
                }
            )
        if not standings:
            from services.content.kbl_data import compute_standings_from_games
            today_d = datetime.now(_KST).date()
            season_start = date(today_d.year if today_d.month >= 9 else today_d.year - 1, 10, 1)
            games = await self.get_schedule_range(season_start, today_d)
            standings = compute_standings_from_games(games)
        return standings

    async def get_news(
        self,
        team: str | None = None,
        recent_games: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch latest KBL news articles from Daum Search, enriched with recent game recaps.
        """
        from services.content.kbl_data import parse_daum_news_html
        query = f"프로농구 {team}" if team else "KBL 프로농구"
        params = {"w": "news", "q": query}
        client = self._get_client()
        try:
            resp = await client.get(_DAUM_SEARCH_URL, params=params)
            resp.raise_for_status()
            return parse_daum_news_html(resp.text, recent_games=recent_games, team=team)
        except Exception as exc:
            logger.warning("Failed to fetch Daum news, using fallback", error=str(exc))
            return parse_daum_news_html("", recent_games=recent_games, team=team)

    async def search_matchup_via_daum_portal(
        self, team_a: str, team_b: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Tier 3 fallback: search ``search.daum.net`` for ``"{team_a} vs {team_b} 프로농구"``,
        extract Daum Sports match IDs from the portal result page, and fetch match details.

        Args:
            team_a: First canonical KBL team name.
            team_b: Optional second canonical KBL team name.

        Returns:
            List of canonical game dicts discovered via Daum Search.
        """
        query = f"{team_a} vs {team_b} 프로농구" if team_b else f"{team_a} 프로농구 일정"
        params = {"w": "tot", "q": query}

        client = self._get_client()
        try:
            resp = await client.get(_DAUM_SEARCH_URL, params=params)
            resp.raise_for_status()
            html = resp.text
        except Exception as exc:
            raise ProviderError(f"Daum portal search failed: {exc}") from exc

        match_ids = list(dict.fromkeys(re.findall(r"sports\.daum\.net/match/(\d+)", html)))
        results: list[dict[str, Any]] = []
        for mid in match_ids[:3]:
            try:
                game = await self.get_game(mid)
                results.append(game)
            except ProviderError:
                continue
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_arms_game_list(
        self, from_date: str, to_date: str
    ) -> list[dict[str, Any]]:
        """Fetch raw game list from Tier 1 ``/api/arms/SPORTS_GAME_LIST``."""
        url = f"{_DAUM_ARMS_BASE}/SPORTS_GAME_LIST"
        params = {
            "leagueCode": "kbl",
            "fromDate": from_date,
            "toDate": to_date,
            "pageSize": "200",
        }
        client = self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

        doc = (payload or {}).get("document") or {}
        return doc.get("list") or []

    async def _fetch_hermes_game_list(
        self, from_date: str, to_date: str
    ) -> list[dict[str, Any]]:
        """Fetch raw game list from Tier 2 ``/api/hermes/game/list.json``."""
        url = f"{_DAUM_HERMES_BASE}/game/list.json"
        params = {
            "leagueCode": "kbl",
            "fromDate": from_date,
            "toDate": to_date,
        }
        client = self._get_client()
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

        return (payload or {}).get("list") or []

    @classmethod
    def _to_canonical_game(cls, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a Daum Sports game object into the internal Canonical Game dict."""
        game_id = str(raw.get("gameId", ""))
        daum_status = str(raw.get("gameStatus") or "BEFORE").upper()
        status = _DAUM_STATUS_MAP.get(daum_status, "SCHEDULED")

        home_obj = raw.get("home") or {}
        away_obj = raw.get("away") or {}
        home_team_obj = home_obj.get("team") or {}
        away_team_obj = away_obj.get("team") or {}

        home_raw_name = (
            home_team_obj.get("shortNameKo")
            or home_team_obj.get("nameKo")
            or "홈팀"
        )
        away_raw_name = (
            away_team_obj.get("shortNameKo")
            or away_team_obj.get("nameKo")
            or "원정팀"
        )

        home_team = normalize_team_name(home_raw_name)
        away_team = normalize_team_name(away_raw_name)

        home_score = cls._parse_score(home_obj.get("result"), raw.get("homeScore"), status)
        away_score = cls._parse_score(away_obj.get("result"), raw.get("awayScore"), status)

        period = cls._parse_period(raw.get("periodType"), status)
        game_clock = str(raw.get("gameDetailStatus") or ("00:00" if status == "FINAL" else ""))

        field_obj = raw.get("field") or {}
        arena = (
            field_obj.get("shortNameKo")
            or field_obj.get("nameKo")
            or field_obj.get("name")
            or None
        )

        start_time_utc = cls._parse_start_time(
            str(raw.get("startDate") or ""),
            str(raw.get("startTime") or "0000"),
        )
        game_url = raw.get("gameUrl") or (
            f"https://sports.daum.net/match/{game_id}" if game_id else None
        )

        return {
            "game_id": game_id,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "period": period,
            "game_clock": game_clock or None,
            "arena": arena,
            "game_url": game_url,
            "status": status,
            "start_time": start_time_utc.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _parse_score(
        result_str: Any, score_obj: dict[str, Any] | None, status: str
    ) -> int | None:
        """Extract integer score from Daum result string or score breakdown object."""
        if status == "SCHEDULED":
            return None
        if result_str is not None and str(result_str).strip().isdigit():
            return int(str(result_str).strip())
        if isinstance(score_obj, dict) and score_obj.get("total") is not None:
            try:
                return int(score_obj["total"])
            except (ValueError, TypeError):
                return None
        return 0 if status == "LIVE" else None

    @staticmethod
    def _parse_period(period_type: Any, status: str) -> int | None:
        """Convert Daum periodType (e.g. 'Q1'..'Q4', 'END') to integer period."""
        if status == "SCHEDULED":
            return None
        if status == "FINAL":
            return 4
        if not period_type:
            return 1
        digits = re.findall(r"\d+", str(period_type))
        if digits:
            return int(digits[0])
        return 4 if str(period_type).upper() == "END" else 1

    @staticmethod
    def _parse_start_time(start_date: str, start_time: str) -> datetime:
        """Parse Daum ``YYYYMMDD`` + ``HHMM`` in KST and convert to UTC datetime."""
        digits_date = re.sub(r"\D", "", start_date)
        digits_time = re.sub(r"\D", "", start_time).ljust(4, "0")[:4]
        if len(digits_date) == 8:
            try:
                dt_kst = datetime(
                    int(digits_date[:4]),
                    int(digits_date[4:6]),
                    int(digits_date[6:8]),
                    int(digits_time[:2]),
                    int(digits_time[2:4]),
                    tzinfo=_KST,
                )
                return dt_kst.astimezone(UTC)
            except ValueError:
                pass
        return datetime.now(UTC)

    @staticmethod
    def _normalize_season_key(season: str) -> str:
        """Convert ``'2026-27'`` or ``'2024-25'`` to Daum 8-digit ``'20262027'``."""
        digits = re.sub(r"\D", "", season)
        if len(digits) == 8:
            return digits
        if len(digits) == 6:
            # e.g. "202425" -> "20242025"
            return f"{digits[:4]}20{digits[4:]}"
        if len(digits) == 4:
            year = int(digits)
            return f"{year}{year + 1}"
        return "20262027"
