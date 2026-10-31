"""Factory functions for building Kakao Skill response payloads (Pro Basketball Bot MVP)."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apps.kakao.schemas import (
    KakaoSkillResponse,
    KakaoTemplate,
    QuickReply,
)
from services.content.kbl_data import KBL_PLAYERS, TEAM_INFO
from services.search.parser import KBL_TEAMS, MatchupQuery

_KST = ZoneInfo("Asia/Seoul")
_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 10 core menu QuickReplies matching https://pf.kakao.com/_HhRnC (프로야구봇 -> 프로농구봇)
MAIN_MENU_QUICK_REPLIES: list[QuickReply] = [
    QuickReply(label="일정", messageText="일정"),
    QuickReply(label="KBL 일정", messageText="KBL 일정"),
    QuickReply(label="결과", messageText="결과"),
    QuickReply(label="뉴스", messageText="뉴스"),
    QuickReply(label="주요장면", messageText="주요장면"),
    QuickReply(label="관심선수", messageText="관심선수"),
    QuickReply(label="팀순위", messageText="팀순위"),
    QuickReply(label="선수순위", messageText="선수순위"),
    QuickReply(label="응원하기", messageText="응원하기"),
    QuickReply(label="설정", messageText="설정"),
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
    """Build the Pro Basketball Bot welcome / home menu response."""
    team_label = (
        f"❤️ 응원팀: {TEAM_INFO.get(favorite_team, {}).get('full_name', favorite_team)}"
        if favorite_team
        else "❤️ 응원팀: 미설정 ('설정'에서 응원팀을 선택해보세요!)"
    )
    players_label = (
        f"⭐ 관심선수: {', '.join(fav_players)}"
        if fav_players
        else "⭐ 관심선수: 미설정 ('관심선수'에서 선수를 등록해보세요!)"
    )
    text = (
        "🏀 프로농구봇 (KBL 공식 데이터·Daum 스포츠 연동)\n\n"
        f"{team_label}\n"
        f"{players_label}\n\n"
        "📌 [이용 가능 메뉴]\n"
        "• 일정 : 내 응원팀 맞춤 일정 및 오늘 경기\n"
        "• KBL 일정 : 주간 KBL 전체 경기 일정\n"
        "• 결과 : 최근 종료된 경기 스코어 및 기록\n"
        "• 뉴스 : KBL 실시간 최신 뉴스\n"
        "• 주요장면 : 경기별 하이라이트 영상\n"
        "• 관심선수 : 내 관심선수 등록 및 시즌 스탯\n"
        "• 팀순위 : 10개 구단 정규리그 순위표\n"
        "• 선수순위 : 득점·리바운드·어시스트 개인 순위\n"
        "• 응원하기 : 오늘 경기 승부예측 & 실시간 응원 투표\n"
        "• 설정 : 응원팀·관심선수·알림 ON/OFF 설정\n\n"
        "💡 아래 버튼을 누르거나 '#KT vs LG'처럼 검색해보세요!"
    )
    return build_simple_response(text, quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_today_games_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build a Skill response that lists today's games (with favorite team highlighted).
    """
    if not games:
        return build_simple_response(
            "📅 오늘 예정된 KBL 경기가 없습니다.\n'KBL 일정' 또는 '결과' 메뉴에서 전체 일정을 확인해보세요!",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    header = "🏀 오늘의 KBL 경기"
    if favorite_team:
        header += f" (❤️ 내 응원팀: {favorite_team})"
    lines: list[str] = [f"{header}\n"]
    status_emoji = {"LIVE": "🔴", "SCHEDULED": "📅", "FINAL": "✅"}

    # Sort favorite team's game to the top if favorite_team is set
    sorted_games = sorted(
        games,
        key=lambda g: (
            0 if favorite_team and favorite_team in (g.get("home_team"), g.get("away_team")) else 1,
            str(g.get("start_time") or ""),
        ),
    )

    for g in sorted_games:
        emoji = status_emoji.get(g.get("status", ""), "⚪")
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        status = g.get("status", "")
        arena = g.get("arena") or ""
        arena_suffix = f" | {arena}" if arena else ""
        fav_mark = (
            "⭐ "
            if favorite_team and favorite_team in (home, away)
            else ""
        )

        if status == "LIVE":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            period = g.get("period") or "?"
            clock = g.get("game_clock") or ""
            clock_str = f" {clock}" if clock else ""
            stale_mark = " ⚠️" if g.get("stale") else ""
            lines.append(
                f"{fav_mark}{emoji} {home} {h_score} - {a_score} {away}"
                f"  ({period}쿼터{clock_str}){stale_mark}{arena_suffix}"
            )
        elif status == "FINAL":
            h_score = g.get("home_score", 0)
            a_score = g.get("away_score", 0)
            lines.append(
                f"{fav_mark}{emoji} {home} {h_score} - {a_score} {away}  [종료]{arena_suffix}"
            )
        else:
            time_str = _format_kst_datetime(g.get("start_time"), include_date=False)
            lines.append(f"{fav_mark}{emoji} {home} vs {away}  {time_str}{arena_suffix}")

    return build_simple_response(
        "\n".join(lines),
        quick_replies=MAIN_MENU_QUICK_REPLIES,
    )


def build_my_schedule_response(
    today_games: list[dict[str, Any]],
    upcoming_games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '일정' (My favorite team's schedule + Today's games).
    """
    lines: list[str] = []
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
        lines.append(f"📅 [{full_name}] 경기 일정\n")
        team_games = [
            g for g in upcoming_games
            if favorite_team in (g.get("home_team"), g.get("away_team"))
        ]
        if team_games:
            for g in team_games[:4]:
                dt_str = _format_kst_datetime(g.get("start_time"), include_date=True)
                home = g.get("home_team", "?")
                away = g.get("away_team", "?")
                arena = g.get("arena") or "경기장 미정"
                status = g.get("status", "SCHEDULED")
                if status == "LIVE":
                    lines.append(
                        f"🔴 [진행중] {home} {g.get('home_score', 0)} - {g.get('away_score', 0)} {away}\n"
                        f"   🕒 {dt_str} | 📍 {arena}"
                    )
                elif status == "FINAL":
                    lines.append(
                        f"✅ [종료] {home} {g.get('home_score', 0)} - {g.get('away_score', 0)} {away}\n"
                        f"   🕒 {dt_str} | 📍 {arena}"
                    )
                else:
                    lines.append(f"🏀 {dt_str} | {home} vs {away} ({arena})")
            lines.append("")
        else:
            lines.append("다가오는 7일 내 예정된 응원팀 경기가 없습니다.\n")
    else:
        lines.append("💡 '설정' 메뉴에서 응원팀을 등록하시면 내 응원팀 일정을 가장 먼저 받아보실 수 있습니다!\n")

    # Append today's KBL games summary
    lines.append("━━━━━━━━━━━━━━")
    today_resp = build_today_games_response(today_games, favorite_team=favorite_team)
    today_text = today_resp.template.outputs[0]["simpleText"]["text"]
    lines.append(today_text)

    return build_simple_response("\n".join(lines), quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_kbl_schedule_response(games: list[dict[str, Any]]) -> KakaoSkillResponse:
    """
    Build response for 'KBL 일정' (Full upcoming 7-day KBL schedule).
    """
    if not games:
        return build_simple_response(
            "📅 조회 가능한 KBL 예정 경기 일정이 없습니다.",
            quick_replies=MAIN_MENU_QUICK_REPLIES,
        )

    lines: list[str] = ["🗓 KBL 프로농구 주요 경기 일정\n"]
    status_emoji = {"LIVE": "🔴", "SCHEDULED": "📅", "FINAL": "✅"}

    for g in games[:8]:
        status = g.get("status", "SCHEDULED")
        emoji = status_emoji.get(status, "📅")
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        dt_str = _format_kst_datetime(g.get("start_time"), include_date=True)
        arena = g.get("arena") or ""
        arena_str = f" ({arena})" if arena else ""

        if status == "LIVE":
            lines.append(
                f"{emoji} {dt_str} | {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away} [진행중]{arena_str}"
            )
        elif status == "FINAL":
            lines.append(
                f"{emoji} {dt_str} | {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away} [종료]{arena_str}"
            )
        else:
            lines.append(f"{emoji} {dt_str} | {home} vs {away}{arena_str}")

    lines.append("\n🎟 티켓 예매: https://www.kbl.or.kr/ticket")
    lines.append("📊 전체 일정: https://sports.daum.net/schedule/kbl")

    return build_simple_response("\n".join(lines), quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_game_results_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '결과' (Recent finished/live KBL game results & boxscore links).
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

    return build_simple_response("\n".join(lines).strip(), quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_news_response(
    news_items: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '뉴스' (Latest KBL basketball news headlines & links).
    """
    title_suffix = f" ({favorite_team})" if favorite_team else ""
    lines: list[str] = [f"📰 KBL 프로농구 최신 뉴스{title_suffix}\n"]

    for idx, item in enumerate(news_items[:5], start=1):
        title = item.get("title", "프로농구 소식")
        url = item.get("url", "https://sports.daum.net/basketball")
        lines.append(f"{idx}. {title}\n   🔗 {url}\n")

    lines.append("🌐 Daum 농구 뉴스 홈: https://sports.daum.net/basketball")
    return build_simple_response("\n".join(lines).strip(), quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_highlights_response(highlights: list[dict[str, Any]]) -> KakaoSkillResponse:
    """
    Build response for '주요장면' (KBL game highlights & video clips).
    """
    lines: list[str] = ["🎬 KBL 프로농구 주요장면 & 하이라이트\n"]

    for idx, item in enumerate(highlights[:5], start=1):
        title = item.get("title", "KBL 경기 하이라이트")
        url = item.get("url", "https://sports.daum.net/video/kbl")
        arena = item.get("arena") or ""
        arena_str = f" ({arena})" if arena else ""
        lines.append(f"▶️ {idx}. {title}{arena_str}\n   🔗 {url}\n")

    return build_simple_response("\n".join(lines).strip(), quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_team_standings_response(
    standings: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '팀순위' (10-team KBL regular season standings).
    """
    lines: list[str] = [
        "🏆 2026-27 KBL 정규리그 팀 순위\n",
        "순위 | 구단 | 승-패 | 승률 | 게임차 | 연속",
        "──────────────────────",
    ]

    for s in standings[:10]:
        rank = s.get("rank", "?")
        team = s.get("team", "?")
        wins = s.get("wins", 0)
        losses = s.get("losses", 0)
        wpct = float(s.get("wpct") or 0.0)
        gb = s.get("gb", "0.0")
        streak = s.get("streak", "-")
        star = "⭐" if favorite_team and team == favorite_team else ""
        lines.append(
            f"{rank}위 {star}{team} | {wins}승 {losses}패 | {wpct:.3f} | {gb} | {streak}"
        )

    lines.append("\n📊 상세 순위표: https://sports.daum.net/record/kbl/team")
    return build_simple_response("\n".join(lines), quick_replies=MAIN_MENU_QUICK_REPLIES)


def build_player_rankings_response(
    rankings: list[dict[str, Any]],
    category: str = "pts",
) -> KakaoSkillResponse:
    """
    Build response for '선수순위' (KBL individual stat leaders by category).
    """
    cat_labels = {
        "pts": ("득점(PTS)", "점"),
        "reb": ("리바운드(REB)", "개"),
        "ast": ("어시스트(AST)", "개"),
        "tpm": ("3점슛(3PM)", "개"),
        "stl": ("스틸(STL)", "개"),
    }
    label, unit = cat_labels.get(category, ("득점(PTS)", "점"))

    lines: list[str] = [
        f"🏅 KBL 개인 순위 — [{label} 부문]\n",
    ]
    for p in rankings[:7]:
        rank = p.get("rank", "?")
        name = p.get("name", "?")
        team = p.get("team", "?")
        val = p.get("value", 0.0)
        lines.append(
            f"{rank}위 {name} ({team}) — 평균 {val}{unit}\n"
            f"   (득점 {p.get('pts')} / 리바 {p.get('reb')} / 어시 {p.get('ast')})"
        )

    lines.append("\n💡 아래 버튼으로 부문별 순위를 전환하거나 '#관심선수 선수명'으로 등록해보세요!")

    cat_qrs: list[QuickReply] = [
        QuickReply(label="🏀 득점순위", messageText="선수순위 득점"),
        QuickReply(label="🏀 리바운드순위", messageText="선수순위 리바운드"),
        QuickReply(label="🏀 어시스트순위", messageText="선수순위 어시스트"),
        QuickReply(label="🏀 3점슛순위", messageText="선수순위 3점"),
        QuickReply(label="🏀 스틸순위", messageText="선수순위 스틸"),
        QuickReply(label="관심선수", messageText="관심선수"),
        QuickReply(label="팀순위", messageText="팀순위"),
        QuickReply(label="일정", messageText="일정"),
        QuickReply(label="결과", messageText="결과"),
        QuickReply(label="설정", messageText="설정"),
    ]
    return build_simple_response("\n".join(lines), quick_replies=cat_qrs)


def build_favorite_players_response(
    fav_players: list[str],
    search_results: list[dict[str, Any]] | None = None,
    notice: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '관심선수' (My favorite players + stats + 1-click add/remove buttons).
    """
    lines: list[str] = ["⭐ KBL 관심선수 & 선수 기록 조회\n"]
    if notice:
        lines.append(f"✅ {notice}\n")

    if fav_players:
        lines.append(f"📌 내 관심선수 ({len(fav_players)}명):")
        for name in fav_players:
            p_info = next((p for p in KBL_PLAYERS if p["name"] == name), None)
            if p_info:
                lines.append(
                    f"• {p_info['name']} ({p_info['team']} / {p_info['pos']} #{p_info['no']})\n"
                    f"  시즌 평균: {p_info['pts']}점 | {p_info['reb']}리바 | {p_info['ast']}어시 | 3점 {p_info['tpm']}개"
                )
            else:
                lines.append(f"• {name}")
        lines.append("")
    else:
        lines.append("📌 아직 등록된 관심선수가 없습니다.\n아래 추천 선수 버튼을 누르거나 '#관심선수 허훈'처럼 입력해 등록해보세요!\n")

    if search_results:
        lines.append("🔍 [선수 검색/추천 목록]")
        for p in search_results[:5]:
            lines.append(
                f"• {p['name']} ({p['team']}, {p['pos']}) — {p['pts']}점 / {p['reb']}리바 / {p['ast']}어시"
            )

    qrs: list[QuickReply] = []
    # Provide 1-click toggle buttons for popular star players
    star_names = ["허훈", "자밀 워니", "이정현", "허웅", "유기상", "아셈 마레이"]
    for s_name in star_names:
        if s_name in fav_players:
            qrs.append(QuickReply(label=f"➖ {s_name} 해제", messageText=f"#관심선수 삭제 {s_name}"))
        else:
            qrs.append(QuickReply(label=f"➕ {s_name} 등록", messageText=f"#관심선수 {s_name}"))

    qrs.extend([
        QuickReply(label="선수순위", messageText="선수순위"),
        QuickReply(label="일정", messageText="일정"),
        QuickReply(label="응원하기", messageText="응원하기"),
        QuickReply(label="설정", messageText="설정"),
    ])
    return build_simple_response("\n".join(lines).strip(), quick_replies=qrs[:10])


def build_cheering_response(
    cheer_list: list[dict[str, Any]],
    notice: str | None = None,
    user_points: int = 0,
) -> KakaoSkillResponse:
    """
    Build response for '응원하기' (Match prediction & live cheering vote battle).
    """
    lines: list[str] = ["📣 KBL 오늘의 경기 응원하기 & 승부예측\n"]
    if notice:
        lines.append(f"🎉 {notice}\n")

    lines.append(f"🏅 내 누적 응원/예측 포인트: {user_points} P\n")

    qrs: list[QuickReply] = []

    if not cheer_list:
        lines.append("오늘 진행 중인 응원 경기가 없습니다.")
        return build_simple_response("\n".join(lines), quick_replies=MAIN_MENU_QUICK_REPLIES)

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

        if len(qrs) <= 6:
            qrs.append(QuickReply(label=f"📣 {home} 응원", messageText=f"#응원 {home}"))
            qrs.append(QuickReply(label=f"📣 {away} 응원", messageText=f"#응원 {away}"))

    lines.append("💡 아래 구단 응원 버튼을 누르면 응원 투표(+10P)가 즉시 반영됩니다!")

    qrs.extend([
        QuickReply(label="일정", messageText="일정"),
        QuickReply(label="결과", messageText="결과"),
        QuickReply(label="팀순위", messageText="팀순위"),
        QuickReply(label="설정", messageText="설정"),
    ])
    return build_simple_response("\n".join(lines).strip(), quick_replies=qrs[:10])


def build_settings_response(
    favorite_team: str | None,
    fav_players: list[str],
    notif_settings: dict[str, bool],
    submode: str = "main",
    notice: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '설정' (My favorite team, favorite players, and notification toggles).
    """
    if submode == "team_select":
        text = (
            "❤️ 응원하는 KBL 구단을 선택해주세요!\n\n"
            "선택 즉시 '일정', '결과', '팀순위', '뉴스'에서 내 응원팀 정보가 최우선으로 표시됩니다."
        )
        team_qrs = [
            QuickReply(label=f"❤️ {t}", messageText=f"#응원팀 {t}")
            for t in KBL_TEAMS
        ]
        return build_simple_response(text, quick_replies=team_qrs[:10])

    on_off = lambda v: "🔔 ON" if v else "🔕 OFF"  # noqa: E731
    full_team = (
        TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
        if favorite_team
        else "미설정"
    )
    players_str = ", ".join(fav_players) if fav_players else "미등록"

    lines: list[str] = ["⚙️ 프로농구봇 개인화 및 알림 설정\n"]
    if notice:
        lines.append(f"✅ {notice}\n")

    lines.append(f"• 내 응원팀 : {full_team}")
    lines.append(f"• 관심선수  : {players_str}")
    lines.append("• 경기 시작 10분 전 알림 : " + on_off(notif_settings.get("game_start", True)))
    lines.append("• 경기 종료 결과 알림    : " + on_off(notif_settings.get("game_end", False)))
    lines.append("• 4쿼터 접전(클러치) 알림 : " + on_off(notif_settings.get("clutch", False)))
    lines.append("\n💡 아래 버튼을 눌러 응원팀 변경 및 알림 수신 여부를 즉시 설정하세요!")

    qrs: list[QuickReply] = [
        QuickReply(label="❤️ 응원팀 변경", messageText="#응원팀변경"),
        QuickReply(
            label=f"시작알림 {'OFF' if notif_settings.get('game_start', True) else 'ON'}",
            messageText="#알림 시작",
        ),
        QuickReply(
            label=f"종료알림 {'OFF' if notif_settings.get('game_end', False) else 'ON'}",
            messageText="#알림 종료",
        ),
        QuickReply(
            label=f"클러치알림 {'OFF' if notif_settings.get('clutch', False) else 'ON'}",
            messageText="#알림 클러치",
        ),
        QuickReply(label="⭐ 관심선수 관리", messageText="관심선수"),
        QuickReply(label="일정", messageText="일정"),
        QuickReply(label="KBL 일정", messageText="KBL 일정"),
        QuickReply(label="결과", messageText="결과"),
        QuickReply(label="팀순위", messageText="팀순위"),
        QuickReply(label="응원하기", messageText="응원하기"),
    ]
    return build_simple_response("\n".join(lines), quick_replies=qrs[:10])


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
    Build a Skill response for a single live game score.
    """
    home = snapshot.get("home_team", "?")
    away = snapshot.get("away_team", "?")
    h_score = snapshot.get("home_score", 0)
    a_score = snapshot.get("away_score", 0)
    period = snapshot.get("period") or "?"
    clock = snapshot.get("game_clock") or ""
    clock_str = f" {clock}" if clock else ""
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
            f"🔴 LIVE — {period}쿼터{clock_str}\n"
            f"{home} {h_score} - {a_score} {away}{stale_note}"
        )
    else:
        text = f"📅 경기 예정\n{home} vs {away}"

    return build_simple_response(
        text,
        quick_replies=MAIN_MENU_QUICK_REPLIES,
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
