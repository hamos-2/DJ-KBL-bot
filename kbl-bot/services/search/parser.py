"""Parser for Kakao chatbot matchup search queries (e.g. '#KT vs LG')."""

import re
from dataclasses import dataclass
from typing import Final

# Canonical KBL team short codes and all common aliases / full names on Daum Sports
KBL_TEAM_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "SK": ("SK", "서울SK", "서울 SK", "SK나이츠", "서울 SK 나이츠", "나이츠"),
    "KT": ("KT", "수원KT", "수원 KT", "KT소닉붐", "수원 KT 소닉붐", "소닉붐"),
    "LG": ("LG", "창원LG", "창원 LG", "LG세이커스", "창원 LG 세이커스", "세이커스", "엘지"),
    "KCC": ("KCC", "부산KCC", "부산 KCC", "KCC이지스", "부산 KCC 이지스", "이지스"),
    "삼성": ("삼성", "서울삼성", "서울 삼성", "삼성썬더스", "서울 삼성 썬더스", "썬더스"),
    "현대모비스": (
        "현대모비스",
        "울산현대모비스",
        "울산 현대모비스",
        "모비스",
        "현대모비스피버스",
        "울산 현대모비스 피버스",
        "피버스",
    ),
    "DB": ("DB", "원주DB", "원주 DB", "DB프로미", "원주 DB 프로미", "프로미", "디비"),
    "정관장": (
        "정관장",
        "안양정관장",
        "안양 정관장",
        "정관장레드부스터스",
        "안양 정관장 레드부스터스",
        "레드부스터스",
        "KGC",
        "안양KGC",
    ),
    "소노": (
        "소노",
        "고양소노",
        "고양 소노",
        "소노스카이거너스",
        "고양 소노 스카이거너스",
        "스카이거너스",
        "오리온",
        "데이원",
    ),
    "한국가스공사": (
        "한국가스공사",
        "대구한국가스공사",
        "대구 한국가스공사",
        "가스공사",
        "페가수스",
        "대구 한국가스공사 페가수스",
        "가스",
    ),
}

# Build reverse lookup (longest alias first to avoid partial shadowing)
_ALIAS_TO_CANONICAL: list[tuple[str, str]] = sorted(
    [
        (alias.upper().replace(" ", ""), canonical)
        for canonical, aliases in KBL_TEAM_ALIASES.items()
        for alias in aliases
    ],
    key=lambda item: len(item[0]),
    reverse=True,
)


@dataclass(frozen=True)
class MatchupQuery:
    """Represents a parsed KBL team or head-to-head matchup search query."""

    raw_query: str
    team_a: str
    team_b: str | None = None

    @property
    def is_head_to_head(self) -> bool:
        """Return True if two distinct teams were specified."""
        return self.team_b is not None and self.team_a != self.team_b


def normalize_team_name(name: str) -> str:
    """
    Convert a Daum Sports or user-supplied team name to its canonical KBL code.

    Args:
        name: Raw team name, e.g. ``"수원 KT 소닉붐"``, ``"창원 LG"``, ``"KT"``.

    Returns:
        Canonical team code (e.g. ``"KT"``, ``"LG"``), or stripped *name* if unknown.
    """
    cleaned = name.strip().upper().replace(" ", "")
    for alias_norm, canonical in _ALIAS_TO_CANONICAL:
        if alias_norm in cleaned:
            return canonical
    return name.strip()


def parse_matchup_query(utterance: str) -> MatchupQuery | None:
    """
    Parse a Kakao user utterance or search string such as ``"#KT vs LG"``.

    Supported formats:
        - ``"#KT vs LG"``
        - ``"KT vs LG"``
        - ``"#SK vs KCC 일정"``
        - ``"정관장 소노"``
        - ``"#현대모비스"`` (single team schedule lookup)

    Args:
        utterance: Raw user text or action param string.

    Returns:
        :class:`MatchupQuery` if at least one KBL team was recognized, else ``None``.
    """
    if not utterance or not utterance.strip():
        return None

    # Strip leading '#' and common noise tokens
    cleaned = re.sub(r"^[#\s]+", "", utterance.strip())
    cleaned = re.sub(r"(?i)\b(vs\.?|v\.?s\.?|대|경기|일정|결과|스코어|농구|kbl)\b", " ", cleaned)
    cleaned_upper = cleaned.upper().replace(" ", "")

    found_teams: list[str] = []
    remaining = cleaned_upper

    # Scan for longest matching team aliases in order of appearance
    matches_with_pos: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []

    for alias_norm, canonical in _ALIAS_TO_CANONICAL:
        idx = remaining.find(alias_norm)
        while idx != -1:
            end = idx + len(alias_norm)
            if not any( not (end <= s or idx >= e) for s, e in occupied ):
                occupied.append((idx, end))
                matches_with_pos.append((idx, canonical))
            idx = remaining.find(alias_norm, idx + 1)

    matches_with_pos.sort(key=lambda x: x[0])
    for _, canonical in matches_with_pos:
        if canonical not in found_teams:
            found_teams.append(canonical)
        if len(found_teams) == 2:
            break

    if not found_teams:
        return None

    team_a = found_teams[0]
    team_b = found_teams[1] if len(found_teams) > 1 else None
    return MatchupQuery(raw_query=utterance.strip(), team_a=team_a, team_b=team_b)
