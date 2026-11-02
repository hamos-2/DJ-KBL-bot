"""Dynamic KBL 2-Column Lineup Board Image Renderer & Daum Match Lineup Fetcher."""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.content.kbl_data import (
    DEFAULT_SPORTS_LOGO,
    TEAM_INFO,
    TEAM_LINEUPS,
    get_team_lineup,
    get_team_logo,
)
from services.search.parser import normalize_team_name

_CACHE_DIR = Path("/tmp/kbl_lineup_cache")
_AVATAR_DIR = _CACHE_DIR / "avatars"
_BOARD_DIR = _CACHE_DIR / "boards"
_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
_BOARD_DIR.mkdir(parents=True, exist_ok=True)

_DAUM_GAME_URL = "https://sports.daum.net/api/arms/SPORTS_GAME"

# Official Daum Sports KBL player headshot URLs (186 active players across 10 clubs)
PLAYER_PHOTO_URLS: dict[str, str] = {
    "김선형": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290407.jpg",
    "정창영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290454.jpg",
    "한희원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290583.jpg",
    "서민수": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290599.jpg",
    "문성곤": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290661.jpg",
    "전성현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290763.jpg",
    "이현석": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290783.jpg",
    "박지원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291352.jpg",
    "김준환": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291476.jpg",
    "하윤기": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291492.jpg",
    "이두원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291586.jpg",
    "문정현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291667.jpg",
    "패리스 배스": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291671.jpg",
    "미구엘 옥존": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291692.jpg",
    "조환희": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291765.jpg",
    "강성욱": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291842.jpg",
    "박민재": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291843.jpg",
    "트레이 포터": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291885.jpg",
    "정준원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290489.jpg",
    "배병준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290553.jpg",
    "이승현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290787.jpg",
    "서명진": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291189.jpg",
    "조한진": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291208.jpg",
    "김경원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291275.jpg",
    "이우석": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291375.jpg",
    "이도헌": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291388.jpg",
    "김동준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291494.jpg",
    "게이지 프림": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291579.jpg",
    "김태완": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291594.jpg",
    "박무빈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291649.jpg",
    "이대균": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291756.jpg",
    "최강민": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291847.jpg",
    "박정환": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291848.jpg",
    "김건하": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291849.jpg",
    "다리우스 베즐리": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291886.jpg",
    "제리 아바디아노": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291887.jpg",
    "이정현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291488.jpg",
    "정효근": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290790.jpg",
    "박봉진": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290904.jpg",
    "강상재": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291001.jpg",
    "최성원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291070.jpg",
    "이윤수": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291304.jpg",
    "이용우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291355.jpg",
    "이준희": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291386.jpg",
    "이윤기": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291351.jpg",
    "정호영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291483.jpg",
    "조은후": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291499.jpg",
    "이선 알바노": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291511.jpg",
    "인승찬": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291589.jpg",
    "레이션 해먼즈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291698.jpg",
    "앨런 윌리엄스": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291695.jpg",
    "김보배": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291752.jpg",
    "백승엽": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291753.jpg",
    "헨리 엘런슨": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291785.jpg",
    "이유진": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291850.jpg",
    "김휴범": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291851.jpg",
    "송재환": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291852.jpg",
    "이관희": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290440.jpg",
    "최현민": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290501.jpg",
    "이대성": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290742.jpg",
    "한호빈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290754.jpg",
    "최성모": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290985.jpg",
    "윤성원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291095.jpg",
    "크리스 맥컬러": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291237.jpg",
    "박진철": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291370.jpg",
    "이근휘": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291374.jpg",
    "저스틴 구탕": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291512.jpg",
    "신동혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291597.jpg",
    "여준형": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291592.jpg",
    "조준희": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291653.jpg",
    "임동언": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291763.jpg",
    "황영찬": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291764.jpg",
    "정성조": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291750.jpg",
    "케렘 칸터": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291787.jpg",
    "이규태": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291853.jpg",
    "안세준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291854.jpg",
    "장민국": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290478.jpg",
    "한상혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290648.jpg",
    "정인덕": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290996.jpg",
    "양홍석": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291091.jpg",
    "박정현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291291.jpg",
    "이광진": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291349.jpg",
    "윤원상": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291363.jpg",
    "문시윤": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291489.jpg",
    "아셈 마레이": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291432.jpg",
    "김종호": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291486.jpg",
    "양준석": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291576.jpg",
    "유기상": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291640.jpg",
    "칼 타마요": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291699.jpg",
    "최형찬": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291771.jpg",
    "김선우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291865.jpg",
    "김준영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291866.jpg",
    "임정현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291867.jpg",
    "지용현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291868.jpg",
    "아치 굿윈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291882.jpg",
    "오세근": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290450.jpg",
    "최부경": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290485.jpg",
    "전준범": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290740.jpg",
    "최원혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290784.jpg",
    "김낙현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291068.jpg",
    "안영준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291084.jpg",
    "자밀 워니": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291248.jpg",
    "김형빈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291303.jpg",
    "전성환": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291266.jpg",
    "아이재아 힉스": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291333.jpg",
    "오재현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291368.jpg",
    "임현택": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291383.jpg",
    "선상혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291497.jpg",
    "김수환": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291498.jpg",
    "이민서": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291760.jpg",
    "알빈 톨렌티노": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291784.jpg",
    "김명진": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291844.jpg",
    "안성우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291845.jpg",
    "에디 다니엘": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291846.jpg",
    "프레디": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291869.jpg",
    "장재석": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290539.jpg",
    "허웅": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290776.jpg",
    "이호현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290788.jpg",
    "허훈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291085.jpg",
    "김훈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291287.jpg",
    "최진광": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291293.jpg",
    "숀 롱": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291342.jpg",
    "김동현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291490.jpg",
    "서정현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291491.jpg",
    "이주영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291651.jpg",
    "조혁재": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291768.jpg",
    "이찬영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291769.jpg",
    "이현호": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291770.jpg",
    "윤기찬": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291859.jpg",
    "강태현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291860.jpg",
    "김윤성": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291861.jpg",
    "루이스 킹": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291884.jpg",
    "허일영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290284.jpg",
    "이대헌": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290603.jpg",
    "김종규": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290750.jpg",
    "박지훈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291008.jpg",
    "김준형": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291210.jpg",
    "변준형": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291220.jpg",
    "김진영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291277.jpg",
    "김세창": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291281.jpg",
    "박찬호": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291276.jpg",
    "한승희": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291372.jpg",
    "라숀 토마스": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291436.jpg",
    "주현우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291482.jpg",
    "렌즈 아반도": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291583.jpg",
    "표승빈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291648.jpg",
    "박정웅": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291746.jpg",
    "문유현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291857.jpg",
    "송한준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291858.jpg",
    "데이본 리드": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291888.jpg",
    "라건아": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290524.jpg",
    "김준일": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290781.jpg",
    "정성우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290901.jpg",
    "최승욱": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290785.jpg",
    "김국찬": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291087.jpg",
    "우동현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291182.jpg",
    "박준영": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291226.jpg",
    "전현우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291194.jpg",
    "박준은": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291289.jpg",
    "양재혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291274.jpg",
    "양준우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291376.jpg",
    "샘조세프 벨란겔": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291556.jpg",
    "염유성": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291599.jpg",
    "케베 알루마": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291680.jpg",
    "손준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291754.jpg",
    "권순우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291755.jpg",
    "양우혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291862.jpg",
    "김민규": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291863.jpg",
    "우상현": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291864.jpg",
    "정희재": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290529.jpg",
    "임동섭": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290542.jpg",
    "이동엽": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290662.jpg",
    "이재도": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290765.jpg",
    "김진유": "https://t1.daumcdn.net/media/img-section/sports13/player/10/290997.jpg",
    "조석호": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291391.jpg",
    "자니 오브라이언트": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291500.jpg",
    "조재우": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291605.jpg",
    "안정욱": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291606.jpg",
    "박종하": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291641.jpg",
    "소준혁": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291747.jpg",
    "이근준": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291748.jpg",
    "서동원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291749.jpg",
    "케빈 켐바오": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291778.jpg",
    "강지훈": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291855.jpg",
    "신지원": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291856.jpg",
    "스카티 제임스": "https://t1.daumcdn.net/media/img-section/sports13/player/10/291881.jpg"
}

_MEMORY_GAME_LINEUP_CACHE: dict[str, tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]] = {}


def get_player_photo_url(player_name: str) -> str | None:
    """Return official Daum KBL headshot URL for *player_name* if available."""
    if not player_name:
        return None
    clean = player_name.strip()
    if clean in PLAYER_PHOTO_URLS:
        return PLAYER_PHOTO_URLS[clean]
    compact = clean.replace(" ", "")
    for k, v in PLAYER_PHOTO_URLS.items():
        if k.replace(" ", "") == compact:
            return v
    return None


def get_baseline_starters_with_photos(team: str) -> list[dict[str, Any]]:
    """Return verified 5 starters for *team* enriched with official Daum photo URLs."""
    info = get_team_lineup(team) or {}
    starters = info.get("starters", [])
    out: list[dict[str, Any]] = []
    for s in starters[:5]:
        name = s.get("name", "")
        no = str(s.get("no", "")).replace("#", "").strip()
        pos = s.get("pos", "")
        out.append({
            "name": name,
            "no": no,
            "pos": pos,
            "imageUrl": s.get("imageUrl") or get_player_photo_url(name),
        })
    return out


def fetch_daum_match_lineup_sync(
    game_id: str,
    fallback_home: str | None = None,
    fallback_away: str | None = None,
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    """
    Fetch live or finished match starting 5 from Daum ARMS API (`SPORTS_GAME?detail=true`).
    Returns (home_team, away_team, home_starters, away_starters, is_official_daum_lineup).
    """
    gid = str(game_id).strip()
    if gid in _MEMORY_GAME_LINEUP_CACHE:
        return _MEMORY_GAME_LINEUP_CACHE[gid]

    home_team = fallback_home or "SK"
    away_team = fallback_away or "DB"

    if gid.isdigit() and len(gid) >= 6:
        try:
            resp = httpx.get(
                _DAUM_GAME_URL,
                params={"gameId": gid, "detail": "true"},
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": f"https://sports.daum.net/match/{gid}?tab=lineup",
                },
                verify=False,
                timeout=3.5,
            )
            if resp.status_code == 200:
                doc = (resp.json() or {}).get("document") or {}
                h_raw = ((doc.get("home") or {}).get("team") or {})
                a_raw = ((doc.get("away") or {}).get("team") or {})
                h_name = h_raw.get("shortNameKo") or h_raw.get("nameKo") or ""
                a_name = a_raw.get("shortNameKo") or a_raw.get("nameKo") or ""
                if h_name:
                    home_team = normalize_team_name(h_name) or home_team
                if a_name:
                    away_team = normalize_team_name(a_name) or away_team

                h_persons = doc.get("homePerson") or []
                a_persons = doc.get("awayPerson") or []
                h_started = [p for p in h_persons if p.get("isStarted")]
                a_started = [p for p in a_persons if p.get("isStarted")]

                if len(h_started) >= 5 and len(a_started) >= 5:
                    def _map_p(p: dict[str, Any]) -> dict[str, Any]:
                        nm = (p.get("nameKo") or p.get("nameMain") or "").strip()
                        img = (p.get("imageUrl") or "").replace("http://", "https://") or get_player_photo_url(nm)
                        return {
                            "name": nm,
                            "no": str(p.get("backNumber") or "").strip(),
                            "pos": str(p.get("positionName") or p.get("positionNameKo") or "").strip(),
                            "imageUrl": img,
                        }

                    h_list = [_map_p(p) for p in h_started[:5]]
                    a_list = [_map_p(p) for p in a_started[:5]]
                    res = (home_team, away_team, h_list, a_list, True)
                    _MEMORY_GAME_LINEUP_CACHE[gid] = res
                    return res
        except Exception:
            pass

    h_list = get_baseline_starters_with_photos(home_team)
    a_list = get_baseline_starters_with_photos(away_team)
    return (home_team, away_team, h_list, a_list, False)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load Korean font across Linux container (/app/assets/fonts) and macOS."""
    candidates = (
        [
            "/app/assets/fonts/NanumGothic-Bold.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        ]
        if bold
        else [
            "/app/assets/fonts/NanumGothic-Regular.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
        ]
    )
    for path in candidates:
        if os.path.exists(path):
            try:
                if path.endswith(".ttc"):
                    # Index 6 in AppleSDGothicNeo.ttc is Bold, 0 is Regular
                    return ImageFont.truetype(path, size=size, index=(6 if bold else 0))
                return ImageFont.truetype(path, size=size)
            except Exception:
                try:
                    return ImageFont.truetype(path, size=size)
                except Exception:
                    continue
    return ImageFont.load_default()


def _download_image_cached(url: str | None) -> Image.Image | None:
    """Download an image (player avatar or team logo) with local disk caching and retry."""
    if not url:
        return None
    norm_url = url.replace("http://", "https://")
    key = hashlib.md5(norm_url.encode("utf-8")).hexdigest()
    cache_path = _AVATAR_DIR / f"{key}.png"
    if cache_path.exists():
        try:
            return Image.open(cache_path).convert("RGBA")
        except Exception:
            pass

    for attempt in range(2):
        try:
            resp = httpx.get(
                norm_url,
                headers={"User-Agent": "Mozilla/5.0"},
                verify=False,
                timeout=4.5,
            )
            if resp.status_code == 200 and len(resp.content) > 100:
                img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                img.save(cache_path, format="PNG")
                return img
        except Exception:
            continue
    return None


def _make_circular_avatar(raw_img: Image.Image | None, diameter: int = 64) -> Image.Image:
    """Crop *raw_img* into a smooth antialiased circle with head-and-shoulders framing (matching Daum CSS)."""
    scale = 2
    big_d = diameter * scale
    canvas = Image.new("RGBA", (big_d, big_d), (0, 0, 0, 0))

    # Mask
    mask = Image.new("L", (big_d, big_d), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.ellipse((2, 2, big_d - 3, big_d - 3), fill=255)

    # Background circle (#F3F4F6)
    bg = Image.new("RGBA", (big_d, big_d), (243, 244, 246, 255))
    canvas.paste(bg, (0, 0), mask)

    if raw_img is not None:
        # Head-and-shoulders close-up crop (matching Daum Sports CSS top-center portrait zoom)
        src_w, src_h = raw_img.size
        crop_side = int(min(src_w, src_h) * 0.76)
        left = (src_w - crop_side) // 2
        top = int(src_h * 0.02)
        cropped = raw_img.crop((left, top, left + crop_side, top + crop_side))
        resized = cropped.resize((big_d, big_d), Image.Resampling.LANCZOS)
        canvas.paste(resized, (0, 0), mask)

    # Subtle outer border (#E5E7EB)
    b_draw = ImageDraw.Draw(canvas)
    b_draw.ellipse((2, 2, big_d - 3, big_d - 3), outline=(229, 231, 235, 255), width=2)

    return canvas.resize((diameter, diameter), Image.Resampling.LANCZOS)


def render_lineup_board_png(
    home_team: str,
    away_team: str,
    home_starters: list[dict[str, Any]],
    away_starters: list[dict[str, Any]],
) -> bytes:
    """
    Render the 2-column KBL starting lineup board PNG matching Daum Sports (`?tab=lineup`).
    Dimensions: 960 x 540 px.
    """
    from concurrent.futures import ThreadPoolExecutor

    sig_payload = f"v2:{home_team}:{away_team}:" + "|".join(
        f"{p.get('no')}-{p.get('name')}" for p in (home_starters + away_starters)
    )
    sig = hashlib.md5(sig_payload.encode("utf-8")).hexdigest()
    board_path = _BOARD_DIR / f"board_{sig}.png"
    if board_path.exists():
        try:
            return board_path.read_bytes()
        except Exception:
            pass

    # Pre-warm all logo & player avatar downloads concurrently (< 0.4s total)
    urls_to_fetch: list[str] = [get_team_logo(home_team), get_team_logo(away_team)]
    for p in (home_starters[:5] + away_starters[:5]):
        u = p.get("imageUrl") or get_player_photo_url(str(p.get("name") or ""))
        if u:
            urls_to_fetch.append(u)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_download_image_cached, urls_to_fetch))

    width, height = 960, 540
    header_h = 75
    row_h = (height - header_h) // 5  # 93px per starter row
    half_w = width // 2  # 480px

    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Top header background (#FAFAFA)
    draw.rectangle((0, 0, width, header_h), fill=(250, 250, 250, 255))
    draw.line((0, header_h, width, header_h), fill=(238, 238, 238, 255), width=1)

    # Center vertical divider
    draw.line((half_w, 0, half_w, height), fill=(238, 238, 238, 255), width=1)

    # Horizontal row dividers
    for r_idx in range(1, 5):
        y = header_h + r_idx * row_h
        draw.line((0, y, width, y), fill=(242, 243, 245, 255), width=1)

    font_header = _load_font(21, bold=True)
    font_num = _load_font(21, bold=False)
    font_name = _load_font(21, bold=False)

    # Draw headers for Home (left) and Away (right)
    for col_idx, team_code in enumerate([home_team, away_team]):
        col_x = col_idx * half_w
        full_name = TEAM_INFO.get(team_code, {}).get("full_name", f"{team_code} 프로농구단")
        logo_img = _download_image_cached(get_team_logo(team_code))
        if logo_img is not None:
            logo_resized = logo_img.resize((40, 40), Image.Resampling.LANCZOS)
            img.paste(logo_resized, (col_x + 28, (header_h - 40) // 2), logo_resized)
        draw.text(
            (col_x + 78, header_h // 2),
            full_name,
            font=font_header,
            fill=(17, 17, 17, 255),
            anchor="lm",
        )

    # Draw 5 starter rows for Home (left, green numbers) and Away (right, red numbers)
    for col_idx, (starters, num_color) in enumerate(
        [
            (home_starters[:5], (0, 172, 71, 255)),   # Daum Sports Green (#00AC47)
            (away_starters[:5], (217, 43, 43, 255)),  # Daum Sports Red (#D92B2B)
        ]
    ):
        col_x = col_idx * half_w
        for r_idx, player in enumerate(starters):
            row_top = header_h + r_idx * row_h
            row_center_y = row_top + row_h // 2

            # 1. Circular player headshot (64x64)
            p_name = str(player.get("name") or "").strip()
            p_no = str(player.get("no") or "").replace("#", "").strip()
            p_url = player.get("imageUrl") or get_player_photo_url(p_name)
            raw_avatar = _download_image_cached(p_url)
            avatar = _make_circular_avatar(raw_avatar, diameter=64)
            img.paste(avatar, (col_x + 28, row_top + (row_h - 64) // 2), avatar)

            # 2. Jersey number (centered at col_x + 118)
            draw.text(
                (col_x + 118, row_center_y),
                p_no,
                font=font_num,
                fill=num_color,
                anchor="mm",
            )

            # 3. Player Korean name (left-aligned at col_x + 150)
            draw.text(
                (col_x + 150, row_center_y),
                p_name,
                font=font_name,
                fill=(17, 17, 17, 255),
                anchor="lm",
            )

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        board_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes
