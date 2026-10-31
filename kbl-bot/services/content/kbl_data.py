"""KBL teams, players, standings computation, and Daum News/Highlights parsers."""

import html
import re
from typing import Any

from services.search.parser import KBL_TEAMS

# Full display names and home arenas for all 10 KBL clubs
TEAM_INFO: dict[str, dict[str, str]] = {
    "SK": {
        "full_name": "서울 SK 나이츠",
        "arena": "잠실학생체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/383",
    },
    "KT": {
        "full_name": "수원 KT 소닉붐",
        "arena": "수원 KT 소닉붐 아레나",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/386",
    },
    "KCC": {
        "full_name": "부산 KCC 이지스",
        "arena": "부산사직체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/385",
    },
    "LG": {
        "full_name": "창원 LG 세이커스",
        "arena": "창원실내체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/384",
    },
    "정관장": {
        "full_name": "안양 정관장 레드부스터스",
        "arena": "안양 정관장 아레나",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/387",
    },
    "소노": {
        "full_name": "고양 소노 스카이거너스",
        "arena": "고양 소노 아레나",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/389",
    },
    "DB": {
        "full_name": "원주 DB 프로미",
        "arena": "원주종합체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/381",
    },
    "삼성": {
        "full_name": "서울 삼성 썬더스",
        "arena": "잠실실내체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/382",
    },
    "현대모비스": {
        "full_name": "울산 현대모비스 피버스",
        "arena": "울산동천체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/380",
    },
    "한국가스공사": {
        "full_name": "대구 한국가스공사 페가수스",
        "arena": "대구실내체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://sports.daum.net/team/kbl/388",
    },
}

# Comprehensive KBL Star Players database across all 10 clubs
KBL_PLAYERS: list[dict[str, Any]] = [
    {"name": "자밀 워니", "team": "SK", "pos": "C", "no": "34", "pts": 23.8, "reb": 11.9, "ast": 4.1, "tpm": 0.9, "stl": 1.2},
    {"name": "이정현", "team": "소노", "pos": "G", "no": "6", "pts": 21.4, "reb": 3.5, "ast": 6.4, "tpm": 3.1, "stl": 2.1},
    {"name": "아셈 마레이", "team": "LG", "pos": "C", "no": "50", "pts": 18.9, "reb": 13.8, "ast": 4.2, "tpm": 0.0, "stl": 1.8},
    {"name": "이선 알바노", "team": "DB", "pos": "G", "no": "4", "pts": 18.6, "reb": 3.4, "ast": 6.8, "tpm": 2.1, "stl": 1.6},
    {"name": "허훈", "team": "KT", "pos": "G", "no": "2", "pts": 17.8, "reb": 2.9, "ast": 7.2, "tpm": 2.3, "stl": 1.5},
    {"name": "앤드류 니콜슨", "team": "한국가스공사", "pos": "F", "no": "44", "pts": 21.1, "reb": 8.4, "ast": 1.5, "tpm": 2.4, "stl": 0.7},
    {"name": "코피 코번", "team": "삼성", "pos": "C", "no": "10", "pts": 20.5, "reb": 11.4, "ast": 2.0, "tpm": 0.0, "stl": 0.6},
    {"name": "허웅", "team": "KCC", "pos": "G", "no": "3", "pts": 16.9, "reb": 2.6, "ast": 4.3, "tpm": 2.7, "stl": 1.1},
    {"name": "최준용", "team": "KCC", "pos": "F", "no": "2", "pts": 15.4, "reb": 6.2, "ast": 3.8, "tpm": 1.4, "stl": 1.0},
    {"name": "변준형", "team": "정관장", "pos": "G", "no": "5", "pts": 16.2, "reb": 3.1, "ast": 5.9, "tpm": 1.8, "stl": 1.3},
    {"name": "박지훈", "team": "정관장", "pos": "G", "no": "6", "pts": 13.8, "reb": 4.1, "ast": 5.1, "tpm": 1.5, "stl": 1.6},
    {"name": "이우석", "team": "현대모비스", "pos": "G", "no": "1", "pts": 15.8, "reb": 5.4, "ast": 4.0, "tpm": 1.9, "stl": 1.2},
    {"name": "김낙현", "team": "한국가스공사", "pos": "G", "no": "4", "pts": 16.1, "reb": 2.8, "ast": 5.2, "tpm": 2.5, "stl": 1.1},
    {"name": "유기상", "team": "LG", "pos": "G", "no": "24", "pts": 13.5, "reb": 3.2, "ast": 1.9, "tpm": 2.9, "stl": 1.3},
    {"name": "안영준", "team": "SK", "pos": "F", "no": "8", "pts": 14.7, "reb": 5.8, "ast": 2.5, "tpm": 1.9, "stl": 1.1},
    {"name": "김선형", "team": "SK", "pos": "G", "no": "5", "pts": 13.2, "reb": 2.7, "ast": 5.5, "tpm": 1.1, "stl": 1.4},
    {"name": "하윤기", "team": "KT", "pos": "C", "no": "0", "pts": 14.5, "reb": 6.9, "ast": 1.8, "tpm": 0.1, "stl": 0.7},
    {"name": "문정현", "team": "KT", "pos": "F", "no": "21", "pts": 11.4, "reb": 5.6, "ast": 2.9, "tpm": 1.3, "stl": 1.1},
    {"name": "송교창", "team": "KCC", "pos": "F", "no": "12", "pts": 14.2, "reb": 5.7, "ast": 2.6, "tpm": 1.2, "stl": 1.0},
    {"name": "전성현", "team": "LG", "pos": "F", "no": "23", "pts": 12.8, "reb": 2.1, "ast": 1.4, "tpm": 2.8, "stl": 0.7},
    {"name": "양준석", "team": "LG", "pos": "G", "no": "11", "pts": 10.6, "reb": 2.5, "ast": 5.7, "tpm": 1.4, "stl": 1.0},
    {"name": "이정현(삼성)", "team": "삼성", "pos": "G", "no": "5", "pts": 13.9, "reb": 3.4, "ast": 5.3, "tpm": 1.9, "stl": 1.1},
    {"name": "이원석", "team": "삼성", "pos": "C", "no": "2", "pts": 11.8, "reb": 6.8, "ast": 1.3, "tpm": 0.3, "stl": 0.6},
    {"name": "강상재", "team": "DB", "pos": "F", "no": "13", "pts": 13.1, "reb": 6.3, "ast": 3.4, "tpm": 1.3, "stl": 0.8},
    {"name": "김종규", "team": "DB", "pos": "C", "no": "15", "pts": 11.2, "reb": 6.1, "ast": 1.2, "tpm": 0.4, "stl": 0.5},
    {"name": "정성우", "team": "한국가스공사", "pos": "G", "no": "3", "pts": 10.9, "reb": 2.7, "ast": 4.8, "tpm": 1.2, "stl": 1.9},
    {"name": "이지우", "team": "현대모비스", "pos": "F", "no": "7", "pts": 11.0, "reb": 4.5, "ast": 3.1, "tpm": 1.2, "stl": 0.9},
    {"name": "함지훈", "team": "현대모비스", "pos": "F", "no": "12", "pts": 9.8, "reb": 4.9, "ast": 3.7, "tpm": 0.3, "stl": 0.7},
    {"name": "이재도", "team": "소노", "pos": "G", "no": "4", "pts": 12.9, "reb": 3.1, "ast": 4.9, "tpm": 1.5, "stl": 1.3},
    {"name": "정효근", "team": "정관장", "pos": "F", "no": "33", "pts": 11.7, "reb": 5.5, "ast": 2.3, "tpm": 1.2, "stl": 0.8},
]


def search_kbl_players(query: str) -> list[dict[str, Any]]:
    """
    Search KBL players by name or team code.

    Args:
        query: Player name substring or team code.

    Returns:
        List of matching player dicts.
    """
    cleaned = re.sub(r"^(#?\s*(관심선수|선수검색|선수|추가|등록|삭제)\s*)+", "", query.strip()).strip()
    if not cleaned:
        return KBL_PLAYERS[:5]

    matches: list[dict[str, Any]] = []
    for p in KBL_PLAYERS:
        if cleaned in p["name"] or p["name"] in cleaned or cleaned.upper() == p["team"].upper():
            matches.append(p)
    return matches


def get_default_player_rankings() -> dict[str, list[dict[str, Any]]]:
    """Build top-5 leaderboards by category (pts, reb, ast, tpm, stl)."""
    categories = ["pts", "reb", "ast", "tpm", "stl"]
    out: dict[str, list[dict[str, Any]]] = {}
    for cat in categories:
        sorted_p = sorted(KBL_PLAYERS, key=lambda x: float(x.get(cat, 0.0)), reverse=True)[:7]
        out[cat] = [
            {
                "rank": idx + 1,
                "name": p["name"],
                "team": p["team"],
                "pos": p["pos"],
                "value": p[cat],
                "pts": p["pts"],
                "reb": p["reb"],
                "ast": p["ast"],
            }
            for idx, p in enumerate(sorted_p)
        ]
    return out


def compute_standings_from_games(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Compute 10-team KBL standings directly from a list of canonical season games.

    Args:
        games: Canonical game dicts (including FINAL games).

    Returns:
        List of 10 team standing dicts sorted by win percentage and wins.
    """
    stats: dict[str, dict[str, Any]] = {
        t: {"team": t, "wins": 0, "losses": 0, "history": []} for t in KBL_TEAMS
    }

    # Sort games chronologically to compute streaks accurately
    sorted_games = sorted(games, key=lambda g: str(g.get("start_time") or ""))
    for g in sorted_games:
        if g.get("status") != "FINAL":
            continue
        h = g.get("home_team")
        a = g.get("away_team")
        hs = g.get("home_score")
        as_ = g.get("away_score")
        if h not in stats or a not in stats or hs is None or as_ is None:
            continue
        if hs > as_:
            stats[h]["wins"] += 1
            stats[h]["history"].append("W")
            stats[a]["losses"] += 1
            stats[a]["history"].append("L")
        elif as_ > hs:
            stats[a]["wins"] += 1
            stats[a]["history"].append("W")
            stats[h]["losses"] += 1
            stats[h]["history"].append("L")

    rows: list[dict[str, Any]] = []
    for t, st in stats.items():
        w = st["wins"]
        l_ = st["losses"]
        total = w + l_
        wpct = round(w / total, 3) if total > 0 else 0.0
        hist = st["history"]
        streak = "-"
        if hist:
            last = hist[-1]
            cnt = 0
            for res in reversed(hist):
                if res == last:
                    cnt += 1
                else:
                    break
            streak = f"{cnt}연승" if last == "W" else f"{cnt}연패"
        rows.append(
            {
                "team": t,
                "wins": w,
                "losses": l_,
                "wpct": wpct,
                "streak": streak,
                "diff": w - l_,
            }
        )

    rows.sort(key=lambda r: (r["wpct"], r["wins"], -r["losses"], r["team"]), reverse=True)
    leader_diff = rows[0]["diff"] if rows else 0

    standings: list[dict[str, Any]] = []
    for idx, r in enumerate(rows):
        gb_val = (leader_diff - r["diff"]) / 2.0
        gb_str = "0.0" if gb_val <= 0 else f"{gb_val:.1f}"
        standings.append(
            {
                "rank": idx + 1,
                "team": r["team"],
                "wins": r["wins"],
                "losses": r["losses"],
                "wpct": r["wpct"],
                "gb": gb_str,
                "streak": r["streak"],
                "season": "2026-27",
            }
        )
    return standings


def parse_daum_news_html(raw_html: str) -> list[dict[str, Any]]:
    """
    Extract KBL news articles (title + v.daum.net URL) from Daum Search HTML.
    """
    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Match <a href="https://v.daum.net/v/..." ...>Title</a>
    pattern = re.compile(
        r'<a[^>]+href=["\'](https://v\.daum\.net/v/\d+)[^"\']*["\'][^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(raw_html):
        url = match.group(1)
        if url in seen_urls:
            continue
        raw_title = re.sub(r"<[^>]+>", "", match.group(2))
        title = html.unescape(raw_title).strip()
        title = re.sub(r"\s+", " ", title)
        # Filter out short labels like "다음뉴스" or empty image links
        if len(title) < 10 or title in ("다음뉴스", "언론사 픽", "관련뉴스"):
            continue
        seen_urls.add(url)
        items.append({"title": title, "url": url, "source": "Daum 스포츠"})
        if len(items) >= 6:
            break

    if not items:
        items = [
            {
                "title": "KBL 프로농구 최신 뉴스 및 구단별 소식 모아보기",
                "url": "https://sports.daum.net/basketball",
                "source": "Daum 스포츠",
            },
            {
                "title": "KBL 공식 리그 소식 및 라운드 프리뷰/리뷰",
                "url": "https://www.kbl.or.kr/news/kbl-news",
                "source": "KBL 공식",
            },
        ]
    return items


def build_highlights_from_games(
    recent_games: list[dict[str, Any]], raw_html: str = ""
) -> list[dict[str, Any]]:
    """
    Build KBL highlight video links from recent live/finished games and Daum vclip search.
    """
    items: list[dict[str, Any]] = []

    for g in recent_games[:4]:
        status = g.get("status")
        if status in ("FINAL", "LIVE"):
            h = g.get("home_team", "?")
            a = g.get("away_team", "?")
            hs = g.get("home_score", 0)
            as_ = g.get("away_score", 0)
            gid = g.get("game_id", "")
            tag = "주요장면/하이라이트" if status == "FINAL" else "실시간 중계/주요장면"
            items.append(
                {
                    "title": f"[{tag}] {h} {hs} : {as_} {a}",
                    "url": f"https://sports.daum.net/match/{gid}" if gid else "https://sports.daum.net/video/kbl",
                    "arena": g.get("arena") or "",
                }
            )

    items.append(
        {
            "title": "🎬 Daum 스포츠 KBL 전체 하이라이트 & 명장면 모음",
            "url": "https://sports.daum.net/video/kbl",
            "arena": "Daum 스포츠 영상센터",
        }
    )
    items.append(
        {
            "title": "📺 KBL TV 공식 유튜브 전체 경기 하이라이트",
            "url": "https://www.youtube.com/@KBLTV/videos",
            "arena": "KBL TV",
        }
    )
    return items[:6]
