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


# Known team mappings for players whose club tag might be missing in Daum search HTML
KNOWN_PLAYER_TEAMS: dict[str, str] = {
    "존 무니": "정관장",
    "존무니": "정관장",
}


def parse_daum_standings_and_rankings(
    html_content: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """
    Parse official KBL 10-team standings and player leaderboards from Daum Search HTML.

    Tables structure on Daum Search (https://search.daum.net/search?w=tot&q=KBL+순위):
        - Table 0: 10-Team Standings (순위, 경기, 승, 패, 승차, 승률)
        - Table 1: PTS 득점 순위
        - Table 2: AST 도움 순위
        - Table 3: BLK 블록슛 순위
        - Table 4: REB 리바운드 순위
        - Table 5: STL 스틸 순위
    """
    tables = re.findall(r"<table[^>]*>.*?</table>", html_content, re.DOTALL)
    standings: list[dict[str, Any]] = []
    player_rankings: dict[str, list[dict[str, Any]]] = {}

    if tables:
        # Table 0: Team Standings
        rows = re.findall(r"<tr[^>]*>.*?</tr>", tables[0], re.DOTALL)[1:]
        for idx, r in enumerate(rows):
            cols = [
                re.sub(r"<[^>]+>", "", c).strip()
                for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", r, re.DOTALL)
            ]
            if not cols:
                continue
            rank_m = re.search(r"^\s*(\d+)\s+(.+)$", cols[0])
            rank = int(rank_m.group(1)) if rank_m else idx + 1
            raw_team = rank_m.group(2) if rank_m else cols[0]
            team = normalize_team_name(raw_team)
            games_cnt = int(cols[1]) if len(cols) > 1 and cols[1].isdigit() else 0
            wins = int(cols[2]) if len(cols) > 2 and cols[2].isdigit() else 0
            losses = int(cols[3]) if len(cols) > 3 and cols[3].isdigit() else 0
            gb = cols[4] if len(cols) > 4 else "0.0"
            wpct = (
                float(cols[5])
                if len(cols) > 5 and cols[5].replace(".", "", 1).isdigit()
                else round(wins / max(1, games_cnt), 3)
            )
            standings.append(
                {
                    "rank": rank,
                    "team": team,
                    "games": games_cnt,
                    "wins": wins,
                    "losses": losses,
                    "gb": gb,
                    "wpct": wpct,
                    "streak": "-",
                    "season": "2026-27",
                }
            )

    # Tables 1..5: Player category leaderboards
    cat_keys = ["pts", "ast", "blk", "reb", "stl"]
    for cat_idx, cat in enumerate(cat_keys):
        if len(tables) <= cat_idx + 1:
            break
        table = tables[cat_idx + 1]
        rows = re.findall(r"<tr[^>]*>.*?</tr>", table, re.DOTALL)[1:]
        cat_list: list[dict[str, Any]] = []
        for r in rows:
            tds = re.findall(r"<t[dh][^>]*>.*?</t[dh]>", r, re.DOTALL)
            if not tds:
                continue
            first_td = tds[0]
            rank_m = re.search(r'class="rank_num[^"]*">(\d+)</strong>', first_td)
            rank = int(rank_m.group(1)) if rank_m else len(cat_list) + 1
            name_m = re.search(r'<span class="txt_ellip">([^<]+)</span>', first_td)
            name = name_m.group(1).strip() if name_m else "?"
            team_m = re.search(r'<span class="team_name txt_ellip">([^<]+)</span>', first_td)
            raw_team = team_m.group(1).strip() if team_m else ""
            if not raw_team and name in KNOWN_PLAYER_TEAMS:
                raw_team = KNOWN_PLAYER_TEAMS[name]
            team = normalize_team_name(raw_team) if raw_team else "?"

            def _to_float(td_str: str) -> float:
                txt = re.sub(r"<[^>]+>", "", td_str).strip()
                try:
                    return float(txt)
                except ValueError:
                    return 0.0

            pts = _to_float(tds[1]) if len(tds) > 1 else 0.0
            ast = _to_float(tds[2]) if len(tds) > 2 else 0.0
            blk = _to_float(tds[3]) if len(tds) > 3 else 0.0
            reb = _to_float(tds[4]) if len(tds) > 4 else 0.0
            stl = _to_float(tds[5]) if len(tds) > 5 else 0.0

            val_map = {"pts": pts, "ast": ast, "blk": blk, "reb": reb, "stl": stl}
            cat_list.append(
                {
                    "rank": rank,
                    "name": name,
                    "team": team,
                    "pos": "F" if cat in ("reb", "blk") else ("G" if cat in ("ast", "stl") else "G/F"),
                    "value": val_map[cat],
                    "pts": pts,
                    "ast": ast,
                    "reb": reb,
                    "stl": stl,
                    "blk": blk,
                }
            )
        player_rankings[cat] = cat_list

    return standings, player_rankings


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
        timeout_seconds: float = 2.5,
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
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0),
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

    async def get_standings(self, season: str = "2026-27") -> list[dict[str, Any]]:
        """
        Fetch official KBL 10-team standings from Daum Search.
        Falls back to Daum ARMS ``SPORTS_TEAM_RANK``, then ``compute_standings_from_games``.
        """
        # Tier 1: Real-time official KBL standings from Daum Search portal
        client = self._get_client()
        try:
            params = {"w": "tot", "q": "KBL 순위"}
            resp = await client.get(_DAUM_SEARCH_URL, params=params)
            if resp.status_code == 200:
                standings, rankings = parse_daum_standings_and_rankings(resp.text)
                if len(standings) >= 10:
                    if rankings:
                        try:
                            from core.cache.redis import save_player_rankings_cache
                            await save_player_rankings_cache(rankings)
                        except Exception:
                            pass
                    return standings
        except Exception as exc:
            logger.warning("Failed to fetch standings from Daum search, falling back to ARMS", error=str(exc))

        # Tier 2: Daum ARMS JSON API
        season_key = self._normalize_season_key(season)
        url = f"{_DAUM_ARMS_BASE}/SPORTS_TEAM_RANK"
        params = {"leagueCode": "kbl", "seasonKey": season_key}

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            raw_list = ((payload or {}).get("document") or {}).get("list") or []
            standings = []
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
            if standings:
                return standings
        except Exception as exc:
            logger.warning("Failed to fetch standings from Daum ARMS, falling back to games", error=str(exc))

        # Tier 3: Compute from finished games
        from services.content.kbl_data import compute_standings_from_games
        today_d = datetime.now(_KST).date()
        season_start = date(today_d.year if today_d.month >= 9 else today_d.year - 1, 10, 1)
        games = await self.get_schedule_range(season_start, today_d)
        return compute_standings_from_games(games)

    async def get_player_rankings(self) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch real-time official KBL player rankings (PTS, AST, BLK, REB, STL) from Daum Search.
        """
        client = self._get_client()
        try:
            params = {"w": "tot", "q": "KBL 순위"}
            resp = await client.get(_DAUM_SEARCH_URL, params=params)
            if resp.status_code == 200:
                _, rankings = parse_daum_standings_and_rankings(resp.text)
                if rankings and any(rankings.values()):
                    return rankings
        except Exception as exc:
            logger.warning("Failed to fetch player rankings from Daum search, using defaults", error=str(exc))

        from services.content.kbl_data import get_default_player_rankings
        return get_default_player_rankings()

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

        home_quarters = cls._parse_quarters(raw.get("homeScore"))
        away_quarters = cls._parse_quarters(raw.get("awayScore"))

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
            "home_quarters": home_quarters,
            "away_quarters": away_quarters,
            "period": period,
            "game_clock": game_clock or None,
            "arena": arena,
            "game_url": game_url,
            "status": status,
            "start_time": start_time_utc.isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _parse_quarters(score_obj: dict[str, Any] | None) -> list[int]:
        """Extract list of quarter scores [q1, q2, q3, q4, (optional extra)] from Daum score breakdown."""
        if not isinstance(score_obj, dict):
            return []
        quarters = []
        for k in ("quarter1", "quarter2", "quarter3", "quarter4"):
            v = score_obj.get(k)
            quarters.append(int(v) if v is not None and str(v).isdigit() else 0)
        extra_val = score_obj.get("extra")
        if extra_val is not None and str(extra_val).isdigit() and int(extra_val) > 0:
            quarters.append(int(extra_val))
        return quarters

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
        """Convert Daum periodType (e.g. 'Q1'..'Q4', 'OT1', 'END') to integer period."""
        if status == "SCHEDULED":
            return None
        if status == "FINAL":
            return 4
        if not period_type:
            return 1
        pt = str(period_type).upper().strip()
        if "OT" in pt or "연장" in pt or "EXTRA" in pt:
            digits = re.findall(r"\d+", pt)
            ot_num = int(digits[0]) if digits else 1
            return 4 + ot_num
        digits = re.findall(r"\d+", pt)
        if digits:
            return int(digits[0])
        return 4 if pt == "END" else 1

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
