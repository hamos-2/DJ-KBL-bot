"""Mock sports data provider for development and unit testing."""

import random
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from core.exceptions import ProviderError
from core.logging import get_logger
from services.provider.interface import SportsDataProvider

logger = get_logger("provider.mock")

_KST = ZoneInfo("Asia/Seoul")

_KBL_TEAMS: list[str] = [
    "SK", "KT", "KCC", "삼성", "LG", "현대모비스", "정관장", "DB", "한국가스공사", "소노"
]

_LIVE_GAME_ID = "MOCK-LIVE-001"
_SCHEDULED_GAME_ID = "MOCK-SCHED-001"
_FINAL_GAME_ID = "MOCK-FINAL-001"
_UPCOMING_KT_LG_ID = "MOCK-SCHED-KT-LG"


class MockSportsDataProvider(SportsDataProvider):
    """Deterministic mock provider that simulates live game progression and transitions."""

    def __init__(self) -> None:
        self._live_period: int = 1
        self._live_home_score: int = 0
        self._live_away_score: int = 0
        self._live_clock_seconds: int = 600  # 10:00
        self._live_status: str = "LIVE"
        self._tick_count: int = 0

    def _tick_live_game(self) -> None:
        """Advance the simulated live game state by one polling tick."""
        if self._live_status == "FINAL":
            return

        self._tick_count += 1
        self._live_clock_seconds = max(0, self._live_clock_seconds - random.randint(5, 15))

        if random.random() < 0.4:
            self._live_home_score += random.choice([1, 2, 3])
        if random.random() < 0.35:
            self._live_away_score += random.choice([1, 2, 3])

        # Advance period every 20 ticks or when clock reaches 0
        if (self._tick_count % 20 == 0 or self._live_clock_seconds == 0) and self._live_period < 4:
            self._live_period += 1
            self._live_clock_seconds = 600
            logger.info(
                "Mock game period advanced",
                game_id=_LIVE_GAME_ID,
                period=self._live_period,
            )
        elif self._live_period == 4 and self._live_clock_seconds == 0:
            # Ensure non-tie at end of 4Q and transition to FINAL
            if self._live_home_score == self._live_away_score:
                self._live_home_score += 2
            self._live_status = "FINAL"
            logger.info("Mock game finished", game_id=_LIVE_GAME_ID)

    @staticmethod
    def _format_clock(seconds: int) -> str:
        """Format *seconds* as MM:SS."""
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    async def get_schedule(
        self, for_date: date, team_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return a mock schedule containing three games (LIVE, SCHEDULED, FINAL).

        Args:
            for_date: Target calendar date (KST).
            team_id: Optional team filter.

        Returns:
            List of canonical game dicts.
        """
        day_start_kst = datetime.combine(for_date, datetime.min.time(), tzinfo=_KST)
        now_iso = datetime.now(UTC).isoformat()

        games: list[dict[str, Any]] = [
            {
                "game_id": _LIVE_GAME_ID,
                "home_team": "SK",
                "away_team": "KT",
                "home_score": self._live_home_score,
                "away_score": self._live_away_score,
                "period": self._live_period,
                "game_clock": self._format_clock(self._live_clock_seconds),
                "arena": "잠실학생체육관",
                "game_url": "https://sports.daum.net/schedule/kbl",
                "status": self._live_status,
                "start_time": (day_start_kst + timedelta(hours=14)).astimezone(UTC).isoformat(),
                "updated_at": now_iso,
            },
            {
                "game_id": _SCHEDULED_GAME_ID,
                "home_team": "KCC",
                "away_team": "삼성",
                "home_score": None,
                "away_score": None,
                "period": None,
                "game_clock": None,
                "arena": "부산사직체육관",
                "game_url": "https://sports.daum.net/schedule/kbl",
                "status": "SCHEDULED",
                "start_time": (day_start_kst + timedelta(hours=19)).astimezone(UTC).isoformat(),
                "updated_at": now_iso,
            },
            {
                "game_id": _FINAL_GAME_ID,
                "home_team": "LG",
                "away_team": "현대모비스",
                "home_score": 98,
                "away_score": 91,
                "period": 4,
                "game_clock": "00:00",
                "arena": "창원체육관",
                "game_url": "https://sports.daum.net/schedule/kbl",
                "status": "FINAL",
                "start_time": (day_start_kst + timedelta(hours=11)).astimezone(UTC).isoformat(),
                "updated_at": now_iso,
            },
        ]

        if team_id:
            games = [
                g for g in games if team_id in (g["home_team"], g["away_team"])
            ]
        logger.debug("Mock schedule returned", date=str(for_date), count=len(games))
        return games

    async def get_schedule_range(
        self, start_date: date, end_date: date, team_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return today's mock games plus a scheduled KT vs LG matchup."""
        games = await self.get_schedule(start_date, team_id=team_id)
        future_kst = datetime.combine(
            start_date + timedelta(days=2), datetime.min.time(), tzinfo=_KST
        ) + timedelta(hours=19)
        kt_lg_game: dict[str, Any] = {
            "game_id": _UPCOMING_KT_LG_ID,
            "home_team": "KT",
            "away_team": "LG",
            "home_score": None,
            "away_score": None,
            "period": None,
            "game_clock": None,
            "arena": "수원KT소닉붐아레나",
            "game_url": "https://sports.daum.net/schedule/kbl",
            "status": "SCHEDULED",
            "start_time": future_kst.astimezone(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if not team_id or team_id in ("KT", "LG"):
            games.append(kt_lg_game)
        return games

    async def get_game(self, game_id: str) -> dict[str, Any]:
        """
        Return a single mock game by *game_id*.

        Args:
            game_id: Provider game ID.

        Returns:
            Canonical game dict.

        Raises:
            ProviderError: If *game_id* is unknown.
        """
        today_kst = datetime.now(_KST).date()
        all_games = await self.get_schedule_range(today_kst, today_kst + timedelta(days=7))
        for g in all_games:
            if g["game_id"] == game_id:
                return g
        raise ProviderError(f"Game not found in mock provider: {game_id}")

    async def get_live_score(self, game_id: str) -> dict[str, Any]:
        """
        Return current live score after ticking the simulated game state.

        Args:
            game_id: Provider game ID.

        Returns:
            Canonical live score dict.

        Raises:
            ProviderError: If *game_id* is not the live mock game.
        """
        if game_id != _LIVE_GAME_ID:
            raise ProviderError(f"No live score for non-live game: {game_id}")
        self._tick_live_game()
        today_kst = datetime.now(_KST).date()
        day_start_kst = datetime.combine(today_kst, datetime.min.time(), tzinfo=_KST)
        score: dict[str, Any] = {
            "game_id": game_id,
            "status": self._live_status,
            "home_team": "SK",
            "away_team": "KT",
            "home_score": self._live_home_score,
            "away_score": self._live_away_score,
            "period": self._live_period,
            "game_clock": self._format_clock(self._live_clock_seconds),
            "arena": "잠실학생체육관",
            "game_url": "https://sports.daum.net/schedule/kbl",
            "start_time": (day_start_kst + timedelta(hours=14)).astimezone(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        logger.debug("Mock live score ticked", **score)
        return score

    async def get_standings(self, season: str) -> list[dict[str, Any]]:
        """
        Return mock KBL standings for *season*.

        Args:
            season: Season string, e.g. ``"2026-27"``.

        Returns:
            List of team standing dicts.
        """
        teams = _KBL_TEAMS.copy()
        standings: list[dict[str, Any]] = [
            {
                "rank": idx + 1,
                "team": team,
                "wins": max(0, 20 - idx * 2 + random.randint(-1, 1)),
                "losses": min(20, idx * 2 + random.randint(-1, 1)),
                "season": season,
            }
            for idx, team in enumerate(teams)
        ]
        logger.debug("Mock standings returned", season=season, count=len(standings))
        return standings
