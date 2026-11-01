"""KBL teams, players, standings computation, and Daum News/Highlights parsers."""

import html
import re
import urllib.parse
from typing import Any

from services.search.parser import KBL_TEAMS

# Full display names, logos, and home arenas for all 10 KBL clubs (official Kakao CDN emblems)
TEAM_INFO: dict[str, dict[str, str]] = {
    "SK": {
        "full_name": "서울 SK 나이츠",
        "arena": "잠실학생체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%84%9C%EC%9A%B8%20SK%20%EB%82%98%EC%9D%B4%EC%8A%87",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F55_300300.png",
    },
    "KT": {
        "full_name": "수원 KT 소닉붐",
        "arena": "수원 KT 소닉붐 아레나",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%88%98%EC%9B%90%20KT%20%EC%86%8C%EB%8B%89%E1%84%87%E1%85%AE%E1%86%B7",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F06_300300.png",
    },
    "KCC": {
        "full_name": "부산 KCC 이지스",
        "arena": "부산사직체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EB%B6%80%EC%82%B0%20KCC%20%EC%9D%B4%EC%A7%80%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F60_300300.png",
    },
    "LG": {
        "full_name": "창원 LG 세이커스",
        "arena": "창원실내체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%B0%BD%EC%9B%90%20LG%20%EC%84%B8%EC%9D%B4%EC%BB%A4%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F50_300300.png",
    },
    "정관장": {
        "full_name": "안양 정관장 레드부스터스",
        "arena": "안양 정관장 아레나",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%95%88%EC%96%91%20%EC%A0%95%EA%B4%80%EC%9E%A5%20%EB%A0%88%EB%93%9C%EB%B6%80%EC%8A%A4%ED%84%B0%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F70_300300.png",
    },
    "소노": {
        "full_name": "고양 소노 스카이거너스",
        "arena": "고양 소노 아레나",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EA%B3%A0%EC%96%91%20%EC%86%8C%EB%85%B8%20%EC%8A%A4%EC%B9%B4%EC%9D%B4%EA%B1%B0%EB%84%88%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F66_300300.png",
    },
    "DB": {
        "full_name": "원주 DB 프로미",
        "arena": "원주종합체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%9B%90%EC%A3%BC%20DB%20%ED%94%84%EB%A1%9C%EB%8F%88",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F16_300300.png",
    },
    "삼성": {
        "full_name": "서울 삼성 썬더스",
        "arena": "잠실실내체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%84%9C%EC%9A%B8%20%EC%82%BC%EC%84%B1%20%EC%8D%AC%EB%8D%94%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F35_300300.png",
    },
    "현대모비스": {
        "full_name": "울산 현대모비스 피버스",
        "arena": "울산동천체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EC%9A%B8%EC%82%B0%20%ED%98%84%EB%8C%80%EB%AA%A8%EB%B9%84%EC%8A%A4%20%ED%94%BC%EB%B2%84%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F10_300300.png",
    },
    "한국가스공사": {
        "full_name": "대구 한국가스공사 페가수스",
        "arena": "대구실내체육관",
        "ticket_url": "https://www.kbl.or.kr/ticket",
        "club_url": "https://search.daum.net/search?w=tot&q=%EB%8C%80%EA%B5%AC%20%ED%95%9C%EA%B5%AD%EA%B0%80%EC%8A%A4%EA%B3%B5%EC%82%AC%20%ED%8E%98%EA%B0%80%EC%88%98%EC%8A%A4",
        "logo_url": "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports13%2Flogo%2Fteam%2F10%2F64_300300.png",
    },
}

# Daum/Kakao Sports Official 300x300 PNG Logo CDN lookup
TEAM_LOGOS: dict[str, str] = {k: v["logo_url"] for k, v in TEAM_INFO.items()}
DEFAULT_SPORTS_LOGO: str = "https://search1.kakaocdn.net/thumb/R300x300.fpng/?fname=http%3A%2F%2Ft1.daumcdn.net%2Fmedia%2Fimg-section%2Fsports%2Fmeta%2Fsports_meta_2026.png"


def get_team_logo(team: str | None) -> str:
    """Return verified official Daum CDN emblem URL for the given team name or alias."""
    if not team:
        return DEFAULT_SPORTS_LOGO
    t = team.strip()
    if t in TEAM_LOGOS:
        return TEAM_LOGOS[t]
    for k, url in TEAM_LOGOS.items():
        if k in t or t in k:
            return url
    return DEFAULT_SPORTS_LOGO

# Comprehensive KBL Star Players database across all 10 clubs (updated with 2026-27 active rosters & leaders)
KBL_PLAYERS: list[dict[str, Any]] = [
    {"name": "케렘 칸터", "team": "삼성", "pos": "C", "no": "11", "pts": 26.8, "reb": 10.7, "ast": 2.7, "tpm": 0.5, "stl": 1.0, "blk": 0.3},
    {"name": "패리스 배스", "team": "KT", "pos": "F", "no": "25", "pts": 26.3, "reb": 9.7, "ast": 4.2, "tpm": 2.1, "stl": 0.9, "blk": 1.0},
    {"name": "헨리 엘런슨", "team": "DB", "pos": "F", "no": "32", "pts": 24.5, "reb": 8.2, "ast": 2.8, "tpm": 1.8, "stl": 1.3, "blk": 0.2},
    {"name": "게이지 프림", "team": "현대모비스", "pos": "C", "no": "2", "pts": 23.4, "reb": 7.3, "ast": 3.3, "tpm": 0.0, "stl": 0.7, "blk": 0.6},
    {"name": "자니 오브라이언트", "team": "소노", "pos": "F", "no": "9", "pts": 22.5, "reb": 7.9, "ast": 3.4, "tpm": 1.9, "stl": 1.1, "blk": 0.5},
    {"name": "레이션 해먼즈", "team": "DB", "pos": "F", "no": "33", "pts": 22.2, "reb": 9.5, "ast": 2.5, "tpm": 1.5, "stl": 1.0, "blk": 0.4},
    {"name": "다리우스 베즐리", "team": "현대모비스", "pos": "F", "no": "23", "pts": 21.6, "reb": 9.9, "ast": 4.3, "tpm": 1.2, "stl": 1.6, "blk": 2.0},
    {"name": "루이스 킹", "team": "KCC", "pos": "F", "no": "7", "pts": 21.0, "reb": 5.8, "ast": 2.7, "tpm": 1.8, "stl": 1.4, "blk": 0.7},
    {"name": "존 무니", "team": "정관장", "pos": "C", "no": "34", "pts": 20.6, "reb": 12.9, "ast": 3.6, "tpm": 0.8, "stl": 1.1, "blk": 0.7},
    {"name": "케베 알루마", "team": "한국가스공사", "pos": "F", "no": "22", "pts": 20.0, "reb": 9.5, "ast": 3.7, "tpm": 1.6, "stl": 0.8, "blk": 1.3},
    {"name": "자밀 워니", "team": "SK", "pos": "C", "no": "34", "pts": 18.8, "reb": 9.6, "ast": 5.6, "tpm": 0.9, "stl": 1.0, "blk": 1.0},
    {"name": "이선 알바노", "team": "DB", "pos": "G", "no": "4", "pts": 19.2, "reb": 3.9, "ast": 7.6, "tpm": 2.1, "stl": 1.6, "blk": 0.1},
    {"name": "안영준", "team": "SK", "pos": "F", "no": "8", "pts": 17.8, "reb": 5.2, "ast": 3.6, "tpm": 2.3, "stl": 3.2, "blk": 0.6},
    {"name": "숀 롱", "team": "현대모비스", "pos": "C", "no": "21", "pts": 16.6, "reb": 12.9, "ast": 1.5, "tpm": 0.0, "stl": 0.9, "blk": 0.5},
    {"name": "허훈", "team": "KT", "pos": "G", "no": "2", "pts": 15.5, "reb": 2.7, "ast": 8.5, "tpm": 2.3, "stl": 0.6, "blk": 0.0},
    {"name": "아셈 마레이", "team": "LG", "pos": "C", "no": "50", "pts": 15.1, "reb": 14.2, "ast": 6.8, "tpm": 0.0, "stl": 0.8, "blk": 0.2},
    {"name": "샘조세프 벨란겔", "team": "한국가스공사", "pos": "G", "no": "1", "pts": 15.9, "reb": 2.3, "ast": 5.8, "tpm": 2.2, "stl": 1.2, "blk": 0.0},
    {"name": "변준형", "team": "정관장", "pos": "G", "no": "5", "pts": 11.5, "reb": 2.2, "ast": 5.9, "tpm": 1.8, "stl": 0.4, "blk": 0.1},
    {"name": "저스틴 구탕", "team": "삼성", "pos": "F", "no": "21", "pts": 8.1, "reb": 4.6, "ast": 5.9, "tpm": 0.9, "stl": 1.7, "blk": 0.2},
    {"name": "이정현", "team": "소노", "pos": "G", "no": "6", "pts": 21.4, "reb": 3.5, "ast": 6.4, "tpm": 3.1, "stl": 2.1, "blk": 0.3},
    {"name": "앤드류 니콜슨", "team": "한국가스공사", "pos": "F", "no": "44", "pts": 21.1, "reb": 8.4, "ast": 1.5, "tpm": 2.4, "stl": 0.7, "blk": 0.8},
    {"name": "허웅", "team": "KCC", "pos": "G", "no": "3", "pts": 16.9, "reb": 2.6, "ast": 4.3, "tpm": 2.7, "stl": 1.1, "blk": 0.1},
    {"name": "최준용", "team": "KCC", "pos": "F", "no": "2", "pts": 15.4, "reb": 6.2, "ast": 3.8, "tpm": 1.4, "stl": 1.0, "blk": 0.9},
    {"name": "박지훈", "team": "정관장", "pos": "G", "no": "6", "pts": 13.8, "reb": 4.1, "ast": 5.1, "tpm": 1.5, "stl": 1.6, "blk": 0.2},
    {"name": "이우석", "team": "현대모비스", "pos": "G", "no": "1", "pts": 15.8, "reb": 5.4, "ast": 4.0, "tpm": 1.9, "stl": 1.2, "blk": 0.4},
    {"name": "김낙현", "team": "SK", "pos": "G", "no": "4", "pts": 16.1, "reb": 2.8, "ast": 5.2, "tpm": 2.5, "stl": 1.1, "blk": 0.1},
    {"name": "유기상", "team": "LG", "pos": "G", "no": "24", "pts": 13.5, "reb": 3.2, "ast": 1.9, "tpm": 2.9, "stl": 1.3, "blk": 0.3},
    {"name": "김선형", "team": "KT", "pos": "G", "no": "5", "pts": 13.2, "reb": 2.7, "ast": 5.5, "tpm": 1.1, "stl": 1.4, "blk": 0.2},
    {"name": "하윤기", "team": "KT", "pos": "C", "no": "0", "pts": 14.5, "reb": 6.9, "ast": 1.8, "tpm": 0.1, "stl": 0.7, "blk": 1.0},
    {"name": "이관희", "team": "삼성", "pos": "G", "no": "5", "pts": 12.1, "reb": 3.2, "ast": 2.4, "tpm": 1.8, "stl": 1.2, "blk": 0.3},
    {"name": "강상재", "team": "DB", "pos": "F", "no": "13", "pts": 13.1, "reb": 6.3, "ast": 3.4, "tpm": 1.3, "stl": 0.8, "blk": 0.5},
    {"name": "김종규", "team": "DB", "pos": "C", "no": "15", "pts": 11.2, "reb": 6.1, "ast": 1.2, "tpm": 0.4, "stl": 0.5, "blk": 0.9},
    {"name": "정성우", "team": "한국가스공사", "pos": "G", "no": "3", "pts": 10.9, "reb": 2.7, "ast": 4.8, "tpm": 1.2, "stl": 1.9, "blk": 0.1},
    {"name": "서명진", "team": "현대모비스", "pos": "G", "no": "9", "pts": 12.0, "reb": 3.2, "ast": 4.6, "tpm": 1.8, "stl": 1.1, "blk": 0.1},
    {"name": "이재도", "team": "소노", "pos": "G", "no": "4", "pts": 12.9, "reb": 3.1, "ast": 4.9, "tpm": 1.5, "stl": 1.3, "blk": 0.1},
    {"name": "정효근", "team": "정관장", "pos": "F", "no": "33", "pts": 11.7, "reb": 5.5, "ast": 2.3, "tpm": 1.2, "stl": 0.8, "blk": 0.6},
]


# Official Starting 5 Lineups (베스트 5) and Head Coaches for all 10 KBL clubs
TEAM_LINEUPS: dict[str, dict[str, Any]] = {
    "SK": {
        "head_coach": "전희철",
        "starters": [
            {"pos": "G", "name": "김낙현", "no": "4"},
            {"pos": "G", "name": "오재현", "no": "0"},
            {"pos": "F", "name": "안영준", "no": "8"},
            {"pos": "F", "name": "최부경", "no": "14"},
            {"pos": "C", "name": "자밀 워니", "no": "34"},
        ],
        "key_bench": ["오세근", "최원혁", "고메즈 딜 리아노"],
    },
    "DB": {
        "head_coach": "김주성",
        "starters": [
            {"pos": "G", "name": "이선 알바노", "no": "4"},
            {"pos": "G", "name": "유현준", "no": "7"},
            {"pos": "F", "name": "강상재", "no": "13"},
            {"pos": "F", "name": "로버트 카터", "no": "32"},
            {"pos": "C", "name": "김종규", "no": "15"},
        ],
        "key_bench": ["박인웅", "이정현(DB)", "서민수"],
    },
    "KT": {
        "head_coach": "송영진",
        "starters": [
            {"pos": "G", "name": "김선형", "no": "5"},
            {"pos": "G", "name": "허훈", "no": "2"},
            {"pos": "F", "name": "문정현", "no": "21"},
            {"pos": "F", "name": "문성곤", "no": "10"},
            {"pos": "C", "name": "하윤기", "no": "0"},
        ],
        "key_bench": ["레이션 해먼즈", "한희원", "최진광", "박지원", "이두원"],
    },
    "LG": {
        "head_coach": "조상현",
        "starters": [
            {"pos": "G", "name": "양준석", "no": "11"},
            {"pos": "G", "name": "유기상", "no": "24"},
            {"pos": "F", "name": "정인덕", "no": "7"},
            {"pos": "F", "name": "칼 타마요", "no": "1"},
            {"pos": "C", "name": "아셈 마레이", "no": "50"},
        ],
        "key_bench": ["전성현", "두경민", "대릴 먼로"],
    },
    "정관장": {
        "head_coach": "김상식",
        "starters": [
            {"pos": "G", "name": "박지훈", "no": "6"},
            {"pos": "G", "name": "최성원", "no": "11"},
            {"pos": "F", "name": "배병준", "no": "1"},
            {"pos": "F", "name": "정효근", "no": "33"},
            {"pos": "C", "name": "캐디 라렌", "no": "25"},
        ],
        "key_bench": ["변준형", "한승희", "마이클 영"],
    },
    "KCC": {
        "head_coach": "전창진",
        "starters": [
            {"pos": "G", "name": "이호현", "no": "6"},
            {"pos": "G", "name": "허웅", "no": "3"},
            {"pos": "F", "name": "최준용", "no": "2"},
            {"pos": "F", "name": "송교창", "no": "12"},
            {"pos": "F", "name": "이승현", "no": "11"},
        ],
        "key_bench": ["디온테 버튼", "정창영", "켈빈 에피스톨라"],
    },
    "한국가스공사": {
        "head_coach": "강혁",
        "starters": [
            {"pos": "G", "name": "정성우", "no": "3"},
            {"pos": "G", "name": "SJ 벨란겔", "no": "1"},
            {"pos": "F", "name": "신승민", "no": "11"},
            {"pos": "F", "name": "앤드류 니콜슨", "no": "44"},
            {"pos": "C", "name": "유슈 은도예", "no": "15"},
        ],
        "key_bench": ["차바위", "곽정훈", "우동현"],
    },
    "현대모비스": {
        "head_coach": "조동현",
        "starters": [
            {"pos": "G", "name": "서명진", "no": "9"},
            {"pos": "G", "name": "이우석", "no": "1"},
            {"pos": "F", "name": "함지훈", "no": "12"},
            {"pos": "F", "name": "숀 롱", "no": "21"},
            {"pos": "C", "name": "케이지 프림", "no": "0"},
        ],
        "key_bench": ["장재석", "김국찬", "미구엘 옥존"],
    },
    "소노": {
        "head_coach": "김승기",
        "starters": [
            {"pos": "G", "name": "이재도", "no": "4"},
            {"pos": "G", "name": "이정현", "no": "6"},
            {"pos": "F", "name": "정희재", "no": "11"},
            {"pos": "F", "name": "최승욱", "no": "24"},
            {"pos": "C", "name": "앨런 윌리엄스", "no": "15"},
        ],
        "key_bench": ["임동섭", "김진유", "디제이 번즈"],
    },
    "삼성": {
        "head_coach": "김효범",
        "starters": [
            {"pos": "G", "name": "이동엽", "no": "3"},
            {"pos": "G", "name": "이관희", "no": "5"},
            {"pos": "F", "name": "저스틴 구탕", "no": "1"},
            {"pos": "C", "name": "이원석", "no": "2"},
            {"pos": "C", "name": "코피 코번", "no": "10"},
        ],
        "key_bench": ["최성모", "신동혁", "마커스 데릭슨"],
    },
}


def get_team_lineup(team: str) -> dict[str, Any] | None:
    """Return lineup and head coach info for a given KBL team."""
    for t_key, info in TEAM_LINEUPS.items():
        if team == t_key or team in t_key or t_key in team:
            return info
    return None


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
    """Build top-7 leaderboards by category (pts, reb, ast, tpm, stl, blk)."""
    categories = ["pts", "reb", "ast", "tpm", "stl", "blk"]
    out: dict[str, list[dict[str, Any]]] = {}
    for cat in categories:
        sorted_p = sorted(KBL_PLAYERS, key=lambda x: float(x.get(cat, 0.0)), reverse=True)[:7]
        out[cat] = [
            {
                "rank": idx + 1,
                "name": p["name"],
                "team": p["team"],
                "pos": p["pos"],
                "value": p.get(cat, 0.0),
                "pts": p.get("pts", 0.0),
                "reb": p.get("reb", 0.0),
                "ast": p.get("ast", 0.0),
                "stl": p.get("stl", 0.0),
                "blk": p.get("blk", 0.0),
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


def parse_daum_news_html(
    raw_html: str,
    recent_games: list[dict[str, Any]] | None = None,
    team: str | None = None,
) -> list[dict[str, Any]]:
    """
    Extract KBL news articles from Daum Search HTML and live game recaps.
    Optionally tailored to a specific favorite team.
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
        if len(title) < 10 or title in ("다음뉴스", "언론사 픽", "관련뉴스"):
            continue
        seen_urls.add(url)
        items.append({"title": title, "url": url, "source": "Daum 스포츠"})
        if len(items) >= 10:
            break

    # If team is specified, prioritize articles mentioning the team or its key players
    if team and items:
        full_name = TEAM_INFO.get(team, {}).get("full_name", team)
        team_players = [p["name"] for p in KBL_PLAYERS if p.get("team") == team]
        team_keywords = [team, full_name] + team_players

        def _is_team_relevant(item: dict[str, Any]) -> bool:
            tit = item.get("title", "")
            return any(k in tit for k in team_keywords)

        team_articles = [it for it in items if _is_team_relevant(it)]
        other_articles = [it for it in items if not _is_team_relevant(it)]
        items = (team_articles + other_articles)[:10]

    if recent_games and len(items) < 10:
        # Prioritize games involving the favorite team
        candidate_games = recent_games
        if team:
            t_games = [g for g in recent_games if team in (g.get("home_team"), g.get("away_team"))]
            o_games = [g for g in recent_games if team not in (g.get("home_team"), g.get("away_team"))]
            candidate_games = t_games + o_games

        for g in candidate_games[:8]:
            if len(items) >= 10:
                break
            status = g.get("status")
            h = g.get("home_team", "?")
            a = g.get("away_team", "?")
            hs = g.get("home_score") or 0
            as_ = g.get("away_score") or 0
            gid = g.get("game_id", "")
            arena = g.get("arena") or ""
            url = f"https://sports.daum.net/match/{gid}" if gid else "https://sports.daum.net/basketball"

            if team and team in (h, a):
                is_home = (h == team)
                my_score = hs if is_home else as_
                opp_score = as_ if is_home else hs
                opp = a if is_home else h
                diff = abs(my_score - opp_score)

                if status == "FINAL":
                    if my_score > opp_score:
                        headline = f"[승전보] {team}, {opp} 꺾고 {my_score}-{opp_score} 승리! ({arena})"
                    else:
                        headline = f"[경기리뷰] {team}, {opp}전 {diff}점차 아쉬운 석패 ({arena})"
                elif status == "LIVE":
                    headline = f"[속보/LIVE] {team} vs {opp} {my_score}:{opp_score} 실시간 격돌 중 ({arena})"
                else:
                    headline = f"[매치프리뷰] {team} vs {opp} 맞대결 관전포인트 및 전력 비교"
                items.append({"title": headline, "url": url, "source": "Daum 스포츠"})
            else:
                if status == "FINAL":
                    winner, loser, ws, ls = (h, a, hs, as_) if hs >= as_ else (a, h, as_, hs)
                    diff = abs(hs - as_)
                    headline = (
                        f"[경기리뷰] {winner}, {loser} 상대로 {ws}-{ls} 짜릿한 {diff}점차 접전 승리!"
                        if diff <= 5
                        else f"[경기리뷰] {winner}, {loser} 꺾고 {ws}-{ls} 쾌승 ({arena})"
                    )
                    items.append({"title": headline, "url": url, "source": "Daum 스포츠"})
                elif status == "LIVE":
                    items.append(
                        {
                            "title": f"[속보/생중계] {h} {hs} : {as_} {a} 실시간 격돌 ({arena})",
                            "url": url,
                            "source": "Daum 스포츠",
                        }
                    )
                else:
                    items.append(
                        {
                            "title": f"[매치프리뷰] {h} vs {a} 맞대결 관전포인트 및 전력 비교",
                            "url": url,
                            "source": "Daum 스포츠",
                        }
                    )

    if len(items) < 10:
        if team:
            full = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
            club_url = TEAM_INFO.get(team, {}).get("club_url", "https://sports.daum.net/basketball")
            coach = TEAM_LINEUPS.get(team, {}).get("head_coach", "감독")
            team_players = [p["name"] for p in KBL_PLAYERS if p.get("team") == team]
            star = team_players[0] if team_players else "주전 라인업"
            extra_items = [
                {
                    "title": f"[{team} 포커스] {coach} 감독의 승리 전략과 선수단 집중 분석",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
                {
                    "title": f"[{team} 주역] '{star}' 에이스의 맹활약... 팀 전력의 핵심",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
                {
                    "title": f"[KBL 순위] {full}, 치열한 2026-27 정규리그 순위 레이스",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
                {
                    "title": f"{full} 구단 소식 및 공식 하이라이트 영상 모아보기",
                    "url": club_url,
                    "source": "구단 공식",
                },
                {
                    "title": f"[{team}] 선수단 주요 기록 및 정규리그 경기 일정표",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
                {
                    "title": "KBL 프로농구 전체 최신 뉴스 및 라운드 결산",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
            ]
            for ext in extra_items:
                if len(items) >= 10:
                    break
                items.append(ext)
        else:
            generic_items = [
                {
                    "title": "[KBL 주간전망] 10개 구단 순위 경쟁 점입가경... 주말 빅매치 총정리",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
                {
                    "title": "[기록실] 득점·어시스트 부문별 1위 누구? KBL 개인 타이틀 레이스",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
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
                {
                    "title": "[이슈] 2026-27 KBL 농구팬 직관 열기 후끈... 흥행 신바람",
                    "url": "https://sports.daum.net/basketball",
                    "source": "Daum 스포츠",
                },
            ]
            for ext in generic_items:
                if len(items) >= 10:
                    break
                items.append(ext)

    return items[:10]


def build_highlights_from_games(
    recent_games: list[dict[str, Any]],
    raw_html: str = "",
    team: str | None = None,
) -> list[dict[str, Any]]:
    """
    Build KBL highlight video links from recent live/finished games and official channels.
    Optionally tailored to user's favorite team.
    """
    items: list[dict[str, Any]] = []

    # Prioritize games involving the favorite team
    candidate_games = recent_games
    if team:
        t_games = [g for g in recent_games if team in (g.get("home_team"), g.get("away_team"))]
        o_games = [g for g in recent_games if team not in (g.get("home_team"), g.get("away_team"))]
        candidate_games = t_games + o_games

    for g in candidate_games[:4]:
        status = g.get("status")
        if status in ("FINAL", "LIVE"):
            h = g.get("home_team", "?")
            a = g.get("away_team", "?")
            hs = g.get("home_score", 0)
            as_ = g.get("away_score", 0)
            arena = g.get("arena") or ""

            if team and team in (h, a):
                opp = a if h == team else h
                tag = "하이라이트" if status == "FINAL" else "실시간 LIVE"
                title = f"[{tag}] {team} vs {opp} 명장면 & 주요 클립 ({h} {hs}:{as_} {a})"
                q_str = urllib.parse.quote(f"KBL {team} {opp} 하이라이트")
            else:
                tag = "주요장면/하이라이트" if status == "FINAL" else "실시간 중계/주요장면"
                title = f"[{tag}] {h} {hs} : {as_} {a}"
                q_str = urllib.parse.quote(f"KBL {h} {a} 하이라이트")

            video_url = f"https://search.daum.net/search?w=vclip&q={q_str}"
            items.append(
                {
                    "title": title,
                    "url": video_url,
                    "arena": arena or "다음 동영상 클립",
                }
            )

    if team:
        full = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
        q_team = urllib.parse.quote(f"KBL {team} 하이라이트")
        items.append(
            {
                "title": f"🎬 {full} 최신 명장면 & 하이라이트 영상",
                "url": f"https://search.daum.net/search?w=vclip&q={q_team}",
                "arena": f"{team} 공식 영상",
            }
        )
        items.append(
            {
                "title": f"📺 Daum 스포츠 {team} 경기 영상 & 인터뷰 클립",
                "url": f"https://search.daum.net/search?w=vclip&q={q_team}",
                "arena": "Daum 스포츠",
            }
        )
    else:
        q_all = urllib.parse.quote("KBL 프로농구 하이라이트")
        items.append(
            {
                "title": "🎬 Daum 스포츠 KBL 전체 하이라이트 & 명장면 모음",
                "url": f"https://search.daum.net/search?w=vclip&q={q_all}",
                "arena": "Daum 스포츠 영상센터",
            }
        )

    items.append(
        {
            "title": "📺 KBL TV 공식 유튜브 전체 경기 하이라이트",
            "url": "https://www.youtube.com/@kbl_official",
            "arena": "KBL TV 공식 채널",
        }
    )
    return items[:6]
