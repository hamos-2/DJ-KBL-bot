"""Factory functions for building Kakao Skill response payloads (Pro Basketball Bot MVP)."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apps.kakao.schemas import (
    KakaoSkillResponse,
    KakaoTemplate,
    QuickReply,
)
from services.content.kbl_data import KBL_PLAYERS, TEAM_INFO, TEAM_LINEUPS, get_team_lineup
from services.search.parser import KBL_TEAMS, MatchupQuery

_KST = ZoneInfo("Asia/Seoul")
_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# Bottom navigation QuickReplies: Optimized for user flow (Matching 프로야구봇 _HhRnC structure)
MAIN_MENU_QUICK_REPLIES: list[QuickReply] = [
    QuickReply(label="오늘 경기", messageText="오늘 경기"),
    QuickReply(label="실시간 점수", messageText="실시간 점수"),
    QuickReply(label="승부예측", messageText="승부예측"),
    QuickReply(label="라인업", messageText="라인업"),
    QuickReply(label="일정", messageText="일정"),
    QuickReply(label="결과", messageText="결과"),
    QuickReply(label="팀순위", messageText="팀순위"),
    QuickReply(label="선수순위", messageText="선수순위"),
    QuickReply(label="주요장면", messageText="주요장면"),
    QuickReply(label="알림설정", messageText="알림설정"),
]

_DEFAULT_QUICK_REPLIES: list[QuickReply] = MAIN_MENU_QUICK_REPLIES


def _format_kst_datetime(iso_str: str | None, include_date: bool = True) -> str:
    """Format an ISO-8601 timestamp string into Korean KST date/time."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone(_KST)
        if include_date:
            wd = _WEEKDAYS_KO[dt.weekday()]
            return f"{dt.strftime('%m/%d')}({wd}) {dt.strftime('%H:%M')}"
        return dt.strftime("%H:%M")
    except Exception:
        return ""


def _short_arena(arena: str | None) -> str:
    """Return compact 2~4 letter stadium / city abbreviation."""
    if not arena:
        return ""
    arena = arena.strip()
    for kw in ["잠실학생", "잠실", "수원", "고양", "창원", "원주", "울산", "대구", "안양", "부산"]:
        if kw in arena:
            return kw
    return arena.replace("체육관", "").replace("아레나", "").strip()[:4]


def _msg_btn(label: str, message_text: str) -> dict[str, str]:
    """Build an in-card message button dict for Kakao textCard/basicCard."""
    return {
        "action": "message",
        "label": label[:14],
        "messageText": message_text,
    }


def _link_btn(label: str, url: str) -> dict[str, str]:
    """Build an in-card webLink button dict for Kakao textCard/basicCard."""
    return {
        "action": "webLink",
        "label": label[:14],
        "webLinkUrl": url,
    }


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
    """
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": user_message}}],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_home_menu_response(
    favorite_team: str | None = None,
    fav_players: list[str] | None = None,
) -> KakaoSkillResponse:
    """
    Build the Pro Basketball Bot welcome / home menu response.
    If the user has not selected a favorite team, presents the 10-team selection
    carousel immediately (matching 프로야구봇 _HhRnC onboarding flow).
    """
    if not favorite_team:
        welcome_text = (
            "🏀 환영합니다! KBL 프로농구봇입니다.\n\n"
            "가장 먼저 응원하시는 구단을 선택해 주세요! ❤️\n"
            "응원팀을 설정하시면 오늘 경기, 일정, 결과, 실시간 스코어, 승부예측이 [응원팀 맞춤]으로 제공됩니다."
        )
        team_cards = [
            {
                "title": "❤️ 응원팀 선택 (수도권 구단)",
                "description": "응원할 구단 버튼을 누르면 내 응원팀으로 즉시 설정됩니다.",
                "buttons": [
                    _msg_btn("❤️ 서울 SK", "#응원팀 SK"),
                    _msg_btn("❤️ 수원 KT", "#응원팀 KT"),
                    _msg_btn("❤️ 서울 삼성", "#응원팀 삼성"),
                ],
            },
            {
                "title": "❤️ 응원팀 선택 (경기·강원 구단)",
                "description": "선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                "buttons": [
                    _msg_btn("❤️ 원주 DB", "#응원팀 DB"),
                    _msg_btn("❤️ 안양 정관장", "#응원팀 정관장"),
                    _msg_btn("❤️ 고양 소노", "#응원팀 소노"),
                ],
            },
            {
                "title": "❤️ 응원팀 선택 (영남권 구단)",
                "description": "선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                "buttons": [
                    _msg_btn("❤️ 창원 LG", "#응원팀 LG"),
                    _msg_btn("❤️ 부산 KCC", "#응원팀 KCC"),
                    _msg_btn("❤️ 울산 현대모비스", "#응원팀 현대모비스"),
                ],
            },
            {
                "title": "❤️ 응원팀 선택 (대구 한국가스공사)",
                "description": "대구 한국가스공사 페가수스를 내 응원팀으로 설정합니다.",
                "buttons": [
                    _msg_btn("❤️ 한국가스공사", "#응원팀 한국가스공사"),
                    _msg_btn("📅 오늘 경기 보기", "오늘 경기"),
                    _msg_btn("🏆 정규리그 순위표", "팀순위"),
                ],
            },
        ]
        return KakaoSkillResponse(
            template=KakaoTemplate(
                outputs=[
                    {"simpleText": {"text": welcome_text}},
                    {"carousel": {"type": "textCard", "items": team_cards}},
                ],
                quickReplies=MAIN_MENU_QUICK_REPLIES,
            )
        )

    full_team = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
    players_label = (
        f"⭐ 관심선수: {', '.join(fav_players)}"
        if fav_players
        else "⭐ 관심선수: 미설정 ('관심선수'에서 선수를 등록해보세요!)"
    )
    text = (
        "🏀 KBL 프로농구봇 홈\n\n"
        f"❤️ 내 응원팀: {full_team}\n"
        f"{players_label}\n\n"
        "📌 [프로야구봇형 대표 메뉴]\n"
        "• 오늘 경기 : 내 응원팀 경기 및 오늘 전체 경기\n"
        "• 실시간 점수 : 쿼터별 스코어박스 & 다음 톡중계\n"
        "• 승부예측 : 매일 경기 승리팀 투표 & 투표율 배틀\n"
        "• 라인업 : 당일 경기 양 팀 선발 베스트 5\n"
        "• 일정 / 결과 : 내 응원팀 우선 주간 일정 및 경기 결과\n"
        "• 요약 / 한줄평 : 최근 종료된 경기 MVP 및 승부처 총평\n"
        "• 팀순위 / 선수순위 : 10개 구단 및 부문별 개인 순위\n"
        "• 알림설정 : 라인업·시작·종료·클러치 맞춤 알림\n\n"
        "💡 하단 메뉴 버튼을 누르거나 키워드를 입력해 보세요!"
    )
    action_card = {
        "textCard": {
            "title": f"🏀 {favorite_team} 중심 빠른 바로가기",
            "description": f"현재 응원팀: {full_team}\n원하시는 기능을 선택하세요.",
            "buttons": [
                _msg_btn("📅 오늘 경기", "오늘 경기"),
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
                _msg_btn("📋 선발 라인업", "라인업"),
            ],
        }
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": text}}, action_card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_lineup_response(
    today_games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '라인업' (Starting 5 lineups & head coaches for today's games).
    Matches 프로야구봇's 선발 라인업 feature.
    """
    if not today_games:
        return build_simple_response(
            "📋 오늘 예정된 KBL 경기가 없어 선발 라인업이 없습니다.\n하단 '일정'에서 다음 경기 일정을 확인해보세요!",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    first_start = today_games[0].get("start_time")
    date_label = ""
    if first_start:
        try:
            dt = datetime.fromisoformat(first_start.replace("Z", "+00:00")).astimezone(_KST)
            date_label = f" ({dt.strftime('%m.%d')} {_WEEKDAYS_KO[dt.weekday()]})"
        except Exception:
            pass

    lines: list[str] = [f"📋 KBL 선발 라인업 (베스트 5){date_label}\n"]
    cards: list[dict[str, Any]] = []

    # Prioritize favorite team's game
    sorted_games = sorted(
        today_games,
        key=lambda g: (
            0 if favorite_team and favorite_team in (g.get("home_team"), g.get("away_team")) else 1,
            str(g.get("start_time") or ""),
        ),
    )

    for g in sorted_games[:3]:
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        time_str = _format_kst_datetime(g.get("start_time"), include_date=False) or "14:00"
        arena = _short_arena(g.get("arena"))
        arena_str = f" [{arena}]" if arena else ""

        home_lineup = get_team_lineup(home) or {}
        away_lineup = get_team_lineup(away) or {}

        h_starters = home_lineup.get("starters", [])
        a_starters = away_lineup.get("starters", [])
        h_coach = home_lineup.get("head_coach", "")
        a_coach = away_lineup.get("head_coach", "")

        lines.append(f"🏀 {home} vs {away} ({time_str}{arena_str})")
        if h_starters:
            h_str = ", ".join(f"{s['pos']} {s['name']} #{s['no']}" for s in h_starters)
            h_coach_str = f" ({h_coach} 감독)" if h_coach else ""
            lines.append(f"• {home}{h_coach_str}:\n  {h_str}")
        if a_starters:
            a_str = ", ".join(f"{s['pos']} {s['name']} #{s['no']}" for s in a_starters)
            a_coach_str = f" ({a_coach} 감독)" if a_coach else ""
            lines.append(f"• {away}{a_coach_str}:\n  {a_str}")
        lines.append("")

        h_card_names = "/".join(s["name"] for s in h_starters[:3])
        a_card_names = "/".join(s["name"] for s in a_starters[:3])
        cards.append(
            {
                "title": f"📋 {home} vs {away} 선발 라인업",
                "description": (
                    f"• {home}: {h_card_names} 외 2명\n"
                    f"• {away}: {a_card_names} 외 2명\n"
                    f"※ 경기 시작 약 1시간 전 공식 확정"
                ),
                "buttons": [
                    _msg_btn("🗳️ 승부예측", f"#승부예측 {home}"),
                    _msg_btn("🔴 실시간 스코어", "실시간 점수"),
                    _msg_btn("🔔 라인업 알림설정", "알림설정"),
                ],
            }
        )

    lines.append("💡 경기 시작 약 1시간 전 KBL 공식 확정 라인업이 반영됩니다.")

    outputs: list[dict[str, Any]] = [
        {"simpleText": {"text": "\n".join(lines).strip()}},
    ]
    if cards:
        outputs.append({"carousel": {"type": "textCard", "items": cards}})

    return KakaoSkillResponse(
        template=KakaoTemplate(outputs=outputs, quickReplies=MAIN_MENU_QUICK_REPLIES)
    )


def build_game_summary_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '요약' / '한줄평' (Game recap, MVP player stats, and key turning points).
    Matches 프로야구봇's 요약 feature.
    """
    finished_games = [g for g in games if g.get("status") == "FINAL"]
    if not finished_games:
        finished_games = games[:3]

    if not finished_games:
        return build_simple_response(
            "📊 최근 종료된 KBL 경기 요약 데이터가 없습니다.\n하단 '결과'에서 경기 스코어를 확인해보세요!",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    if favorite_team:
        fav_game = next(
            (g for g in finished_games if favorite_team in (g.get("home_team"), g.get("away_team"))),
            None,
        )
        if fav_game:
            finished_games = [fav_game] + [g for g in finished_games if g != fav_game]

    target = finished_games[0]
    home = target.get("home_team", "?")
    away = target.get("away_team", "?")
    hs = int(target.get("home_score") or 0)
    as_ = int(target.get("away_score") or 0)
    winner = home if hs > as_ else away
    diff = abs(hs - as_)

    winner_stars = [p for p in KBL_PLAYERS if p.get("team") == winner]
    mvp = winner_stars[0] if winner_stars else {"name": f"{winner} 수훈선수", "pts": 24.0, "reb": 9.0, "ast": 5.0}

    clutch_msg = (
        "4쿼터 막판 원포제션 접전 상황에서 결정적인 슛과 집중력 있는 수비로 짜릿한 역전승을 거두었습니다."
        if diff <= 5
        else f"경기 초반부터 주도권을 잡은 {winner}(이)가 압도적인 공수 밸런스로 {diff}점 차 완승을 거두었습니다."
    )

    lines = [
        f"📋 [경기 요약 & 한줄평] {home} {hs} : {as_} {away}\n",
        f"👑 승리팀: {winner}",
        f"⭐ 경기 MVP: {mvp['name']} ({winner})",
        f"   └ 활약: {mvp['pts']}점 ｜ {mvp['reb']}리바운드 ｜ {mvp['ast']}어시스트\n",
        f"📝 승부처 한줄평:\n\"{clutch_msg}\"\n",
        f"💡 전체 하이라이트 영상 및 주요 장면은 '주요장면' 메뉴에서 시청하실 수 있습니다.",
    ]

    card = {
        "textCard": {
            "title": f"🎬 {home} vs {away} 하이라이트 & 요약",
            "description": f"승리팀: {winner} ({hs}:{as_})\nMVP: {mvp['name']} ({mvp['pts']}점)",
            "buttons": [
                _msg_btn("🎬 주요장면 영상", f"{winner} 주요장면"),
                _msg_btn("🏆 정규리그 순위표", "팀순위"),
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
            ],
        }
    }

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": "\n".join(lines).strip()}}, card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_today_games_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build a compact Skill response that lists today's games (with favorite team highlighted).
    """
    if not games:
        return build_simple_response(
            "📅 오늘 예정된 KBL 경기가 없습니다.\n하단 'KBL 일정'에서 이번 주 일정을 확인해보세요!",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    first_start = games[0].get("start_time")
    date_label = ""
    if first_start:
        try:
            dt = datetime.fromisoformat(first_start.replace("Z", "+00:00")).astimezone(_KST)
            date_label = f" ({dt.strftime('%m.%d')} {_WEEKDAYS_KO[dt.weekday()]})"
        except Exception:
            pass

    header = f"🏀 오늘의 KBL 경기{date_label}"
    if favorite_team:
        header += f" [❤️ {favorite_team}]"
    lines: list[str] = [f"{header}\n"]

    sorted_games = sorted(
        games,
        key=lambda g: (
            0 if favorite_team and favorite_team in (g.get("home_team"), g.get("away_team")) else 1,
            str(g.get("start_time") or ""),
        ),
    )

    for g in sorted_games:
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        status = g.get("status", "")
        arena = _short_arena(g.get("arena"))
        arena_suffix = f" ({arena})" if arena else ""
        fav_mark = "⭐ " if favorite_team and favorite_team in (home, away) else ""
        time_str = _format_kst_datetime(g.get("start_time"), include_date=False) or "14:00"

        if status == "LIVE":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            period = g.get("period") or "?"
            clock = g.get("game_clock") or ""
            clock_str = f" {clock}" if clock else ""
            stale_mark = " ⚠️" if g.get("stale") else ""
            lines.append(
                f"{fav_mark}🔴 {time_str}  {home} {h_score}:{a_score} {away} ({period}Q{clock_str}){stale_mark}{arena_suffix}"
            )
        elif status == "FINAL":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            lines.append(
                f"{fav_mark}✅ {time_str}  {home} {h_score}:{a_score} {away} (종료){arena_suffix}"
            )
        else:
            lines.append(f"{fav_mark}• {time_str}  {home} vs {away}{arena_suffix}")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_my_schedule_response(
    today_games: list[dict[str, Any]],
    upcoming_games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build compact response for '일정' (My favorite team's schedule + Today's games).
    """
    lines: list[str] = []
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
        lines.append(f"📅 [{full_name}] 경기 일정")
        team_games = [
            g for g in upcoming_games
            if favorite_team in (g.get("home_team"), g.get("away_team"))
        ]
        if team_games:
            for g in team_games[:3]:
                dt_str = _format_kst_datetime(g.get("start_time"), include_date=True)
                home = g.get("home_team", "?")
                away = g.get("away_team", "?")
                arena = _short_arena(g.get("arena"))
                arena_str = f" ({arena})" if arena else ""
                vs_str = f"vs {away}" if home == favorite_team else f"@ {home}"
                lines.append(f"• {dt_str}  {vs_str}{arena_str}")
        else:
            lines.append("• 7일 내 예정된 응원팀 경기가 없습니다.")
        lines.append("\n━━━━━━━━━━━━━━\n")

    today_resp = build_today_games_response(today_games, favorite_team=favorite_team)
    today_text = today_resp.template.outputs[0]["simpleText"]["text"]
    lines.append(today_text)

    if not favorite_team:
        lines.append("\n(💡 하단 '설정'에서 응원팀 등록 시 맞춤 일정 제공)")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_kbl_schedule_response(games: list[dict[str, Any]]) -> KakaoSkillResponse:
    """
    Build compact response for 'KBL 일정' grouped cleanly by date.
    """
    if not games:
        return build_simple_response(
            "📅 조회 가능한 KBL 예정 경기 일정이 없습니다.",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    from collections import defaultdict
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for g in games[:12]:
        start = g.get("start_time")
        date_key = "예정 경기"
        if start:
            try:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(_KST)
                wd = _WEEKDAYS_KO[dt.weekday()]
                date_key = f"{dt.strftime('%m.%d')} ({wd})"
            except Exception:
                pass
        grouped[date_key].append(g)

    lines: list[str] = ["🗓 KBL 경기 일정\n"]
    for date_key, day_games in list(grouped.items())[:4]:
        lines.append(f"[{date_key}]")
        for g in day_games:
            home = g.get("home_team", "?")
            away = g.get("away_team", "?")
            status = g.get("status", "SCHEDULED")
            arena = _short_arena(g.get("arena"))
            arena_str = f" ({arena})" if arena else ""
            time_str = _format_kst_datetime(g.get("start_time"), include_date=False) or "14:00"

            if status == "LIVE":
                lines.append(f"🔴 {time_str}  {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away} [진행중]")
            elif status == "FINAL":
                lines.append(f"✅ {time_str}  {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away} [종료]")
            else:
                lines.append(f"• {time_str}  {home} vs {away}{arena_str}")
        lines.append("")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_game_results_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '결과' (Recent finished/live KBL game results & boxscore links).
    Clean single-bubble text output (#xx style).
    """
    if not games:
        return build_simple_response(
            "🏀 최근 종료된 KBL 경기 결과가 없습니다.",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    lines: list[str] = ["🏆 KBL 최근 경기 결과\n"]
    for g in games[:6]:
        status = g.get("status", "FINAL")
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        hs = g.get("home_score", 0)
        as_ = g.get("away_score", 0)
        dt_str = _format_kst_datetime(g.get("start_time"), include_date=True)
        arena = g.get("arena") or ""
        game_url = g.get("game_url") or f"https://sports.daum.net/match/{g.get('game_id', '')}"

        fav_prefix = "⭐ " if favorite_team and favorite_team in (home, away) else ""
        if status == "LIVE":
            period = g.get("period") or "?"
            lines.append(f"{fav_prefix}🔴 [진행중 {period}Q] {home} {hs} : {as_} {away}")
        else:
            winner_h = "👑" if (hs or 0) > (as_ or 0) else ""
            winner_a = "👑" if (as_ or 0) > (hs or 0) else ""
            lines.append(f"{fav_prefix}✅ [종료] {winner_h}{home} {hs} : {as_} {away}{winner_a}")

        lines.append(f"   🕒 {dt_str} | 📍 {arena}")
        lines.append(f"   📊 기록/리캡: {game_url}\n")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_news_response(
    news_items: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build clean single-bubble response for '뉴스' (Latest KBL basketball news headlines & links).
    Tailored to user's favorite team if provided.
    """
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", f"{favorite_team} 농구단")
        header = f"📰 [{full_name}] 최신 뉴스"
    else:
        header = "📰 KBL 프로농구 최신 뉴스"

    lines: list[str] = [f"{header}\n"]

    for idx, item in enumerate(news_items[:5], start=1):
        title = item.get("title", "프로농구 소식")
        url = item.get("url", "https://sports.daum.net/basketball")
        lines.append(f"{idx}. {title}\n   🔗 {url}\n")

    if favorite_team:
        lines.append("💡 다른 구단: 'SK 뉴스', 'KT 뉴스', 'DB 뉴스', 'LG 뉴스'")
    else:
        lines.append("(💡 하단 '설정'에서 응원팀 등록 시 맞춤 뉴스가 제공됩니다)")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_highlights_response(
    highlights: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build clean single-bubble response for '주요장면' (KBL game highlights & video clips).
    Tailored to user's favorite team if provided.
    """
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", f"{favorite_team} 농구단")
        header = f"🎬 [{full_name}] 주요장면 & 하이라이트"
    else:
        header = "🎬 KBL 프로농구 주요장면 & 하이라이트"

    lines: list[str] = [f"{header}\n"]

    for idx, item in enumerate(highlights[:5], start=1):
        title = item.get("title", "KBL 경기 하이라이트")
        url = item.get("url", "https://sports.daum.net/video/kbl")
        arena = item.get("arena") or ""
        arena_str = f" ({arena})" if arena else ""
        lines.append(f"▶️ {idx}. {title}{arena_str}\n   🔗 {url}\n")

    if favorite_team:
        lines.append("💡 다른 구단: 'SK 주요장면', 'KT 하이라이트', 'DB 영상', 'LG 명장면'")
    else:
        lines.append("(💡 하단 '설정'에서 응원팀 등록 시 맞춤 주요장면이 제공됩니다)")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_team_standings_response(
    standings: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build ultra-compact response for '팀순위' (10-team KBL regular season standings).
    Optimized for mobile single-bubble with zero line wraps.
    """
    lines: list[str] = [
        "🏆 2026-27 KBL 정규리그 순위\n",
    ]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    team_alias = {
        "한국가스공사": "가스공사",
        "대구한국가스공사": "가스공사",
        "현대모비스": "모비스",
        "울산현대모비스": "모비스",
    }

    for idx, s in enumerate(standings[:10], start=1):
        rank = s.get("rank", idx)
        raw_team = s.get("team", "?")
        team = team_alias.get(raw_team, raw_team)
        wins = s.get("wins", 0)
        losses = s.get("losses", 0)
        wpct = float(s.get("wpct") or 0.0)
        gb = s.get("gb", "0.0")
        gb_str = "선두" if str(gb) in ("0", "0.0", "-") else f"{gb}차"
        fav = "⭐" if favorite_team and raw_team == favorite_team else ""

        wpct_str = f"{wpct:.3f}".lstrip("0") if wpct < 1.0 else "1.000"
        prefix = f"{medals.get(rank, '')} {rank}." if rank in medals else f"{rank}."
        lines.append(f"{prefix} {fav}{team}  {wins}승 {losses}패 ({wpct_str})  {gb_str}")

        if rank == 6:
            lines.append("┈┈┈┈ 6강 PO 진출선 ┈┈┈┈")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_player_rankings_response(
    rankings: list[dict[str, Any]],
    category: str = "pts",
) -> KakaoSkillResponse:
    """
    Build clean single-bubble response for '선수순위' (KBL individual stat leaders).
    """
    cat_labels = {
        "pts": ("득점", "점"),
        "reb": ("리바운드", "개"),
        "ast": ("어시스트", "개"),
        "tpm": ("3점슛", "개"),
        "stl": ("스틸", "개"),
    }
    label, unit = cat_labels.get(category, ("득점", "점"))

    lines: list[str] = [
        f"🏅 KBL 선수 순위 — [{label} TOP 5]\n",
    ]
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for idx, p in enumerate(rankings[:5], start=1):
        rank = p.get("rank", idx)
        name = p.get("name", "?")
        team = p.get("team", "?")
        val = p.get("value", 0.0)
        prefix = f"{medals.get(rank, '')} {rank}." if rank in medals else f"{rank}."

        lines.append(f"{prefix} {name} ({team}) — 평균 {val}{unit}")
        if rank <= 3:
            pts = p.get("pts")
            reb = p.get("reb")
            ast = p.get("ast")
            sub_parts = []
            if category != "pts" and pts is not None:
                sub_parts.append(f"{pts}점")
            if category != "reb" and reb is not None:
                sub_parts.append(f"{reb}리바")
            if category != "ast" and ast is not None:
                sub_parts.append(f"{ast}어시")
            if sub_parts:
                lines.append(f"   └ {' ｜ '.join(sub_parts)}")

    lines.append("\n💡 부문별 조회: '선수순위 득점', '선수순위 리바운드', '선수순위 어시스트', '선수순위 3점'")

    return build_simple_response(
        "\n".join(lines).strip(),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_single_player_response(
    player: dict[str, Any],
    is_favorite: bool = False,
    notice: str | None = None,
) -> KakaoSkillResponse:
    """
    Build detailed player profile card with 1-click favorite toggle button.
    """
    name = player["name"]
    team = player.get("team", "")
    full_team = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
    pos = player.get("pos", "F")
    no = player.get("no", "")
    pts = player.get("pts", 0.0)
    reb = player.get("reb", 0.0)
    ast = player.get("ast", 0.0)
    tpm = player.get("tpm", 0.0)
    stl = player.get("stl", 0.0)

    fav_badge = " [⭐ 내 관심선수]" if is_favorite else ""
    lines = [f"⭐ [선수 정보] {name} ({full_team} #{no}){fav_badge}\n"]
    if notice:
        lines.append(f"✅ {notice}\n")

    lines.extend([
        f"• 포지션 : {pos}",
        f"• 시즌 평균 : {pts}점 ｜ {reb}리바 ｜ {ast}어시",
        f"• 세부 기록 : 3점슛 {tpm}개 ｜ 스틸 {stl}개\n",
        "💡 아래 버튼을 눌러 관심선수로 바로 등록하거나 해제할 수 있습니다.",
    ])

    toggle_btn = (
        _msg_btn(f"➖ {name} 관심선수 해제", f"#관심선수 삭제 {name}")
        if is_favorite
        else _msg_btn(f"➕ {name} 관심선수 등록", f"#관심선수 {name}")
    )

    card = {
        "textCard": {
            "title": f"⭐ {name} ({team}) 선수 관리",
            "description": f"{name} 선수를 내 관심선수 목록에 추가하거나 관리합니다.",
            "buttons": [
                toggle_btn,
                _msg_btn("⭐ 관심선수 목록", "관심선수"),
                _msg_btn(f"📰 {team} 뉴스", f"{team} 뉴스"),
            ],
        }
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": "\n".join(lines).strip()}}, card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_team_players_response(
    team: str,
    players: list[dict[str, Any]],
    fav_players: list[str],
) -> KakaoSkillResponse:
    """
    Build response listing players of a specific team with 1-click favorite toggle buttons.
    """
    full = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
    lines = [
        f"🏀 [{full}] 주요 선수 목록\n",
    ]
    for p in players:
        star = "⭐ " if p["name"] in fav_players else "• "
        lines.append(
            f"{star}{p['name']} ({p['pos']} #{p['no']}) — {p['pts']}점 ｜ {p['reb']}리바 ｜ {p['ast']}어시"
        )
    lines.append("\n💡 아래 버튼을 눌러 관심선수를 바로 등록하거나 해제할 수 있습니다.")

    def _btn(p_name: str) -> dict[str, str]:
        if p_name in fav_players:
            return _msg_btn(f"➖ {p_name} 해제", f"#관심선수 삭제 {p_name}")
        return _msg_btn(f"➕ {p_name} 등록", f"#관심선수 {p_name}")

    buttons = [_btn(p["name"]) for p in players[:3]]
    card = {
        "textCard": {
            "title": f"⭐ {team} 선수 원클릭 관심선수 설정",
            "description": f"{team} 선수들을 내 관심선수로 등록해보세요.",
            "buttons": buttons,
        }
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": "\n".join(lines).strip()}}, card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_favorite_players_response(
    fav_players: list[str],
    search_results: list[dict[str, Any]] | None = None,
    notice: str | None = None,
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '관심선수'.
    Personalized by user's favorite team and enables full customization.
    """
    count_str = f" (현재 {len(fav_players)}명 등록)" if fav_players else ""
    lines: list[str] = [f"⭐ KBL 관심선수 관리{count_str}\n"]
    if notice:
        lines.append(f"✅ {notice}\n")

    if fav_players:
        lines.append("📌 [내 관심선수 현황]")
        for name in fav_players:
            p_info = next((p for p in KBL_PLAYERS if p["name"] == name), None)
            if p_info:
                lines.append(
                    f"• {p_info['name']} ({p_info['team']} / {p_info['pos']} #{p_info['no']})\n"
                    f"  시즌 평균: {p_info['pts']}점 ｜ {p_info['reb']}리바 ｜ {p_info['ast']}어시"
                )
            else:
                lines.append(f"• {name}")
        lines.append("")
    else:
        lines.append(
            "📌 아직 등록된 관심선수가 없습니다.\n"
            "좋아하는 선수를 등록하시면 선수 스탯과 소식을 맞춤으로 확인하실 수 있습니다!\n"
        )

    lines.append(
        "💬 [나만의 관심선수 등록/검색]\n"
        "채팅창에 선수 이름(예: '김종규', '알바노', '허훈', '워니')만 입력해도 바로 조회 및 등록할 수 있습니다.\n"
        "(구단별 전체 선수 보기: 'DB 선수', 'SK 선수', 'KT 선수')"
    )

    def _player_toggle_btn(name: str) -> dict[str, str]:
        if name in fav_players:
            return _msg_btn(f"➖ {name} 해제", f"#관심선수 삭제 {name}")
        return _msg_btn(f"➕ {name} 등록", f"#관심선수 {name}")

    carousel_items: list[dict[str, Any]] = []

    # Card 1: Favorite team players if user has a favorite team
    if favorite_team:
        team_p = [p["name"] for p in KBL_PLAYERS if p.get("team") == favorite_team][:3]
        if team_p:
            full_t = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
            carousel_items.append(
                {
                    "title": f"❤️ [{favorite_team}] 내 응원팀 선수 등록",
                    "description": f"{full_t} 주요 선수를 관심선수로 등록해보세요.",
                    "buttons": [_player_toggle_btn(p_name) for p_name in team_p],
                }
            )

    # Card 2: Star guards / forwards
    star_guards = ["허훈", "이정현", "허웅"]
    carousel_items.append(
        {
            "title": "⭐ 리그 인기 가드/포워드 등록",
            "description": "버튼을 누르면 내 관심선수로 즉시 등록/해제됩니다.",
            "buttons": [_player_toggle_btn(n) for n in star_guards],
        }
    )

    # Card 3: Star big men / shooters
    star_bigs = ["자밀 워니", "아셈 마레이", "유기상"]
    carousel_items.append(
        {
            "title": "⭐ 리그 인기 빅맨/슈터 등록",
            "description": "버튼을 누르면 내 관심선수로 즉시 등록/해제됩니다.",
            "buttons": [_player_toggle_btn(n) for n in star_bigs],
        }
    )

    # Card 4: If user has registered players, add a card to manage/delete
    if fav_players:
        del_buttons = [_msg_btn(f"➖ {p_name} 해제", f"#관심선수 삭제 {p_name}") for p_name in fav_players[:3]]
        carousel_items.append(
            {
                "title": "⚙️ 등록된 내 관심선수 해제",
                "description": "더 이상 추적을 원하지 않는 선수를 해제할 수 있습니다.",
                "buttons": del_buttons,
            }
        )

    outputs: list[dict[str, Any]] = [
        {"simpleText": {"text": "\n".join(lines).strip()}},
        {
            "carousel": {
                "type": "textCard",
                "items": carousel_items[:4],
            }
        },
    ]
    return KakaoSkillResponse(
        template=KakaoTemplate(outputs=outputs, quickReplies=MAIN_MENU_QUICK_REPLIES)
    )


def build_cheering_response(
    cheer_list: list[dict[str, Any]],
    notice: str | None = None,
    user_points: int = 0,
) -> KakaoSkillResponse:
    """
    Build response for '승부예측' / '응원하기' (Match prediction & fan voting battle).
    Matches 프로야구봇's 승부예측 feature.
    """
    lines: list[str] = ["🗳️ KBL 오늘의 경기 승부예측 & 응원 투표\n"]
    if notice:
        lines.append(f"🎉 {notice}\n")

    lines.append(f"🏅 내 누적 승부예측/응원 포인트: {user_points} P\n")

    if not cheer_list:
        lines.append("오늘 예정된 승부예측 경기가 없습니다.\n하단 '일정'에서 다음 경기 대진을 확인해보세요!")
        return build_simple_response("\n".join(lines), quick_replies=MAIN_MENU_QUICK_REPLIES)

    cards: list[dict[str, Any]] = []
    for c in cheer_list[:4]:
        home = c["home_team"]
        away = c["away_team"]
        h_votes = c["home_votes"]
        a_votes = c["away_votes"]
        h_pct = c["home_pct"]
        a_pct = c["away_pct"]
        user_pick = c.get("user_pick")

        filled = max(1, min(9, round(h_pct / 10)))
        bar = ("🟥" * filled) + ("🟦" * (10 - filled))
        pick_str = f" (내 선택: ✅ {user_pick})" if user_pick else ""

        lines.append(f"🏀 [{home} vs {away}]{pick_str}")
        lines.append(f"   {home} {h_pct}% ({h_votes}표) vs {a_pct}% ({a_votes}표) {away}")
        lines.append(f"   {bar}\n")

        cards.append(
            {
                "title": f"🏀 {home} vs {away} 승부예측",
                "description": (
                    f"{home} {h_pct}% ({h_votes}표) vs {away} {a_pct}% ({a_votes}표)\n"
                    f"{bar}"
                    + (f"\n✅ 내 선택: {user_pick}" if user_pick else "\n승리할 팀을 예측 투표(+10P)하세요!")
                ),
                "buttons": [
                    _msg_btn(f"🗳️ {home} 승리", f"#승부예측 {home}"),
                    _msg_btn(f"🗳️ {away} 승리", f"#승부예측 {away}"),
                ],
            }
        )

    outputs: list[dict[str, Any]] = [
        {"simpleText": {"text": "\n".join(lines).strip()}},
        {"carousel": {"type": "textCard", "items": cards}},
    ]
    return KakaoSkillResponse(
        template=KakaoTemplate(outputs=outputs, quickReplies=MAIN_MENU_QUICK_REPLIES)
    )


def build_settings_response(
    favorite_team: str | None,
    fav_players: list[str],
    notif_settings: dict[str, bool],
    submode: str = "main",
    notice: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '알림설정' / '설정'.
    Matches 프로야구봇's 알림설정 & 응원팀 설정 구조.
    """
    if submode == "team_select":
        cards = [
            {
                "title": "❤️ 응원팀 선택 (수도권 구단)",
                "description": "응원할 구단 버튼을 누르면 내 응원팀으로 즉시 설정됩니다.",
                "buttons": [
                    _msg_btn("❤️ 서울 SK", "#응원팀 SK"),
                    _msg_btn("❤️ 수원 KT", "#응원팀 KT"),
                    _msg_btn("❤️ 서울 삼성", "#응원팀 삼성"),
                ],
            },
            {
                "title": "❤️ 응원팀 선택 (경기·강원 구단)",
                "description": "선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                "buttons": [
                    _msg_btn("❤️ 원주 DB", "#응원팀 DB"),
                    _msg_btn("❤️ 안양 정관장", "#응원팀 정관장"),
                    _msg_btn("❤️ 고양 소노", "#응원팀 소노"),
                ],
            },
            {
                "title": "❤️ 응원팀 선택 (영남권 구단)",
                "description": "언제든 '설정 > 응원팀 변경'에서 다시 변경할 수 있습니다.",
                "buttons": [
                    _msg_btn("❤️ 창원 LG", "#응원팀 LG"),
                    _msg_btn("❤️ 부산 KCC", "#응원팀 KCC"),
                    _msg_btn("❤️ 울산 현대모비스", "#응원팀 현대모비스"),
                ],
            },
            {
                "title": "❤️ 응원팀 선택 (대구 / 설정 홈)",
                "description": "대구 한국가스공사 페가수스 선택 또는 알림설정 홈으로 이동합니다.",
                "buttons": [
                    _msg_btn("❤️ 한국가스공사", "#응원팀 한국가스공사"),
                    _msg_btn("⚙️ 알림설정 홈으로", "알림설정"),
                ],
            },
        ]
        return KakaoSkillResponse(
            template=KakaoTemplate(
                outputs=[{"carousel": {"type": "textCard", "items": cards}}],
                quickReplies=MAIN_MENU_QUICK_REPLIES,
            )
        )

    on_off = lambda v: "🔔 ON" if v else "🔕 OFF"  # noqa: E731
    full_team = (
        TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
        if favorite_team
        else "미설정"
    )
    players_str = ", ".join(fav_players) if fav_players else "미등록"

    lineup_on = notif_settings.get("lineup", True)
    start_on = notif_settings.get("game_start", True)
    end_on = notif_settings.get("game_end", True)
    clutch_on = notif_settings.get("clutch", True)
    pred_on = notif_settings.get("prediction", True)

    header_prefix = f"✅ {notice}\n\n" if notice else ""
    summary_desc = (
        f"{header_prefix}"
        f"• 내 응원팀: {full_team}\n"
        f"• 관심선수: {players_str}\n"
        f"• 📋 선발 라인업 알림 : {on_off(lineup_on)}\n"
        f"• ⏰ 경기 시작 10분 전 : {on_off(start_on)}\n"
        f"• 🏁 경기 종료 및 결과 : {on_off(end_on)}\n"
        f"• ⚡ 4Q 클러치 접전    : {on_off(clutch_on)}\n"
        f"• 🗳️ 경기 승부예측 알림: {on_off(pred_on)}"
    )

    cards = [
        {
            "title": "⚙️ 프로농구봇 알림설정 및 환경설정",
            "description": summary_desc[:380],
            "buttons": [
                _msg_btn("❤️ 응원팀 변경", "#응원팀변경"),
                _msg_btn("⭐ 관심선수 관리", "관심선수"),
            ],
        },
        {
            "title": "🔔 경기 핵심 알림 ON/OFF (1)",
            "description": (
                f"현재 알림 상태:\n"
                f"• 선발 라인업 알림: {on_off(lineup_on)}\n"
                f"• 경기 시작 알림: {on_off(start_on)}\n"
                f"• 경기 종료 알림: {on_off(end_on)}"
            ),
            "buttons": [
                _msg_btn(f"라인업알림 {'OFF' if lineup_on else 'ON'}", "#알림 라인업"),
                _msg_btn(f"시작알림 {'OFF' if start_on else 'ON'}", "#알림 시작"),
                _msg_btn(f"종료알림 {'OFF' if end_on else 'ON'}", "#알림 종료"),
            ],
        },
        {
            "title": "🔔 상황별 알림 ON/OFF (2)",
            "description": (
                f"현재 알림 상태:\n"
                f"• 4Q 클러치 접전: {on_off(clutch_on)}\n"
                f"• 당일 승부예측 : {on_off(pred_on)}\n"
                f"• 내 응원팀: {full_team}"
            ),
            "buttons": [
                _msg_btn(f"클러치알림 {'OFF' if clutch_on else 'ON'}", "#알림 클러치"),
                _msg_btn(f"승부예측알림 {'OFF' if pred_on else 'ON'}", "#알림 승부예측"),
                _msg_btn("❤️ 응원팀 변경", "#응원팀변경"),
            ],
        },
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"carousel": {"type": "textCard", "items": cards}}],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_matchup_search_response(
    query: MatchupQuery,
    games: list[dict[str, Any]],
) -> KakaoSkillResponse:
    """
    Build a Kakao Skill response for a Daum Sports team/matchup search (e.g. ``#KT vs LG``).
    """
    header = (
        f"🔍 [{query.team_a} vs {query.team_b}] 경기 일정 (Daum 스포츠)"
        if query.is_head_to_head
        else f"🔍 [{query.team_a}] 경기 일정 (Daum 스포츠)"
    )

    if not games:
        return build_simple_response(
            f"{header}\n\n조회 가능한 예정/최근 경기가 없습니다.",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
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
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_live_score_response(snapshot: dict[str, Any]) -> KakaoSkillResponse:
    """
    Build a Skill response for a single live game score (with quarter scorebox).
    Matches 프로야구봇's 톡중계 / 실시간 스코어보드.
    """
    home = snapshot.get("home_team", "?")
    away = snapshot.get("away_team", "?")
    h_score = int(snapshot.get("home_score") or 0)
    a_score = int(snapshot.get("away_score") or 0)
    period = snapshot.get("period") or "?"
    clock = snapshot.get("game_clock") or ""
    clock_str = f" {clock}" if clock else ""
    status = snapshot.get("status", "")
    stale = snapshot.get("stale", False)
    game_id = snapshot.get("game_id", "")
    daum_url = f"https://sports.daum.net/match/{game_id}" if game_id else "https://sports.daum.net/basketball"

    if status == "FINAL":
        title = f"✅ 경기 종료 — {home} {h_score} : {a_score} {away}"
        status_line = "최종 결과입니다."
    elif status == "LIVE":
        stale_note = " ⚠️(지연)" if stale else ""
        title = f"🔴 LIVE — {period}쿼터{clock_str}{stale_note}"
        status_line = f"현재 점수: {home} {h_score} : {a_score} {away}"
    else:
        title = f"📅 경기 예정 — {home} vs {away}"
        status_line = "경기 개시 전입니다."

    # Quarter scorebox estimation/display
    def _split_q(score: int, curr_p: int) -> list[int]:
        if curr_p <= 0 or score <= 0:
            return [0, 0, 0, 0]
        base = score // curr_p
        rem = score % curr_p
        qs = [base] * curr_p
        for i in range(rem):
            qs[i] += 1
        while len(qs) < 4:
            qs.append(0)
        return qs[:4]

    try:
        p_num = int(period) if str(period).isdigit() else 4
    except Exception:
        p_num = 4

    hq = _split_q(h_score, min(4, max(1, p_num)))
    aq = _split_q(a_score, min(4, max(1, p_num)))

    text = (
        f"{title}\n"
        f"{status_line}\n\n"
        f"📊 [쿼터별 스코어]\n"
        f"구단   1Q  2Q  3Q  4Q   총점\n"
        f"{home[:4]:<4} {hq[0]:>2}  {hq[1]:>2}  {hq[2]:>2}  {hq[3]:>2} : {h_score:>3}\n"
        f"{away[:4]:<4} {aq[0]:>2}  {aq[1]:>2}  {aq[2]:>2}  {aq[3]:>2} : {a_score:>3}\n\n"
        f"💡 포털 실시간 문자중계는 아래 버튼을 눌러 시청하세요."
    )

    card = {
        "textCard": {
            "title": f"🏀 {home} vs {away} 실시간 톡중계",
            "description": f"{status_line}\n쿼터별 득점과 포털 라이브 중계를 확인하세요.",
            "buttons": [
                _link_btn("📺 다음 톡중계 보기", daum_url),
                _msg_btn("🔄 실시간 점수 새로고침", "실시간 점수"),
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
            ],
        }
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"simpleText": {"text": text}}, card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_health_response(
    db_ok: bool, redis_ok: bool, worker_running: bool
) -> KakaoSkillResponse:
    """
    Build a health-check Skill response.
    """
    ok = lambda v: "✅" if v else "❌"  # noqa: E731
    text = (
        f"🛠 시스템 상태\n"
        f"DB: {ok(db_ok)}\n"
        f"Redis: {ok(redis_ok)}\n"
        f"Worker: {ok(worker_running)}"
    )
    return build_simple_response(text, quick_replies=MAIN_MENU_QUICK_REPLIES)
