"""KBL Season management utilities for dynamic and automatic season rollover."""

from datetime import UTC, date, datetime
import os
import re
from typing import Final
from zoneinfo import ZoneInfo

_KST: Final[ZoneInfo] = ZoneInfo("Asia/Seoul")


def get_kst_now() -> datetime:
    """Return current datetime in Asia/Seoul (KST)."""
    return datetime.now(_KST)


def get_season_years(target_date: date | datetime | None = None) -> tuple[int, int]:
    """
    Return (start_year, end_year) for the KBL season corresponding to target_date.

    KBL seasons run across two calendar years:
    - Starts in October of year Y (Regular season opening)
    - Concludes in May/June of year Y+1 (Playoffs / Championship finals)
    - Pre-season & KBL Cup take place in late September / October.

    Automatic Rollover Rule:
    - October ~ December (months 10, 11, 12): start_year = year, end_year = year + 1
    - January ~ September (months 1..9): start_year = year - 1, end_year = year

    Args:
        target_date: Optional reference date or datetime. If omitted, uses current KST date.

    Returns:
        Tuple of (start_year, end_year), e.g. (2026, 2027).
    """
    # Environment variable override if explicitly configured
    env_override = os.environ.get("KBL_CURRENT_SEASON")
    if env_override:
        parsed = parse_season_string(env_override)
        if parsed:
            return parsed

    if target_date is None:
        target_date = get_kst_now().date()
    elif isinstance(target_date, datetime):
        if target_date.tzinfo is None:
            target_date = target_date.replace(tzinfo=UTC).astimezone(_KST).date()
        else:
            target_date = target_date.astimezone(_KST).date()

    year = target_date.year
    month = target_date.month

    if month >= 10:
        return (year, year + 1)
    else:
        return (year - 1, year)


def get_current_season(target_date: date | datetime | None = None) -> str:
    """
    Return standard 2-digit season string, e.g. ``'2026-27'``.

    Args:
        target_date: Optional reference date. Defaults to current KST date.
    """
    start_y, end_y = get_season_years(target_date)
    return f"{start_y}-{str(end_y)[2:]}"


def get_current_season_full(target_date: date | datetime | None = None) -> str:
    """
    Return full 4-digit season string for search queries and formal titles, e.g. ``'2026-2027'``.

    Args:
        target_date: Optional reference date. Defaults to current KST date.
    """
    start_y, end_y = get_season_years(target_date)
    return f"{start_y}-{end_y}"


def get_current_season_key(target_date: date | datetime | None = None) -> str:
    """
    Return 8-digit season key used by Daum ARMS API, e.g. ``'20262027'``.

    Args:
        target_date: Optional reference date. Defaults to current KST date.
    """
    start_y, end_y = get_season_years(target_date)
    return f"{start_y}{end_y}"


def get_season_search_query(base_query: str, target_date: date | datetime | None = None) -> str:
    """
    Prefix a base query with the active 4-digit season string.

    Example:
        >>> get_season_search_query("KBL 순위")
        '2026-2027 KBL 순위'
    """
    season_full = get_current_season_full(target_date)
    clean_base = base_query.strip()
    return f"{season_full} {clean_base}"


def get_season_date_range(target_date: date | datetime | None = None) -> tuple[date, date]:
    """
    Return (opening_date, closing_date) window for the active regular season.
    - Opening: October 1st of start_year
    - Closing: June 30th of end_year
    """
    start_y, end_y = get_season_years(target_date)
    return (date(start_y, 10, 1), date(end_y, 6, 30))


def parse_season_string(season_str: str) -> tuple[int, int] | None:
    """
    Parse various season strings into (start_year, end_year).

    Supports:
        - "2026-27" -> (2026, 2027)
        - "2026-2027" -> (2026, 2027)
        - "20262027" -> (2026, 2027)
        - "2026/2027" -> (2026, 2027)
    """
    if not season_str or not isinstance(season_str, str):
        return None

    clean = season_str.strip()
    # 8-digit continuous: 20262027
    m8 = re.match(r"^(\d{4})(\d{4})$", clean)
    if m8:
        return int(m8.group(1)), int(m8.group(2))

    # 4-digit - 4-digit: 2026-2027 or 2026/2027
    m44 = re.match(r"^(\d{4})[-/](\d{4})$", clean)
    if m44:
        return int(m44.group(1)), int(m44.group(2))

    # 4-digit - 2-digit: 2026-27
    m42 = re.match(r"^(\d{4})[-/](\d{2})$", clean)
    if m42:
        start_y = int(m42.group(1))
        century = (start_y // 100) * 100
        end_y = century + int(m42.group(2))
        return start_y, end_y

    return None
