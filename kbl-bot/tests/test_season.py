"""Unit tests for KBL Season management and automatic rollover."""

from datetime import date, datetime
from zoneinfo import ZoneInfo
import pytest

from core.season import (
    get_current_season,
    get_current_season_full,
    get_current_season_key,
    get_season_date_range,
    get_season_search_query,
    get_season_years,
    parse_season_string,
)


class TestKblSeasonRollover:
    """Tests for dynamic season detection and automatic rollover by date."""

    def test_current_date_is_2026_2027(self) -> None:
        """Current date (November 2026) must evaluate to 2026-2027 season."""
        # Baseline reference: 2026-11-01
        ref_d = date(2026, 11, 1)
        assert get_season_years(ref_d) == (2026, 2027)
        assert get_current_season(ref_d) == "2026-27"
        assert get_current_season_full(ref_d) == "2026-2027"
        assert get_current_season_key(ref_d) == "20262027"

    def test_season_opening_october_boundary(self) -> None:
        """October 1st begins the new season cycle."""
        assert get_season_years(date(2026, 10, 1)) == (2026, 2027)
        assert get_current_season(date(2026, 10, 1)) == "2026-27"
        assert get_current_season_full(date(2026, 10, 1)) == "2026-2027"

    def test_mid_season_january_to_may(self) -> None:
        """January through May of year Y+1 remains in season Y ~ Y+1."""
        assert get_season_years(date(2027, 1, 15)) == (2026, 2027)
        assert get_season_years(date(2027, 3, 20)) == (2026, 2027)
        assert get_season_years(date(2027, 5, 10)) == (2026, 2027)
        assert get_current_season_full(date(2027, 5, 10)) == "2026-2027"

    def test_offseason_summer_months(self) -> None:
        """June through September still reflects the concluded/draft preparation season."""
        assert get_season_years(date(2027, 6, 30)) == (2026, 2027)
        assert get_season_years(date(2027, 9, 30)) == (2026, 2027)
        assert get_current_season_full(date(2027, 9, 30)) == "2026-2027"

    def test_automatic_rollover_to_next_season_2027_2028(self) -> None:
        """On October 1st, 2027, the season automatically rolls over to 2027-2028."""
        oct_2027 = date(2027, 10, 1)
        assert get_season_years(oct_2027) == (2027, 2028)
        assert get_current_season(oct_2027) == "2027-28"
        assert get_current_season_full(oct_2027) == "2027-2028"
        assert get_current_season_key(oct_2027) == "20272028"

    def test_season_search_query_generation(self) -> None:
        """Search query must prepend the 4-digit season string."""
        ref_d = date(2026, 11, 1)
        assert get_season_search_query("KBL 순위", ref_d) == "2026-2027 KBL 순위"
        assert get_season_search_query("프로농구 SK", ref_d) == "2026-2027 프로농구 SK"
        assert get_season_search_query("  선수순위  ", ref_d) == "2026-2027 선수순위"

    def test_season_date_range(self) -> None:
        """Season date range opens Oct 1 and closes June 30."""
        start_d, end_d = get_season_date_range(date(2026, 11, 1))
        assert start_d == date(2026, 10, 1)
        assert end_d == date(2027, 6, 30)

    def test_parse_season_string_formats(self) -> None:
        """Test parsing diverse string formats into (start_year, end_year)."""
        assert parse_season_string("2026-27") == (2026, 2027)
        assert parse_season_string("2026-2027") == (2026, 2027)
        assert parse_season_string("20262027") == (2026, 2027)
        assert parse_season_string("2026/2027") == (2026, 2027)
        assert parse_season_string("invalid") is None
        assert parse_season_string("") is None

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variable KBL_CURRENT_SEASON overrides date-based logic."""
        monkeypatch.setenv("KBL_CURRENT_SEASON", "2028-29")
        assert get_current_season(date(2026, 11, 1)) == "2028-29"
        assert get_current_season_full(date(2026, 11, 1)) == "2028-2029"
        assert get_current_season_key(date(2026, 11, 1)) == "20282029"
