"""Dynamic KBL 2-Column Lineup Board Image Renderer & Daum Match Lineup Fetcher."""

from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
import hashlib
import io
import os
import re
import threading
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.content.kbl_data import (
    DEFAULT_SPORTS_LOGO,
    TEAM_INFO,
    TEAM_LINEUPS,
    _get_tls_verify,
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

import time

# ---------------------------------------------------------------------------
# High-Performance In-Memory LRU & TTL Caches
# ---------------------------------------------------------------------------
class _LineupCacheEntry:
    def __init__(
        self,
        data: tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool],
        ttl: float = 600.0,
    ) -> None:
        self.data = data
        self.expires_at = time.time() + ttl

_GAME_LINEUP_CACHE: dict[str, _LineupCacheEntry] = {}
_MAX_LINEUP_CACHE_SIZE = 50

# Backward compatibility alias
_MEMORY_GAME_LINEUP_CACHE: dict[str, tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]] = {}

def get_cached_game_lineup(
    gid: str,
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool] | None:
    """Retrieve non-expired game lineup from memory cache."""
    entry = _GAME_LINEUP_CACHE.get(gid)
    if entry:
        if time.time() < entry.expires_at:
            return entry.data
        _GAME_LINEUP_CACHE.pop(gid, None)
        _MEMORY_GAME_LINEUP_CACHE.pop(gid, None)
    return None

def set_cached_game_lineup(
    gid: str,
    data: tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool],
    ttl: float = 600.0,
) -> None:
    """Cache game lineup with TTL and LRU eviction."""
    now = time.time()
    if len(_GAME_LINEUP_CACHE) >= _MAX_LINEUP_CACHE_SIZE:
        expired = [k for k, v in _GAME_LINEUP_CACHE.items() if now >= v.expires_at]
        for k in expired:
            _GAME_LINEUP_CACHE.pop(k, None)
            _MEMORY_GAME_LINEUP_CACHE.pop(k, None)
        if len(_GAME_LINEUP_CACHE) >= _MAX_LINEUP_CACHE_SIZE:
            first_k = next(iter(_GAME_LINEUP_CACHE))
            _GAME_LINEUP_CACHE.pop(first_k, None)
            _MEMORY_GAME_LINEUP_CACHE.pop(first_k, None)
    _GAME_LINEUP_CACHE[gid] = _LineupCacheEntry(data, ttl=ttl)
    _MEMORY_GAME_LINEUP_CACHE[gid] = data

# In-memory rendered PNG image LRU cache (eliminates disk I/O while bounding RAM on 952 MiB OCI)
_BOARD_IMAGE_MEMORY_CACHE: OrderedDict[str, bytes] = OrderedDict()
_MAX_BOARD_IMAGE_CACHE_SIZE = 40
_MAX_BOARD_IMAGE_CACHE_BYTES = 16 * 1024 * 1024  # 16 MiB strict RAM budget
_RENDER_SEMAPHORE = threading.Semaphore(2)


def get_cached_board_image(sig: str) -> bytes | None:
    data = _BOARD_IMAGE_MEMORY_CACHE.get(sig)
    if data is not None:
        _BOARD_IMAGE_MEMORY_CACHE.move_to_end(sig)
    return data


def set_cached_board_image(sig: str, img_bytes: bytes) -> None:
    if sig in _BOARD_IMAGE_MEMORY_CACHE:
        _BOARD_IMAGE_MEMORY_CACHE.move_to_end(sig)
    _BOARD_IMAGE_MEMORY_CACHE[sig] = img_bytes
    total_bytes = sum(len(v) for v in _BOARD_IMAGE_MEMORY_CACHE.values())
    while (
        len(_BOARD_IMAGE_MEMORY_CACHE) > _MAX_BOARD_IMAGE_CACHE_SIZE
        or total_bytes > _MAX_BOARD_IMAGE_CACHE_BYTES
    ):
        if len(_BOARD_IMAGE_MEMORY_CACHE) <= 1 and total_bytes > _MAX_BOARD_IMAGE_CACHE_BYTES:
            _BOARD_IMAGE_MEMORY_CACHE.clear()
            break
        _, evicted = _BOARD_IMAGE_MEMORY_CACHE.popitem(last=False)
        total_bytes -= len(evicted)


def invalidate_lineup_caches(game_id: str | None = None) -> None:
    """Evict in-memory lineup and rendered PNG board caches when lineups change."""
    if game_id:
        gid = str(game_id).strip()
        _GAME_LINEUP_CACHE.pop(gid, None)
        _MEMORY_GAME_LINEUP_CACHE.pop(gid, None)
    else:
        _GAME_LINEUP_CACHE.clear()
        _MEMORY_GAME_LINEUP_CACHE.clear()
    # Always clear board image cache so updated starters/numbers re-render immediately
    _BOARD_IMAGE_MEMORY_CACHE.clear()



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
    timeout: float = 2.5,
    force_refresh: bool = False,
    ttl: float = 120.0,
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    """
    Fetch live or finished match starting 5 from Daum ARMS API (`SPORTS_GAME?detail=true`).
    Returns (home_team, away_team, home_starters, away_starters, is_official_daum_lineup).
    """
    gid = str(game_id).strip()
    if not force_refresh:
        cached = get_cached_game_lineup(gid)
        if cached is not None:
            return cached

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
                verify=_get_tls_verify(),
                timeout=timeout,
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

                    from services.roster.naver_verifier import verify_and_enrich_starters_sync
                    h_list = verify_and_enrich_starters_sync(
                        home_team, [_map_p(p) for p in h_started[:5]], is_official_daum=True
                    )["verified_starters"]
                    a_list = verify_and_enrich_starters_sync(
                        away_team, [_map_p(p) for p in a_started[:5]], is_official_daum=True
                    )["verified_starters"]
                    res = (home_team, away_team, h_list, a_list, True)
                    set_cached_game_lineup(gid, res, ttl=ttl)
                    return res
        except Exception:
            pass

    from services.roster.naver_verifier import verify_and_enrich_starters_sync
    h_list = verify_and_enrich_starters_sync(
        home_team, get_baseline_starters_with_photos(home_team), is_official_daum=False
    )["verified_starters"]
    a_list = verify_and_enrich_starters_sync(
        away_team, get_baseline_starters_with_photos(away_team), is_official_daum=False
    )["verified_starters"]
    return (home_team, away_team, h_list, a_list, False)


@lru_cache(maxsize=64)
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
            with Image.open(cache_path) as im:
                return im.convert("RGBA")
        except Exception:
            pass

    for attempt in range(2):
        try:
            resp = httpx.get(
                norm_url,
                headers={"User-Agent": "Mozilla/5.0"},
                verify=_get_tls_verify(),
                timeout=4.5,
            )
            if resp.status_code == 200 and len(resp.content) > 100:
                with Image.open(io.BytesIO(resp.content)) as im:
                    img = im.convert("RGBA")
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
    Dimensions: 800 x 800 px (1:1 square so Kakao basicCard fixedRatio=True has zero top/bottom margin).
    """
    from concurrent.futures import ThreadPoolExecutor

    font_sig = getattr(_load_font(22, bold=True), "path", "default")
    sig_payload = f"v5_800x800:{font_sig}:{home_team}:{away_team}:" + "|".join(
        f"{p.get('no')}-{p.get('name')}" for p in (home_starters + away_starters)
    )
    sig = hashlib.md5(sig_payload.encode("utf-8")).hexdigest()
    mem_hit = get_cached_board_image(sig)
    if mem_hit is not None:
        return mem_hit

    board_path = _BOARD_DIR / f"board_{sig}.png"
    if board_path.exists():
        try:
            b_data = board_path.read_bytes()
            set_cached_board_image(sig, b_data)
            return b_data
        except Exception:
            pass

    # Pre-warm all logo & player avatar downloads concurrently (< 0.4s total)
    urls_to_fetch: list[str] = [get_team_logo(home_team), get_team_logo(away_team)]
    for p in (home_starters[:5] + away_starters[:5]):
        u = p.get("imageUrl") or get_player_photo_url(str(p.get("name") or ""))
        if u:
            urls_to_fetch.append(u)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, urls_to_fetch))

    width, height = 800, 800
    header_h = 95
    row_h = (height - header_h) // 5  # 141px per starter row
    half_w = width // 2  # 400px

    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Top header background (#FAFAFA)
    draw.rectangle((0, 0, width, header_h), fill=(250, 250, 250, 255))
    draw.line((0, header_h, width, header_h), fill=(235, 235, 235, 255), width=2)

    # Center vertical divider
    draw.line((half_w, 0, half_w, height), fill=(235, 235, 235, 255), width=2)

    # Horizontal row dividers
    for r_idx in range(1, 5):
        y = header_h + r_idx * row_h
        draw.line((0, y, width, y), fill=(240, 241, 243, 255), width=1)

    font_header = _load_font(22, bold=True)
    font_num = _load_font(24, bold=True)
    font_name = _load_font(23, bold=False)

    # Draw headers for Home (left) and Away (right)
    for col_idx, team_code in enumerate([home_team, away_team]):
        col_x = col_idx * half_w
        full_name = TEAM_INFO.get(team_code, {}).get("full_name", f"{team_code} 프로농구단")
        logo_img = _download_image_cached(get_team_logo(team_code))
        if logo_img is not None:
            logo_resized = logo_img.resize((46, 46), Image.Resampling.LANCZOS)
            img.paste(logo_resized, (col_x + 20, (header_h - 46) // 2), logo_resized)
        draw.text(
            (col_x + 76, header_h // 2),
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

            # 1. Circular player headshot (96x96)
            p_name = str(player.get("name") or "").strip()
            p_no = str(player.get("no") or "").replace("#", "").strip()
            p_url = player.get("imageUrl") or get_player_photo_url(p_name)
            raw_avatar = _download_image_cached(p_url)
            avatar = _make_circular_avatar(raw_avatar, diameter=96)
            img.paste(avatar, (col_x + 20, row_top + (row_h - 96) // 2), avatar)

            # 2. Jersey number (centered at col_x + 144)
            draw.text(
                (col_x + 144, row_center_y),
                p_no,
                font=font_num,
                fill=num_color,
                anchor="mm",
            )

            # 3. Player Korean name (left-aligned at col_x + 178)
            draw.text(
                (col_x + 178, row_center_y),
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
    set_cached_board_image(sig, png_bytes)
    return png_bytes


def render_single_team_lineup_board_png(
    team: str,
    starters: list[dict[str, Any]],
    coach: str = "",
) -> bytes:
    """
    Render a 1-column (single-team) KBL starting lineup board PNG (800 x 800 px)
    when the user requests a specific club's lineup (e.g. '정관장 라인업', 'SK 라인업').
    Displays only the requested team's logo, head coach, and 5 starters (portrait + number + name + position).
    """
    from concurrent.futures import ThreadPoolExecutor

    font_sig = getattr(_load_font(25, bold=True), "path", "default")
    sig_payload = f"v5_single_800x800:{font_sig}:{team}:{coach}:" + "|".join(
        f"{p.get('no')}-{p.get('name')}" for p in starters[:5]
    )
    sig = hashlib.md5(sig_payload.encode("utf-8")).hexdigest()
    mem_hit = get_cached_board_image(sig)
    if mem_hit is not None:
        return mem_hit

    board_path = _BOARD_DIR / f"board_single_{sig}.png"
    if board_path.exists():
        try:
            b_data = board_path.read_bytes()
            set_cached_board_image(sig, b_data)
            return b_data
        except Exception:
            pass

    urls_to_fetch: list[str] = [get_team_logo(team)]
    for p in starters[:5]:
        u = p.get("imageUrl") or get_player_photo_url(str(p.get("name") or ""))
        if u:
            urls_to_fetch.append(u)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, urls_to_fetch))

    width, height = 800, 800
    header_h = 95
    row_h = (height - header_h) // 5  # 141px per starter row

    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Top header background (#FAFAFA)
    draw.rectangle((0, 0, width, header_h), fill=(250, 250, 250, 255))
    draw.line((0, header_h, width, header_h), fill=(235, 235, 235, 255), width=2)

    # Horizontal row dividers
    for r_idx in range(1, 5):
        y = header_h + r_idx * row_h
        draw.line((0, y, width, y), fill=(240, 241, 243, 255), width=1)

    font_header = _load_font(25, bold=True)
    font_coach = _load_font(20, bold=False)
    font_num = _load_font(27, bold=True)
    font_name = _load_font(26, bold=True)
    font_pos = _load_font(21, bold=False)

    full_name = TEAM_INFO.get(team, {}).get("full_name", f"{team} 프로농구단")
    logo_img = _download_image_cached(get_team_logo(team))
    if logo_img is not None:
        logo_resized = logo_img.resize((52, 52), Image.Resampling.LANCZOS)
        img.paste(logo_resized, (32, (header_h - 52) // 2), logo_resized)

    draw.text(
        (98, header_h // 2),
        full_name,
        font=font_header,
        fill=(17, 17, 17, 255),
        anchor="lm",
    )
    if coach:
        draw.text(
            (width - 36, header_h // 2),
            f"{coach} 감독",
            font=font_coach,
            fill=(110, 110, 110, 255),
            anchor="rm",
        )

    num_color = (217, 43, 43, 255) if team in ("정관장", "SK", "LG", "모비스", "현대모비스") else (0, 172, 71, 255)

    for r_idx, player in enumerate(starters[:5]):
        row_top = header_h + r_idx * row_h
        row_center_y = row_top + row_h // 2

        p_name = str(player.get("name") or "").strip()
        p_no = str(player.get("no") or "").replace("#", "").strip()
        p_pos = str(player.get("pos") or "").strip()
        p_url = player.get("imageUrl") or get_player_photo_url(p_name)

        raw_avatar = _download_image_cached(p_url)
        avatar = _make_circular_avatar(raw_avatar, diameter=100)
        img.paste(avatar, (36, row_top + (row_h - 100) // 2), avatar)

        draw.text(
            (176, row_center_y),
            p_no,
            font=font_num,
            fill=num_color,
            anchor="mm",
        )

        draw.text(
            (226, row_center_y),
            p_name,
            font=font_name,
            fill=(17, 17, 17, 255),
            anchor="lm",
        )

        if p_pos:
            draw.text(
                (width - 36, row_center_y),
                p_pos,
                font=font_pos,
                fill=(130, 130, 130, 255),
                anchor="rm",
            )

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        board_path.write_bytes(png_bytes)
    except Exception:
        pass
    set_cached_board_image(sig, png_bytes)
    return png_bytes


# ---------------------------------------------------------------------------
# Pre-warming & Cache Priming Engine
# ---------------------------------------------------------------------------
def prewarm_match_lineup(
    game_id: str,
    home_team: str,
    away_team: str,
    timeout: float = 2.0,
) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    """
    Pre-warm Daum lineup data and render board image for *game_id*.
    Populates in-memory & disk caches so subsequent user/Kakao requests are instant.
    """
    h_team, a_team, h_starters, a_starters, is_off = fetch_daum_match_lineup_sync(
        game_id, fallback_home=home_team, fallback_away=away_team, timeout=timeout
    )
    # Render and cache both the 2-column match board and individual single-team boards
    try:
        render_lineup_board_png(h_team, a_team, h_starters, a_starters)
        h_info = get_team_lineup(h_team) or {}
        a_info = get_team_lineup(a_team) or {}
        render_single_team_lineup_board_png(h_team, h_starters, coach=str(h_info.get("head_coach") or ""))
        render_single_team_lineup_board_png(a_team, a_starters, coach=str(a_info.get("head_coach") or ""))
    except Exception:
        pass
    return (h_team, a_team, h_starters, a_starters, is_off)


def _prune_old_cache_files(max_age_seconds: int = 48 * 3600) -> int:
    """Remove cached PNG files older than *max_age_seconds* to keep disk usage bounded."""
    import time

    removed = 0
    cutoff = time.time() - max_age_seconds
    for folder in (_AVATAR_DIR, _BOARD_DIR, _BANNER_DIR):
        try:
            for p in folder.iterdir():
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
                    removed += 1
        except Exception:
            pass
    return removed


def prewarm_daily_lineups(games: list[dict[str, Any]]) -> int:
    """
    Pre-warm lineups and board images for all given games (typically today's games).
    Also prunes stale disk cache PNGs (>48h). Returns count of games successfully pre-warmed.
    """
    from concurrent.futures import ThreadPoolExecutor

    _prune_old_cache_files()

    count = 0
    games_to_prewarm: list[tuple[str, str, str]] = []
    for g in games:
        gid = str(g.get("game_id") or "")
        home = str(g.get("home_team") or "")
        away = str(g.get("away_team") or "")
        if home and away:
            games_to_prewarm.append((gid, home, away))

    if not games_to_prewarm:
        return 0

    with ThreadPoolExecutor(max_workers=min(len(games_to_prewarm), 4)) as pool:
        futures = [
            pool.submit(prewarm_match_lineup, gid, home, away)
            for gid, home, away in games_to_prewarm
        ]
        for fut in futures:
            try:
                fut.result()
                count += 1
            except Exception:
                pass
    return count


_BANNER_DIR = _CACHE_DIR / "banners"
_BANNER_DIR.mkdir(parents=True, exist_ok=True)


def render_player_category_banner_png(
    title: str,
    players: list[tuple[str, str]],
    width: int = 800,
    height: int = 400,
) -> bytes:
    """
    Render 2:1 ratio (800x400) visual banner for favorite player categories
    (e.g. Popular Guards, Popular Bigs & Shooters).
    """
    from concurrent.futures import ThreadPoolExecutor

    sig_payload = f"cat_v1:{title}:" + "|".join(f"{n}-{t}" for n, t in players)
    sig = hashlib.md5(sig_payload.encode("utf-8")).hexdigest()
    banner_path = _BANNER_DIR / f"banner_{sig}.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    urls_to_fetch: list[str] = []
    for name, team in players:
        p_u = get_player_photo_url(name)
        if p_u:
            urls_to_fetch.append(p_u)
        t_u = get_team_logo(team)
        if t_u:
            urls_to_fetch.append(t_u)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, urls_to_fetch))

    img = Image.new("RGBA", (width, height), (248, 249, 251, 255))
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle((0, 0, width - 1, height - 1), outline=(225, 228, 232, 255), width=2)

    # Top header bar
    draw.rectangle((0, 0, width, 68), fill=(240, 243, 246, 255))
    draw.line((0, 68, width, 68), fill=(225, 228, 232, 255), width=1)

    font_title = _load_font(23, bold=True)
    font_name = _load_font(22, bold=True)
    font_team = _load_font(18, bold=False)
    font_action = _load_font(16, bold=False)

    draw.text((width // 2, 34), title, font=font_title, fill=(30, 30, 30, 255), anchor="mm")

    n = max(1, len(players))
    slot_w = width // n
    for i, (name, team) in enumerate(players):
        cx = slot_w * i + slot_w // 2
        cy = 185

        p_url = get_player_photo_url(name)
        raw = _download_image_cached(p_url)
        avatar = _make_circular_avatar(raw, diameter=128)
        img.paste(avatar, (cx - 64, cy - 64), avatar)

        t_logo = _download_image_cached(get_team_logo(team))
        if t_logo:
            t_resized = t_logo.resize((34, 34), Image.Resampling.LANCZOS)
            img.paste(t_resized, (cx + 28, cy + 28), t_resized)

        draw.text((cx, 280), name, font=font_name, fill=(17, 17, 17, 255), anchor="mm")
        full_t = TEAM_INFO.get(team, {}).get("full_name", team)
        draw.text((cx, 312), full_t, font=font_team, fill=(110, 110, 110, 255), anchor="mm")
        draw.text((cx, 355), "선택 등록/해제", font=font_action, fill=(24, 119, 242, 255), anchor="mm")

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_team_starters_banner_png(
    team: str,
    player_names: list[str],
    part_label: str = "(1/2)",
    width: int = 800,
    height: int = 400,
) -> bytes:
    """Render 2:1 ratio (800x400) visual banner for a club's Best 5 starters."""
    from concurrent.futures import ThreadPoolExecutor

    sig_payload = f"team_starters_v1:{team}:{part_label}:" + "|".join(player_names)
    sig = hashlib.md5(sig_payload.encode("utf-8")).hexdigest()
    banner_path = _BANNER_DIR / f"banner_{sig}.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    urls_to_fetch: list[str] = [get_team_logo(team)]
    for name in player_names:
        p_u = get_player_photo_url(name)
        if p_u:
            urls_to_fetch.append(p_u)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, urls_to_fetch))

    img = Image.new("RGBA", (width, height), (248, 249, 251, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, width - 1, height - 1), outline=(225, 228, 232, 255), width=2)
    draw.rectangle((0, 0, width, 68), fill=(240, 243, 246, 255))
    draw.line((0, 68, width, 68), fill=(225, 228, 232, 255), width=1)

    full_t = TEAM_INFO.get(team, {}).get("full_name", f"{team} 농구단")
    font_title = _load_font(23, bold=True)
    draw.text((width // 2, 34), f"{full_t} 베스트 5 {part_label}", font=font_title, fill=(30, 30, 30, 255), anchor="mm")

    font_name = _load_font(22, bold=True)
    font_sub = _load_font(18, bold=False)
    font_action = _load_font(16, bold=False)

    n = max(1, len(player_names))
    slot_w = width // n
    for i, name in enumerate(player_names):
        cx = slot_w * i + slot_w // 2
        cy = 185

        p_url = get_player_photo_url(name)
        raw = _download_image_cached(p_url)
        avatar = _make_circular_avatar(raw, diameter=128)
        img.paste(avatar, (cx - 64, cy - 64), avatar)

        t_logo = _download_image_cached(get_team_logo(team))
        if t_logo:
            t_resized = t_logo.resize((34, 34), Image.Resampling.LANCZOS)
            img.paste(t_resized, (cx + 28, cy + 28), t_resized)

        draw.text((cx, 280), name, font=font_name, fill=(17, 17, 17, 255), anchor="mm")
        draw.text((cx, 312), f"{team} 주전", font=font_sub, fill=(110, 110, 110, 255), anchor="mm")
        draw.text((cx, 355), "선택 등록/해제", font=font_action, fill=(24, 119, 242, 255), anchor="mm")

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_all_teams_banner_png(width: int = 800, height: int = 400) -> bytes:
    """Render 2:1 ratio (800x400) visual banner for all 10 KBL clubs."""
    from concurrent.futures import ThreadPoolExecutor

    banner_path = _BANNER_DIR / "banner_all_teams_v1.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    teams = ["SK", "KT", "삼성", "DB", "정관장", "소노", "LG", "KCC", "현대모비스", "한국가스공사"]
    urls_to_fetch = [get_team_logo(t) for t in teams]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, urls_to_fetch))

    img = Image.new("RGBA", (width, height), (248, 249, 251, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, width - 1, height - 1), outline=(225, 228, 232, 255), width=2)
    draw.rectangle((0, 0, width, 68), fill=(240, 243, 246, 255))
    draw.line((0, 68, width, 68), fill=(225, 228, 232, 255), width=1)

    font_title = _load_font(23, bold=True)
    draw.text((width // 2, 34), "KBL 10개 구단 선수단 둘러보기", font=font_title, fill=(30, 30, 30, 255), anchor="mm")

    col_w = width // 5
    row_h = (height - 68) // 2

    font_alias = _load_font(18, bold=True)
    for idx, t in enumerate(teams):
        r = idx // 5
        c = idx % 5
        cx = c * col_w + col_w // 2
        cy = 68 + r * row_h + row_h // 2

        logo = _download_image_cached(get_team_logo(t))
        if logo:
            l_resized = logo.resize((68, 68), Image.Resampling.LANCZOS)
            img.paste(l_resized, (cx - 34, cy - 46), l_resized)

        alias = "모비스" if t == "현대모비스" else ("가스공사" if t == "한국가스공사" else t)
        draw.text((cx, cy + 38), alias, font=font_alias, fill=(40, 40, 40, 255), anchor="mm")

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_team_home_banner_png(
    team: str, width: int = 800, height: int = 400
) -> bytes:
    """Render bold, high-visibility 2:1 (800x400) banner for home/welcome screen."""
    t_clean = team.strip() if team else "SK"
    banner_path = _BANNER_DIR / f"banner_home_{t_clean}_v3.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    full_t = TEAM_INFO.get(t_clean, {}).get("full_name", f"{t_clean} 농구단")
    arena = TEAM_INFO.get(t_clean, {}).get("arena", "홈경기장")

    img = Image.new("RGBA", (width, height), (248, 249, 252, 255))
    draw = ImageDraw.Draw(img)

    # Outer border & header bar
    draw.rectangle((0, 0, width - 1, height - 1), outline=(225, 228, 234, 255), width=2)
    draw.rectangle((0, 0, width, 64), fill=(240, 243, 248, 255))
    draw.line((0, 64, width, 64), fill=(225, 228, 234, 255), width=1)

    font_title = _load_font(25, bold=True)
    draw.text((width // 2, 32), full_t, font=font_title, fill=(22, 24, 29, 255), anchor="mm")

    # Prominent center logo badge (diameter 192px, logo 164x164)
    cx, cy = width // 2, 190
    r = 96
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(220, 225, 235, 255), width=3)

    logo = _download_image_cached(get_team_logo(t_clean))
    if logo:
        l_resized = logo.resize((164, 164), Image.Resampling.LANCZOS)
        img.paste(l_resized, (cx - 82, cy - 82), l_resized if l_resized.mode == "RGBA" else None)

    # Subtitles
    font_sub = _load_font(19, bold=True)
    font_hint = _load_font(17, bold=False)
    draw.text((width // 2, 322), f"2026-2027 KBL 정규리그  |  {arena}", font=font_sub, fill=(85, 92, 105, 255), anchor="mm")
    draw.text((width // 2, 360), "일정  •  선발 라인업  •  경기결과  •  실시간 점수", font=font_hint, fill=(24, 119, 242, 255), anchor="mm")

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_news_home_banner_png(
    team: str | None = None, width: int = 800, height: int = 400
) -> bytes:
    """Render bold, high-visibility 2:1 (800x400) banner for home news card."""
    t_clean = team.strip() if team else "all"
    banner_path = _BANNER_DIR / f"banner_home_news_{t_clean}_v3.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    img = Image.new("RGBA", (width, height), (248, 249, 252, 255))
    draw = ImageDraw.Draw(img)

    # Outer border & header bar
    draw.rectangle((0, 0, width - 1, height - 1), outline=(225, 228, 234, 255), width=2)
    draw.rectangle((0, 0, width, 64), fill=(240, 243, 248, 255))
    draw.line((0, 64, width, 64), fill=(225, 228, 234, 255), width=1)

    font_title = _load_font(25, bold=True)
    header_text = f"[{team}] 최신 뉴스 & 주요 소식" if (team and team != "all") else "실시간 KBL 뉴스 & 주요 헤드라인"
    draw.text((width // 2, 32), header_text, font=font_title, fill=(22, 24, 29, 255), anchor="mm")

    cx, cy = width // 2, 190
    r = 96
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(220, 225, 235, 255), width=3)

    logo_url = get_team_logo(team) if (team and team != "all") else DEFAULT_SPORTS_LOGO
    logo = _download_image_cached(logo_url)
    if logo:
        l_resized = logo.resize((164, 164), Image.Resampling.LANCZOS)
        img.paste(l_resized, (cx - 82, cy - 82), l_resized if l_resized.mode == "RGBA" else None)

    font_sub = _load_font(19, bold=True)
    font_hint = _load_font(17, bold=False)
    sub_text = f"{team} 감독·선수 인터뷰 및 경기 분석 리포트" if (team and team != "all") else "10개 구단 속보 및 현장 인터뷰 제공"
    draw.text((width // 2, 322), sub_text, font=font_sub, fill=(85, 92, 105, 255), anchor="mm")
    draw.text((width // 2, 360), "실시간 속보  •  공식 인터뷰  •  하이라이트 영상", font=font_hint, fill=(24, 119, 242, 255), anchor="mm")

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_onboarding_region_banner_png(
    region_key: str, width: int = 800, height: int = 400
) -> bytes:
    """Render bold, high-visibility 2:1 (800x400) banner for onboarding region cards."""
    rk = region_key.lower().strip()
    banner_path = _BANNER_DIR / f"banner_region_{rk}_v3.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    region_map: dict[str, tuple[str, list[str]]] = {
        "capital": ("수도권 구단 선택 (SK • KT • 삼성)", ["SK", "KT", "삼성"]),
        "gangwon_gyeonggi": ("경기·강원 구단 선택 (DB • 정관장 • 소노)", ["DB", "정관장", "소노"]),
        "yeongnam": ("영남권 구단 선택 (LG • KCC • 현대모비스)", ["LG", "KCC", "현대모비스"]),
        "daegu": ("대구 구단 선택 (대구 한국가스공사)", ["한국가스공사"]),
    }

    title, teams = region_map.get(rk, ("응원팀 선택", ["SK", "DB", "LG"]))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, [get_team_logo(t) for t in teams]))

    img = Image.new("RGBA", (width, height), (248, 249, 252, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, width - 1, height - 1), outline=(225, 228, 234, 255), width=2)
    draw.rectangle((0, 0, width, 64), fill=(240, 243, 248, 255))
    draw.line((0, 64, width, 64), fill=(225, 228, 234, 255), width=1)

    font_title = _load_font(24, bold=True)
    draw.text((width // 2, 32), title, font=font_title, fill=(22, 24, 29, 255), anchor="mm")

    font_name = _load_font(22, bold=True)
    font_sub = _load_font(16, bold=False)

    n = len(teams)
    slot_w = width // n
    for i, t in enumerate(teams):
        cx = slot_w * i + slot_w // 2
        cy = 185 if n > 1 else 190
        r = 72 if n > 1 else 96
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(220, 225, 235, 255), width=3)

        logo = _download_image_cached(get_team_logo(t))
        if logo:
            size = 118 if n > 1 else 164
            l_resized = logo.resize((size, size), Image.Resampling.LANCZOS)
            img.paste(l_resized, (cx - size // 2, cy - size // 2), l_resized if l_resized.mode == "RGBA" else None)

        alias = "현대모비스" if t == "현대모비스" else ("한국가스공사" if t == "한국가스공사" else t)
        draw.text((cx, 298 if n > 1 else 322), alias, font=font_name, fill=(22, 24, 29, 255), anchor="mm")
        draw.text((cx, 336 if n > 1 else 360), "응원팀 설정하기", font=font_sub, fill=(24, 119, 242, 255), anchor="mm")

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_notification_settings_banner_png(
    mode: str,
    s1: int = 1,
    s2: int = 1,
    s3: int = 1,
    team: str | None = None,
    width: int = 800,
    height: int = 400,
) -> bytes:
    """
    Render a custom 2:1 (800x400) visual dashboard banner for '경기 핵심 알림' (mode='core')
    and '상황별 알림' (mode='situational') with live ON/OFF status cards and club emblem.
    """
    m_key = "situational" if mode == "situational" else "core"
    t_clean = (team or "SK").strip()
    if t_clean not in TEAM_INFO:
        t_clean = "SK"
    sig_str = f"notif_v1:{m_key}:{s1}:{s2}:{s3}:{t_clean}"
    sig = hashlib.md5(sig_str.encode("utf-8")).hexdigest()[:12]
    banner_path = _BANNER_DIR / f"banner_notif_{sig}.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    img = Image.new("RGBA", (width, height), (246, 248, 252, 255))
    draw = ImageDraw.Draw(img)

    # Outer border & header bar
    draw.rectangle((0, 0, width - 1, height - 1), outline=(222, 226, 234, 255), width=2)
    draw.rectangle((0, 0, width, 64), fill=(238, 242, 248, 255))
    draw.line((0, 64, width, 64), fill=(222, 226, 234, 255), width=1)

    font_title = _load_font(24, bold=True)
    font_card_title = _load_font(22, bold=True)
    font_card_sub = _load_font(16, bold=False)
    font_badge = _load_font(19, bold=True)

    header_title = (
        f"[{t_clean}] 경기 핵심 알림 실시간 스위치"
        if m_key == "core"
        else f"[{t_clean}] 상황별 맞춤 알림 실시간 스위치"
    )
    draw.text((width // 2, 32), header_title, font=font_title, fill=(22, 24, 29, 255), anchor="mm")

    if m_key == "core":
        cards_meta = [
            ("선발 라인업", "경기 20분 전 발표", bool(s1)),
            ("경기 시작", "팁오프 10분 전", bool(s2)),
            ("경기 종료", "최종 스코어·MVP", bool(s3)),
        ]
    else:
        cards_meta = [
            ("4Q 클러치", "승부처 박빙 접전", bool(s1)),
            ("당일 승부예측", "투표·적중 정산", bool(s2)),
            (f"{t_clean} 전용 알림", "내 응원팀 맞춤", True),
        ]

    logo = _download_image_cached(get_team_logo(t_clean))

    slot_w = width // 3
    for i, (c_title, c_sub, is_on) in enumerate(cards_meta):
        cx = slot_w * i + slot_w // 2
        card_left = cx - 108
        card_right = cx + 108
        card_top = 86
        card_bottom = 372

        # Card box
        border_col = (59, 130, 246, 255) if is_on else (209, 213, 219, 255)
        bg_col = (255, 255, 255, 255) if is_on else (249, 250, 251, 255)
        draw.rounded_rectangle(
            (card_left, card_top, card_right, card_bottom),
            radius=18,
            fill=bg_col,
            outline=border_col,
            width=2,
        )

        # Top emblem / status circle inside card
        circle_y = 148
        circle_r = 40
        draw.ellipse(
            (cx - circle_r, circle_y - circle_r, cx + circle_r, circle_y + circle_r),
            fill=(240, 245, 255, 255) if is_on else (243, 244, 246, 255),
            outline=border_col,
            width=2,
        )
        if logo is not None:
            l_res = logo.resize((62, 62), Image.Resampling.LANCZOS)
            img.paste(l_res, (cx - 31, circle_y - 31), l_res if l_res.mode == "RGBA" else None)

        # Card labels
        draw.text(
            (cx, 224),
            c_title,
            font=font_card_title,
            fill=(17, 24, 39, 255) if is_on else (107, 114, 128, 255),
            anchor="mm",
        )
        draw.text(
            (cx, 258),
            c_sub,
            font=font_card_sub,
            fill=(100, 116, 139, 255),
            anchor="mm",
        )

        # Bottom ON / OFF pill switch
        pill_w, pill_h = 148, 46
        p_left = cx - pill_w // 2
        p_top = 298
        pill_col = (16, 185, 129, 255) if is_on else (156, 163, 175, 255)
        if m_key == "situational" and i == 2:
            pill_col = (37, 99, 235, 255)
            pill_text = f"{t_clean} 설정됨"
        else:
            pill_text = "ON 켜짐" if is_on else "OFF 꺼짐"

        draw.rounded_rectangle(
            (p_left, p_top, p_left + pill_w, p_top + pill_h),
            radius=23,
            fill=pill_col,
        )
        draw.text(
            (cx, p_top + pill_h // 2),
            pill_text,
            font=font_badge,
            fill=(255, 255, 255, 255),
            anchor="mm",
        )

    out_buf = io.BytesIO()
    img.convert("RGB").save(out_buf, format="PNG", optimize=True)
    png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def _new_banner_canvas(
    title: str,
    width: int = 800,
    height: int = 400,
    header_h: int = 64,
    title_size: int = 24,
) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    """Create standard 2:1 banner canvas with outer frame and centered title bar."""
    img = Image.new("RGBA", (width, height), (248, 249, 252, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(222, 226, 234, 255), width=2)
    draw.rectangle((0, 0, width, header_h), fill=(238, 242, 248, 255))
    draw.line((0, header_h, width, header_h), fill=(222, 226, 234, 255), width=1)
    draw.text(
        (width // 2, header_h // 2),
        title,
        font=_load_font(title_size, bold=True),
        fill=(22, 24, 29, 255),
        anchor="mm",
    )
    return img, draw


def _save_banner_png(img: Image.Image, banner_path: Path) -> bytes:
    """Encode banner image as optimized RGB PNG and best-effort cache on disk under a 2-render semaphore."""
    with _RENDER_SEMAPHORE:
        out_buf = io.BytesIO()
        img.convert("RGB").save(out_buf, format="PNG", optimize=True)
        png_bytes = out_buf.getvalue()
    try:
        banner_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def render_single_player_banner_png(
    name: str,
    team: str = "SK",
    pos: str = "F",
    no: str = "",
    pts: float = 0.0,
    reb: float = 0.0,
    ast: float = 0.0,
    width: int = 800,
    height: int = 400,
) -> bytes:
    """Render 2:1 (800x400) uncropped player profile banner with circular portrait and stats."""
    from concurrent.futures import ThreadPoolExecutor

    t_clean = team.strip() if team else "SK"
    sig_str = f"player_v1:{name}:{t_clean}:{pos}:{no}:{pts}:{reb}:{ast}"
    sig = hashlib.md5(sig_str.encode("utf-8")).hexdigest()[:12]
    banner_path = _BANNER_DIR / f"banner_player_{sig}.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    p_url = get_player_photo_url(name)
    t_url = get_team_logo(t_clean)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(_download_image_cached, [u for u in (p_url, t_url) if u]))

    full_t = TEAM_INFO.get(t_clean, {}).get("full_name", f"{t_clean} 농구단")
    num_str = f"#{no} " if no else ""
    img, draw = _new_banner_canvas(f"{full_t}  |  {num_str}{name}", width, height, title_size=23)

    # Left circular portrait (never cropped at top/face) + team crest badge
    cx, cy = 165, 228
    ring_r = 104
    draw.ellipse(
        (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
        fill=(255, 255, 255, 255),
        outline=(210, 218, 232, 255),
        width=4,
    )
    avatar = _make_circular_avatar(_download_image_cached(p_url), diameter=192)
    img.paste(avatar, (cx - 96, cy - 96), avatar)

    t_logo = _download_image_cached(t_url)
    if t_logo:
        draw.ellipse(
            (cx + 46, cy + 44, cx + 106, cy + 104),
            fill=(255, 255, 255, 255),
            outline=(210, 218, 232, 255),
            width=2,
        )
        t_res = t_logo.resize((46, 46), Image.Resampling.LANCZOS)
        img.paste(t_res, (cx + 53, cy + 51), t_res if t_res.mode == "RGBA" else None)

    # Right player headline & stat cards
    draw.text((310, 128), name, font=_load_font(34, bold=True), fill=(17, 24, 39, 255), anchor="lm")
    pos_label = f"포지션 {pos}" if pos else "KBL 선수"
    name_w = min(240, max(110, len(name) * 34 + 18))
    pill_x = 310 + name_w
    draw.rounded_rectangle((pill_x, 108, pill_x + 114, 146), radius=18, fill=(37, 99, 235, 255))
    draw.text((pill_x + 57, 127), pos_label, font=_load_font(17, bold=True), fill=(255, 255, 255, 255), anchor="mm")

    draw.text((310, 174), f"{full_t}  •  2026-2027 시즌 평균 기록", font=_load_font(18, bold=False), fill=(100, 110, 128, 255), anchor="lm")

    stats = [
        ("득점", f"{pts:.1f}", (220, 38, 38, 255)),
        ("리바운드", f"{reb:.1f}", (37, 99, 235, 255)),
        ("어시스트", f"{ast:.1f}", (16, 185, 129, 255)),
    ]
    box_w, gap = 136, 16
    for idx, (lbl, val, accent) in enumerate(stats):
        bx = 310 + idx * (box_w + gap)
        by = 216
        draw.rounded_rectangle(
            (bx, by, bx + box_w, by + 126),
            radius=14,
            fill=(255, 255, 255, 255),
            outline=(218, 224, 234, 255),
            width=2,
        )
        draw.text((bx + box_w // 2, by + 34), lbl, font=_load_font(17, bold=True), fill=(95, 104, 122, 255), anchor="mm")
        draw.text((bx + box_w // 2, by + 84), val, font=_load_font(32, bold=True), fill=accent, anchor="mm")

    return _save_banner_png(img, banner_path)


def render_user_points_banner_png(
    team: str | None = None,
    points: int = 0,
    nickname: str = "",
    width: int = 800,
    height: int = 400,
) -> bytes:
    """Render clean 2:1 (800x400) points & fan-tier banner without logo cropping or emoji tofu."""
    t_clean = team.strip() if (team and team in TEAM_INFO) else ""
    if points >= 1000:
        tier_text = "KBL 레전드"
    elif points >= 500:
        tier_text = "올스타 VIP"
    elif points >= 200:
        tier_text = "베스트5 MVP"
    elif points >= 50:
        tier_text = "주전 식스맨"
    else:
        tier_text = "루키 농구팬"

    sig_str = f"pts_v1:{t_clean}:{points}:{nickname}"
    sig = hashlib.md5(sig_str.encode("utf-8")).hexdigest()[:12]
    banner_path = _BANNER_DIR / f"banner_pts_{sig}.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    full_t = TEAM_INFO.get(t_clean, {}).get("full_name", "KBL 프로농구")
    img, draw = _new_banner_canvas(f"{full_t}  |  승부예측 포인트", width, height, title_size=23)

    # Left circular team crest badge
    cx, cy, r = 165, 228, 94
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(214, 220, 232, 255), width=3)
    logo = _download_image_cached(get_team_logo(t_clean) if t_clean else DEFAULT_SPORTS_LOGO)
    if logo:
        l_res = logo.resize((152, 152), Image.Resampling.LANCZOS)
        img.paste(l_res, (cx - 76, cy - 76), l_res if l_res.mode == "RGBA" else None)

    # Right score & fan tier cards
    clean_nick = re.sub(r"[^\w\s가-힣#·-]", "", nickname or "").strip() or (f"{t_clean} 팬" if t_clean else "KBL 팬")
    draw.text((295, 118), f"랭킹 닉네임  {clean_nick}", font=_load_font(20, bold=True), fill=(82, 92, 110, 255), anchor="lm")

    draw.rounded_rectangle((295, 146, 750, 260), radius=16, fill=(255, 255, 255, 255), outline=(214, 220, 232, 255), width=2)
    draw.text((330, 203), f"{points:,} P", font=_load_font(46, bold=True), fill=(37, 99, 235, 255), anchor="lm")

    draw.rounded_rectangle((558, 178, 728, 228), radius=24, fill=(16, 185, 129, 255))
    draw.text((643, 203), tier_text, font=_load_font(20, bold=True), fill=(255, 255, 255, 255), anchor="mm")

    draw.text((295, 306), "참여 +10P   •   적중 +50P   •   3/5/10연승 추가 보너스", font=_load_font(18, bold=True), fill=(55, 65, 81, 255), anchor="lm")
    draw.text((295, 342), "팬 랭킹 배틀 & 이벤트 응모 포인트 실시간 누적", font=_load_font(16, bold=False), fill=(110, 120, 138, 255), anchor="lm")

    return _save_banner_png(img, banner_path)


def render_region_menu_banner_png(
    menu_type: str,
    region_key: str,
    width: int = 800,
    height: int = 400,
) -> bytes:
    """Render 2:1 (800x400) multi-club banner for '다른팀 뉴스' and '구단별 선수' carousels."""
    from concurrent.futures import ThreadPoolExecutor

    m_type = "players" if menu_type == "players" else "news"
    rk = region_key.lower().strip()
    banner_path = _BANNER_DIR / f"banner_menu_{m_type}_{rk}_v1.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    if m_type == "news":
        region_map: dict[str, tuple[str, list[str], str]] = {
            "capital": ("수도권 구단 뉴스 (SK • KT • 삼성)", ["SK", "KT", "삼성"], "구단 뉴스 보기"),
            "gangwon_gyeonggi": ("경기·강원 구단 뉴스 (DB • 정관장 • 소노)", ["DB", "정관장", "소노"], "구단 뉴스 보기"),
            "yeongnam": ("영남권 구단 뉴스 (LG • KCC • 현대모비스)", ["LG", "KCC", "현대모비스"], "구단 뉴스 보기"),
            "daegu": ("대구 구단 & KBL 전체 뉴스", ["한국가스공사"], "구단 · 전체 뉴스"),
        }
    else:
        region_map = {
            "capital": ("수도권 구단 선수단 (SK • KT • 삼성)", ["SK", "KT", "삼성"], "선수단 보기"),
            "gangwon_gyeonggi": ("경기·강원 구단 선수단 (DB • 정관장 • 소노)", ["DB", "정관장", "소노"], "선수단 보기"),
            "yeongnam": ("영남권 구단 선수단 (LG • KCC • 현대모비스)", ["LG", "KCC", "현대모비스"], "선수단 보기"),
            "daegu": ("대구 구단 & KBL 선수 순위", ["한국가스공사"], "선수단 · 순위"),
        }

    title, teams, action_txt = region_map.get(rk, ("KBL 구단 둘러보기", ["SK", "DB", "LG"], "바로가기"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(_download_image_cached, [get_team_logo(t) for t in teams]))

    img, draw = _new_banner_canvas(title, width, height, title_size=23)
    font_name = _load_font(22, bold=True)
    font_sub = _load_font(16, bold=False)

    n = len(teams)
    slot_w = width // n
    for i, t in enumerate(teams):
        cx = slot_w * i + slot_w // 2
        cy = 185 if n > 1 else 190
        r = 72 if n > 1 else 96
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=(220, 225, 235, 255), width=3)

        logo = _download_image_cached(get_team_logo(t))
        if logo:
            sz = 118 if n > 1 else 164
            l_res = logo.resize((sz, sz), Image.Resampling.LANCZOS)
            img.paste(l_res, (cx - sz // 2, cy - sz // 2), l_res if l_res.mode == "RGBA" else None)

        draw.text((cx, 298 if n > 1 else 322), t, font=font_name, fill=(22, 24, 29, 255), anchor="mm")
        draw.text((cx, 336 if n > 1 else 360), action_txt, font=font_sub, fill=(24, 119, 242, 255), anchor="mm")

    return _save_banner_png(img, banner_path)


def render_game_recap_banner_png(
    home: str,
    away: str,
    home_score: int = 0,
    away_score: int = 0,
    width: int = 800,
    height: int = 400,
) -> bytes:
    """Render compact 2:1 (800x400) match recap scoreboard banner with both team emblems."""
    from concurrent.futures import ThreadPoolExecutor

    h_clean = home.strip() or "HOME"
    a_clean = away.strip() or "AWAY"
    sig_str = f"recap_v1:{h_clean}:{a_clean}:{home_score}:{away_score}"
    sig = hashlib.md5(sig_str.encode("utf-8")).hexdigest()[:12]
    banner_path = _BANNER_DIR / f"banner_recap_{sig}.png"
    if banner_path.exists():
        try:
            return banner_path.read_bytes()
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(_download_image_cached, [get_team_logo(h_clean), get_team_logo(a_clean)]))

    img, draw = _new_banner_canvas(f"{h_clean} vs {a_clean}  |  경기 요약 리캡", width, height, title_size=23)

    home_won = home_score >= away_score
    sides = [
        (165, h_clean, home_won),
        (635, a_clean, not home_won),
    ]
    for cx, t_name, is_winner in sides:
        cy, r = 190, 78
        border_col = (37, 99, 235, 255) if is_winner else (218, 224, 234, 255)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 255), outline=border_col, width=4 if is_winner else 2)
        logo = _download_image_cached(get_team_logo(t_name))
        if logo:
            l_res = logo.resize((126, 126), Image.Resampling.LANCZOS)
            img.paste(l_res, (cx - 63, cy - 63), l_res if l_res.mode == "RGBA" else None)

        draw.text((cx, 300), t_name, font=_load_font(22, bold=True), fill=(22, 24, 29, 255), anchor="mm")
        if is_winner:
            draw.rounded_rectangle((cx - 42, 326, cx + 42, 356), radius=15, fill=(37, 99, 235, 255))
            draw.text((cx, 341), "WIN", font=_load_font(16, bold=True), fill=(255, 255, 255, 255), anchor="mm")
        else:
            draw.text((cx, 341), "FULL TIME", font=_load_font(15, bold=False), fill=(120, 128, 142, 255), anchor="mm")

    # Center final scoreboard
    draw.rounded_rectangle((285, 138, 515, 258), radius=18, fill=(255, 255, 255, 255), outline=(218, 224, 234, 255), width=2)
    draw.text((400, 166), "FINAL SCORE", font=_load_font(15, bold=True), fill=(100, 110, 128, 255), anchor="mm")
    draw.text((400, 214), f"{home_score} : {away_score}", font=_load_font(44, bold=True), fill=(17, 24, 39, 255), anchor="mm")
    winner_name = h_clean if home_won else a_clean
    diff = abs(home_score - away_score)
    draw.text((400, 316), f"{winner_name} {diff}점 차 승리", font=_load_font(20, bold=True), fill=(37, 99, 235, 255), anchor="mm")

    return _save_banner_png(img, banner_path)
