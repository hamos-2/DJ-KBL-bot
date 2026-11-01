"""Abstract interface for sports data providers."""

from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Any


class SportsDataProvider(ABC):
    """Protocol that every data provider adapter must satisfy."""

    @abstractmethod
    async def get_schedule(
        self, for_date: date, team_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return a list of game dicts for *for_date*.

        Args:
            for_date: Calendar date to fetch games for.
            team_id: Optional team filter.

        Returns:
            List of canonical game dicts.
        """

    async def get_schedule_range(
        self, start_date: date, end_date: date, team_id: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Return a list of game dicts between *start_date* and *end_date* (inclusive).

        Providers with native range endpoints (such as Daum Sports) override this
        to fetch the entire date range in a single HTTP request.
        """
        results: list[dict[str, Any]] = []
        cur = start_date
        while cur <= end_date:
            results.extend(await self.get_schedule(cur, team_id=team_id))
            cur += timedelta(days=1)
        return results

    @abstractmethod
    async def get_game(self, game_id: str) -> dict[str, Any]:
        """
        Return a single game dict by provider *game_id*.

        Args:
            game_id: Provider-supplied game identifier.

        Returns:
            Canonical game dict.

        Raises:
            ProviderError: If the game does not exist or provider fails.
        """

    @abstractmethod
    async def get_live_score(self, game_id: str) -> dict[str, Any]:
        """
        Return the current live score for *game_id*.

        Args:
            game_id: Provider-supplied game identifier.

        Returns:
            Canonical live score dict.

        Raises:
            ProviderError: If the provider is unavailable.
        """

    @abstractmethod
    async def get_standings(self, season: str) -> list[dict[str, Any]]:
        """
        Return the current season standings.

        Args:
            season: Season identifier, e.g. ``"2026-27"``.

        Returns:
            List of team standing dicts sorted by rank.
        """

    async def get_news(
        self,
        team: str | None = None,
        recent_games: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return latest KBL news items."""
        return []

