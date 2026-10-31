"""Unit tests for MockSportsDataProvider."""

import pytest
import pytest_asyncio
from datetime import date

from services.provider.mock import MockSportsDataProvider


@pytest.fixture
def provider() -> MockSportsDataProvider:
    """Return a fresh MockSportsDataProvider."""
    return MockSportsDataProvider()


class TestGetSchedule:
    """Tests for get_schedule()."""

    @pytest.mark.asyncio
    async def test_returns_three_games(self, provider: MockSportsDataProvider) -> None:
        """Mock schedule must return exactly 3 games."""
        games = await provider.get_schedule(date.today())
        assert len(games) == 3

    @pytest.mark.asyncio
    async def test_required_fields_present(self, provider: MockSportsDataProvider) -> None:
        """Each game dict must contain all canonical fields."""
        games = await provider.get_schedule(date.today())
        required = {"game_id", "home_team", "away_team", "status", "start_time", "updated_at"}
        for game in games:
            assert required.issubset(game.keys()), f"Missing fields in: {game}"

    @pytest.mark.asyncio
    async def test_status_values_valid(self, provider: MockSportsDataProvider) -> None:
        """All returned statuses must be one of SCHEDULED, LIVE, FINAL."""
        games = await provider.get_schedule(date.today())
        valid_statuses = {"SCHEDULED", "LIVE", "FINAL"}
        for game in games:
            assert game["status"] in valid_statuses

    @pytest.mark.asyncio
    async def test_contains_all_statuses(self, provider: MockSportsDataProvider) -> None:
        """Mock must include at least one game of each status type."""
        games = await provider.get_schedule(date.today())
        statuses = {g["status"] for g in games}
        assert "LIVE" in statuses
        assert "SCHEDULED" in statuses
        assert "FINAL" in statuses


class TestGetGame:
    """Tests for get_game()."""

    @pytest.mark.asyncio
    async def test_get_known_game(self, provider: MockSportsDataProvider) -> None:
        """get_game() with a known ID must return a game dict."""
        game = await provider.get_game("MOCK-LIVE-001")
        assert game["game_id"] == "MOCK-LIVE-001"
        assert game["status"] == "LIVE"

    @pytest.mark.asyncio
    async def test_get_unknown_game_raises(self, provider: MockSportsDataProvider) -> None:
        """get_game() with an unknown ID must raise ProviderError."""
        from core.exceptions import ProviderError
        with pytest.raises(ProviderError):
            await provider.get_game("NONEXISTENT-999")


class TestGetLiveScore:
    """Tests for get_live_score()."""

    @pytest.mark.asyncio
    async def test_live_score_returns_dict(self, provider: MockSportsDataProvider) -> None:
        """get_live_score() must return a dict with required live fields."""
        score = await provider.get_live_score("MOCK-LIVE-001")
        assert score["game_id"] == "MOCK-LIVE-001"
        assert score["status"] == "LIVE"
        assert isinstance(score["home_score"], int)
        assert isinstance(score["away_score"], int)

    @pytest.mark.asyncio
    async def test_live_score_non_live_raises(self, provider: MockSportsDataProvider) -> None:
        """Calling get_live_score on a non-live game ID must raise ProviderError."""
        from core.exceptions import ProviderError
        with pytest.raises(ProviderError):
            await provider.get_live_score("MOCK-SCHED-001")

    @pytest.mark.asyncio
    async def test_scores_non_negative(self, provider: MockSportsDataProvider) -> None:
        """Scores must always be >= 0."""
        for _ in range(5):
            score = await provider.get_live_score("MOCK-LIVE-001")
            assert score["home_score"] >= 0
            assert score["away_score"] >= 0


class TestGetStandings:
    """Tests for get_standings()."""

    @pytest.mark.asyncio
    async def test_standings_count(self, provider: MockSportsDataProvider) -> None:
        """Must return 10 teams (all KBL teams)."""
        standings = await provider.get_standings("2024-25")
        assert len(standings) == 10

    @pytest.mark.asyncio
    async def test_standings_rank_field(self, provider: MockSportsDataProvider) -> None:
        """Each entry must have a rank field starting at 1."""
        standings = await provider.get_standings("2024-25")
        ranks = [s["rank"] for s in standings]
        assert ranks[0] == 1
