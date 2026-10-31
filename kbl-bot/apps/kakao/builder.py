"""Factory functions for building Kakao Skill response payloads."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apps.kakao.schemas import (
    KakaoSkillResponse,
    KakaoTemplate,
    QuickReply,
)
from services.search.parser import MatchupQuery

_KST = ZoneInfo("Asia/Seoul")
_WEEKDAY_KO = ("월", "화", "수", "목", "금", "토", "일")

_DEFAULT_QUICK_REPLIES: list[QuickReply] = [
    QuickReply(label="오늘 경기", messageText="오늘 경기"),
    QuickReply(label="처음으로", messageText="처음으로"),
]


def _format_kst_datetime(iso_str: str | None, include_date: bool = True) -> str:
    """Format an ISO-8601 timestamp string into KST ``MM/DD(요일) HH:MM`` or ``HH:MM``."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(_KST)
        if include_date:
            wd = _WEEKDAY_KO[dt.weekday()]
            return f"{dt.strftime('%m/%d')}({wd}) {dt.strftime('%H:%M')}"
        return dt.strftime("%H:%M")
    except Exception:
        return ""


def build_simple_response(
    text: str,
    quick_replies: list[QuickReply] | None = None,
) -> KakaoSkillResponse:
    """
    Build a Kakao Skill response containing a single SimpleText bubble.

    Args:
        text: Message text to display.
        quick_replies: Optional quick-reply buttons. Defaults to empty list.

    Returns:
        Fully populated KakaoSkillResponse.
    """
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": text}}],
            quickReplies=quick_replies or [],
        )
    )


def build_error_response(
    user_message: str = "일시적으로 데이터를 불러올 수 없습니다.",
) -> KakaoSkillResponse:
    """
    Build a standardised error response with default quick-reply shortcuts.

    Args:
        user_message: Human-readable error explanation (Korean).

    Returns:
        KakaoSkillResponse with the error text and retry quick-replies.
    """
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": user_message}}],
            quickReplies=_DEFAULT_QUICK_REPLIES,
        )
    )


def build_today_games_response(games: list[dict[str, Any]]) -> KakaoSkillResponse:
    """
    Build a Skill response that lists today's games.

    Args:
        games: List of canonical game dicts.

    Returns:
        KakaoSkillResponse with a multi-line SimpleText listing.
    """
    if not games:
        return build_simple_response(
            "오늘 예정된 경기가 없습니다.",
            quick_replies=[QuickReply(label="일정 보기", messageText="일정")],
        )

    lines: list[str] = ["🏀 오늘의 KBL 경기\n"]
    status_emoji = {"LIVE": "🔴", "SCHEDULED": "📅", "FINAL": "✅"}

    for g in games:
        emoji = status_emoji.get(g.get("status", ""), "⚪")
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        status = g.get("status", "")
        arena = g.get("arena") or ""
        arena_suffix = f" | {arena}" if arena else ""

        if status == "LIVE":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            period = g.get("period") or "?"
            clock = g.get("game_clock") or ""
            clock_str = f" {clock}" if clock else ""
            stale_mark = " ⚠️" if g.get("stale") else ""
            lines.append(
                f"{emoji} {home} {h_score} - {a_score} {away}"
                f"  ({period}쿼터{clock_str}){stale_mark}{arena_suffix}"
            )
        elif status == "FINAL":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            lines.append(f"{emoji} {home} {h_score} - {a_score} {away}  [종료]{arena_suffix}")
        else:
            time_str = _format_kst_datetime(g.get("start_time"), include_date=False)
            lines.append(f"{emoji} {home} vs {away}  {time_str}{arena_suffix}")

    return build_simple_response(
        "\n".join(lines),
        quick_replies=[
            QuickReply(label="실시간 점수", messageText="실시간 점수"),
            QuickReply(label="팀 순위", messageText="팀 순위"),
        ],
    )


def build_matchup_search_response(
    query: MatchupQuery,
    games: list[dict[str, Any]],
) -> KakaoSkillResponse:
    """
    Build a Kakao Skill response for a Daum Sports team/matchup search (e.g. ``#KT vs LG``).

    Args:
        query: Parsed :class:`MatchupQuery` with ``team_a`` and optional ``team_b``.
        games: Matching canonical game dicts ordered by start_time.

    Returns:
        KakaoSkillResponse with matchup schedule, arena, score/status, and Daum match URL.
    """
    header = (
        f"🔍 [{query.team_a} vs {query.team_b}] 경기 일정 (Daum 스포츠)"
        if query.is_head_to_head
        else f"🔍 [{query.team_a}] 경기 일정 (Daum 스포츠)"
    )

    if not games:
        return build_simple_response(
            f"{header}\n\n조회 가능한 예정/최근 경기가 없습니다.",
            quick_replies=_DEFAULT_QUICK_REPLIES,
        )

    lines: list[str] = [header, ""]
    status_emoji = {"LIVE": "🔴", "SCHEDULED": "📅", "FINAL": "✅"}

    for g in games:
        status = g.get("status", "SCHEDULED")
        emoji = status_emoji.get(status, "⚪")
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        dt_str = _format_kst_datetime(g.get("start_time"), include_date=True)
        arena = g.get("arena") or "경기장 미정"
        game_url = g.get("game_url") or ""

        if status == "LIVE":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            period = g.get("period") or "?"
            clock = g.get("game_clock") or ""
            clock_str = f" {clock}" if clock else ""
            lines.append(f"{emoji} [진행중] {home} {h_score} - {a_score} {away} ({period}쿼터{clock_str})")
        elif status == "FINAL":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            lines.append(f"{emoji} [종료] {home} {h_score} - {a_score} {away}")
        else:
            lines.append(f"{emoji} [예정] {home} vs {away}")

        lines.append(f"   🕒 {dt_str} | 📍 {arena}")
        if game_url:
            lines.append(f"   🔗 {game_url}")
        lines.append("")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=[
            QuickReply(label="오늘 경기", messageText="오늘 경기"),
            QuickReply(label="실시간 점수", messageText="실시간 점수"),
        ],
    )


def build_live_score_response(snapshot: dict[str, Any]) -> KakaoSkillResponse:
    """
    Build a Skill response for a single live game score.

    Args:
        snapshot: Game snapshot dict (may contain ``stale`` boolean).

    Returns:
        KakaoSkillResponse with live score details.
    """
    home = snapshot.get("home_team", "?")
    away = snapshot.get("away_team", "?")
    h_score = snapshot.get("home_score", 0)
    a_score = snapshot.get("away_score", 0)
    period = snapshot.get("period", "?")
    clock = snapshot.get("game_clock", "")
    status = snapshot.get("status", "")
    stale = snapshot.get("stale", False)

    if status == "FINAL":
        text = (
            f"✅ 경기 종료\n"
            f"{home} {h_score} - {a_score} {away}\n"
            f"최종 결과입니다."
        )
    elif status == "LIVE":
        stale_note = "\n⚠️ 데이터가 지연될 수 있습니다." if stale else ""
        text = (
            f"🔴 LIVE — {period}쿼터 {clock}\n"
            f"{home} {h_score} - {a_score} {away}{stale_note}"
        )
    else:
        text = f"📅 경기 예정\n{home} vs {away}"

    return build_simple_response(
        text,
        quick_replies=[
            QuickReply(label="새로고침", messageText="실시간 점수"),
            QuickReply(label="오늘 경기", messageText="오늘 경기"),
        ],
    )


def build_health_response(
    db_ok: bool, redis_ok: bool, worker_running: bool
) -> KakaoSkillResponse:
    """
    Build a health-check Skill response.

    Args:
        db_ok: Whether PostgreSQL is reachable.
        redis_ok: Whether Redis is reachable.
        worker_running: Whether the ingestion worker task is active.

    Returns:
        KakaoSkillResponse with system status summary.
    """
    ok = lambda v: "✅" if v else "❌"  # noqa: E731
    text = (
        f"🛠 시스템 상태\n"
        f"DB: {ok(db_ok)}\n"
        f"Redis: {ok(redis_ok)}\n"
        f"Worker: {ok(worker_running)}"
    )
    return build_simple_response(text)
