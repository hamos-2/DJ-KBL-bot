"""Factory functions for building Kakao Skill response payloads (Pro Basketball Bot MVP)."""

import hashlib
import os
import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apps.kakao.schemas import (
    KakaoSkillResponse,
    KakaoTemplate,
    QuickReply,
)
from core.season import get_current_season
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

_DEFAULT_PUBLIC_BASE_URL = os.environ.get(
    "PUBLIC_BASE_URL",
    "https://activity-lexmark-insert-styles.trycloudflare.com",
)

# Bottom navigation QuickReplies: Clean text without leading emoji clutter
MAIN_MENU_QUICK_REPLIES: list[QuickReply] = [
    QuickReply(label="오늘 경기", messageText="오늘 경기"),
    QuickReply(label="실시간 점수", messageText="실시간 점수"),
    QuickReply(label="승부예측", messageText="승부예측"),
    QuickReply(label="라인업", messageText="라인업"),
    QuickReply(label="관심선수", messageText="관심선수"),
    QuickReply(label="최신 뉴스", messageText="뉴스"),
    QuickReply(label="주요장면", messageText="주요장면"),
    QuickReply(label="팀순위", messageText="팀순위"),
    QuickReply(label="설정", messageText="설정"),
    QuickReply(label="홈으로", messageText="처음으로"),
]

FAVORITE_PLAYERS_QUICK_REPLIES: list[QuickReply] = [
    QuickReply(label="내 관심선수", messageText="관심선수"),
    QuickReply(label="10개 구단 선수", messageText="구단별 선수"),
    QuickReply(label="SK 선수", messageText="SK 선수"),
    QuickReply(label="KT 선수", messageText="KT 선수"),
    QuickReply(label="DB 선수", messageText="DB 선수"),
    QuickReply(label="KCC 선수", messageText="KCC 선수"),
    QuickReply(label="LG 선수", messageText="LG 선수"),
    QuickReply(label="선수순위", messageText="선수순위"),
    QuickReply(label="관심선수 초기화", messageText="관심선수 초기화"),
    QuickReply(label="홈으로", messageText="처음으로"),
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


def _u16_len(text: str) -> int:
    """Return length in UTF-16 code units (matching Kakao i OpenBuilder JS length)."""
    return len(str(text).encode("utf-16-le")) // 2


def _u16_truncate(text: str, max_u16: int, suffix: str = "") -> str:
    """Truncate *text* safely so its UTF-16 code unit length never exceeds *max_u16*."""
    s = str(text or "")
    if _u16_len(s) <= max_u16:
        return s
    suf_len = _u16_len(suffix)
    limit = max(0, max_u16 - suf_len)
    out: list[str] = []
    cur = 0
    for ch in s:
        w = _u16_len(ch)
        if cur + w > limit:
            break
        out.append(ch)
        cur += w
    res = "".join(out).rstrip()
    if suffix and len(res) >= 2 and " " in res and len(res) - res.rfind(" ") <= 5:
        res = res[: res.rfind(" ")].rstrip()
    return f"{res}{suffix}" if suffix else res


def _clean_btn_label(label: str) -> str:
    """Strip leading decorative emojis/symbols from button labels for clean UI."""
    s = str(label or "").strip()
    cleaned = re.sub(r"^[^\w가-힣#()\[\]]+", "", s).strip()
    return cleaned or s


def _msg_btn(label: str, message_text: str) -> dict[str, str]:
    """Build an in-card message button dict for Kakao textCard/basicCard."""
    return {
        "action": "message",
        "label": _u16_truncate(_clean_btn_label(label), 14),
        "messageText": message_text,
    }


def _link_btn(label: str, url: str) -> dict[str, str]:
    """Build an in-card webLink button dict for Kakao textCard/basicCard."""
    return {
        "action": "webLink",
        "label": _u16_truncate(_clean_btn_label(label), 14),
        "webLinkUrl": url,
    }


def _share_btn(label: str) -> dict[str, str]:
    """Build an in-card KakaoTalk viral share button dict (action: 'share') for basicCard/listCard."""
    return {
        "action": "share",
        "label": _u16_truncate(_clean_btn_label(label), 14),
    }


def _list_card(
    header_title: str,
    items: list[dict[str, Any]],
    buttons: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build native Kakao listCard component (max 5 items, max 2 buttons)."""
    card_items = []
    for it in items[:5]:
        raw_title = str(it.get("title", ""))
        item_dict: dict[str, Any] = {
            "title": _u16_truncate(raw_title, 35, suffix="…") if _u16_len(raw_title) > 35 else raw_title
        }
        if it.get("description"):
            raw_desc = str(it["description"])
            item_dict["description"] = (
                _u16_truncate(raw_desc, 30, suffix="…") if _u16_len(raw_desc) > 30 else raw_desc
            )
        if it.get("imageUrl"):
            item_dict["imageUrl"] = str(it["imageUrl"])
        if it.get("link"):
            item_dict["link"] = it["link"]
        card_items.append(item_dict)

    card: dict[str, Any] = {
        "header": {"title": _u16_truncate(header_title, 30)},
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
    include_thumbnail: bool = True,
    thumbnail_width: int = 300,
    thumbnail_height: int = 300,
) -> dict[str, Any]:
    """Build native Kakao itemCard component (table key-values, title <= 6 chars)."""
    card: dict[str, Any] = {}
    thumb = thumbnail_url or (image_title.get("imageUrl") if image_title else None)
    if include_thumbnail and thumb:
        card["thumbnail"] = {"imageUrl": thumb, "width": thumbnail_width, "height": thumbnail_height}
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
    fixed_ratio: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Build a single basicCard dict (with official Daum logo or 2-column lineup board thumbnail)."""
    card: dict[str, Any] = {
        "title": title[:30],
        "description": description[:400],
    }
    if thumbnail_url:
        thumb: dict[str, Any] = {"imageUrl": thumbnail_url}
        if fixed_ratio:
            thumb["fixedRatio"] = True
        if width is not None:
            thumb["width"] = width
        if height is not None:
            thumb["height"] = height
        card["thumbnail"] = thumb
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
    team_game: dict[str, Any] | None = None,
    base_url: str | None = None,
    *,
    is_welcome_entry: bool = False,
    team_standing: dict[str, Any] | None = None,
    last_game: dict[str, Any] | None = None,
    hot_player: dict[str, Any] | None = None,
) -> KakaoSkillResponse:
    """
    Build the Pro Basketball Bot welcome / home menu response.
    When `is_welcome_entry=True` (chatroom initial entry / Welcome Block),
    emits a personalized greeting bubble (`또 오셨군요, 반가워요! 우리 팀 소식을 준비했어요.`)
    followed by a 3-card carousel (`[구단] 현황` / `화제의 선수` / `주요장면`),
    matching 프로야구봇 (`_HhRnC`).
    """
    b_url = (base_url or _DEFAULT_PUBLIC_BASE_URL).rstrip("/")

    if not favorite_team:
        team_cards = [
            _basic_card(
                title="❤️ 응원팀 선택 (수도권 구단)",
                description="서울 SK, 수원 KT, 서울 삼성\n응원할 구단 버튼을 누르면 내 응원팀으로 즉시 설정됩니다.",
                thumbnail_url=f"{b_url}/integrations/kakao/skills/banner/home/region/capital.png?v=home_v3_800x400",
                buttons=[
                    _msg_btn("❤️ 서울 SK", "#응원팀 SK"),
                    _msg_btn("❤️ 수원 KT", "#응원팀 KT"),
                    _msg_btn("❤️ 서울 삼성", "#응원팀 삼성"),
                ],
                fixed_ratio=False,
                width=800,
                height=400,
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (경기·강원 구단)",
                description="원주 DB, 안양 정관장, 고양 소노\n선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                thumbnail_url=f"{b_url}/integrations/kakao/skills/banner/home/region/gangwon_gyeonggi.png?v=home_v3_800x400",
                buttons=[
                    _msg_btn("❤️ 원주 DB", "#응원팀 DB"),
                    _msg_btn("❤️ 안양 정관장", "#응원팀 정관장"),
                    _msg_btn("❤️ 고양 소노", "#응원팀 소노"),
                ],
                fixed_ratio=False,
                width=800,
                height=400,
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (영남권 구단)",
                description="창원 LG, 부산 KCC, 울산 현대모비스\n선택 즉시 일정·결과·순위에서 내 응원팀이 최우선 표시됩니다.",
                thumbnail_url=f"{b_url}/integrations/kakao/skills/banner/home/region/yeongnam.png?v=home_v3_800x400",
                buttons=[
                    _msg_btn("❤️ 창원 LG", "#응원팀 LG"),
                    _msg_btn("❤️ 부산 KCC", "#응원팀 KCC"),
                    _msg_btn("❤️ 울산 현대모비스", "#응원팀 현대모비스"),
                ],
                fixed_ratio=False,
                width=800,
                height=400,
            ),
            _basic_card(
                title="❤️ 응원팀 선택 (대구 한국가스공사)",
                description="대구 한국가스공사 페가수스를 내 응원팀으로 설정합니다.",
                thumbnail_url=f"{b_url}/integrations/kakao/skills/banner/home/region/daegu.png?v=home_v3_800x400",
                buttons=[
                    _msg_btn("❤️ 한국가스공사", "#응원팀 한국가스공사"),
                    _msg_btn("📅 오늘 경기 보기", "오늘 경기"),
                    _msg_btn("📰 KBL 최신 뉴스", "뉴스"),
                ],
                fixed_ratio=False,
                width=800,
                height=400,
            ),
        ]
        onboard_outputs: list[dict[str, Any]] = [
            {"carousel": {"type": "basicCard", "items": team_cards}},
        ]
        if is_welcome_entry:
            onboard_outputs.insert(
                0,
                {
                    "simpleText": {
                        "text": "👋 반가워요! 응원하는 KBL 구단을 선택하시면 맞춤 소식을 준비해 드릴게요."
                    }
                },
            )
        return KakaoSkillResponse(
            template=KakaoTemplate(
                outputs=onboard_outputs,
                quickReplies=MAIN_MENU_QUICK_REPLIES,
            )
        )

    full_team = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
    home_banner_url = f"{b_url}/integrations/kakao/skills/banner/home/team/{favorite_team}.png?v=home_v3_800x400"
    news_banner_url = f"{b_url}/integrations/kakao/skills/banner/home/news/{favorite_team}.png?v=home_v3_800x400"

    fav_p_str = (
        f"\n• 관심선수: {', '.join(fav_players[:2])}"
        if fav_players
        else "\n• 관심선수: 미등록 (아래 버튼으로 등록)"
    )

    if team_game:
        home = team_game.get("home_team", "?")
        away = team_game.get("away_team", "?")
        status = team_game.get("status", "")
        h_score = team_game.get("home_score")
        a_score = team_game.get("away_score")
        period = team_game.get("period")
        clock = team_game.get("game_clock")
        time_str = _format_kst_datetime(team_game.get("start_time"), include_date=False) or "14:00"
        arena = _short_arena(team_game.get("arena"))
        arena_str = f" [{arena}]" if arena else ""

        if status == "LIVE":
            h_s = h_score if h_score is not None else 0
            a_s = a_score if a_score is not None else 0
            period_str = f"{period}쿼터" if period else "실시간"
            clock_str = f" {clock}" if clock else ""
            card_title = f"🔴 [LIVE] {home} {h_s} : {a_s} {away}"
            card_desc = (
                f"• 경기 현황: {full_team} 실시간 경기 중\n"
                f"• 현재 상황: {period_str}{clock_str}{arena_str}\n"
                f"• 매치업: {home} vs {away}"
                f"{fav_p_str}"
            )
            buttons = [
                _msg_btn("🔴 실시간 스코어", "실시간 점수"),
                _msg_btn("📋 선발 라인업", "라인업"),
                _msg_btn("⭐ 관심선수 설정", "관심선수"),
            ]
        elif status == "FINAL":
            h_s = h_score if h_score is not None else 0
            a_s = a_score if a_score is not None else 0
            won = (favorite_team == home and h_s > a_s) or (favorite_team == away and a_s > h_s)
            result_tag = "승리" if won else "경기 종료"
            card_title = f"✅ [{result_tag}] {home} {h_s} : {a_s} {away}"
            card_desc = (
                f"• 경기 현황: {full_team} 경기 종료\n"
                f"• 최종 결과: {home} {h_s} : {a_s} {away}{arena_str}\n"
                f"• 하이라이트 영상과 경기 요약을 확인하세요."
                f"{fav_p_str}"
            )
            buttons = [
                _msg_btn("🎬 주요장면 보기", "주요장면"),
                _msg_btn("🏆 정규리그 순위", "팀순위"),
                _msg_btn("⭐ 관심선수 설정", "관심선수"),
            ]
        else:  # SCHEDULED or upcoming
            dt_str = _format_kst_datetime(team_game.get("start_time"), include_date=True) or f"오늘 {time_str}"
            opponent = away if favorite_team == home else home
            vs_type = "홈경기" if favorite_team == home else "원정경기"
            card_title = f"📅 [경기 안내] {home} vs {away}"
            card_desc = (
                f"• 경기 구분: {full_team} {vs_type}\n"
                f"• 경기 시간: {dt_str}{arena_str}\n"
                f"• 매치업: {home} vs {away}\n"
                f"※ 경기 시작 20분 전 확정 라인업이 공개됩니다."
                f"{fav_p_str}"
            )
            buttons = [
                _msg_btn("📋 선발 라인업", "라인업"),
                _msg_btn("🗳️ 승부예측 참여", f"#승부예측 {favorite_team}"),
                _msg_btn("⭐ 관심선수 설정", "관심선수"),
            ]

        game_card = _basic_card(
            title=card_title,
            description=card_desc,
            thumbnail_url=home_banner_url,
            buttons=buttons,
            fixed_ratio=False,
            width=800,
            height=400,
        )
    else:
        game_card = _basic_card(
            title=f"🏀 {full_team}",
            description=(
                f"내 응원팀 설정이 완료되었습니다.\n"
                f"하단 버튼을 눌러 오늘 경기와 일정을 확인하세요."
                f"{fav_p_str}"
            ),
            thumbnail_url=home_banner_url,
            buttons=[
                _msg_btn("📅 오늘 경기", "오늘 경기"),
                _msg_btn("🗳️ 오늘 승부예측", f"#승부예측 {favorite_team}"),
                _msg_btn("⭐ 관심선수 설정", "관심선수"),
            ],
            fixed_ratio=False,
            width=800,
            height=400,
        )

    # Enrich Card 1 ([구단] 현황) with league rank/record
    if team_standing:
        rk = team_standing.get("rank", "?")
        w = team_standing.get("wins", 0)
        l = team_standing.get("losses", 0)
        stk = str(team_standing.get("streak") or "").strip()
        stk_str = f" · {stk}" if stk and stk != "-" else ""
        standing_line = f"• 정규리그: 현재 {rk}위 ({w}승 {l}패{stk_str})\n"
        if not team_game:
            game_card["title"] = f"🏀 [{favorite_team}] 구단 현황 ({rk}위 · {w}승{l}패)"[:30]
        game_card["description"] = f"{standing_line}{game_card['description']}"[:400]

    # Card 2: 화제의 선수 (1순위: 직전 경기 최고 수훈선수 -> 2순위: 시즌 공헌도 팀 내 1위 에이스)
    hp = hot_player or resolve_team_hot_player(favorite_team, last_game, fetch_boxscore=False)
    hp_name = str(hp.get("name") or f"{favorite_team} 에이스")
    hp_pos = str(hp.get("pos") or "F")
    hp_no = str(hp.get("no") or "0")
    hp_pts = float(hp.get("pts") or 18.0)
    hp_reb = float(hp.get("reb") or 5.0)
    hp_ast = float(hp.get("ast") or 4.0)
    q_hp_name = urllib.parse.quote(hp_name)
    q_fav_team = urllib.parse.quote(favorite_team)
    q_hp_pos = urllib.parse.quote(hp_pos)
    q_hp_no = urllib.parse.quote(hp_no)
    hp_banner_url = (
        f"{b_url}/integrations/kakao/skills/banner/player/{q_hp_name}.png"
        f"?team={q_fav_team}&pos={q_hp_pos}&no={q_hp_no}&pts={hp_pts}&reb={hp_reb}&ast={hp_ast}&v=player_v1"
    )
    is_fav_hp = hp_name in (fav_players or [])
    hp_toggle_btn = (
        _msg_btn(f"➖ {hp_name} 해제", f"#관심선수 삭제 {hp_name}")
        if is_fav_hp
        else _msg_btn(f"➕ {hp_name} 등록", f"#관심선수 {hp_name}")
    )
    hot_player_card = _basic_card(
        title=f"🔥 화제의 선수: {hp_name} (#{hp_no})",
        description=(
            f"{hp.get('badge', '[팀 내 핵심 에이스]')}\n"
            f"• 소속/포지션: {full_team} ({hp_pos})\n"
            f"• {hp.get('game_stat_line', f'시즌 평균: {hp_pts}점 · {hp_reb}리바 · {hp_ast}어시')}\n"
            f"• 시즌 평균: {hp_pts}점 | {hp_reb}리바 | {hp_ast}어시"
        ),
        thumbnail_url=hp_banner_url,
        buttons=[
            _msg_btn(f"📊 {hp_name} 기록", hp_name),
            hp_toggle_btn,
            _msg_btn(f"🏀 {favorite_team} 선수단", f"{favorite_team} 선수"),
        ],
        fixed_ratio=False,
        width=800,
        height=400,
    )

    # Card 3: 주요장면 & 구단 소식
    hl_line = ""
    if last_game:
        lh = last_game.get("home_team", "?")
        la = last_game.get("away_team", "?")
        lhs = last_game.get("home_score", 0)
        las = last_game.get("away_score", 0)
        opp = la if lh == favorite_team else lh
        hl_line = f"• 최근 영상: [하이라이트] {favorite_team} vs {opp} ({lh} {lhs}:{las} {la})\n"

    highlights_news_card = _basic_card(
        title=f"🎬 [{favorite_team}] 주요장면 & 구단 소식",
        description=(
            f"{hl_line}"
            f"• {full_team} 공식 하이라이트 영상과 실시간 구단 뉴스를 한눈에 확인하세요!"
        ),
        thumbnail_url=news_banner_url,
        buttons=[
            _msg_btn("🎬 주요장면 보기", f"{favorite_team} 주요장면"),
            _msg_btn(f"📰 {favorite_team} 뉴스", f"{favorite_team} 뉴스"),
            _msg_btn("📋 직전 경기 요약", f"{favorite_team} 요약"),
        ],
        fixed_ratio=False,
        width=800,
        height=400,
    )

    home_outputs: list[dict[str, Any]] = [
        {
            "carousel": {
                "type": "basicCard",
                "items": [game_card, hot_player_card, highlights_news_card],
            }
        }
    ]
    if is_welcome_entry:
        home_outputs.insert(
            0,
            {
                "simpleText": {
                    "text": f"👋 또 오셨군요, 반가워요! 우리 팀 {full_team} 소식을 준비했어요."
                }
            },
        )

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=home_outputs,
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def build_lineup_response(
    today_games: list[dict[str, Any]],
    favorite_team: str | None = None,
    target_team: str | None = None,
    base_url: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '라인업' (Starting 5 lineups, head coaches, foreign imports, Asian quotas,
    and 2-column Daum-style visual lineup board image with circular player photos).
    Matches 프로야구봇's 선발 라인업 feature & Daum Sports `?tab=lineup`.
    """
    import urllib.parse
    from services.content.lineup_board import fetch_daum_match_lineup_sync

    cards: list[dict[str, Any]] = []
    primary_board_url: str | None = None
    primary_board_alt: str = "KBL 선발 라인업 보드"

    # Prioritize target_team or favorite_team's game
    focus_team = target_team or favorite_team
    sorted_games = sorted(
        today_games,
        key=lambda g: (
            0 if focus_team and focus_team in (g.get("home_team"), g.get("away_team")) else 1,
            str(g.get("start_time") or ""),
        ),
    )

    if target_team:
        t_lineup = get_team_lineup(target_team) or {}
        if t_lineup:
            full_name = TEAM_INFO.get(target_team, {}).get("full_name", f"{target_team} 프로농구단")
            t_coach = t_lineup.get("head_coach", "")
            t_starters = t_lineup.get("starters", [])
            t_foreign = ", ".join(t_lineup.get("foreign_players", []))
            t_aq = t_lineup.get("asian_quota", "")
            t_bench = ", ".join(t_lineup.get("key_bench", [])[:4])

            # Check if target_team has a game in sorted_games to pull live Daum starters & board image
            t_game = next(
                (g for g in sorted_games if target_team in (g.get("home_team"), g.get("away_team"))),
                None,
            )
            t_thumb_url = get_team_logo(target_team)
            t_fixed = False
            t_w, t_h = None, None
            tg_id = ""
            t_is_official = False
            if t_game:
                tg_id = str(t_game.get("game_id") or "")
                tg_home = t_game.get("home_team", target_team)
                tg_away = t_game.get("away_team", "SK")
                if tg_id.isdigit() and len(tg_id) >= 6:
                    _, _, h_live, a_live, is_off = fetch_daum_match_lineup_sync(tg_id, tg_home, tg_away)
                    if is_off:
                        t_starters = h_live if target_team == tg_home else a_live
                        t_is_official = True

            from services.roster.naver_verifier import verify_and_enrich_starters_sync
            t_verify = verify_and_enrich_starters_sync(
                target_team, t_starters, is_official_daum=t_is_official
            )
            t_starters = t_verify["verified_starters"]

            if base_url:
                import hashlib
                q_t = urllib.parse.quote(target_team)
                gid_param = f"game_id={tg_id}&" if (tg_id.isdigit() and len(tg_id) >= 6) else ""
                t_sig = hashlib.md5(
                    "|".join(str(s.get("name") or "") for s in t_starters).encode("utf-8")
                ).hexdigest()[:8]
                t_thumb_url = (
                    f"{base_url.rstrip('/')}/integrations/kakao/skills/lineup-image/team/{q_t}.png?{gid_param}v=nanum20261117_{t_sig}"
                )
                t_fixed, t_w, t_h = True, 800, 800
                primary_board_url = t_thumb_url
                primary_board_alt = f"📋 {target_team} 선발 라인업 보드"

            s_lines = "\n".join(
                f"{s.get('pos', '')} {s.get('name', '')} #{s.get('no', '')}".strip() for s in t_starters
            )
            desc = (
                f"[{full_name} (2026-2027)]\n"
                f"• 감독: {t_coach} 감독\n"
                f"────────────────────\n"
                f"[베스트 5 선발]\n{s_lines}\n"
                f"────────────────────\n"
                f"• 외인: {t_foreign}\n"
                f"• 아시아쿼터: {t_aq}\n"
                f"• 식스맨: {t_bench}"
            )
            cards.append(
                _basic_card(
                    title=f"📋 [{target_team}] 2026-27 공식 라인업",
                    description=desc[:380],
                    thumbnail_url=t_thumb_url,
                    buttons=[
                        _msg_btn(f"⭐ {target_team} 선수단", f"{target_team} 선수"),
                        _msg_btn(f"📅 {target_team} 일정", f"{target_team} 일정"),
                        _share_btn("📤 라인업 공유하기"),
                    ],
                    fixed_ratio=t_fixed,
                    width=t_w,
                    height=t_h,
                )
            )

    if not today_games and not cards:
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

    # Multi-game parallel fetch for up to 3 games (< 0.3s concurrent vs 7.5s sequential)
    lineup_data_map: dict[str, tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]] = {}
    if not target_team and sorted_games:
        games_to_fetch = [
            g for g in sorted_games[:3]
            if str(g.get("game_id") or "").isdigit() and len(str(g.get("game_id") or "")) >= 6
        ]
        if games_to_fetch:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(len(games_to_fetch), 3)) as pool:
                futures = {
                    pool.submit(
                        fetch_daum_match_lineup_sync,
                        str(g.get("game_id")),
                        fallback_home=g.get("home_team"),
                        fallback_away=g.get("away_team"),
                        timeout=1.8,
                    ): str(g.get("game_id"))
                    for g in games_to_fetch
                }
                for fut in futures:
                    gid_key = futures[fut]
                    try:
                        lineup_data_map[gid_key] = fut.result()
                    except Exception:
                        pass

    for g in ([] if target_team else sorted_games[:3]):
        gid = str(g.get("game_id") or "")
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

        is_daum_official = False
        if gid in lineup_data_map:
            _, _, h_live, a_live, is_daum_official = lineup_data_map[gid]
            if is_daum_official:
                h_starters = h_live
                a_starters = a_live
        elif gid.isdigit() and len(gid) >= 6:
            _, _, h_live, a_live, is_daum_official = fetch_daum_match_lineup_sync(
                gid, fallback_home=home, fallback_away=away, timeout=1.8
            )
            if is_daum_official:
                h_starters = h_live
                a_starters = a_live

        from services.roster.naver_verifier import verify_and_enrich_starters_sync
        h_verify = verify_and_enrich_starters_sync(home, h_starters, is_official_daum=is_daum_official)
        a_verify = verify_and_enrich_starters_sync(away, a_starters, is_official_daum=is_daum_official)
        h_starters = h_verify["verified_starters"]
        a_starters = a_verify["verified_starters"]

        def _format_starter_entry(s: dict[str, Any]) -> str:
            pos = s.get("pos", "").strip()
            name = s.get("name", "").strip()
            no = str(s.get("no", "")).replace("#", "").strip()
            return f"{pos} {name} #{no}".strip()

        h_players_lines = "\n".join(_format_starter_entry(s) for s in h_starters) or "출전 명단 확인 중"
        a_players_lines = "\n".join(_format_starter_entry(s) for s in a_starters) or "출전 명단 확인 중"
        h_coach_str = f" ({h_coach} 감독)" if h_coach else ""
        a_coach_str = f" ({a_coach} 감독)" if a_coach else ""

        # Check if game is within 25 min of start or already started/live or confirmed by Daum
        is_confirmed = is_daum_official
        start_time_raw = g.get("start_time")
        status = g.get("status", "")
        if status in ("LIVE", "FINAL"):
            is_confirmed = True
        elif start_time_raw:
            try:
                g_start = datetime.fromisoformat(str(start_time_raw).replace("Z", "+00:00"))
                if datetime.now(UTC) >= g_start - timedelta(minutes=25):
                    is_confirmed = True
            except Exception:
                pass

        if is_confirmed:
            status_badge = "[공식 확정 선발 라인업]"
            title_tag = "[확정]"
            card_desc = (
                f"{status_badge}\n\n"
                f"[홈팀] {home}{h_coach_str}\n"
                f"────────────────────\n"
                f"{h_players_lines}\n\n"
                f"[원정] {away}{a_coach_str}\n"
                f"────────────────────\n"
                f"{a_players_lines}\n\n"
                f"※ KBL 공식 제출 확정 베스트 5"
            )
        else:
            status_badge = "[공식 라인업 발표 준비 중]"
            title_tag = "[준비중]"
            card_desc = (
                f"{status_badge}\n"
                f"※ 경기 시작 20~30분 전 공식 발표\n\n"
                f"[홈팀 예상] {home}{h_coach_str}\n"
                f"────────────────────\n"
                f"{h_players_lines}\n\n"
                f"[원정 예상] {away}{a_coach_str}\n"
                f"────────────────────\n"
                f"{a_players_lines}"
            )

        import hashlib
        g_sig = hashlib.md5(
            "|".join(str(s.get("name") or "") for s in (h_starters + a_starters)).encode("utf-8")
        ).hexdigest()[:8]
        if base_url and primary_board_url is None:
            q_h = urllib.parse.quote(home)
            q_a = urllib.parse.quote(away)
            card_thumb = f"{base_url.rstrip('/')}/integrations/kakao/skills/lineup-image/game/{gid or '0'}.png?home={q_h}&away={q_a}&v=nanum20261117_{g_sig}"
            c_fixed, c_w, c_h = True, 800, 800
            primary_board_url = card_thumb
            primary_board_alt = f"📋 {home} vs {away} 선발 라인업 보드"
        elif base_url and not target_team:
            q_h = urllib.parse.quote(home)
            q_a = urllib.parse.quote(away)
            card_thumb = f"{base_url.rstrip('/')}/integrations/kakao/skills/lineup-image/game/{gid or '0'}.png?home={q_h}&away={q_a}&v=nanum20261117_{g_sig}"
            c_fixed, c_w, c_h = True, 800, 800
        else:
            card_thumb = get_team_logo(home)
            c_fixed, c_w, c_h = False, None, None

        first_btn = (
            _link_btn("📋 공식 라인업 탭", f"https://sports.daum.net/match/{gid}?tab=lineup")
            if (gid.isdigit() and len(gid) >= 6)
            else _msg_btn("🗳️ 승부예측", f"#승부예측 {home}")
        )

        cards.append(
            _basic_card(
                title=f"📋 {home} vs {away} 선발 라인업 {title_tag}",
                description=card_desc,
                thumbnail_url=card_thumb,
                buttons=[
                    first_btn,
                    _msg_btn("🗳️ 승부예측", f"#승부예측 {home}") if (gid.isdigit() and len(gid) >= 6) else _msg_btn("🔴 실시간 스코어", "실시간 점수"),
                    _share_btn("📤 라인업 공유하기"),
                ],
                fixed_ratio=c_fixed,
                width=c_w,
                height=c_h,
            )
        )

    outputs: list[dict[str, Any]] = [
        {"carousel": {"type": "basicCard", "items": cards[:5]}},
    ]

    lineup_qrs: list[QuickReply] = []
    if target_team:
        lineup_qrs.extend([
            QuickReply(label=f"⭐ {target_team} 선수단", messageText=f"{target_team} 선수"),
            QuickReply(label=f"📅 {target_team} 일정", messageText=f"{target_team} 일정"),
            QuickReply(label="📋 오늘 라인업", messageText="라인업"),
            QuickReply(label="🔴 실시간 점수", messageText="실시간 점수"),
            QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
            QuickReply(label="🏆 팀순위", messageText="팀순위"),
            QuickReply(label="⭐ 관심선수", messageText="관심선수"),
            QuickReply(label="🏠 홈으로", messageText="처음으로"),
        ])
    else:
        # Multi-game day: add dynamic match jump quick buttons (Plan B convenience)
        _qr_alias = {"현대모비스": "모비스", "한국가스공사": "가스공사"}
        for g in sorted_games[:3]:
            h_ = str(g.get("home_team") or "")
            a_ = str(g.get("away_team") or "")
            if h_ and a_:
                sh = _qr_alias.get(h_, h_)
                sa = _qr_alias.get(a_, a_)
                lineup_qrs.append(
                    QuickReply(label=_u16_truncate(f"📋 {sh} vs {sa}", 14), messageText=f"{h_} 라인업")
                )
        lineup_qrs.extend([
            QuickReply(label="🔴 실시간 점수", messageText="실시간 점수"),
            QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
            QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
            QuickReply(label="🏆 팀순위", messageText="팀순위"),
            QuickReply(label="⭐ 관심선수", messageText="관심선수"),
            QuickReply(label="🏠 홈으로", messageText="처음으로"),
        ])
    lineup_qrs = lineup_qrs[:10]
    return KakaoSkillResponse(
        template=KakaoTemplate(outputs=outputs, quickReplies=lineup_qrs)
    )


_GAME_MVP_CACHE: dict[str, dict[str, Any]] = {}
_GAME_MVP_CACHE_MAX = 100


def _fetch_real_game_mvp_sync(
    game_id: str,
    winner: str,
    home_team: str,
    timeout: float = 1.8,
) -> dict[str, Any] | None:
    """
    Fetch actual single-game MVP stats (integer pts, reb, ast) for the winning team
    from Daum Hermes boxscore API (`homePerson` / `homePersonStat`).
    """
    gid = str(game_id or "").strip()
    if not gid.isdigit() or len(gid) < 6:
        return None
    cache_key = f"{gid}:{winner}"
    if cache_key in _GAME_MVP_CACHE:
        return _GAME_MVP_CACHE[cache_key]

    try:
        import httpx
        from services.content.kbl_data import _get_tls_verify

        resp = httpx.get(
            "https://sports.daum.net/api/hermes/game/get.json",
            params={"gameId": gid, "detail": "liveData"},
            headers={"Referer": "https://sports.daum.net/", "User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            verify=_get_tls_verify(),
        )
        if resp.status_code == 200:
            d = resp.json() or {}
            home_wlt = (d.get("home") or {}).get("wlt")
            if winner and home_team:
                side = "home" if winner == home_team else "away"
            elif home_wlt in ("W", "L"):
                side = "home" if home_wlt == "W" else "away"
            else:
                side = "home"
            persons = {p.get("personId"): p for p in (d.get(f"{side}Person") or [])}
            stats = d.get(f"{side}PersonStat") or []
            best_mvp: dict[str, Any] | None = None
            best_score = -1.0
            for st in stats:
                pid = st.get("personId")
                p_info = persons.get(pid) or {}
                name = str(p_info.get("nameKo") or p_info.get("name") or "").strip()
                if not name:
                    continue
                pts = int(st.get("pts") or 0)
                reb = int(st.get("reb") or 0)
                ast = int(st.get("ast") or 0)
                impact = pts + (reb * 0.6) + (ast * 0.8)
                if impact > best_score:
                    best_score = impact
                    best_mvp = {"name": name, "pts": pts, "reb": reb, "ast": ast}
            if best_mvp and best_mvp["pts"] > 0:
                if len(_GAME_MVP_CACHE) >= _GAME_MVP_CACHE_MAX:
                    _GAME_MVP_CACHE.pop(next(iter(_GAME_MVP_CACHE)), None)
                _GAME_MVP_CACHE[cache_key] = best_mvp
                return best_mvp
    except Exception:
        pass
    return None


def resolve_team_hot_player(
    team: str,
    last_game: dict[str, Any] | None = None,
    fetch_boxscore: bool = True,
) -> dict[str, Any]:
    """
    Resolve the '화제의 선수' (Hot Player) for a club using the 2-tier priority:
      1순위: 직전 경기 팀 내 최고 활약 선수 (Daum Hermes boxscore pts + 0.6*reb + 0.8*ast 1위)
      2순위: 시즌 평균 공헌도 (pts + 0.7*reb + 0.8*ast) 팀 내 1위 에이스
    """
    team_roster = [p for p in KBL_PLAYERS if p.get("team") == team]
    roster_by_name = {p["name"]: p for p in team_roster}

    if last_game and last_game.get("status") == "FINAL":
        gid = str(last_game.get("game_id") or "").strip()
        h_team = str(last_game.get("home_team") or "")
        a_team = str(last_game.get("away_team") or "")
        opp = a_team if h_team == team else h_team
        mvp = (
            _fetch_real_game_mvp_sync(gid, team, h_team)
            if fetch_boxscore
            else _GAME_MVP_CACHE.get(f"{gid}:{team}")
        )
        if mvp and mvp.get("name"):
            m_name = str(mvp["name"])
            prof = roster_by_name.get(m_name, {})
            return {
                "name": m_name,
                "team": team,
                "pos": str(prof.get("pos") or "F"),
                "no": str(prof.get("no") or "0"),
                "pts": float(prof.get("pts") or mvp["pts"]),
                "reb": float(prof.get("reb") or mvp["reb"]),
                "ast": float(prof.get("ast") or mvp["ast"]),
                "source": "boxscore_mvp",
                "badge": f"[직전 {opp}전 팀 내 최고 수훈선수]",
                "game_stat_line": f"직전 경기 활약: {mvp['pts']}득점 · {mvp['reb']}리바 · {mvp['ast']}어시",
            }

    sorted_stars = sorted(
        team_roster,
        key=lambda p: (
            float(p.get("pts") or 0)
            + 0.7 * float(p.get("reb") or 0)
            + 0.8 * float(p.get("ast") or 0)
        ),
        reverse=True,
    )
    ace = sorted_stars[0] if sorted_stars else {"name": f"{team} 에이스", "pos": "F", "no": "1", "pts": 18.0, "reb": 5.0, "ast": 4.0}
    return {
        "name": str(ace["name"]),
        "team": team,
        "pos": str(ace.get("pos") or "F"),
        "no": str(ace.get("no") or "1"),
        "pts": float(ace.get("pts") or 18.0),
        "reb": float(ace.get("reb") or 5.0),
        "ast": float(ace.get("ast") or 4.0),
        "source": "season_ace",
        "badge": "[시즌 평균 공헌도 팀 내 1위 에이스]",
        "game_stat_line": f"시즌 평균 활약: {ace['pts']}득점 · {ace['reb']}리바 · {ace['ast']}어시",
    }


def _build_witty_kbl_commentary(
    winner: str,
    loser: str,
    hs: int,
    as_: int,
    mvp: dict[str, Any],
    focus_team: str | None = None,
) -> tuple[str, str, str]:
    """
    Generate KBL fan-native witty one-liner ('촌철살인 한줄평') inspired by 프로야구봇 (_HhRnC).
    Returns (turning_point_short, summary_30, full_commentary).
    """
    diff = abs(hs - as_)
    w_lineup = get_team_lineup(winner) or {}
    l_lineup = get_team_lineup(loser) or {}
    w_coach = w_lineup.get("head_coach", f"{winner} 벤치")
    l_coach = l_lineup.get("head_coach", f"{loser} 벤치")
    loser_stars = sorted(
        [p for p in KBL_PLAYERS if p.get("team") == loser],
        key=lambda p: float(p.get("pts") or 0),
        reverse=True,
    )
    l_star = loser_stars[0]["name"] if loser_stars else f"{loser} 주전진"
    m_pts = int(round(float(mvp.get("pts") or 0)))
    m_reb = int(round(float(mvp.get("reb") or 0)))
    m_ast = int(round(float(mvp.get("ast") or 0)))

    if diff <= 4:
        turning_short = f"4Q 클러치 {diff}점차 극장승"
        summary_30 = f"{mvp['name']} 위닝샷! {diff}점차 극장승"[:30]
        if focus_team == loser:
            full_msg = (
                f"[{loser} 시점 촌철살인 한줄평]\n"
                f"\"심장 부여잡은 4쿼터 막판 원포제션 승부! {l_star}의 분전에도 마지막 클러치 포제션 야투 한 방이 림을 외면하며 {winner}에 {diff}점 차로 뼈아픈 석패를 당했습니다. {l_coach} 감독의 다음 경기 리벤지 매치 플랜이 절실합니다!\""
            )
        else:
            full_msg = (
                f"[{winner} 시점 촌철살인 한줄평]\n"
                f"\"이게 바로 KBL 클러치 농구! 4쿼터 종료 직전 숨 막히는 승부처에서 {w_coach} 감독의 작전타임 승부수와 에이스 {mvp['name']}({m_pts}점 {m_ast}어시)의 강심장 클러치 득점이 터지며 {loser} 상대로 짜릿한 {diff}점 차 극장승을 완성했습니다!\""
            )
    elif diff <= 10:
        turning_short = f"후반 승부처 제압 ({diff}점차)"
        summary_30 = f"{mvp['name']} 맹활약! 승부처 완벽 제압"[:30]
        if focus_team == loser:
            full_msg = (
                f"[{loser} 시점 촌철살인 한줄평]\n"
                f"\"쫓아갈 만하면 터진 상대의 찬물 외곽포! {loser}({l_coach} 감독)는 {l_star}를 앞세워 추격전을 벌였으나, 3·4쿼터 승부처 턴오버와 {mvp['name']} 수비 제어 실패가 겹치며 {diff}점 차로 아쉬운 패배를 기록했습니다.\""
            )
        else:
            full_msg = (
                f"[{winner} 시점 촌철살인 한줄평]\n"
                f"\"3·4쿼터 약속의 땅을 지배한 {winner}! {w_coach} 감독의 탄탄한 로테이션과 {mvp['name']}({m_pts}점 {m_reb}리바 {m_ast}어시)의 내외곽 폭격으로 {loser}의 추격 의지를 꺾고 {diff}점 차 기분 좋은 승리를 챙겼습니다!\""
            )
    else:
        turning_short = f"공수 압도 {diff}점차 대승"
        summary_30 = f"{winner} 화력 대폭발! {diff}점차 완승"[:30]
        if focus_team == loser:
            full_msg = (
                f"[{loser} 시점 촌철살인 한줄평]\n"
                f"\"공수 밸런스가 급격히 흔들린 하루! {loser}({l_coach} 감독)는 초반부터 {winner}의 트랜지션과 {mvp['name']}의 화력에 주도권을 내주며 {diff}점 차 완패를 당했습니다. 분위기 쇄신이 시급합니다!\""
            )
        else:
            full_msg = (
                f"[{winner} 시점 촌철살인 한줄평]\n"
                f"\"코트를 폭격한 {winner}의 무자비한 화력쇼! {w_coach} 감독표 에너지 농구와 {mvp['name']}({m_pts}점 {m_reb}리바)의 원맨쇼가 폭발하며 일찌감치 가비지 타임을 선언, {loser}를 {diff}점 차로 완벽히 제압했습니다!\""
            )

    return turning_short[:30], summary_30[:30], full_msg


SUMMARY_QUICK_REPLIES: list[QuickReply] = [
    QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
    QuickReply(label="🔴 실시간 점수", messageText="실시간 점수"),
    QuickReply(label="💬 DB 요약", messageText="DB 요약"),
    QuickReply(label="💬 SK 요약", messageText="SK 요약"),
    QuickReply(label="💬 정관장 요약", messageText="정관장 요약"),
    QuickReply(label="💬 가스공사 요약", messageText="가스공사 요약"),
    QuickReply(label="💬 KCC 요약", messageText="KCC 요약"),
    QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
    QuickReply(label="🏆 팀순위", messageText="팀순위"),
    QuickReply(label="🏠 홈으로", messageText="처음으로"),
]


def build_game_summary_response(
    games: list[dict[str, Any]],
    favorite_team: str | None = None,
    target_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '요약' / '한줄평' / '[구단명] 요약' (Game recap, MVP player stats,
    and KBL fan-native '촌철살인 한줄평' with KakaoTalk viral share button).
    Matches 프로야구봇's '[구단명] 요약' viral engine.
    """
    focus_team = target_team or favorite_team
    finished_games = [g for g in games if g.get("status") == "FINAL"]
    if not finished_games:
        finished_games = games[:3]

    # If user explicitly queried "[구단명] 요약" (target_team), look for that team's game first
    matched_target_game = None
    if target_team:
        matched_target_game = next(
            (g for g in finished_games if target_team in (g.get("home_team"), g.get("away_team"))),
            None,
        )
        if matched_target_game is None:
            matched_target_game = next(
                (g for g in games if target_team in (g.get("home_team"), g.get("away_team"))),
                None,
            )

    # Fallback: if target_team was explicitly requested but has no game in DB yet,
    # render a rich team power-recap & witty season one-liner for target_team!
    if target_team and matched_target_game is None:
        t_lineup = get_team_lineup(target_team) or {}
        coach = t_lineup.get("head_coach", "감독")
        starters = t_lineup.get("starters", [])
        starter_names = ", ".join(s["name"] for s in starters[:5]) if starters else "주전 베스트 5"
        foreigns = ", ".join(t_lineup.get("foreign_players", []))
        asian_q = t_lineup.get("asian_quota", "")
        team_stars = sorted(
            [p for p in KBL_PLAYERS if p.get("team") == target_team],
            key=lambda p: float(p.get("pts") or 0),
            reverse=True,
        )
        ace = team_stars[0] if team_stars else {"name": f"{target_team} 에이스", "pts": 18.5, "reb": 5.2, "ast": 4.8}

        one_liner = (
            f"[{target_team} 촌철살인 전력 한줄평]\n"
            f"\"{coach} 감독 체제의 {target_team}! 에이스 {ace['name']}(평균 {ace['pts']}점 {ace['ast']}어시)과 "
            f"외국인 원투펀치({foreigns}), 아시아쿼터({asian_q})의 공수 시너지가 터지면 어느 팀도 막기 힘든 다크호스입니다!\""
        )
        base_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
        q_target = urllib.parse.quote(target_team)
        team_banner_url = f"{base_url}/integrations/kakao/skills/banner/home/team/{q_target}.png?v=nanum20261117_v3"
        item_card_output = _item_card(
            head_title=f"📋 {target_team} 경기 요약",
            image_title={
                "title": f"🏀 {target_team} 전력 요약 & 한줄평",
                "description": f"{coach} 감독 · 베스트5 리캡",
                "imageUrl": get_team_logo(target_team),
            },
            item_list=[
                {"title": "핵심MVP", "description": f"{ace['name']} (평균 {ace['pts']}점 {ace['ast']}어시)"},
                {"title": "베스트5", "description": starter_names[:30]},
                {"title": "외인/AQ", "description": f"{foreigns} / {asian_q}"[:30]},
            ],
            summary={"title": "한줄평", "description": f"{coach}표 {target_team}, 화력 폭발 예고!"[:30]},
            buttons=[
                _share_btn("📤 한줄평 공유하기"),
                _msg_btn(f"📋 {target_team} 라인업", f"{target_team} 라인업"),
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
            ],
            include_thumbnail=False,
        )
        commentary_card = {
            "basicCard": _basic_card(
                title=f"💬 {target_team} 촌철살인 한줄평",
                description=one_liner,
                thumbnail_url=team_banner_url,
                fixed_ratio=False,
                width=800,
                height=400,
                buttons=[
                    _share_btn("📤 한줄평 공유하기"),
                    _msg_btn(f"🏀 {target_team} 선수단", f"{target_team} 선수"),
                    _msg_btn("🏆 정규리그 순위표", "팀순위"),
                ],
            )
        }
        return KakaoSkillResponse(
            template=KakaoTemplate(
                outputs=[item_card_output, commentary_card],
                quickReplies=SUMMARY_QUICK_REPLIES,
            )
        )

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
            template=KakaoTemplate(outputs=[card], quickReplies=SUMMARY_QUICK_REPLIES)
        )

    if matched_target_game:
        finished_games = [matched_target_game] + [g for g in finished_games if g != matched_target_game]
    elif favorite_team:
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
    winner = home if hs >= as_ else away
    loser = away if winner == home else home
    diff = abs(hs - as_)

    gid = target.get("game_id", "")
    real_mvp = _fetch_real_game_mvp_sync(gid, winner, home)
    if real_mvp:
        mvp = real_mvp
    else:
        winner_stars = sorted(
            [p for p in KBL_PLAYERS if p.get("team") == winner],
            key=lambda p: float(p.get("pts") or 0),
            reverse=True,
        )
        base_mvp = winner_stars[0] if winner_stars else {"name": f"{winner} 수훈선수", "pts": 24, "reb": 9, "ast": 5}
        mvp = {
            "name": base_mvp["name"],
            "pts": int(round(float(base_mvp.get("pts") or 20))),
            "reb": int(round(float(base_mvp.get("reb") or 6))),
            "ast": int(round(float(base_mvp.get("ast") or 4))),
        }
    from services.content.kbl_data import resolve_kbl_highlight_video_url
    vod_url, _ = resolve_kbl_highlight_video_url(home, away, target.get("start_time"))

    turning_short, summary_30, full_commentary = _build_witty_kbl_commentary(
        winner=winner,
        loser=loser,
        hs=hs,
        as_=as_,
        mvp=mvp,
        focus_team=focus_team,
    )

    head_label = f"📋 {target_team} 경기 요약" if target_team else "📋 경기 요약"
    badge_team = target_team if (target_team and target_team in (home, away)) else winner
    base_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
    q_home = urllib.parse.quote(home)
    q_away = urllib.parse.quote(away)
    recap_banner_url = (
        f"{base_url}/integrations/kakao/skills/banner/recap/{q_home}/{q_away}.png"
        f"?hs={hs}&as_={as_}&v=recap_v1"
    )

    item_card_output = _item_card(
        head_title=head_label,
        image_title={
            "title": f"👑 {winner} 승리 ({hs}:{as_})",
            "description": f"{home} vs {away} 경기 리캡",
            "imageUrl": get_team_logo(badge_team),
        },
        item_list=[
            {"title": "경기MVP", "description": f"{mvp['name']} ({mvp['pts']}점 {mvp['reb']}리바)"},
            {"title": "승리구단", "description": f"{winner} ({diff}점 차 승)"},
            {"title": "승부처", "description": turning_short},
        ],
        summary={"title": "한줄평", "description": summary_30},
        buttons=[
            _share_btn("📤 한줄평 공유하기"),
            _link_btn("▶️ 공식 하이라이트 영상", vod_url),
            _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
        ],
        include_thumbnail=False,
    )

    commentary_card_output = {
        "basicCard": _basic_card(
            title=f"💬 {home} vs {away} 촌철살인 한줄평",
            description=(
                f"• 최종 스코어: {home} {hs} : {as_} {away}\n"
                f"• 수훈선수: {mvp['name']} ({mvp['pts']}점·{mvp['reb']}리바·{mvp['ast']}어시)\n\n"
                f"{full_commentary}"
            ),
            thumbnail_url=recap_banner_url,
            fixed_ratio=False,
            width=800,
            height=400,
            buttons=[
                _share_btn("📤 한줄평 공유하기"),
                _link_btn("▶️ 하이라이트 영상", vod_url),
                _msg_btn("🏆 정규리그 순위표", "팀순위"),
            ],
        )
    }

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[item_card_output, commentary_card_output],
            quickReplies=SUMMARY_QUICK_REPLIES,
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
            title = f"{home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{time_str}{arena_str} | 최종 종료"
        else:
            title = f"{home} vs {away}"
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
            title = f"{home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 경기 종료"
        else:
            title = f"{home} vs {away}"
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
            title = f"{home} {g.get('home_score', 0)}:{g.get('away_score', 0)} {away}"
            desc = f"{dt_str} [{arena}] | 종료"
        else:
            title = f"{home} vs {away}"
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
    page: int = 1,
) -> KakaoSkillResponse:
    """
    Build response for '뉴스'.
    Supports 5 news items per page and continuous fresh news cycling via '🔄 새로운 뉴스' (Pages 1..5).
    Returns pure listCard with verified official logos/press photos and action buttons.
    """
    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", f"{favorite_team} 농구단")
        default_img = get_team_logo(favorite_team)
    else:
        full_name = "KBL 프로농구"
        default_img = DEFAULT_SPORTS_LOGO

    total_pages = max(1, (len(news_items) + 4) // 5)
    curr_page = ((max(1, page) - 1) % total_pages) + 1 if total_pages > 1 else 1

    if curr_page >= 2:
        start_idx = (curr_page - 1) * 5
        slice_items = news_items[start_idx : start_idx + 5] if len(news_items) > start_idx else news_items[:5]
        header = (
            f"{favorite_team} 새로운 뉴스 ({curr_page}/{total_pages} 더보기)"
            if favorite_team
            else f"KBL 새로운 뉴스 ({curr_page}/{total_pages} 더보기)"
        )
        if curr_page < total_pages:
            next_p = curr_page + 1
            next_msg = f"#{favorite_team} 새로운 뉴스 {next_p}" if favorite_team else f"새로운 뉴스 {next_p}"
            toggle_btn = _msg_btn("🔄 새로운 뉴스", next_msg)
            qr_news = QuickReply(label="🔄 새로운 뉴스", messageText=next_msg)
        else:
            reset_msg = f"#{favorite_team} 뉴스" if favorite_team else "뉴스"
            toggle_btn = _msg_btn("최신 뉴스로", reset_msg)
            qr_news = QuickReply(label="🔄 최신 뉴스로", messageText=reset_msg)
    else:
        slice_items = news_items[:5]
        header = f"{favorite_team} 관련 뉴스" if favorite_team else "KBL 프로농구 최신 뉴스"
        if total_pages > 1:
            next_msg = f"#{favorite_team} 새로운 뉴스 2" if favorite_team else "새로운 뉴스 2"
            toggle_btn = _msg_btn("🔄 새로운 뉴스", next_msg)
            qr_news = QuickReply(label="🔄 새로운 뉴스", messageText=next_msg)
        else:
            toggle_btn = _msg_btn("📰 KBL 전체 뉴스", "KBL 전체 뉴스")
            qr_news = QuickReply(label="📰 KBL 전체 뉴스", messageText="KBL 전체 뉴스")

    items: list[dict[str, Any]] = []
    for item in slice_items:
        title = item.get("title", "프로농구 소식")
        url = item.get("url", "https://sports.daum.net/basketball")
        raw_time = item.get("time") or ""
        date_match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", raw_time)
        if date_match:
            time_desc = f"{int(date_match.group(2)):02d}.{int(date_match.group(3)):02d}."
        elif raw_time:
            time_desc = raw_time
        else:
            time_desc = item.get("source") or "최신 뉴스"

        items.append({
            "title": title,
            "description": time_desc,
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
            toggle_btn,
            _msg_btn("다른팀 뉴스", "다른팀 뉴스"),
        ],
    )
    custom_qr = [
        qr_news,
        QuickReply(label="🏀 다른팀 뉴스", messageText="다른팀 뉴스"),
        QuickReply(label="🏀 전체 뉴스", messageText="전체 뉴스"),
    ]
    all_teams_order = ["SK", "KT", "DB", "LG", "소노", "KCC", "현대모비스", "정관장", "한국가스공사", "삼성"]
    other_teams = [t for t in all_teams_order if t != favorite_team]
    for ot in other_teams:
        if len(custom_qr) >= 9:
            break
        alias_label = "모비스" if ot == "현대모비스" else ("가스공사" if ot == "한국가스공사" else ot)
        custom_qr.append(QuickReply(label=f"📰 {alias_label} 뉴스", messageText=f"{alias_label} 뉴스"))

    while len(custom_qr) < 9:
        for qr in MAIN_MENU_QUICK_REPLIES:
            if qr.label != "홈으로" and qr.label not in [q.label for q in custom_qr]:
                custom_qr.append(qr)
                if len(custom_qr) >= 9:
                    break
    custom_qr.append(QuickReply(label="홈으로", messageText="처음으로"))

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=custom_qr,
        )
    )


def _build_region_menu_cards(
    menu_type: str,
    specs: list[tuple[str, str, str, list[tuple[str, str]]]],
) -> list[dict[str, Any]]:
    """Build 4 regional carousel cards with 2:1 multi-club banners (no cropped square logos)."""
    base_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
    return [
        _basic_card(
            title=title,
            description=desc,
            thumbnail_url=f"{base_url}/integrations/kakao/skills/banner/menu/{menu_type}/{region_key}.png?v=menu_v1",
            fixed_ratio=False,
            width=800,
            height=400,
            buttons=[_msg_btn(lbl, msg) for lbl, msg in btn_specs],
        )
        for region_key, title, desc, btn_specs in specs
    ]


def build_team_news_menu_response(
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build a 4-card carousel menu allowing 1-tap browsing of news for all 10 KBL clubs + KBL overall news.
    """
    cards = _build_region_menu_cards(
        "news",
        [
            (
                "capital",
                "📰 수도권 구단 뉴스",
                "서울 SK, 수원 KT, 서울 삼성의 최신 구단 소식 및 선수단 인터뷰를 확인하세요.",
                [("📰 서울 SK 뉴스", "SK 뉴스"), ("📰 수원 KT 뉴스", "KT 뉴스"), ("📰 서울 삼성 뉴스", "삼성 뉴스")],
            ),
            (
                "gangwon_gyeonggi",
                "📰 경기·강원 구단 뉴스",
                "원주 DB, 안양 정관장, 고양 소노의 최신 구단 소식 및 경기 리뷰를 확인하세요.",
                [("📰 원주 DB 뉴스", "DB 뉴스"), ("📰 안양 정관장 뉴스", "정관장 뉴스"), ("📰 고양 소노 뉴스", "소노 뉴스")],
            ),
            (
                "yeongnam",
                "📰 영남권 구단 뉴스",
                "창원 LG, 부산 KCC, 울산 현대모비스의 최신 구단 소식 및 경기 리뷰를 확인하세요.",
                [("📰 창원 LG 뉴스", "LG 뉴스"), ("📰 부산 KCC 뉴스", "KCC 뉴스"), ("📰 현대모비스 뉴스", "모비스 뉴스")],
            ),
            (
                "daegu",
                "📰 대구 구단 & KBL 전체 뉴스",
                "대구 한국가스공사 페가수스 및 KBL 프로농구 리그 전체 주요 헤드라인을 확인하세요.",
                [("📰 한국가스공사 뉴스", "가스공사 뉴스"), ("🏀 KBL 전체 뉴스", "전체 뉴스"), ("🏠 처음으로", "처음으로")],
            ),
        ],
    )
    menu_qrs = [
        QuickReply(label="🏀 전체 뉴스", messageText="전체 뉴스"),
        QuickReply(label="📰 SK 뉴스", messageText="SK 뉴스"),
        QuickReply(label="📰 KT 뉴스", messageText="KT 뉴스"),
        QuickReply(label="📰 DB 뉴스", messageText="DB 뉴스"),
        QuickReply(label="📰 LG 뉴스", messageText="LG 뉴스"),
        QuickReply(label="📰 소노 뉴스", messageText="소노 뉴스"),
        QuickReply(label="📰 KCC 뉴스", messageText="KCC 뉴스"),
        QuickReply(label="📰 모비스 뉴스", messageText="모비스 뉴스"),
        QuickReply(label="📰 가스공사 뉴스", messageText="가스공사 뉴스"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
    ]
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"carousel": {"type": "basicCard", "items": cards}}],
            quickReplies=menu_qrs,
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
    import urllib.parse

    if favorite_team:
        full_name = TEAM_INFO.get(favorite_team, {}).get("full_name", f"{favorite_team} 농구단")
        header = f"🎬 [{full_name}] 주요장면"
        if _u16_len(header) > 22:
            header = f"🎬 [{favorite_team}] 주요장면 & 하이라이트"
        default_img = get_team_logo(favorite_team)
        tving_vclip_url = (
            f"https://www.youtube.com/@tvingsports/search?query="
            f"{urllib.parse.quote(f'2026-27 KCC 프로농구 {favorite_team} 하이라이트')}"
        )
    else:
        header = "🎬 KBL 프로농구 주요장면"
        default_img = DEFAULT_SPORTS_LOGO
        tving_vclip_url = (
            "https://www.youtube.com/@tvingsports/search?query="
            "2026-27+KCC+%ED%94%84%EB%A1%9C%EB%86%8D%EA%B5%AC+%ED%95%98%EC%9D%B4%EB%9D%BC%EC%9D%B4%ED%8A%B8"
        )

    items: list[dict[str, Any]] = []
    for item in highlights[:5]:
        title = item.get("title", "KBL 경기 하이라이트")
        raw_url = item.get("url") or "https://www.youtube.com/@onkbl/videos"
        # Replace broken legacy /video/kbl SPA route or Daum vclip search with official TVING highlights
        if "sports.daum.net/video/kbl" in raw_url or "search.daum.net/search?w=vclip" in raw_url:
            url = tving_vclip_url
        else:
            url = raw_url
        arena = str(item.get("arena") or "TVING / KBL TV 공식 영상")
        desc = re.sub(r"^[^\w가-힣#()\[\]]+", "", arena).strip() or arena
        items.append({
            "title": title,
            "description": desc,
            "imageUrl": item.get("imageUrl") or default_img,
            "link": {"web": url},
        })

    if not items:
        items.append({
            "title": "등록된 주요장면 영상이 없습니다.",
            "description": "KBL TV 및 TVING SPORTS 공식 유튜브에서 시청하실 수 있습니다.",
            "imageUrl": default_img,
            "link": {"web": "https://www.youtube.com/@onkbl/videos"},
        })

    card = _list_card(
        header_title=header,
        items=items,
        buttons=[
            _link_btn("📺 KBL TV 유튜브", "https://www.youtube.com/@onkbl/videos"),
            _link_btn("🎬 TVING 하이라이트", tving_vclip_url),
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
    Highlights KBL 6강 플레이오프 threshold and streak indicators.
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

        streak = s.get("streak", "")
        streak_str = ""
        if streak and streak != "-":
            streak_str = f" | {streak}🔥" if "연승" in streak else (f" | {streak}❄️" if "연패" in streak else f" | {streak}")

        po_tag = " [PO마지노선]" if rank == 6 else ""

        return {
            "title": f"{rank}위 {fav}{team}{po_tag}"[:35],
            "description": f"{wins}승 {losses}패 ({wpct_str}) | {gb_str}{streak_str}"[:30],
            "imageUrl": get_team_logo(raw_team),
            "link": {"web": "https://sports.daum.net/record/kbl"},
        }

    top_items = [_make_item(s, i) for i, s in enumerate(standings[:5], start=1)]
    bottom_items = [_make_item(s, i) for i, s in enumerate(standings[5:10], start=6)]

    card1 = _list_card(
        header_title=f"🏆 {get_current_season()} KBL 순위 (1~5위 상위권)",
        items=top_items or [{
            "title": "순위 집계 중",
            "description": "KBL 순위 데이터",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        }],
        buttons=[
            _msg_btn("🏅 선수 순위 보기", "선수순위"),
            _link_btn("📊 전체 순위 상세", "https://sports.daum.net/record/kbl"),
        ],
    )

    outputs = [card1]
    if bottom_items:
        card2 = _list_card(
            header_title=f"🔥 {get_current_season()} KBL 6~10위 순위",
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

    from services.content.lineup_board import get_player_photo_url

    items: list[dict[str, Any]] = []
    for idx, p in enumerate(rankings[:5], start=1):
        rank = p.get("rank", idx)
        name = p.get("name", "?")
        team = p.get("team", "?")
        val = p.get("value", 0.0)
        items.append({
            "title": f"{rank}위 {name} ({team})",
            "description": f"시즌 평균 {val}{unit}",
            "imageUrl": get_player_photo_url(name) or get_team_logo(team),
            "link": {"web": "https://sports.daum.net/record/kbl/person"},
        })

    if not items:
        items.append({
            "title": "선수 순위를 집계 중입니다.",
            "description": "KBL 공식 기록실에서 확인하세요.",
            "imageUrl": get_team_logo("SK"),
        })

    next_cat_map = {
        "pts": ("ast", "어시스트", "어시스트순위"),
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
            _link_btn("📊 선수 기록 전체보기", "https://sports.daum.net/record/kbl/person"),
        ],
    )

    player_rank_quick_replies: list[QuickReply] = [
        QuickReply(label="🏀 득점", messageText="득점순위"),
        QuickReply(label="🏀 어시스트", messageText="어시스트순위"),
        QuickReply(label="🏀 리바운드", messageText="리바운드순위"),
        QuickReply(label="🏀 블록슛", messageText="블록순위"),
        QuickReply(label="🏀 스틸", messageText="스틸순위"),
        QuickReply(label="🏀 3점슛", messageText="3점슛순위"),
        QuickReply(label="⭐ 관심선수", messageText="관심선수"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="📅 오늘 경기", messageText="오늘 경기"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
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

    from services.content.lineup_board import get_player_photo_url

    if is_favorite:
        full_lbl = f"➖ {name} 관심선수 해제"
        lbl = full_lbl if _u16_len(full_lbl) <= 14 else f"➖ {name} 해제"
        toggle_btn = _msg_btn(lbl, f"#관심선수 삭제 {name}")
    else:
        full_lbl = f"➕ {name} 관심선수 등록"
        lbl = full_lbl if _u16_len(full_lbl) <= 14 else f"➕ {name} 등록"
        toggle_btn = _msg_btn(lbl, f"#관심선수 {name}")

    base_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
    q_name = urllib.parse.quote(str(name))
    q_team = urllib.parse.quote(str(team))
    q_pos = urllib.parse.quote(str(pos))
    q_no = urllib.parse.quote(str(no))
    player_banner_url = (
        f"{base_url}/integrations/kakao/skills/banner/player/{q_name}.png"
        f"?team={q_team}&pos={q_pos}&no={q_no}&pts={pts}&reb={reb}&ast={ast}&v=player_v1"
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
            thumbnail_url=player_banner_url,
            fixed_ratio=False,
            width=800,
            height=400,
            buttons=[
                toggle_btn,
                _msg_btn("⭐ 관심선수 목록", "관심선수"),
                _share_btn("📤 선수 스탯 공유하기"),
            ],
        )
    }
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=MAIN_MENU_QUICK_REPLIES,
        )
    )


def _team_starters_banner_url(
    base_url: str,
    team: str,
    part: int,
    starter_names: list[str],
) -> str:
    """Build URL-encoded 2:1 Best 5 banner URL with content-hash query param for automatic cache-busting."""
    q_team = urllib.parse.quote(str(team))
    sig = hashlib.md5("|".join(starter_names).encode("utf-8")).hexdigest()[:8]
    return f"{base_url.rstrip('/')}/integrations/kakao/skills/banner/team/{q_team}/{part}.png?v=s_{sig}"


def build_team_players_response(
    team: str,
    players: list[dict[str, Any]],
    fav_players: list[str],
) -> KakaoSkillResponse:
    """
    Build response listing players of a specific team.
    Returns listCard overview + 2-card carousel covering all Best 5 starters.
    """
    full = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
    starters_info = TEAM_LINEUPS.get(team, {}).get("starters", [])
    starter_names = [s["name"] for s in starters_info] if starters_info else [p["name"] for p in players[:5]]

    # Ensure Best 5 starters come first
    def _player_sort_key(p: dict[str, Any]) -> int:
        if p["name"] in starter_names:
            return starter_names.index(p["name"])
        return 100

    sorted_players = sorted(players, key=_player_sort_key)

    from services.content.lineup_board import get_player_photo_url

    items = []
    for p in sorted_players[:5]:
        star = "⭐ " if p["name"] in fav_players else ""
        items.append({
            "title": f"{star}{p['name']} ({p['pos']} #{p['no']})",
            "description": f"평균 {p['pts']}점 | {p['reb']}리바 | {p['ast']}어시",
            "imageUrl": get_player_photo_url(p["name"]) or get_team_logo(team),
            "link": {"web": "https://sports.daum.net/record/kbl/person"},
        })
    if not items:
        items.append({
            "title": f"{team} 등록 선수가 없습니다.",
            "description": "선수 명단이 업데이트 중입니다.",
            "imageUrl": get_team_logo(team),
        })

    team_header = f"🏀 [{full}] 공식 베스트 5"
    if _u16_len(team_header) > 24:
        team_header = f"🏀 [{team}] 공식 베스트 5"

    list_card = _list_card(
        header_title=team_header,
        items=items,
        buttons=[
            _msg_btn("🏀 다른 구단 찾기", "구단별 선수"),
            _msg_btn("⭐ 내 관심선수 목록", "관심선수"),
        ],
    )

    def _p_toggle_btn(name: str) -> dict[str, str]:
        if name in fav_players:
            return _msg_btn(f"➖ {name} 해제", f"#관심선수 삭제 {name}")
        return _msg_btn(f"➕ {name} 등록", f"#관심선수 {name}")

    t_info = TEAM_LINEUPS.get(team, {})
    t_coach = t_info.get("head_coach", "")
    t_foreign = ", ".join(t_info.get("foreign_players", []))
    t_aq = t_info.get("asian_quota", "")
    t_bench = ", ".join(t_info.get("key_bench", [])[:4])

    base_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
    banner_1_url = _team_starters_banner_url(base_url, team, 1, starter_names)
    banner_2_url = _team_starters_banner_url(base_url, team, 2, starter_names)

    card1 = _basic_card(
        title=f"⭐ [{team}] Best 5 등록 (1/2)",
        description=(
            f"• 구단/감독: {full} ({t_coach} 감독)\n"
            f"• 주전 (1~3): {', '.join(starter_names[:3])}\n"
            f"• 외국인 용병: {t_foreign}\n"
            f"• 아시아쿼터: {t_aq}"
        )[:300],
        thumbnail_url=banner_1_url,
        fixed_ratio=False,
        width=800,
        height=400,
        buttons=[_p_toggle_btn(name) for name in starter_names[:3]],
    )
    carousel_cards = [card1]
    if len(starter_names) >= 4:
        b2 = [_p_toggle_btn(name) for name in starter_names[3:5]]
        b2.append(_msg_btn("🏀 다른 구단 찾기", "구단별 선수"))
        card2 = _basic_card(
            title=f"⭐ [{team}] Best 5 등록 (2/2)",
            description=(
                f"• 구단/감독: {full} ({t_coach} 감독)\n"
                f"• 주전 (4~5): {', '.join(starter_names[3:5])}\n"
                f"• 식스맨/벤치: {t_bench}"
            )[:300],
            thumbnail_url=banner_2_url,
            fixed_ratio=False,
            width=800,
            height=400,
            buttons=b2,
        )
        carousel_cards.append(card2)

    team_quick_replies = [
        QuickReply(label="🏀 다른 구단 찾기", messageText="구단별 선수"),
        QuickReply(label="⭐ 내 관심선수", messageText="관심선수"),
        QuickReply(label=f"📰 {team} 뉴스", messageText=f"{team} 뉴스"),
        QuickReply(label=f"📅 {team} 일정", messageText=f"{team} 일정"),
        QuickReply(label="🏅 선수순위", messageText="선수순위"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[list_card, {"carousel": {"type": "basicCard", "items": carousel_cards}}],
            quickReplies=team_quick_replies,
        )
    )


def build_team_players_menu_response(
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build a 4-card carousel menu allowing 1-tap browsing of players for all 10 KBL clubs.
    """
    cards = _build_region_menu_cards(
        "players",
        [
            (
                "capital",
                "🏀 수도권 구단 선수단",
                "서울 SK, 수원 KT, 서울 삼성의 주요 선수 명단을 확인하고 관심선수로 등록하세요.",
                [("🏀 서울 SK 선수", "SK 선수"), ("🏀 수원 KT 선수", "KT 선수"), ("🏀 서울 삼성 선수", "삼성 선수")],
            ),
            (
                "gangwon_gyeonggi",
                "🏀 경기·강원 구단 선수단",
                "원주 DB, 안양 정관장, 고양 소노의 주요 선수 명단을 확인하고 관심선수로 등록하세요.",
                [("🏀 원주 DB 선수", "DB 선수"), ("🏀 안양 정관장 선수", "정관장 선수"), ("🏀 고양 소노 선수", "소노 선수")],
            ),
            (
                "yeongnam",
                "🏀 영남권 구단 선수단",
                "창원 LG, 부산 KCC, 울산 현대모비스의 주요 선수 명단을 확인하고 관심선수로 등록하세요.",
                [("🏀 창원 LG 선수", "LG 선수"), ("🏀 부산 KCC 선수", "KCC 선수"), ("🏀 현대모비스 선수", "현대모비스 선수")],
            ),
            (
                "daegu",
                "🏀 대구 구단 & 관심선수 관리",
                "대구 한국가스공사 페가수스 선수단 및 KBL 전체 득점·어시스트 순위를 확인하세요.",
                [("🏀 한국가스공사 선수", "한국가스공사 선수"), ("⭐ 내 관심선수 목록", "관심선수"), ("🏅 KBL 선수 순위", "선수순위")],
            ),
        ],
    )
    quick_replies = [
        QuickReply(label="🏀 SK 선수", messageText="SK 선수"),
        QuickReply(label="🏀 KT 선수", messageText="KT 선수"),
        QuickReply(label="🏀 DB 선수", messageText="DB 선수"),
        QuickReply(label="🏀 LG 선수", messageText="LG 선수"),
        QuickReply(label="🏀 KCC 선수", messageText="KCC 선수"),
        QuickReply(label="🏀 소노 선수", messageText="소노 선수"),
        QuickReply(label="🏀 모비스 선수", messageText="현대모비스 선수"),
        QuickReply(label="🏀 정관장 선수", messageText="정관장 선수"),
        QuickReply(label="🏀 가스공사 선수", messageText="한국가스공사 선수"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
    ]
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"carousel": {"type": "basicCard", "items": cards}}],
            quickReplies=quick_replies,
        )
    )


def build_favorite_players_response(
    fav_players: list[str],
    search_results: list[dict[str, Any]] | None = None,
    notice: str | None = None,
    favorite_team: str | None = None,
    base_url: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '관심선수'.
    Returns pure visual cards (listCard + carousel) without speech bubbles.
    Uses 2:1 ratio (800x400) dedicated visual banners with player portraits and official emblems.
    IMPORTANT: Kakao enforces a strict 30,720-byte per-bubble limit (bubbleExtraBytesLimit),
    where each basicCard inside a carousel uses ~4,200 bytes internally.
    Therefore, carousel_items MUST be capped at <= 5 cards (~20,500 bytes).
    """
    from services.content.lineup_board import get_player_photo_url

    b_url = (base_url or _DEFAULT_PUBLIC_BASE_URL).rstrip("/")
    fallback_logo = get_team_logo(favorite_team or "SK")
    items = []
    if fav_players:
        for name in fav_players[:5]:
            p_photo = get_player_photo_url(name)
            p_info = next((p for p in KBL_PLAYERS if p["name"] == name), None)
            if p_info:
                p_team = p_info["team"]
                items.append({
                    "title": f"⭐ {p_info['name']} ({p_team} #{p_info['no']})",
                    "description": f"시즌 평균: {p_info['pts']}점 | {p_info['reb']}리바 | {p_info['ast']}어시",
                    "imageUrl": p_photo or get_team_logo(p_team),
                    "link": {"web": "https://sports.daum.net/record/kbl/person"},
                })
            else:
                # Fallback lookup in TEAM_LINEUPS if not in KBL_PLAYERS
                found_team = None
                for t_code, l_info in TEAM_LINEUPS.items():
                    all_t_names = (
                        [s.get("name", "") for s in l_info.get("starters", [])]
                        + l_info.get("foreign_players", [])
                        + ([l_info["asian_quota"]] if l_info.get("asian_quota") else [])
                        + l_info.get("key_bench", [])
                    )
                    if name in all_t_names:
                        found_team = t_code
                        break
                items.append({
                    "title": f"⭐ {name}" + (f" ({found_team})" if found_team else ""),
                    "description": "내 등록 관심선수",
                    "imageUrl": p_photo or (get_team_logo(found_team) if found_team else fallback_logo),
                })
    else:
        items.append({
            "title": "등록된 관심선수가 없습니다.",
            "description": "아래 카드 버튼을 눌러 좋아하는 선수를 등록해보세요!",
            "imageUrl": fallback_logo,
        })

    header_title = "⭐ 내 관심선수 현황"
    if notice:
        header_title = f"✅ {notice}"

    list_card = _list_card(
        header_title=header_title,
        items=items,
        buttons=[
            _msg_btn("🏀 구단별 선수 찾기", "구단별 선수"),
            _msg_btn("🏅 전체 선수 순위", "선수순위"),
        ],
    )

    def _player_toggle_btn(name: str) -> dict[str, str]:
        if name in fav_players:
            return _msg_btn(f"➖ {name} 해제", f"#관심선수 삭제 {name}")
        return _msg_btn(f"➕ {name} 등록", f"#관심선수 {name}")

    carousel_items: list[dict[str, Any]] = []

    if favorite_team:
        starters_info = TEAM_LINEUPS.get(favorite_team, {}).get("starters", [])
        starter_names = [s["name"] for s in starters_info] if starters_info else [p["name"] for p in KBL_PLAYERS if p.get("team") == favorite_team][:5]
        full_t = TEAM_INFO.get(favorite_team, {}).get("full_name", favorite_team)
        if len(starter_names) >= 3:
            thumb_t1 = _team_starters_banner_url(b_url, favorite_team, 1, starter_names)
            carousel_items.append(
                _basic_card(
                    title=f"❤️ [{favorite_team}] 응원팀 선수 Best 5 (1/2)",
                    description=f"{full_t} 선발 주전 멤버 (1~3)를 관심선수로 등록하세요.",
                    thumbnail_url=thumb_t1,
                    buttons=[_player_toggle_btn(p_name) for p_name in starter_names[:3]],
                    width=800,
                    height=400,
                )
            )
        if len(starter_names) >= 4:
            b2 = [_player_toggle_btn(p_name) for p_name in starter_names[3:5]]
            b2.append(_msg_btn(f"🏀 {favorite_team} 선수단", f"{favorite_team} 선수"))
            thumb_t2 = _team_starters_banner_url(b_url, favorite_team, 2, starter_names)
            carousel_items.append(
                _basic_card(
                    title=f"❤️ [{favorite_team}] 응원팀 선수 Best 5 (2/2)",
                    description=f"{full_t} 선발 주전 멤버 (4~5)를 관심선수로 등록하세요.",
                    thumbnail_url=thumb_t2,
                    buttons=b2,
                    width=800,
                    height=400,
                )
            )

    star_guards = ["김선형", "허훈", "이정현"]
    thumb_guards = f"{b_url}/integrations/kakao/skills/banner/category/guards.png?v=nanum20261117_800x400"
    carousel_items.append(
        _basic_card(
            title="⭐ 인기 가드 등록",
            description="버튼을 누르면 즉시 등록/해제됩니다. (선수 이름 직접 입력 가능)",
            thumbnail_url=thumb_guards,
            buttons=[_player_toggle_btn(n) for n in star_guards],
            width=800,
            height=400,
        )
    )

    if not favorite_team or not fav_players:
        star_bigs = ["자밀 워니", "아셈 마레이", "유기상"]
        thumb_bigs = f"{b_url}/integrations/kakao/skills/banner/category/bigs.png?v=nanum20261117_800x400"
        carousel_items.append(
            _basic_card(
                title="⭐ 인기 빅맨/슈터 등록",
                description="버튼을 누르면 즉시 등록/해제됩니다.",
                thumbnail_url=thumb_bigs,
                buttons=[_player_toggle_btn(n) for n in star_bigs],
                width=800,
                height=400,
            )
        )

    thumb_teams = f"{b_url}/integrations/kakao/skills/banner/category/all_teams.png?v=nanum20261117_800x400"
    carousel_items.append(
        _basic_card(
            title="🏀 [구단별 선수] 수도권·경기·강원·영남권",
            description="10개 구단(SK·KT·삼성·DB·정관장·소노·LG·KCC·모비스·가스공사) 선수단을 확인하세요.",
            thumbnail_url=thumb_teams,
            buttons=[
                _msg_btn("🏀 구단별 선수 메뉴", "구단별 선수"),
                _msg_btn("🏀 서울 SK 선수", "SK 선수"),
                _msg_btn("🏀 원주 DB 선수", "DB 선수"),
            ],
            width=800,
            height=400,
        )
    )

    if fav_players:
        del_buttons = [_msg_btn(f"➖ {p_name} 해제", f"#관심선수 삭제 {p_name}") for p_name in fav_players[:3]]
        carousel_items.append(
            _basic_card(
                title="⚙️ 관심선수 간편 해제",
                description="추적을 원하지 않는 선수를 해제하세요.",
                thumbnail_url=thumb_teams,
                buttons=del_buttons,
                width=800,
                height=400,
            )
        )

    outputs = [list_card]
    if carousel_items:
        # Strict 5-card limit so Kakao's internal messageBytes (~4.2KB/card) stays <= 21KB (< 30,720B limit)
        outputs.append({"carousel": {"type": "basicCard", "items": carousel_items[:5]}})

    return KakaoSkillResponse(
        template=KakaoTemplate(outputs=outputs, quickReplies=FAVORITE_PLAYERS_QUICK_REPLIES)
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
        is_closed = c.get("is_closed", False)
        status = c.get("status", "SCHEDULED")

        filled = max(1, min(9, round(h_pct / 10)))
        bar = ("🟥" * filled) + ("🟦" * (10 - filled))

        if is_closed:
            if status == "FINAL":
                title_tag = " [✅ 경기 종료]"
                close_note = "※ 경기가 종료되어 예측이 마감되었습니다.\n"
            else:
                title_tag = " [🔒 3Q 예측 마감]"
                close_note = "※ 3쿼터 진입으로 예측이 마감되었습니다.\n"
        else:
            title_tag = ""
            close_note = ""

        desc_prefix = f"🎉 {notice}\n" if notice else close_note
        if user_pick:
            pick_str = f"✅ 내 선택: {user_pick} 승리" + (" (마감)" if is_closed else "")
        else:
            pick_str = "승부예측 미참여 (마감)" if is_closed else f"승리팀 예측 투표(+10P) / 누적 {user_points}P"

        if is_closed:
            card_btns = [
                _msg_btn("📊 내 예측 결과", "예측결과"),
                _msg_btn("🔴 실시간 스코어", "실시간 점수"),
                _msg_btn("📅 경기 일정", "일정"),
            ]
        else:
            card_btns = [
                _msg_btn(f"🗳️ {home} 승리", f"#승부예측 {home}"),
                _msg_btn(f"🗳️ {away} 승리", f"#승부예측 {away}"),
                _msg_btn("📊 내 예측 결과", "예측결과"),
            ]

        cards.append(
            _basic_card(
                title=f"🏀 {home} vs {away} 승부예측{title_tag}",
                description=(
                    f"{desc_prefix}"
                    f"{home} {h_pct}% ({h_votes}표) vs {away} {a_pct}% ({a_votes}표)\n"
                    f"{bar}\n"
                    f"{pick_str}"
                ),
                thumbnail_url=get_team_logo(home),
                buttons=card_btns,
            )
        )

    cheer_quick_replies = [
        QuickReply(label="📊 내 예측 결과", messageText="예측결과"),
        QuickReply(label="💰 내 포인트 확인", messageText="포인트"),
        QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="📋 라인업", messageText="라인업"),
        QuickReply(label="⚙️ 알림설정", messageText="알림설정"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
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
    streak: int = 0,
    user_hmac: str | None = None,
) -> KakaoSkillResponse:
    """
    Build rich basicCard response for '포인트' / '내 포인트' / '포인트 확인'.
    Displays total point balance, fan tier status, next tier progress, and point tips.
    """
    from core.cache.redis import format_auto_fan_nickname

    tier_name, badge, needed = get_point_tier(user_points)
    auto_nick = format_auto_fan_nickname(user_hmac or favorite_team or "kbl", user_points, favorite_team)
    next_msg = (
        f"다음 등급까지 {needed}P 남음!"
        if needed > 0
        else "최고 등급 달성! 🎉"
    )
    fav_team_str = f" [{favorite_team} 팬]" if favorite_team else ""
    streak_str = f"\n• 연승 보너스 : 🔥 {streak}연승 질주 중! (3연승 +30P / 5연승 +100P)" if streak > 0 else ""

    desc = (
        f"• 랭킹 닉네임 : {auto_nick}{fav_team_str}\n"
        f"• 농구팬 등급 : {tier_name} · {next_msg}{streak_str}\n"
        f"• 적립: 참여 +10P | 적중 +50P | 3/5/10연승 추가"
    )

    base_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
    q_team = urllib.parse.quote(favorite_team or "all")
    q_nick = urllib.parse.quote(auto_nick)
    points_banner_url = (
        f"{base_url}/integrations/kakao/skills/banner/points/{q_team}.png"
        f"?pts={user_points}&nick={q_nick}&v=pts_v1"
    )
    card = _basic_card(
        title=f"{badge} 내 승부예측 포인트: {user_points:,} P",
        description=desc[:380],
        thumbnail_url=points_banner_url,
        fixed_ratio=False,
        width=800,
        height=400,
        buttons=[
            _msg_btn("🏆 승부예측 랭킹", "승부예측 랭킹"),
            _msg_btn("🗳️ 오늘 경기 승부예측", "승부예측"),
            _share_btn("📤 내 적중률 자랑하기"),
        ],
    )

    point_quick_replies = [
        QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
        QuickReply(label="🏆 승부예측 랭킹", messageText="승부예측 랭킹"),
        QuickReply(label="📊 예측결과", messageText="예측결과"),
        QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="🏅 선수순위", messageText="선수순위"),
        QuickReply(label="⚙️ 알림설정", messageText="알림설정"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
    ]

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"basicCard": card}],
            quickReplies=point_quick_replies,
        )
    )


def build_prediction_leaderboard_response(
    rankings: list[dict[str, Any]],
    user_points: int,
    user_rank: int = 12,
    streak: int = 0,
    favorite_team: str | None = None,
    user_hmac: str | None = None,
) -> KakaoSkillResponse:
    """
    Build pure listCard response for '승부예측 랭킹' / '리더보드'.
    Displays monthly top users with Option 1 auto-generated nicknames (`{응원팀} {등급}#{고유4자리}`),
    streaks, and current user's live ranking status.
    """
    from core.cache.redis import format_auto_fan_nickname

    my_nick = (
        format_auto_fan_nickname(user_hmac, user_points, favorite_team)
        if user_hmac
        else None
    )
    items = []
    max_top = 4 if (my_nick and not any(r.get("nickname") == my_nick for r in rankings[:5])) else 5
    for r in rankings[:max_top]:
        rank = r.get("rank", 1)
        nick = str(r.get("nickname", "팬"))
        team = str(r.get("team", ""))
        pts = int(r.get("points", 0))
        stk = int(r.get("streak", 0))
        stk_str = f" ({stk}연승🔥)" if stk >= 3 else ""
        me_tag = " 👈나" if (my_nick and nick == my_nick) else ""
        if "#" in nick:
            item_title = f"{rank}위 {nick}{me_tag}"[:35]
        else:
            item_title = f"{rank}위 {nick} ({team}팬){me_tag}"[:35]
        items.append({
            "title": item_title,
            "description": f"{pts:,}P 획득{stk_str}"[:30],
            "imageUrl": get_team_logo(team) if team else DEFAULT_SPORTS_LOGO,
            "link": {"web": "https://sports.daum.net/record/kbl"},
        })

    if my_nick and not any(r.get("nickname") == my_nick for r in rankings[:5]):
        streak_msg = f" ({streak}연승🔥)" if streak > 0 else ""
        items.append({
            "title": f"나의 닉네임: {my_nick}"[:35],
            "description": f"보유 {user_points:,}P{streak_msg}"[:30],
            "imageUrl": get_team_logo(favorite_team) if favorite_team else DEFAULT_SPORTS_LOGO,
            "link": {"web": "https://sports.daum.net/record/kbl"},
        })
    fav_str = f" [{favorite_team} 팬]" if favorite_team else ""
    header_title = f"🏆 KBL 승부예측 월간 랭킹{fav_str}"[:35].strip()

    card = _list_card(
        header_title=header_title,
        items=items or [{
            "title": "집계 중",
            "description": "승부예측 랭킹 집계 중입니다.",
            "imageUrl": DEFAULT_SPORTS_LOGO,
        }],
        buttons=[
            _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
            _msg_btn("💰 내 포인트 확인", "내 포인트"),
        ],
    )
    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[card],
            quickReplies=[
                QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
                QuickReply(label="📊 내 예측결과", messageText="예측결과"),
                QuickReply(label="💰 내 포인트", messageText="내 포인트"),
                QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
                QuickReply(label="🏆 팀순위", messageText="팀순위"),
                QuickReply(label="🏠 홈으로", messageText="처음으로"),
            ],
        )
    )


def build_prediction_results_response(
    results: list[dict[str, Any]],
    stats: dict[str, Any],
    user_points: int,
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build response for '예측결과' / '승부예측 결과' (Prediction outcome and settlement report).
    Displays user's prediction history, win/miss outcome, hit points (+50P), and total record.
    """
    quick_replies = [
        QuickReply(label="🗳️ 오늘 승부예측", messageText="승부예측"),
        QuickReply(label="💰 내 포인트 확인", messageText="포인트"),
        QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
        QuickReply(label="🏆 팀순위", messageText="팀순위"),
        QuickReply(label="⚙️ 알림설정", messageText="알림설정"),
        QuickReply(label="🏠 홈으로", messageText="처음으로"),
    ]

    tier_name, badge, _ = get_point_tier(user_points)

    if not results:
        card = _list_card(
            header_title="📊 나의 KBL 승부예측 결과",
            items=[
                {
                    "title": "아직 참여한 승부예측이 없습니다.",
                    "description": "승부예측 참여 +10P, 적중 +50P 보너스!",
                    "imageUrl": DEFAULT_SPORTS_LOGO,
                },
                {
                    "title": f"내 보유 포인트: {user_points:,} P ({tier_name})",
                    "description": "매일 승부예측에 참여해 보세요!",
                    "imageUrl": DEFAULT_SPORTS_LOGO,
                },
            ],
            buttons=[
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
                _msg_btn("🏀 오늘 경기 보기", "오늘 경기"),
            ],
        )
        return KakaoSkillResponse(
            template=KakaoTemplate(outputs=[card], quickReplies=quick_replies)
        )

    cards: list[dict[str, Any]] = []

    # 1. Overall stats dashboard card
    hits = stats.get("hits", 0)
    misses = stats.get("misses", 0)
    pending = stats.get("pending", 0)
    total = stats.get("total", 0)
    hit_rate = stats.get("hit_rate", 0)

    fav_logo = get_team_logo(favorite_team) if favorite_team else DEFAULT_SPORTS_LOGO
    summary_desc = (
        f"• 나의 전적 : {hits}승 {misses}패 ({hit_rate}% 적중률)\n"
        f"• 참여 경기 : 총 {total}경기 (진행중 {pending}경기)\n"
        f"• 보유 포인트 : {user_points:,} P ({tier_name})\n"
        f"💡 승리팀 적중 시 1경기당 +50P 자동 보너스!"
    )
    cards.append(
        _basic_card(
            title=f"🏆 나의 승부예측 전적: {hits}승 {misses}패 ({hit_rate}%)",
            description=summary_desc,
            thumbnail_url=fav_logo,
            buttons=[
                _msg_btn("🗳️ 오늘 승부예측", "승부예측"),
                _msg_btn("💰 내 포인트", "포인트"),
                _share_btn("📤 내 적중률 자랑하기"),
            ],
        )
    )

    # 2. Individual game outcome cards (up to 4 recent games)
    for res in results[:4]:
        home = res["home_team"]
        away = res["away_team"]
        user_pick = res["user_pick"]
        status = res["status"]
        outcome_badge = res["outcome_badge"]
        score_text = res["score_text"]
        points_note = res.get("points_note", "")

        desc = (
            f"• 내 선택 : ✅ {user_pick} 승리 예측\n"
            f"• 경기 결과 : {score_text}\n"
            f"• 판정 : {outcome_badge}\n"
            f"{points_note}"
        ).strip()

        cards.append(
            _basic_card(
                title=f"🏀 {home} vs {away} 예측 결과",
                description=desc[:380],
                thumbnail_url=get_team_logo(home),
                buttons=[
                    _msg_btn("🔴 실시간 스코어", "실시간 점수"),
                    _msg_btn("🗳️ 승부예측", "승부예측"),
                    _share_btn("📤 내 적중률 자랑하기"),
                ],
            )
        )

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[{"carousel": {"type": "basicCard", "items": cards}}],
            quickReplies=quick_replies,
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

    on_off = lambda v: "ON" if v else "OFF"  # noqa: E731
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

    header_prefix = f"[{notice}]\n\n" if notice else ""
    summary_desc = (
        f"{header_prefix}"
        f"• 내 응원팀: {full_team}\n"
        f"• 관심선수: {players_str}\n"
        f"• 선발 라인업 알림 : {on_off(lineup_on)}\n"
        f"• 경기 시작 10분 전 : {on_off(start_on)}\n"
        f"• 경기 종료 및 결과 : {on_off(end_on)}\n"
        f"• 4Q 클러치 접전    : {on_off(clutch_on)}\n"
        f"• 경기 승부예측 알림: {on_off(pred_on)}"
    )

    import urllib.parse

    b_url = _DEFAULT_PUBLIC_BASE_URL.rstrip("/")
    t_code = favorite_team if (favorite_team and favorite_team in TEAM_INFO) else "SK"
    q_team = urllib.parse.quote(t_code)

    overview_banner_url = (
        f"{b_url}/integrations/kakao/skills/banner/home/team/{q_team}.png?v=home_v3_800x400"
    )
    core_banner_url = (
        f"{b_url}/integrations/kakao/skills/banner/settings/core.png"
        f"?s1={1 if lineup_on else 0}&s2={1 if start_on else 0}&s3={1 if end_on else 0}"
        f"&team={q_team}&v=notif_v1"
    )
    situational_banner_url = (
        f"{b_url}/integrations/kakao/skills/banner/settings/situational.png"
        f"?s1={1 if clutch_on else 0}&s2={1 if pred_on else 0}&s3=1"
        f"&team={q_team}&v=notif_v1"
    )

    cards = [
        _basic_card(
            title="⚙️ 프로농구봇 알림 및 환경설정",
            description=summary_desc[:380],
            thumbnail_url=overview_banner_url,
            buttons=[
                _msg_btn("❤️ 응원팀 변경", "#응원팀변경"),
                _msg_btn("⭐ 관심선수 관리", "관심선수"),
            ],
            fixed_ratio=False,
            width=800,
            height=400,
        ),
        _basic_card(
            title="🔔 경기 핵심 알림 ON/OFF",
            description=(
                f"현재 알림 상태:\n"
                f"• 선발 라인업 알림: {on_off(lineup_on)}\n"
                f"• 경기 시작 알림: {on_off(start_on)}\n"
                f"• 경기 종료 알림: {on_off(end_on)}"
            ),
            thumbnail_url=core_banner_url,
            buttons=[
                _msg_btn(f"라인업알림 {'OFF' if lineup_on else 'ON'}", "#알림 라인업"),
                _msg_btn(f"시작알림 {'OFF' if start_on else 'ON'}", "#알림 시작"),
                _msg_btn(f"종료알림 {'OFF' if end_on else 'ON'}", "#알림 종료"),
            ],
            fixed_ratio=False,
            width=800,
            height=400,
        ),
        _basic_card(
            title="🔔 상황별 알림 ON/OFF",
            description=(
                f"현재 알림 상태:\n"
                f"• 4Q 클러치 접전: {on_off(clutch_on)}\n"
                f"• 당일 승부예측 : {on_off(pred_on)}\n"
                f"• 내 응원팀: {full_team}"
            ),
            thumbnail_url=situational_banner_url,
            buttons=[
                _msg_btn(f"클러치알림 {'OFF' if clutch_on else 'ON'}", "#알림 클러치"),
                _msg_btn(f"승부예측알림 {'OFF' if pred_on else 'ON'}", "#알림 승부예측"),
                _msg_btn("❤️ 응원팀 변경", "#응원팀변경"),
            ],
            fixed_ratio=False,
            width=800,
            height=400,
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


def is_clutch_snapshot(snapshot: dict[str, Any]) -> bool:
    """Return True if a LIVE game is in a clutch situation (4Q <= 2:00 & diff <= 5, or OT)."""
    if snapshot.get("status") != "LIVE":
        return False
    h_score = int(snapshot.get("home_score") or 0)
    a_score = int(snapshot.get("away_score") or 0)
    diff = abs(h_score - a_score)
    if diff > 5:
        return False
    period = snapshot.get("period") or "?"
    try:
        p_num = int(period) if str(period).isdigit() else 4
    except Exception:
        p_num = 4
    if p_num < 4:
        return False
    if p_num >= 5:
        return True
    clock = snapshot.get("game_clock") or ""
    if clock:
        m_clk = re.match(r"^(\d+):(\d+)$", str(clock).strip())
        if m_clk:
            secs = int(m_clk.group(1)) * 60 + int(m_clk.group(2))
            return secs <= 120
        return ("분" in str(clock)) or ("초" in str(clock))
    return True


def _build_live_score_item_card(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a single itemCard payload dict for a live/final/scheduled game snapshot."""
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

    try:
        p_num = int(period) if str(period).isdigit() else 4
    except Exception:
        p_num = 4

    # Quarter scorebox: use real quarter scores if available, else proportional estimate
    home_q_raw = snapshot.get("home_quarters")
    away_q_raw = snapshot.get("away_quarters")

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

    if home_q_raw and isinstance(home_q_raw, list) and len(home_q_raw) >= 4:
        hq = [int(x or 0) for x in home_q_raw]
    else:
        hq = _split_q(h_score, min(4, max(1, p_num)))

    if away_q_raw and isinstance(away_q_raw, list) and len(away_q_raw) >= 4:
        aq = [int(x or 0) for x in away_q_raw]
    else:
        aq = _split_q(a_score, min(4, max(1, p_num)))

    item_list = [
        {"title": "1쿼터", "description": f"{home} {hq[0]} : {aq[0]} {away}"},
        {"title": "2쿼터", "description": f"{home} {hq[1]} : {aq[1]} {away}"},
        {"title": "3쿼터", "description": f"{home} {hq[2]} : {aq[2]} {away}"},
        {"title": "4쿼터", "description": f"{home} {hq[3]} : {aq[3]} {away}"},
    ]

    # Handle Overtime (OT / 연장전)
    has_ot = p_num >= 5 or len(hq) > 4 or len(aq) > 4
    if has_ot:
        ot_h = hq[4] if len(hq) > 4 else max(0, h_score - sum(hq[:4]))
        ot_a = aq[4] if len(aq) > 4 else max(0, a_score - sum(aq[:4]))
        ot_label = f"연장{p_num - 4}차" if p_num > 5 else "연장(OT)"
        item_list.append({"title": ot_label[:6], "description": f"{home} {ot_h} : {ot_a} {away}"})

    if p_num >= 5:
        period_str = f"연장{p_num - 4}차" if p_num > 5 else "연장(OT)"
    else:
        period_str = f"{period}쿼터"

    diff = abs(h_score - a_score)
    is_clutch = is_clutch_snapshot(snapshot)

    stale_note = " ⚠️(지연)" if stale else ""
    if status == "FINAL":
        head_title = "✅ 경기 종료"
        img_title = f"{home} {h_score} : {a_score} {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | 최종 스코어{stale_note}"
    elif status == "LIVE" and is_clutch:
        head_title = "🔥 클러치"
        lead = home if h_score > a_score else (away if a_score > h_score else "동점")
        clutch_state = "동점 승부처!" if diff == 0 else (f"{lead} {diff}점차 (원포제션!)" if diff <= 3 else f"{lead} {diff}점차 (투포제션)")
        img_title = f"⚡ [초접전] {home} {h_score} : {a_score} {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | {period_str}{clock_str} 클러치!"
    elif status == "LIVE":
        head_title = "🔴 LIVE 톡중계"
        img_title = f"{home} {h_score} : {a_score} {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | {period_str}{clock_str}{stale_note}"
    else:
        head_title = "📅 경기 예정"
        img_title = f"{home} vs {away}"
        img_desc = f"📍 {_short_arena(snapshot.get('arena')) or 'KBL 경기장'} | 경기 시작 전"

    # Prediction locks at 3Q start; switch 3rd button to Lineup after 3Q starts
    if status == "LIVE" and str(period).isdigit() and int(period) >= 3:
        third_btn = _msg_btn(f"📋 {home[:6]} 라인업", f"{home} 라인업")
    elif status == "FINAL":
        third_btn = _msg_btn("📊 경기 요약", "경기 요약")
    else:
        third_btn = _msg_btn("🗳️ 오늘 승부예측", "승부예측")

    if status == "LIVE" and is_clutch:
        live_buttons = [
            _link_btn("📺 다음 톡중계 보기", daum_url),
            _msg_btn("🔄 10초 새로고침", "실시간 점수"),
            third_btn,
        ]
        summary_block = {
            "title": "🔥 승부처",
            "description": clutch_state[:30],
        }
    else:
        live_buttons = [
            _link_btn("📺 다음 톡중계 보기", daum_url),
            _msg_btn("🔄 점수 새로고침", "실시간 점수"),
            third_btn,
        ]
        summary_block = {
            "title": "최종점수" if status == "FINAL" else "현재점수",
            "description": f"{home} {h_score} : {a_score} {away}",
        }

    return _item_card(
        head_title=head_title,
        image_title={
            "title": img_title,
            "description": img_desc,
            "imageUrl": get_team_logo(home),
        },
        item_list=item_list,
        summary=summary_block,
        buttons=live_buttons,
    )


def build_live_score_response(
    snapshot: dict[str, Any] | list[dict[str, Any]],
    favorite_team: str | None = None,
) -> KakaoSkillResponse:
    """
    Build a Skill response for live game score(s) with quarter scorebox.
    - Single snapshot (or 1-game list): returns single itemCard (backward-compatible).
    - Multiple LIVE snapshots: sorts by (favorite_team -> clutch -> start_time)
      and returns an itemCard carousel so users can swipe all concurrent LIVE games.
    """
    if isinstance(snapshot, list):
        snaps = [s for s in snapshot if isinstance(s, dict)]
        if not snaps:
            return build_today_games_response([], favorite_team=favorite_team)
    else:
        snaps = [snapshot]

    sorted_snaps = sorted(
        snaps,
        key=lambda g: (
            0 if favorite_team and favorite_team in (g.get("home_team"), g.get("away_team")) else 1,
            0 if is_clutch_snapshot(g) else 1,
            str(g.get("start_time") or ""),
        ),
    )

    primary = sorted_snaps[0]
    status = primary.get("status", "")

    if status == "LIVE":
        contextual_qrs = [
            QuickReply(label="🔄 점수 새로고침", messageText="실시간 점수"),
            QuickReply(label="📋 라인업", messageText="라인업"),
            QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
            QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
            QuickReply(label="🏆 팀순위", messageText="팀순위"),
            QuickReply(label="🏠 홈으로", messageText="처음으로"),
        ]
    elif status == "FINAL":
        contextual_qrs = [
            QuickReply(label="📊 경기 요약", messageText="경기 요약"),
            QuickReply(label="🎬 주요장면", messageText="주요장면"),
            QuickReply(label="🏆 팀순위", messageText="팀순위"),
            QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
            QuickReply(label="📅 다음 일정", messageText="일정"),
            QuickReply(label="🏠 홈으로", messageText="처음으로"),
        ]
    else:  # SCHEDULED
        contextual_qrs = [
            QuickReply(label="📋 라인업", messageText="라인업"),
            QuickReply(label="🗳️ 승부예측", messageText="승부예측"),
            QuickReply(label="🏀 오늘 경기", messageText="오늘 경기"),
            QuickReply(label="📅 일정", messageText="일정"),
            QuickReply(label="🏆 팀순위", messageText="팀순위"),
            QuickReply(label="🏠 홈으로", messageText="처음으로"),
        ]

    if len(sorted_snaps) == 1:
        output_block = _build_live_score_item_card(primary)
    else:
        items = [_build_live_score_item_card(g)["itemCard"] for g in sorted_snaps[:10]]
        output_block = {
            "carousel": {
                "type": "itemCard",
                "items": items,
            }
        }

    return KakaoSkillResponse(
        template=KakaoTemplate(
            outputs=[output_block],
            quickReplies=contextual_qrs,
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
