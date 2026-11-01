"""Factory functions for building Kakao Skill response payloads (Pro Basketball Bot MVP)."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apps.kakao.schemas import (
    KakaoSkillResponse,
    KakaoTemplate,
    QuickReply,
)
from services.content.kbl_data import (
    DEFAULT_SPORTS_LOGO,
    KBL_PLAYERS,
    TEAM_INFO,
    TEAM_LINEUPS,
    TEAM_LOGOS,
    get_team_lineup,
    get_team_logo,
)
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


def _list_card(
    header_title: str,
    items: list[dict[str, Any]],
    buttons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build native Kakao listCard component (max 5 items, max 2 buttons)."""
    card_items = []
    for it in items[:5]:
        item_dict: dict[str, Any] = {"title": str(it.get("title", ""))[:35]}
        if it.get("description"):
            item_dict["description"] = str(it["description"])[:30]
        if it.get("imageUrl"):
            item_dict["imageUrl"] = str(it["imageUrl"])
        if it.get("link"):
            item_dict["link"] = it["link"]
        card_items.append(item_dict)

    card: dict[str, Any] = {
        "header": {"title": header_title[:30]},
        "items": card_items,
    }
    if buttons:
        card["buttons"] = buttons[:2]
    return {"listCard": card}


def _item_card(
    head_title: str | None = None,
    image_title: dict[str, str] | None = None,
    item_list: list[dict[str, str]] | None = None,
    summary: dict[str, str] | None = None,
    buttons: list[dict[str, str]] | None = None,
    thumbnail_url: str | None = None,
) -> dict[str, Any]:
    """Build native Kakao itemCard component (table key-values, title <= 6 chars)."""
    card: dict[str, Any] = {}
    thumb = thumbnail_url or (image_title.get("imageUrl") if image_title else None)
    if thumb:
        card["thumbnail"] = {"imageUrl": thumb, "width": 300, "height": 300}
    if head_title:
        card["head"] = {"title": head_title[:15]}
    if image_title:
        card["imageTitle"] = {
            "title": str(image_title.get("title", ""))[:30],
            "description": str(image_title.get("description", ""))[:30],
            "imageUrl": str(image_title.get("imageUrl", "")),
        }
    if item_list:
        card["itemList"] = [
            {"title": str(it.get("title", ""))[:6], "description": str(it.get("description", ""))[:30]}
            for it in item_list[:10]
        ]
    if summary:
        card["itemListSummary"] = {
            "title": str(summary.get("title", ""))[:6],
            "description": str(summary.get("description", ""))[:30],
        }
    if buttons:
        card["buttons"] = buttons[:3]
    return {"itemCard": card}


def _basic_card(
    title: str,
    description: str,
    thumbnail_url: str | None = None,
    buttons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a single basicCard dict (with official Daum logo thumbnail)."""
    card: dict[str, Any] = {
        "title": title[:30],
        "description": description[:400],
    }
    if thumbnail_url:
        card["thumbnail"] = {"imageUrl": thumbnail_url}
    if buttons:
        card["buttons"] = buttons[:3]
    return card


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
    Build a standardised error response with buttons (no speech bubbles).
    """
    card = {
        "textCard": {
            "title": "ℹ️ KBL 프로농구 안내",
            "description": user_message,
            "buttons": [
                _msg_btn("📅 오늘 경기", "오늘 경기"),
                _msg_btn("🏆 정규리그 순위", "팀순위"),
            ],
        }
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
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
            _basic_card(
                title="❤️ 응원팀 선택 (수도권 구단)",
                description="서울 SK, 수원 KT, 서울 삼성\n응원할 구단 버튼을 누르면 내 응원팀으로 즉시 설정됩니다.",
                thumbnail_url=TEAM_LOGOS.get("SK", DEFAULT_SPORTS_LOGO),
                buttons=[
                    _msg_btn("❤️ 서울 SK", "#응원팀 SK"),
                    _msg_btn("❤️ 수원 KT", "#응원팀 KT"),
                    _msg_btn("❤️ 서울 삼성", "#응원팀 삼성"),
                ],
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (경기·강원 구단)",
                description="원주 DB, 안양 정관장, 고양 소노\n선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                thumbnail_url=TEAM_LOGOS.get("DB", DEFAULT_SPORTS_LOGO),
                buttons=[
                    _msg_btn("❤️ 원주 DB", "#응원팀 DB"),
                    _msg_btn("❤️ 안양 정관장", "#응원팀 정관장"),
                    _msg_btn("❤️ 고양 소노", "#응원팀 소노"),
                ],
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (영남권 구단)",
                description="창원 LG, 부산 KCC, 울산 현대모비스\n선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                thumbnail_url=TEAM_LOGOS.get("LG", DEFAULT_SPORTS_LOGO),
                buttons=[
                    _msg_btn("❤️ 창원 LG", "#응원팀 LG"),
                    _msg_btn("❤️ 부산 KCC", "#응원팀 KCC"),
                    _msg_btn("❤️ 울산 현대모비스", "#응원팀 현대모비스"),
                ],
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (대구 한국가스공사)",
                description="대구 한국가스공사 페가수스를 내 응원팀으로 설정합니다.",
                thumbnail_url=TEAM_LOGOS.get("한국가스공사", DEFAULT_SPORTS_LOGO),
                buttons=[
                    _msg_btn("❤️ 한국가스공사", "#응원팀 한국가스공사"),
                    _msg_btn("📅 오늘 경기 보기", "오늘 경기"),
                    _msg_btn("🏆 정규리그 순위표", "팀순위"),
                ],
            ),
        ]
        return KakaoSkillResponse(
            template=KakaoTemplate(
                outputs=[
                    {"carousel": {"type": "basicCard", "items": team_cards}},
                ],
                quickReplies=MAIN_MENU_QUICK_REPLIES,
            )
        )

    full_team = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
    action_card = {
        "basicCard": _basic_card(
            title=f"🏀 {full_team}",
            description=f"내 응원팀 설정 완료! ❤️\n하단 버튼을 눌러 오늘 경기와 일정을 확인하세요.",
            thumbnail_url=get_team_logo(favorite_team),
            buttons=[
                _msg_btn("📅 오늘 경기", "오늘 경기"),
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
                _msg_btn("📋 선발 라인업", "라인업"),
            ],
        )
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[action_card],
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
        card = _list_card(
            header_title="📋 KBL 선발 라인업",
            items=[{
                "title": "오늘 예정된 KBL 경기가 없습니다.",
                "description": "경기 시작 약 1시간 전 확정 라인업이 등록됩니다.",
                "imageUrl": DEFAULT_SPORTS_LOGO,
            }],
            buttons=[
                _msg_btn("📅 경기 일정 보기", "일정"),
                _msg_btn("🏆 정규리그 순위", "팀순위"),
            ],
        )
        return KakaoSkillResponse(
            template=KakaoTemplate(outputs=[card], quickReplies=MAIN_MENU_QUICK_REPLIES)
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
            _basic_card(
                title=f"📋 {home} vs {away} 선발 라인업",
                description=(
                    f"• {home}: {h_card_names} 외 2명\n"
                    f"• {away}: {a_card_names} 외 2명\n"
                    f"※ 경기 시작 약 1시간 전 공식 확정"
                ),
                thumbnail_url=get_team_logo(home),
                buttons=[
                    _msg_btn("🗳️ 승부예측", f"#승부예측 {home}"),
                    _msg_btn("🔴 실시간 스코어", "실시간 점수"),
                    _msg_btn("🔔 라인업 알림설정", "알림설정"),
                ],
            )
        )

    outputs: list[dict[str, Any]] = [
        {"carousel": {"type": "basicCard", "items": cards}},
    ]
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
        card = _list_card(
            header_title="📋 KBL 경기 요약",
            items=[{
                "title": "최근 종료된 경기 요약 데이터가 없습니다.",
                "description": "경기가 종료되면 승리팀 및 MVP 리캡이 제공됩니다.",
                "imageUrl": DEFAULT_SPORTS_LOGO,
            }],
            buttons=[
                _msg_btn("🏆 경기 결과 보기", "결과"),
                _msg_btn("📅 오늘 경기 보기", "오늘 경기"),
            ],
        )
        return KakaoSkillResponse(
            template=KakaoTemplate(outputs=[card], quickReplies=MAIN_MENU_QUICK_REPLIES)
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

    item_card_output = _item_card(
        head_title="📋 경기 요약",
        image_title={
            "title": f"👑 {winner} 승리 ({hs}:{as_})",
            "description": f"{home} vs {away} 경기 리캡",
            "imageUrl": get_team_logo(winner),
        },
        item_list=[
            {"title": "경기MVP", "description": f"{mvp['name']} ({mvp['pts']}점 {mvp['reb']}리바)"},
            {"title": "승리구단", "description": f"{winner} ({diff}점 차 승)"},
            {"title": "승부처", "description": ("접전 역전승" if diff <= 5 else f"{diff}점 차 완승")},
        ],
        summary={"title": "한줄평", "description": clutch_msg[:30]},
        buttons=[
            _msg_btn("🎬 주요장면 영상", f"{winner} 주요장면"),
            _msg_btn("🏆 정규리그 순위표", "팀순위"),
            _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
        ],
    )

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[item_card_output],
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
        card = _list_card(
            header_title="🏀 오늘의 KBL 경기",
            items=[{
                "title": "오늘 예정된 KBL 경기가 없습니다.",
                "description": "하단 버튼을 눌러 이번 주 전체 일정을 확인하세요.",
                "imageUrl": DEFAULT_SPORTS_LOGO,
            }],
            buttons=[
                _msg_btn("📅 경기 일정 보기", "일정"),
                _msg_btn("🏆 정규리그 순위", "팀순위"),
            ],
        )
        return KakaoSkillResponse(
            template=KakaoTemplate(outputs=[card], quickReplies=MAIN_MENU_QUICK_REPLIES)
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

    items: list[dict[str, Any]] = []
    for g in sorted_games[:5]:
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        status = g.get("status", "")
        time_str = _format_kst_datetime(g.get("start_time"), include_date=False) or "14:00"
        arena = _short_arena(g.get("arena"))
        arena_str = f" [{arena}]" if arena else ""
        gid = g.get("game_id", "")
        match_url = f"https://sports.daum.net/match/{gid}" if gid else "https://sports.daum.net/basketball"

        if status == "LIVE":
            title = f"🔴 {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{time_str}{arena_str} | {g.get('period', '?')}Q 진행중"
        elif status == "FINAL":
            title = f"✅ {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{time_str}{arena_str} | 최종 종료"
        else:
            title = f"📅 {home} vs {away}"
            desc = f"{time_str}{arena_str} | 경기 예정"

        logo_team = away if (favorite_team and home != favorite_team and away == favorite_team) else home
        items.append({
            "title": title,
            "description": desc,
            "imageUrl": get_team_logo(logo_team),
            "link": {"web": match_url},
        })

    list_card_output = _list_card(
        header_title=f"🏀 오늘의 KBL 경기{date_label}"[:30],
        items=items,
        buttons=[
            _msg_btn("🔴 실시간 점수", "실시간 점수"),
            _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
        ],
    )

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[list_card_output],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_my_schedule_response(
    today_games: list[dict[str, Any]],
    upcoming_games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '일정' (My favorite team's schedule + upcoming games).
    Returns pure listCard with verified official logos and action buttons.
    """
    items: list[dict[str, Any]] = []

    target_games: list[dict[str, Any]] = []
    if favorite_team:
        target_games = [
            g for g in upcoming_games
            if favorite_team in (g.get("home_team"), g.get("away_team"))
        ]
    if not target_games:
        target_games = upcoming_games or today_games

    for g in target_games[:5]:
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        start = g.get("start_time")
        dt_str = _format_kst_datetime(start, include_date=True) or "일정 미정"
        arena = _short_arena(g.get("arena")) or "경기장 미정"

        status = g.get("status", "SCHEDULED")
        if status == "LIVE":
            title = f"🔴 {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 진행중"
        elif status == "FINAL":
            title = f"✅ {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 경기 종료"
        else:
            title = f"📅 {home} vs {away}"
            desc = f"{dt_str} [{arena}] | 경기 예정"

        logo_team = favorite_team if (favorite_team and favorite_team in (home, away)) else home
        items.append({
            "title": title,
            "description": desc,
            "imageUrl": get_team_logo(logo_team),
            "link": {"web": g.get("game_url") or f"https://sports.daum.net/match/{g.get('game_id', '')}"},
        })

    if not items:
        items.append({
            "title": "예정된 경기 일정이 없습니다.",
            "description": "새로운 경기 일정이 등록되면 업데이트됩니다.",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        })

    full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team) if favorite_team else "KBL 프로농구"
    header_title = f"📅 [{full_name}] 경기 일정" if favorite_team else "📅 KBL 경기 일정"

    card = _list_card(
        header_title=header_title,
        items=items,
        buttons=[
            _msg_btn("🗓️ KBL 전체 일정", "KBL 일정"),
            _msg_btn("🏆 정규리그 순위", "팀순위"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_kbl_schedule_response(games: list[dict[str, Any]]) -> KakaoSkillResponse:
    """
    Build response for 'KBL 일정'.
    Returns pure listCard with verified official logos and action buttons.
    """
    items: list[dict[str, Any]] = []
    for g in games[:5]:
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        dt_str = _format_kst_datetime(g.get("start_time"), include_date=True) or "일정 미정"
        arena = _short_arena(g.get("arena")) or "경기장 미정"
        status = g.get("status", "SCHEDULED")
        if status == "LIVE":
            title = f"🔴 {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 진행중"
        elif status == "FINAL":
            title = f"✅ {home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 종료"
        else:
            title = f"📅 {home} vs {away}"
            desc = f"{dt_str} [{arena}] | 예정"

        items.append({
            "title": title,
            "description": desc,
            "imageUrl": get_team_logo(home),
            "link": {"web": g.get("game_url") or f"https://sports.daum.net/match/{g.get('game_id', '')}"},
        })

    if not items:
        items.append({
            "title": "예정된 KBL 일정이 없습니다.",
            "description": "다음 라운드 경기 일정이 공지되면 안내해 드립니다.",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        })

    card = _list_card(
        header_title="🗓️ KBL 주간 경기 일정",
        items=items,
        buttons=[
            _msg_btn("🏀 오늘 경기 보기", "오늘 경기"),
            _msg_btn("🏆 정규리그 순위", "팀순위"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_game_results_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '결과' (Recent finished/live KBL game results).
    Returns pure listCard with verified official logos and action buttons.
    """
    items: list[dict[str, Any]] = []
    for g in games[:5]:
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        hs = g.get("home_score", 0)
        as_ = g.get("away_score", 0)
        dt_str = _format_kst_datetime(g.get("start_time"), include_date=True) or ""
        arena = _short_arena(g.get("arena")) or ""
        status = g.get("status", "FINAL")

        fav_mark = "⭐" if favorite_team and favorite_team in (home, away) else ""
        winner_team = home if (hs or 0) >= (as_ or 0) else away
        if status == "LIVE":
            title = f"🔴 {fav_mark}{home} {hs} : {as_} {away}"
            desc = f"{dt_str} [{arena}] | 진행중"
        else:
            title = f"✅ {fav_mark}{home} {hs} : {as_} {away}"
            desc = f"{dt_str} [{arena}] | 최종 종료"

        items.append({
            "title": title,
            "description": desc,
            "imageUrl": get_team_logo(winner_team),
            "link": {"web": g.get("game_url") or f"https://sports.daum.net/match/{g.get('game_id', '')}"},
        })

    if not items:
        items.append({
            "title": "최근 종료된 경기 결과가 없습니다.",
            "description": "오늘 경기가 종료되면 최종 스코어가 등록됩니다.",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        })

    card = _list_card(
        header_title="🏆 KBL 최근 경기 결과",
        items=items,
        buttons=[
            _msg_btn("📊 최근 경기 요약", "경기 요약"),
            _msg_btn("📅 오늘 경기 보기", "오늘 경기"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_news_response(
    news_items: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '뉴스'.
    Returns pure listCard with verified official logos and action buttons.
    """
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", f"{favorite_team} 농구단")
        header = f"📰 [{full_name}] 최신 뉴스"
        default_img = get_team_logo(favorite_team)
    else:
        header = "📰 KBL 프로농구 최신 뉴스"
        default_img = DEFAULT_SPORTS_LOGO

    items: list[dict[str, Any]] = []
    for item in news_items[:5]:
        title = item.get("title", "프로농구 소식")
        url = item.get("url", "https://sports.daum.net/basketball")
        items.append({
            "title": title,
            "description": "Daum 스포츠 농구 뉴스",
            "imageUrl": item.get("imageUrl") or default_img,
            "link": {"web": url},
        })

    if not items:
        items.append({
            "title": "최신 뉴스를 불러오는 중입니다.",
            "description": "Daum 스포츠에서 프로농구 뉴스를 확인하세요.",
            "imageUrl": default_img,
            "link": {"web": "https://sports.daum.net/basketball"},
        })

    card = _list_card(
        header_title=header,
        items=items,
        buttons=[
            _link_btn("🌐 다음 농구홈 바로가기", "https://sports.daum.net/basketball"),
            _msg_btn("🎬 주요장면 보기", "주요장면"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_highlights_response(
    highlights: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '주요장면'.
    Returns pure listCard with verified official logos and action buttons.
    """
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", f"{favorite_team} 농구단")
        header = f"🎬 [{full_name}] 주요장면 & 하이라이트"
        default_img = get_team_logo(favorite_team)
    else:
        header = "🎬 KBL 프로농구 주요장면 & 하이라이트"
        default_img = DEFAULT_SPORTS_LOGO

    items: list[dict[str, Any]] = []
    for item in highlights[:5]:
        title = item.get("title", "KBL 경기 하이라이트")
        url = item.get("url") or "https://search.daum.net/search?w=vclip&q=KBL+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8"
        arena = item.get("arena") or "다음 동영상 클립"
        items.append({
            "title": title,
            "description": f"📍 {arena}",
            "imageUrl": item.get("imageUrl") or default_img,
            "link": {"web": url},
        })

    if not items:
        items.append({
            "title": "등록된 주요장면 영상이 없습니다.",
            "description": "Daum 스포츠 영상 센터에서 시청하실 수 있습니다.",
            "imageUrl": default_img,
            "link": {"web": "https://search.daum.net/search?w=vclip&q=KBL+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8"},
        })

    card = _list_card(
        header_title=header,
        items=items,
        buttons=[
            _link_btn("🎬 다음 영상 전체보기", "https://search.daum.net/search?w=vclip&q=KBL+%ED%94%84%EB%A1%9C%EB%86%8D%EA%B5%AC+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8"),
            _link_btn("📺 KBL TV 공식 유튜브", "https://www.youtube.com/@kbl_official"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_team_standings_response(
    standings: list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build pure card response for '팀순위' (10-team KBL regular season standings).
    Uses 2 listCards (Rank 1-5 and Rank 6-10) with verified team logos and buttons.
    """
    team_alias = {
        "한국가스공사": "가스공사",
        "대구한국가스공사": "가스공사",
        "현대모비스": "모비스",
        "울산현대모비스": "모비스",
    }

    def _make_item(s: dict[str, Any], idx: int) -> dict[str, Any]:
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
        return {
            "title": f"{rank}위 {fav}{team}",
            "description": f"{wins}승 {losses}패 (승률 {wpct_str}) | {gb_str}",
            "imageUrl": get_team_logo(raw_team),
            "link": {"web": "https://sports.daum.net/record/kbl"},
        }

    top_items = [_make_item(s, i) for i, s in enumerate(standings[:5], start=1)]
    bottom_items = [_make_item(s, i) for i, s in enumerate(standings[5:10], start=6)]

    card1 = _list_card(
        header_title="🏆 2026-27 KBL 순위 (1~5위)",
        items=top_items or [{
            "title": "순위 집계 중",
            "description": "KBL 순위 데이터",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        }],
        buttons=[
            _msg_btn("🏅 선수 순위 보기", "선수순위"),
            _link_btn("📊 전체 순위·기록 상세", "https://sports.daum.net/record/kbl"),
        ],
    )

    outputs = [card1]
    if bottom_items:
        card2 = _list_card(
            header_title="🏆 2026-27 KBL 순위 (6~10위)",
            items=bottom_items,
            buttons=[
                _msg_btn("🏀 오늘 경기 보기", "오늘 경기"),
                _msg_btn("📅 경기 일정 보기", "일정"),
            ],
        )
        outputs.append(card2)

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=outputs,
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_player_rankings_response(
    rankings: list[dict[str, Any]],
    category: str = "pts",
) -> KakaoSkillResponse:
    """
    Build pure card response for '선수순위' (KBL individual stat leaders).
    Returns listCard with verified team logos and category toggle buttons.
    """
    cat_labels = {
        "pts": ("득점", "점"),
        "reb": ("리바운드", "개"),
        "ast": ("도움/어시스트", "개"),
        "tpm": ("3점슛", "개"),
        "stl": ("스틸", "개"),
        "blk": ("블록슛", "개"),
    }
    label, unit = cat_labels.get(category, ("득점", "점"))

    items: list[dict[str, Any]] = []
    for idx, p in enumerate(rankings[:5], start=1):
        rank = p.get("rank", idx)
        name = p.get("name", "?")
        team = p.get("team", "?")
        val = p.get("value", 0.0)
        items.append({
            "title": f"{rank}위 {name} ({team})",
            "description": f"시즌 평균 {val}{unit}",
            "imageUrl": get_team_logo(team),
            "link": {"web": "https://sports.daum.net/record/kbl"},
        })

    if not items:
        items.append({
            "title": "선수 순위를 집계 중입니다.",
            "description": "KBL 공식 기록실에서 확인하세요.",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        })

    next_cat_map = {
        "pts": ("ast", "도움(어시스트)", "어시스트순위"),
        "ast": ("reb", "리바운드", "리바운드순위"),
        "reb": ("stl", "스틸", "스틸순위"),
        "stl": ("blk", "블록슛", "블록순위"),
        "blk": ("pts", "득점", "득점순위"),
        "tpm": ("pts", "득점", "득점순위"),
    }
    next_cat, next_label, next_msg = next_cat_map.get(category, ("ast", "어시스트", "어시스트순위"))

    card = _list_card(
        header_title=f"🏅 KBL 선수 순위 [{label} TOP 5]",
        items=items,
        buttons=[
            _msg_btn(f"🏀 {next_label} TOP 5", next_msg),
            _link_btn("📊 선수 기록 전체보기", "https://sports.daum.net/record/kbl"),
        ],
    )

    player_rank_quick_replies: list[QuickReply] = [
        QuickReply(label="🏀 득점", messageText="득점순위"),
        QuickReply(label="🏀 어시스트", messageText="어시스트순위"),
        QuickReply(label="🏀 리바운드", messageText="리바운드순위"),
        QuickReply(label="🏀 블록슛", messageText="블록순위"),
        QuickReply(label="🏀 스틸", messageText="스틸순위"),
        QuickReply(label="🏀 3점슛", messageText="3점슛순위"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="📅 오늘 경기", messageText="오늘 경기"),
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=player_rank_quick_replies,
        )
    )


def build_single_player_response(
    player: dict[str, Any],
    is_favorite: bool = False,
    notice: str | None = None,
) -> KakaoSkillResponse:
    """
    Build detailed player profile card with 1-click favorite toggle button.
    Returns pure basicCard with verified team logo.
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

    fav_badge = "⭐ 관심선수 등록됨\n" if is_favorite else ""
    notice_str = f"✅ {notice}\n" if notice else ""

    toggle_btn = (
        _msg_btn(f"➖ {name} 관심선수 해제", f"#관심선수 삭제 {name}")
        if is_favorite
        else _msg_btn(f"➕ {name} 관심선수 등록", f"#관심선수 {name}")
    )

    card = {
        "basicCard": _basic_card(
            title=f"⭐ {name} ({team} #{no})",
            description=(
                f"{notice_str}{fav_badge}"
                f"• 포지션: {pos} ({full_team})\n"
                f"• 시즌 평균: {pts}점 | {reb}리바 | {ast}어시\n"
                f"• 세부 기록: 3점슛 {tpm}개 | 스틸 {stl}개"
            ),
            thumbnail_url=get_team_logo(team),
            buttons=[
                toggle_btn,
                _msg_btn("⭐ 관심선수 목록", "관심선수"),
                _msg_btn(f"📰 {team} 뉴스", f"{team} 뉴스"),
            ],
        )
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_team_players_response(
    team: str,
    players: list[dict[str, Any]],
    fav_players: list[str],
) -> KakaoSkillResponse:
    """
    Build response listing players of a specific team.
    Returns pure listCard with verified team logo and action buttons.
    """
    full = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
    items = []
    for p in players[:5]:
        star = "⭐ " if p["name"] in fav_players else ""
        items.append({
            "title": f"{star}{p['name']} ({p['pos']} #{p['no']})",
            "description": f"평균 {p['pts']}점 | {p['reb']}리바 | {p['ast']}어시",
            "imageUrl": get_team_logo(team),
            "link": {"web": "https://sports.daum.net/record/kbl"},
        })
    if not items:
        items.append({
            "title": f"{team} 등록 선수가 없습니다.",
            "description": "선수 명단이 업데이트 중입니다.",
            "imageUrl": get_team_logo(team),
        })

    card = _list_card(
        header_title=f"🏀 [{full}] 주요 선수 목록",
        items=items,
        buttons=[
            _msg_btn("⭐ 관심선수 관리", "관심선수"),
            _msg_btn(f"📰 {team} 뉴스", f"{team} 뉴스"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
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
    Returns pure visual cards (listCard + carousel) without speech bubbles.
    """
    items = []
    if fav_players:
        for name in fav_players[:5]:
            p_info = next((p for p in KBL_PLAYERS if p["name"] == name), None)
            if p_info:
                p_team = p_info["team"]
                items.append({
                    "title": f"⭐ {p_info['name']} ({p_team} #{p_info['no']})",
                    "description": f"시즌 평균: {p_info['pts']}점 | {p_info['reb']}리바 | {p_info['ast']}어시",
                    "imageUrl": get_team_logo(p_team),
                    "link": {"web": "https://sports.daum.net/record/kbl"},
                })
            else:
                items.append({
                    "title": f"⭐ {name}",
                    "description": "내 등록 관심선수",
                    "imageUrl": DEFAULT_SPORTS_LOGO,
                })
    else:
        items.append({
            "title": "등록된 관심선수가 없습니다.",
            "description": "아래 카드 버튼을 눌러 좋아하는 선수를 등록해보세요!",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        })

    header_title = "⭐ 내 관심선수 현황"
    if notice:
        header_title = f"✅ {notice}"

    list_card = _list_card(
        header_title=header_title,
        items=items,
        buttons=[
            _msg_btn("⭐ 관심선수 등록 안내", "관심선수"),
            _msg_btn("🏅 전체 선수 순위", "선수순위"),
        ],
    )

    def _player_toggle_btn(name: str) -> dict[str, str]:
        if name in fav_players:
            return _msg_btn(f"➖ {name} 해제", f"#관심선수 삭제 {name}")
        return _msg_btn(f"➕ {name} 등록", f"#관심선수 {name}")

    carousel_items: list[dict[str, Any]] = []

    if favorite_team:
        team_p = [p["name"] for p in KBL_PLAYERS if p.get("team") == favorite_team][:3]
        if team_p:
            full_t = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
            carousel_items.append(
                _basic_card(
                    title=f"❤️ [{favorite_team}] 응원팀 선수",
                    description=f"{full_t} 선수를 관심선수로 등록하세요.",
                    thumbnail_url=get_team_logo(favorite_team),
                    buttons=[_player_toggle_btn(p_name) for p_name in team_p],
                )
            )

    star_guards = ["허훈", "이정현", "허웅"]
    carousel_items.append(
        _basic_card(
            title="⭐ 인기 가드/포워드 등록",
            description="버튼을 누르면 즉시 등록/해제됩니다.",
            thumbnail_url=get_team_logo("KT"),
            buttons=[_player_toggle_btn(n) for n in star_guards],
        )
    )

    star_bigs = ["자밀 워니", "아셈 마레이", "유기상"]
    carousel_items.append(
        _basic_card(
            title="⭐ 인기 빅맨/슈터 등록",
            description="버튼을 누르면 즉시 등록/해제됩니다.",
            thumbnail_url=get_team_logo("SK"),
            buttons=[_player_toggle_btn(n) for n in star_bigs],
        )
    )

    if fav_players:
        del_buttons = [_msg_btn(f"➖ {p_name} 해제", f"#관심선수 삭제 {p_name}") for p_name in fav_players[:3]]
        carousel_items.append(
            _basic_card(
                title="⚙️ 관심선수 간편 해제",
                description="추적을 원하지 않는 선수를 해제하세요.",
                thumbnail_url=DEFAULT_SPORTS_LOGO,
                buttons=del_buttons,
            )
        )

    outputs = [list_card]
    if carousel_items:
        outputs.append({"carousel": {"type": "basicCard", "items": carousel_items[:4]}})

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
    Returns pure carousel of basicCard with verified logos and prediction buttons.
    """
    if not cheer_list:
        card = _list_card(
            header_title="🗳️ KBL 오늘의 경기 승부예측",
            items=[{
                "title": "오늘 예정된 승부예측 경기가 없습니다.",
                "description": f"내 누적 포인트: {user_points} P | 다음 경기 일정에서 확인하세요.",
                "imageUrl": DEFAULT_SPORTS_LOGO,
            }],
            buttons=[
                _msg_btn("📅 경기 일정 보기", "일정"),
                _msg_btn("🏆 정규리그 순위", "팀순위"),
            ],
        )
        return KakaoSkillResponse(
            template=KakaoTemplate(outputs=[card], quickReplies=MAIN_MENU_QUICK_REPLIES)
        )

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

        desc_prefix = f"🎉 {notice}\n" if notice else ""
        pick_str = f"✅ 내 선택: {user_pick} 승리" if user_pick else f"승리팀 예측 투표(+10P) / 누적 {user_points}P"

        cards.append(
            _basic_card(
                title=f"🏀 {home} vs {away} 승부예측",
                description=(
                    f"{desc_prefix}"
                    f"{home} {h_pct}% ({h_votes}표) vs {away} {a_pct}% ({a_votes}표)\n"
                    f"{bar}\n"
                    f"{pick_str}"
                ),
                thumbnail_url=get_team_logo(home),
                buttons=[
                    _msg_btn(f"🗳️ {home} 승리", f"#승부예측 {home}"),
                    _msg_btn(f"🗳️ {away} 승리", f"#승부예측 {away}"),
                ],
            )
        )

    cheer_quick_replies = [
        QuickReply(label="💰 내 포인트 확인", messageText="포인트"),
        QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="📋 라인업", messageText="라인업"),
        QuickReply(label="⚙️ 알림설정", messageText="알림설정"),
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"carousel": {"type": "basicCard", "items": cards}}],
            quickReplies=cheer_quick_replies,
        )
    )


def get_point_tier(points: int) -> tuple[str, str, int]:
    """
    Return (tier_name, badge_emoji, points_needed_for_next).
    Tier thresholds:
        - 0 ~ 49P: 🥉 루키 (새싹 팬)
        - 50 ~ 199P: 🥈 주전 (열혈 팬)
        - 200 ~ 499P: 🥇 올스타 (찐팬)
        - 500P 이상: 👑 KBL 레전드 (농구 마스터)
    """
    if points >= 500:
        return "👑 KBL 레전드", "👑", 0
    elif points >= 200:
        return "🥇 올스타", "🥇", 500 - points
    elif points >= 50:
        return "🥈 주전", "🥈", 200 - points
    else:
        return "🥉 루키", "🥉", 50 - points


def build_user_points_response(
    user_points: int,
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build rich basicCard response for '포인트' / '내 포인트' / '포인트 확인'.
    Displays total point balance, fan tier status, next tier progress, and point tips.
    """
    tier_name, badge, needed = get_point_tier(user_points)
    next_msg = (
        f"다음 등급까지 {needed}P 남음!"
        if needed > 0
        else "최고 등급 달성! 🎉"
    )
    fav_team_str = f" [{favorite_team} 팬]" if favorite_team else ""

    desc = (
        f"🏀 나의 승부예측 포인트 현황{fav_team_str}\n\n"
        f"• 보유 포인트 : {user_points:,} P\n"
        f"• 농구팬 등급 : {tier_name}\n"
        f"• 승급 현황 : {next_msg}\n\n"
        f"⚡ 포인트 적립 방법:\n"
        f"• 매일 경기 승부예측 투표 시: +10P\n"
        f"• 승리팀 적중 시 보너스: +30P\n"
        f"• 오늘의 경기 출석 체크: +10P\n\n"
        f"※ 모은 포인트는 팬 랭킹 배틀 및 기프티콘 이벤트 응모에 활용됩니다."
    )

    logo_url = get_team_logo(favorite_team) if favorite_team else DEFAULT_SPORTS_LOGO
    card = _basic_card(
        title=f"{badge} 내 승부예측 포인트: {user_points:,} P",
        description=desc[:380],
        thumbnail_url=logo_url,
        buttons=[
            _msg_btn("🗳️ 오늘 경기 승부예측", "승부예측"),
            _msg_btn("🏀 오늘 경기 보기", "오늘 경기"),
            _msg_btn("🏆 정규리그 순위", "팀순위"),
        ],
    )

    point_quick_replies = [
        QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
        QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="🏅 선수순위", messageText="선수순위"),
        QuickReply(label="📋 선발 라인업", messageText="라인업"),
        QuickReply(label="⚙️ 알림설정", messageText="알림설정"),
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"basicCard": card}],
            quickReplies=point_quick_replies,
        )
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
            _basic_card(
                title="❤️ 응원팀 선택 (수도권 구단)",
                description="서울 SK, 수원 KT, 서울 삼성\n구단 버튼을 누르면 내 응원팀으로 설정됩니다.",
                thumbnail_url=get_team_logo("SK"),
                buttons=[
                    _msg_btn("❤️ 서울 SK", "#응원팀 SK"),
                    _msg_btn("❤️ 수원 KT", "#응원팀 KT"),
                    _msg_btn("❤️ 서울 삼성", "#응원팀 삼성"),
                ],
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (경기·강원 구단)",
                description="원주 DB, 안양 정관장, 고양 소노\n선택 즉시 내 응원팀이 최우선 표시됩니다.",
                thumbnail_url=get_team_logo("DB"),
                buttons=[
                    _msg_btn("❤️ 원주 DB", "#응원팀 DB"),
                    _msg_btn("❤️ 안양 정관장", "#응원팀 정관장"),
                    _msg_btn("❤️ 고양 소노", "#응원팀 소노"),
                ],
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (영남권 구단)",
                description="창원 LG, 부산 KCC, 울산 현대모비스\n선택 즉시 내 응원팀이 최우선 표시됩니다.",
                thumbnail_url=get_team_logo("LG"),
                buttons=[
                    _msg_btn("❤️ 창원 LG", "#응원팀 LG"),
                    _msg_btn("❤️ 부산 KCC", "#응원팀 KCC"),
                    _msg_btn("❤️ 울산 현대모비스", "#응원팀 현대모비스"),
                ],
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (대구 한국가스공사)",
                description="대구 한국가스공사 페가수스를 내 응원팀으로 설정합니다.",
                thumbnail_url=get_team_logo("한국가스공사"),
                buttons=[
                    _msg_btn("❤️ 한국가스공사", "#응원팀 한국가스공사"),
                    _msg_btn("⚙️ 알림설정 홈으로", "알림설정"),
                ],
            ),
        ]
        return KakaoSkillResponse(
            template=KakaoTemplate(
                outputs=[{"carousel": {"type": "basicCard", "items": cards}}],
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

    logo_url = get_team_logo(favorite_team) if favorite_team else DEFAULT_SPORTS_LOGO
    cards = [
        _basic_card(
            title="⚙️ 프로농구봇 알림 및 환경설정",
            description=summary_desc[:380],
            thumbnail_url=logo_url,
            buttons=[
                _msg_btn("❤️ 응원팀 변경", "#응원팀변경"),
                _msg_btn("⭐ 관심선수 관리", "관심선수"),
            ],
        ),
        _basic_card(
            title="🔔 경기 핵심 알림 ON/OFF",
            description=(
                f"현재 알림 상태:\n"
                f"• 선발 라인업 알림: {on_off(lineup_on)}\n"
                f"• 경기 시작 알림: {on_off(start_on)}\n"
                f"• 경기 종료 알림: {on_off(end_on)}"
            ),
            thumbnail_url=DEFAULT_SPORTS_LOGO,
            buttons=[
                _msg_btn(f"라인업알림 {'OFF' if lineup_on else 'ON'}", "#알림 라인업"),
                _msg_btn(f"시작알림 {'OFF' if start_on else 'ON'}", "#알림 시작"),
                _msg_btn(f"종료알림 {'OFF' if end_on else 'ON'}", "#알림 종료"),
            ],
        ),
        _basic_card(
            title="🔔 상황별 알림 ON/OFF",
            description=(
                f"현재 알림 상태:\n"
                f"• 4Q 클러치 접전: {on_off(clutch_on)}\n"
                f"• 당일 승부예측 : {on_off(pred_on)}\n"
                f"• 내 응원팀: {full_team}"
            ),
            thumbnail_url=DEFAULT_SPORTS_LOGO,
            buttons=[
                _msg_btn(f"클러치알림 {'OFF' if clutch_on else 'ON'}", "#알림 클러치"),
                _msg_btn(f"승부예측알림 {'OFF' if pred_on else 'ON'}", "#알림 승부예측"),
                _msg_btn("❤️ 응원팀 변경", "#응원팀변경"),
            ],
        ),
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"carousel": {"type": "basicCard", "items": cards}}],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_matchup_search_response(
    query: MatchupQuery,
    games: list[dict[str, Any]],
) -> KakaoSkillResponse:
    """
    Build a Kakao Skill response for a Daum Sports team/matchup search (e.g. ``#KT vs LG``).
    Returns pure listCard with verified team logos and action buttons.
    """
    header = (
        f"🔍 [{query.team_a} vs {query.team_b}] 맞대결"
        if query.is_head_to_head
        else f"🔍 [{query.team_a}] 경기 일정"
    )

    items = []
    for g in games[:5]:
        status = g.get("status", "SCHEDULED")
        home = g.get("home_team", "?")
        away = g.get("away_team", "?")
        dt_str = _format_kst_datetime(g.get("start_time"), include_date=True) or ""
        arena = _short_arena(g.get("arena")) or "경기장 미정"
        game_url = g.get("game_url") or f"https://sports.daum.net/match/{g.get('game_id', '')}"

        if status == "LIVE":
            title = f"🔴 {home} {g.get('home_score', 0)} : {g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 진행중"
        elif status == "FINAL":
            title = f"✅ {home} {g.get('home_score', 0)} : {g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 최종 종료"
        else:
            title = f"📅 {home} vs {away}"
            desc = f"{dt_str} [{arena}] | 경기 예정"

        items.append({
            "title": title,
            "description": desc,
            "imageUrl": get_team_logo(home),
            "link": {"web": game_url},
        })

    if not items:
        items.append({
            "title": "조회 가능한 경기가 없습니다.",
            "description": "Daum 스포츠에서 최신 일정을 확인하세요.",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        })

    card = _list_card(
        header_title=header,
        items=items,
        buttons=[
            _link_btn("🌐 다음 농구홈 바로가기", "https://sports.daum.net/basketball"),
            _msg_btn("🏀 오늘 경기 보기", "오늘 경기"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_live_score_response(snapshot: dict[str, Any]) -> KakaoSkillResponse:
    """
    Build a Skill response for a single live game score (with quarter scorebox).
    Returns pure itemCard with verified official logos and action buttons.
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

    stale_note = " ⚠️(지연)" if stale else ""
    if status == "FINAL":
        head_title = "✅ 경기 종료"
        img_title = f"{home} {h_score} : {a_score} {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | 최종 스코어"
    elif status == "LIVE":
        head_title = "🔴 LIVE 톡중계"
        img_title = f"{home} {h_score} : {a_score} {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | {period}쿼터{clock_str}{stale_note}"
    else:
        head_title = "📅 경기 예정"
        img_title = f"{home} vs {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | 경기 시작 전"

    item_card_output = _item_card(
        head_title=head_title,
        image_title={
            "title": img_title,
            "description": img_desc,
            "imageUrl": get_team_logo(home),
        },
        item_list=[
            {"title": "1쿼터", "description": f"{home[:3]} {hq[0]} : {aq[0]} {away[:3]}"},
            {"title": "2쿼터", "description": f"{home[:3]} {hq[1]} : {aq[1]} {away[:3]}"},
            {"title": "3쿼터", "description": f"{home[:3]} {hq[2]} : {aq[2]} {away[:3]}"},
            {"title": "4쿼터", "description": f"{home[:3]} {hq[3]} : {aq[3]} {away[:3]}"},
        ],
        summary={
            "title": "최종점수" if status == "FINAL" else "현재점수",
            "description": f"{home[:3]} {h_score} : {a_score} {away[:3]}",
        },
        buttons=[
            _link_btn("📺 다음 톡중계 보기", daum_url),
            _msg_btn("🔄 실시간 점수 새로고침", "실시간 점수"),
            _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[item_card_output],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_health_response(
    db_ok: bool, redis_ok: bool, worker_running: bool
) -> KakaoSkillResponse:
    """
    Build a health-check Skill response with buttons (no speech bubbles).
    """
    ok = lambda v: "✅ 정상" if v else "❌ 장애"  # noqa: E731
    card = {
        "textCard": {
            "title": "🛠 프로농구봇 시스템 상태",
            "description": (
                f"• PostgreSQL DB: {ok(db_ok)}\n"
                f"• Redis 캐시: {ok(redis_ok)}\n"
                f"• 실시간 수집 워커: {ok(worker_running)}"
            ),
            "buttons": [
                _msg_btn("📅 오늘 경기", "오늘 경기"),
                _msg_btn("처음으로", "처음으로"),
            ],
        }
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_notice_response() -> KakaoSkillResponse:
    """
    Build response for '공지' / '소식' / '채널소개'.
    Returns pure listCard with channel announcements matching 프로야구봇 (_HhRnC).
    """
    items = [
        {
            "title": "🏀 KBL 프로농구봇 정식 오픈 안내",
            "description": "카톡에서 실시간 스코어·일정·승부예측까지!",
            "imageUrl": DEFAULT_SPORTS_LOGO,
            "link": {"web": "https://pf.kakao.com/_pxgeWX"},
        },
        {
            "title": "🗳️ 오늘의 KBL 경기 승부예측 이벤트",
            "description": "매일 경기 승리팀 예측하고 포인트 적립 배틀!",
            "imageUrl": DEFAULT_SPORTS_LOGO,
            "link": {"web": "https://sports.daum.net/basketball"},
        },
        {
            "title": "📋 경기 1시간 전 선발 라인업 알림",
            "description": "내 응원팀의 당일 Best 5 스타팅 라인업 제공",
            "imageUrl": DEFAULT_SPORTS_LOGO,
            "link": {"web": "https://pf.kakao.com/_pxgeWX"},
        },
        {
            "title": "⚙️ 내 응원팀 설정 & 맞춤 알림 안내",
            "description": "시작·종료·클러치 상황별 맞춤 푸시 알림",
            "imageUrl": DEFAULT_SPORTS_LOGO,
            "link": {"web": "https://pf.kakao.com/_pxgeWX"},
        },
    ]

    card = _list_card(
        header_title="📢 KBL봇 채널 소식 & 공식 공지",
        items=items,
        buttons=[
            _msg_btn("📅 오늘 경기 보기", "오늘 경기"),
            _link_btn("🏠 채널 홈 바로가기", "https://pf.kakao.com/_pxgeWX"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )
