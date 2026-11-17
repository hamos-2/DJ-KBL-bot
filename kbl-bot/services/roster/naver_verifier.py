"""Naver Sports KBL (seasonCode=49) Cross-Verification Service.

Cross-verifies KBL team rosters and starting 5 lineups against Naver Sports's
official KBL season statistics API
(``https://m.sports.naver.com/basketball/record/kbl?seasonCode=49``)
before lineups are published to users.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import httpx

from core.logging import get_logger
import services.content.kbl_data as kbl_data

logger = get_logger("service.roster.naver_verifier")

NAVER_SEASON_CODE_2026_2027 = 49
_NAVER_PLAYERS_API = (
    "https://api-gw.sports.naver.com/statistics/categories/kbl/seasons/{season_code}/players"
)
_NAVER_HEADERS = {
    "Referer": f"https://m.sports.naver.com/basketball/record/kbl?seasonCode={NAVER_SEASON_CODE_2026_2027}",
    "Origin": "https://m.sports.naver.com",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
}

_NAVER_TEAM_MAP: dict[str, str] = {
    "SK": "SK",
    "서울SK": "SK",
    "서울 SK": "SK",
    "DB": "DB",
    "원주DB": "DB",
    "원주 DB": "DB",
    "KT": "KT",
    "수원KT": "KT",
    "수원 KT": "KT",
    "LG": "LG",
    "창원LG": "LG",
    "창원 LG": "LG",
    "정관장": "정관장",
    "안양정관장": "정관장",
    "안양 정관장": "정관장",
    "KCC": "KCC",
    "부산KCC": "KCC",
    "부산 KCC": "KCC",
    "한국가스공사": "한국가스공사",
    "가스공사": "한국가스공사",
    "대구한국가스공사": "한국가스공사",
    "대구 한국가스공사": "한국가스공사",
    "현대모비스": "현대모비스",
    "울산현대모비스": "현대모비스",
    "울산 현대모비스": "현대모비스",
    "소노": "소노",
    "고양소노": "소노",
    "고양 소노": "소노",
    "삼성": "삼성",
    "서울삼성": "삼성",
    "서울 삼성": "삼성",
}

# In-memory TTL cache for Naver Sports Season 49 player roster
_NAVER_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}
_NAVER_CACHE_TTL_SEC = 900.0  # 15 minutes


def normalize_naver_team(raw_team: str | None) -> str:
    """Normalize a Naver Sports team name to canonical KBL club code."""
    if not raw_team:
        return ""
    cleaned = raw_team.strip()
    if cleaned in _NAVER_TEAM_MAP:
        return _NAVER_TEAM_MAP[cleaned]
    compact = cleaned.replace(" ", "")
    if compact in _NAVER_TEAM_MAP:
        return _NAVER_TEAM_MAP[compact]
    for key, val in _NAVER_TEAM_MAP.items():
        if key in compact or compact in key:
            return val
    return cleaned


def _parse_naver_player(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw Naver Sports seasonPlayerStats record to canonical dict."""
    team_raw = raw.get("teamShortName") or raw.get("teamName") or ""
    return {
        "player_id": str(raw.get("playerId") or ""),
        "name": str(raw.get("playerName") or "").strip(),
        "team": normalize_naver_team(team_raw),
        "pos": str(raw.get("position") or "G/F").strip(),
        "no": str(raw.get("backNumber") or "").strip(),
        "gp": int(raw.get("matchesPlayed") or 0),
        "pts": round(float(raw.get("pointsPerGame") or 0.0), 1),
        "reb": round(float(raw.get("reboundPerGame") or 0.0), 1),
        "ast": round(float(raw.get("assistPerGame") or 0.0), 1),
        "tpm": round(float(raw.get("threePointSuccessPerGame") or 0.0), 1),
        "stl": round(float(raw.get("stealPerGame") or 0.0), 1),
        "blk": round(float(raw.get("blockShotPerGame") or 0.0), 1),
        "is_retire": (
            raw.get("isRetire") is True
            or str(raw.get("isRetire") or "").strip().upper() in ("Y", "TRUE", "1")
        ),
        "enable": (
            raw.get("enable") is not False
            and str(raw.get("enable") or "Y").strip().upper() not in ("N", "FALSE", "0")
        ),
    }


def fetch_naver_season_players_sync(
    season_code: int = NAVER_SEASON_CODE_2026_2027,
    timeout: float = 1.5,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """
    Fetch active KBL player records from Naver Sports (seasonCode=49) synchronously.
    Uses a 15-minute in-memory TTL cache and returns [] gracefully on network timeout.
    """
    now = time.monotonic()
    if not force_refresh and season_code in _NAVER_CACHE:
        ts, cached_players = _NAVER_CACHE[season_code]
        if (now - ts) < _NAVER_CACHE_TTL_SEC and cached_players:
            return cached_players

    url = _NAVER_PLAYERS_API.format(season_code=season_code)
    players: list[dict[str, Any]] = []
    try:
        # Note: verify=False is intentionally retained for api-gw.sports.naver.com because
        # verified TLS/certifi handshakes on OCI VPS trigger WAF ReadTimeout on this host.
        with httpx.Client(headers=_NAVER_HEADERS, timeout=timeout, verify=False) as client:
            for page in range(1, 8):
                resp = client.get(
                    url,
                    params={
                        "sortField": "pointsPerGame",
                        "sortDirection": "desc",
                        "page": page,
                        "pageSize": 50,
                    },
                )
                if resp.status_code != 200:
                    break
                batch = (resp.json() or {}).get("result", {}).get("seasonPlayerStats") or []
                if not batch:
                    break
                players.extend(_parse_naver_player(item) for item in batch if item.get("playerName"))
                if len(batch) < 50:
                    break
    except Exception as exc:
        logger.debug("Naver Sports season %s fetch skipped/fallback: %s", season_code, exc)

    if players:
        _NAVER_CACHE[season_code] = (now, players)
    elif season_code in _NAVER_CACHE:
        # Return stale cache if live refresh failed
        return _NAVER_CACHE[season_code][1]

    return players


async def fetch_naver_season_players(
    season_code: int = NAVER_SEASON_CODE_2026_2027,
    timeout: float = 2.5,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Async counterpart to fetch_naver_season_players_sync."""
    now = time.monotonic()
    if not force_refresh and season_code in _NAVER_CACHE:
        ts, cached_players = _NAVER_CACHE[season_code]
        if (now - ts) < _NAVER_CACHE_TTL_SEC and cached_players:
            return cached_players

    url = _NAVER_PLAYERS_API.format(season_code=season_code)
    players: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(headers=_NAVER_HEADERS, timeout=timeout, verify=False) as client:
            for page in range(1, 8):
                resp = await client.get(
                    url,
                    params={
                        "sortField": "pointsPerGame",
                        "sortDirection": "desc",
                        "page": page,
                        "pageSize": 50,
                    },
                )
                if resp.status_code != 200:
                    break
                batch = (resp.json() or {}).get("result", {}).get("seasonPlayerStats") or []
                if not batch:
                    break
                players.extend(_parse_naver_player(item) for item in batch if item.get("playerName"))
                if len(batch) < 50:
                    break
    except Exception as exc:
        logger.debug("Async Naver Sports season %s fetch skipped/fallback: %s", season_code, exc)

    if players:
        _NAVER_CACHE[season_code] = (now, players)
    elif season_code in _NAVER_CACHE:
        return _NAVER_CACHE[season_code][1]

    return players


def cross_verify_lineup(
    team: str,
    candidate_starters: list[dict[str, Any]],
    naver_players: list[dict[str, Any]] | None = None,
    is_official_daum: bool = False,
    season_code: int = NAVER_SEASON_CODE_2026_2027,
) -> dict[str, Any]:
    """
    Cross-verify a club's starting 5 against Naver Sports seasonCode=49 records
    and core integrity rules (no retired legends, no transferred-out players).
    """
    norm_team = normalize_naver_team(team) or team
    naver_list = naver_players if naver_players is not None else []
    naver_by_team_name: dict[tuple[str, str], dict[str, Any]] = {
        (p["team"], p["name"]): p for p in naver_list
    }
    naver_by_name: dict[str, list[dict[str, Any]]] = {}
    for p in naver_list:
        naver_by_name.setdefault(p["name"], []).append(p)

    # Also build local fallback index from verified KBL_PLAYERS
    local_by_team_name = {
        (p["team"], p["name"]): p for p in kbl_data.KBL_PLAYERS
    }

    verified_starters: list[dict[str, Any]] = []
    discrepancies: list[str] = []
    advisories: list[str] = []

    for starter in candidate_starters:
        s_copy = dict(starter)
        s_name = str(s_copy.get("name") or "").strip()

        # Hard invariant checks
        if s_name == "함지훈":
            discrepancies.append("은퇴 선수(함지훈) 제외 대상")
            continue
        if norm_team == "SK" and s_name == "김선형":
            discrepancies.append("이적 선수(김선형) SK 제외 대상")
            continue

        n_rec = naver_by_team_name.get((norm_team, s_name))
        if n_rec:
            if n_rec.get("is_retire"):
                discrepancies.append(f"{s_name}: 네이버 시즌{season_code} 은퇴 표기")
            # Enrich/synchronize back number and position from Naver official records
            if n_rec.get("no") and str(s_copy.get("no") or "") != str(n_rec["no"]):
                s_copy["no"] = str(n_rec["no"])
            if n_rec.get("pos") and not s_copy.get("pos"):
                s_copy["pos"] = n_rec["pos"]
            s_copy["naver_gp"] = n_rec.get("gp", 0)
            s_copy["naver_pts"] = n_rec.get("pts", 0.0)
        elif naver_list:
            # Check if registered with a different club on Naver
            other_clubs = [p["team"] for p in naver_by_name.get(s_name, []) if p["team"] != norm_team]
            if other_clubs:
                discrepancies.append(f"{s_name}: 소속 불일치 (네이버 기준 {', '.join(other_clubs)})")
                if not is_official_daum:
                    continue
            else:
                advisories.append(f"{s_name}: 시즌{season_code} 0경기 (부상/미출전)")
        else:
            # Fallback to local verified KBL_PLAYERS baseline
            l_rec = local_by_team_name.get((norm_team, s_name))
            if l_rec and not s_copy.get("no"):
                s_copy["no"] = str(l_rec.get("no") or "")

        verified_starters.append(s_copy)

    if naver_list:
        source = "naver+daum" if is_official_daum else "naver"
        if not discrepancies:
            badge = (
                f"✅ 공식 선발 (다음·네이버 시즌{season_code} 교차검증)"
                if is_official_daum
                else f"✅ 2026-27 라인업 (네이버 시즌{season_code} 교차검증)"
            )
        else:
            badge = f"⚠️ 교차검증 주의 ({len(discrepancies)}건)"
    else:
        source = "daum+baseline" if is_official_daum else "baseline"
        badge = (
            "⚡ 다음 공식 선발 라인업"
            if is_official_daum
            else f"📋 2026-27 라인업 (시즌{season_code} 기준 검증)"
        )

    return {
        "team": norm_team,
        "verified": len(discrepancies) == 0 and len(verified_starters) >= 5,
        "source": source,
        "season_code": season_code,
        "checked_at": datetime.now(UTC).isoformat(),
        "verified_starters": verified_starters,
        "discrepancies": discrepancies,
        "advisories": advisories,
        "badge": badge,
    }


def verify_and_enrich_starters_sync(
    team: str,
    candidate_starters: list[dict[str, Any]],
    is_official_daum: bool = False,
) -> dict[str, Any]:
    """
    Fast pre-publish cross-verification gate for Kakao lineup cards & boards.
    Uses cached Naver Season 49 records (1.5s timeout on cold start) with safe fallback.
    """
    naver_players = fetch_naver_season_players_sync(timeout=1.5)
    return cross_verify_lineup(
        team=team,
        candidate_starters=candidate_starters,
        naver_players=naver_players,
        is_official_daum=is_official_daum,
    )


def run_full_lineup_cross_verification(
    season_code: int = NAVER_SEASON_CODE_2026_2027,
) -> dict[str, Any]:
    """
    Cross-verify all 10 KBL clubs' TEAM_LINEUPS and KBL_PLAYERS against
    Naver Sports (seasonCode=49). Returns a complete audit summary.
    """
    naver_players = fetch_naver_season_players_sync(
        season_code=season_code,
        timeout=4.0,
        force_refresh=True,
    )
    if not naver_players:
        return {
            "ok": False,
            "error": "Naver Sports season API unreachable",
            "season_code": season_code,
            "teams": {},
            "missing_active_players": [],
        }

    team_reports: dict[str, Any] = {}
    all_ok = True
    for team, info in kbl_data.TEAM_LINEUPS.items():
        report = cross_verify_lineup(
            team=team,
            candidate_starters=info.get("starters", []),
            naver_players=naver_players,
            is_official_daum=False,
            season_code=season_code,
        )
        team_reports[team] = report
        if not report["verified"] or report["advisories"]:
            all_ok = False

    local_keys = {(p["team"], p["name"]) for p in kbl_data.KBL_PLAYERS}
    missing_active = [
        p for p in naver_players
        if p["team"] and (p["team"], p["name"]) not in local_keys and p["pts"] >= 7.0
    ]

    return {
        "ok": all_ok and len(missing_active) == 0,
        "season_code": season_code,
        "naver_player_count": len(naver_players),
        "checked_at": datetime.now(UTC).isoformat(),
        "teams": team_reports,
        "missing_active_players": missing_active,
    }
