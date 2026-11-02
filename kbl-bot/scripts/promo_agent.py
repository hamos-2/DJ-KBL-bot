#!/usr/bin/env python3
"""
KBL 프로농구 카카오톡 챗봇 (KBL봇, _pxgeWX) 홍보 에이전트 스크립트.

기능:
1. 오늘의 KBL 경기 일정/결과를 바탕으로 디시인사이드 국내 농구 갤러리(id=basketball) 맞춤형 홍보 원고 생성
2. Chrome CDP(http://127.0.0.1:9222)를 통해 디시인사이드 농구 갤러리에 자동 글쓰기 및 Turnstile 통과 후 게시물 URL 반환

사용법:
  # 원고 미리보기 (Dry-run)
  python3 scripts/promo_agent.py --dry-run

  # 디시인사이드 농구 갤러리에 홍보 게시글 등록
  python3 scripts/promo_agent.py --post
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import websockets

# Allow importing kbl-bot modules when executed from repo root or kbl-bot/
_BOT_ROOT = Path(__file__).resolve().parent.parent
if str(_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOT_ROOT))

from core.season import get_current_season  # noqa: E402
from services.content.kbl_data import TEAM_LINEUPS  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
KAKAO_CHAT_URL = "https://pf.kakao.com/_pxgeWX/chat"
KAKAO_PROFILE_URL = "https://pf.kakao.com/_pxgeWX"
CDP_URL = "http://127.0.0.1:9222"
_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]


def fetch_live_matchup_summary() -> str:
    """
    Fetch today's and the next upcoming KBL games from Daum Sports API
    so the promotional post always cites real, up-to-date matchups and scores.
    """
    now_kst = datetime.now(KST)
    from_str = now_kst.strftime("%Y%m%d")
    to_str = (now_kst + timedelta(days=5)).strftime("%Y%m%d")
    url = (
        f"https://sports.daum.net/api/arms/SPORTS_GAME_LIST"
        f"?leagueCode=kbl&fromDate={from_str}&toDate={to_str}&pageSize=50"
    )
    try:
        resp = httpx.get(url, verify=False, timeout=5.0)
        games = resp.json().get("document", {}).get("list", [])
        if games:
            dates_seen: list[str] = []
            for g in games:
                sd = str(g.get("startDate", ""))
                if sd and sd not in dates_seen:
                    dates_seen.append(sd)
            segments: list[str] = []
            for target_date in dates_seen[:2]:
                day_games = [g for g in games if str(g.get("startDate")) == target_date]
                dt = datetime.strptime(target_date, "%Y%m%d")
                wd = _WEEKDAYS_KO[dt.weekday()]
                date_label = f"{dt.month}/{dt.day}({wd})"
                pairs = []
                for g in day_games[:4]:
                    st = str(g.get("startTime", "1900"))
                    t_str = f"{st[:2]}:{st[2:4]}" if len(st) >= 4 else "19:00"
                    home_obj = (g.get("home") or {}).get("team") or {}
                    away_obj = (g.get("away") or {}).get("team") or {}
                    home = home_obj.get("shortNameKo") or home_obj.get("shortName") or ""
                    away = away_obj.get("shortNameKo") or away_obj.get("shortName") or ""
                    score_h = (g.get("home") or {}).get("result")
                    score_a = (g.get("away") or {}).get("result")
                    status = g.get("gameStatus", "")
                    if status == "END" and score_h is not None and score_a is not None:
                        pairs.append(f"{home} {score_h}:{score_a} {away}(종료)")
                    else:
                        pairs.append(f"{t_str} {home} vs {away}")
                if pairs:
                    segments.append(f"{date_label} {', '.join(pairs)}")
            if segments:
                return " / ".join(segments)
    except Exception:
        pass
    return "2026-2027 시즌 오늘/주간 KBL 주요 매치업"


def build_roster_highlight_line() -> str:
    """Build a concise 2026-2027 roster summary string from verified TEAM_LINEUPS."""
    db_info = TEAM_LINEUPS.get("DB", {})
    jkj_info = TEAM_LINEUPS.get("정관장", {})
    kt_info = TEAM_LINEUPS.get("KT", {})
    sk_info = TEAM_LINEUPS.get("SK", {})
    return (
        f"2026-27 시즌 최신 로스터 완벽 반영 "
        f"(DB {db_info.get('head_coach', '이규섭')} 감독·알바노·엘런슨 / "
        f"정관장 {jkj_info.get('head_coach', '유도훈')} 감독·오브라이언트·아반도 / "
        f"KT {kt_info.get('head_coach', '문경은')} 감독·김선형·윌리엄스 / "
        f"SK {sk_info.get('head_coach', '전희철')} 감독·자밀 워니·김낙현 등 10개 구단 전수 업데이트)"
    )


def generate_promo_post(gallery_id: str = "basketball", custom_title: str | None = None) -> tuple[str, str]:
    """Generate a DC Inside-native, community-friendly promotional post tailored to the gallery."""
    season = get_current_season()
    matchup_line = fetch_live_matchup_summary()
    roster_line = build_roster_highlight_line()

    if gallery_id == "nba":
        title = custom_title or f"느바 보면서 {season} 국농 라인업·순위도 카톡으로 바로 보는 봇 공유 (링크X)"
        html_body = f"""
        <p>느바 보면서 국농도 챙겨보는데 야구봇처럼 카톡에서 구단별 라인업이나 실시간 점수, 순위 확인할 수 있는 게 없길래 직접 <b>카톡 KBL봇</b> 만들어서 {season} 시즌 최신 로스터까지 싹 업데이트했음.</p>
        <p><br></p>
        <p>🏀 <b>{matchup_line}</b> 같은 거 카톡에서 원클릭으로 바로 뜨고, <b>{roster_line}</b>까지 모두 반영되어 있음.</p>
        <p><br></p>
        <p>📌 <b>어떻게 쓰냐:</b></p>
        <p>카톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가하고 채팅 들어가면 상담원 연결 없이 하단 6칸 메뉴 바로 뜸.</p>
        <p>(디시 링크 필터 때문에 링크는 안 걸음. 카톡 검색창에 <b>KBL봇</b> 치면 바로 나옴)</p>
        <p><br></p>
        <p>🏀 <b>주요 기능 요약 ({season} 최신판):</b></p>
        <p>• <b>구단별 라인업 다이렉트 조회</b> : 채팅창에 <b>'DB 라인업'</b>, <b>'정관장 라인업'</b>, <b>'KT 라인업'</b> 치면 신임 감독·외국인 1·2옵션·아시아쿼터·베스트 5·식스맨 즉시 출력</p>
        <p>• <b>⭐ 관심선수 원클릭 등록</b> : 하단 '관심선수' 탭이나 '허웅', '김선형', '이선 알바노', '유기상' 입력 시 원클릭 등록 & 26-27 시즌 평균 스탯 1초 확인</p>
        <p>• <b>실시간 점수 & 4Q 클러치 알림</b> : 쿼터별 라이브 스코어, 4쿼터 2분 이내 5점 차 접전(클러치) 하이라이트, 종료 후 3초 요약 리캡('요약')</p>
        <p>• <b>승부예측 연승 보너스 & 월간 랭킹</b> : 승리팀 적중 시 +50P, 3연승/5연승 스트릭 보너스 및 <b>'승부예측 랭킹'</b> 월간 리더보드 경쟁</p>
        <p>• <b>#팀 vs 팀 매치업 검색</b> : '#KT vs LG', '#SK vs KCC' 치면 최근 맞대결 전적 및 예정 경기 바로 출력</p>
        <p>• <b>팀순위 / 선수순위 / 주요장면</b> : 6강 PO 마지노선 순위표, 득점·어시·리바 TOP 5, 경기 직후 공식 하이라이트 영상</p>
        <p><br></p>
        <p>광고나 유료 결제 일절 없고 나 편하려고 만든 거니까 느바 보다가 국농 체크할 때 편하게 써봐라.</p>
        <p>버그나 필요한 기능 있으면 댓글 남겨주면 바로 반영해봄.</p>
        """.strip()
    elif gallery_id in ("lotto_new2", "proto"):
        title = custom_title or f"국농(KBL) 26-27 구단별 라인업·실시간 점수 카톡으로 보는 봇 (링크X)"
        html_body = f"""
        <p>국농 분석하거나 경기 실시간으로 챙겨볼 때 포털 일일이 안 켜고 카톡에서 바로 확인할 수 있게 <b>KBL봇</b> ({season} 시즌 최신 로스터 반영본) 만들어서 공유함.</p>
        <p><br></p>
        <p>🏀 <b>{matchup_line}</b> 및 <b>{roster_line}</b> 완료.</p>
        <p><br></p>
        <p>📌 <b>분석 및 실시간 확인 핵심 기능:</b></p>
        <p>• <b>구단별 베스트 5 & 용병/아쿼 즉시 조회</b> : 채팅창에 <b>'DB 라인업'</b>, <b>'정관장 라인업'</b>, <b>'삼성 라인업'</b> 치면 26-27 감독·1·2옵션 외인·아시아쿼터·선발 베스트 5·식스맨 한눈에 출력 + 경기 20분 전 확정 스타팅 공개</p>
        <p>• <b>실시간 쿼터별 점수 & 4Q 클러치 현황</b> : 1Q~4Q·연장 쿼터별 스코어 및 4쿼터 막판 접전 상황 실시간 확인</p>
        <p>• <b>⭐ 관심선수 스탯 조회</b> : '허웅', '김선형', '알바노', '워니', '칸터' 등 선수 이름만 치면 26-27 시즌 평균 득점/리바/어시/3점슛 즉시 출력 및 원클릭 관심선수 등록</p>
        <p>• <b>#팀 vs 팀 맞대결 검색</b> : 채팅창에 '#KT vs LG', '#DB vs 정관장' 치면 맞대결 결과 및 일정 바로 출력</p>
        <p>• <b>팀순위 & 3초 경기 요약('요약')</b> : 10개 구단 승률·게임차·연승 흐름 및 종료 경기 핵심 요약 카드</p>
        <p><br></p>
        <p>📌 <b>이용 방법:</b></p>
        <p>카카오톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색 → 채널 추가 후 채팅방 입장 시 상담원 연결 없이 즉시 메뉴 사용 가능.</p>
        <p>(디시 링크 검열 때문에 링크는 안 넣음. 카톡 검색창에 치면 바로 나옴)</p>
        <p><br></p>
        <p>로그인/광고/유료 일절 없음. 국농 라인업이랑 쿼터 점수 체크할 때 요긴하게 써라.</p>
        """.strip()
    elif gallery_id == "wkbl":
        title = custom_title or f"야구봇처럼 카톡에서 농구 26-27 라인업·순위 바로 보는 봇 공유 (링크X)"
        html_body = f"""
        <p>프로야구봇처럼 카톡에서 농구 경기 일정이나 구단별 라인업, 실시간 스코어, 순위를 바로 확인할 수 있는 <b>카톡 KBL봇</b> ({season} 시즌 최신판) 만들어서 공유함.</p>
        <p><br></p>
        <p>🏀 <b>{matchup_line}</b>부터 10개 구단 신임 감독·외인·아시아쿼터·베스트 5 로스터까지 모두 최신화되어 있음.</p>
        <p><br></p>
        <p>📌 <b>어떻게 쓰냐:</b></p>
        <p>카톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가하고 채팅 들어가면 상담원 연결 없이 하단 6칸 고정 메뉴 바로 뜸.</p>
        <p>(디시 링크 필터 때문에 링크는 안 걸었으니 카톡 검색창에 <b>KBL봇</b> 치면 바로 나옴)</p>
        <p><br></p>
        <p>🏀 <b>기능 요약:</b></p>
        <p>• <b>선발 라인업 & 구단별 라인업</b> : '라인업' 또는 'DB 라인업', '정관장 라인업' 입력 시 감독·외인·아쿼·베스트 5 즉시 확인</p>
        <p>• <b>⭐ 관심선수 원클릭 등록</b> : '관심선수' 메뉴에서 좋아하는 선수 원클릭 등록 & 시즌 평균 득점·리바·어시 즉시 조회</p>
        <p>• <b>실시간 점수 & 3초 경기 요약</b> : 쿼터별 라이브 스코어, 4Q 클러치 알림, 경기 종료 후 '요약' 리캡 카드 및 하이라이트 직행</p>
        <p>• <b>승부예측 & 월간 예측왕 랭킹</b> : 매일 승리팀 투표하고 적중(+50P)·연승 보너스 받아 <b>'승부예측 랭킹'</b> 리더보드 경쟁</p>
        <p>• <b>일정 / 팀순위 / 선수순위 / 뉴스</b> : 주간 일정표, 6강 PO 마지노선 순위표, 개인 부문별 TOP 5</p>
        <p><br></p>
        <p>광고나 유료 결제 일절 없고 나 쓰려고 만든 거니까 농구 챙겨볼 때 편하게 써봐라.</p>
        """.strip()
    else:
        title = custom_title or f"카톡 KBL봇 26-27 최신 로스터·구단별 라인업·관심선수 업데이트 공유 (링크X)"
        html_body = f"""
        <p>프로야구봇은 카톡에 있는데 KBL은 없어서 일정이나 라인업, 점수, 순위 확인할 때마다 포털 뒤적거리기 귀찮아서 직접 만들어 운영 중인 <b>카톡 KBL봇</b>에 <b>{season} 시즌 10개 구단 최신 로스터 및 신규 기능</b>을 대거 업데이트했음.</p>
        <p><br></p>
        <p>🏀 <b>{matchup_line}</b> 실시간 확인 가능하며, <b>{roster_line}</b>까지 100% 반영 완료함.</p>
        <p><br></p>
        <p>📌 <b>어떻게 쓰냐:</b></p>
        <p>카톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가하고 채팅 들어가면 상담원 연결 없이 즉시 챗봇 메뉴와 하단 6칸 고정 탭이 바로 뜸.</p>
        <p>(디시 링크 필터 때문에 링크는 안 걸었으니 카톡 검색창에 <b>KBL봇</b> 치면 바로 나옴)</p>
        <p><br></p>
        <p>🏀 <b>이번에 업데이트된 핵심 기능 ({season} 시즌 기준):</b></p>
        <p>• <b>구단별 라인업 다이렉트 조회</b> : 채팅창에 <b>'DB 라인업'</b>, <b>'정관장 라인업'</b>, <b>'삼성 라인업'</b>, <b>'KT 라인업'</b> 치면 26-27 시즌 감독·1·2옵션 외국인 용병·아시아쿼터·공식 베스트 5·식스맨 명단이 카드 한 장에 바로 출력됨 (경기 시작 20분 전 본부석 확정 선발 자동 전환)</p>
        <p>• <b>⭐ 관심선수 원클릭 등록 & 스탯 조회</b> : 하단 <b>'⭐ 관심선수'</b> 탭을 누르거나 채팅창에 '허웅', '김선형', '이선 알바노', '유기상', '케렘 칸터' 등 선수 이름을 치면 26-27 시즌 실제 평균 득점/리바/어시/3점슛 확인 및 원터치 관심선수 등록/해제 가능</p>
        <p>• <b>실시간 쿼터 스코어 & 4Q 클러치 알림</b> : 1Q~4Q·연장 쿼터별 실시간 점수판 + 4쿼터 종료 2분 전 5점 차 이내 접전 시 🔥클러치 상황 자동 하이라이트</p>
        <p>• <b>3초 경기 요약 리캡 & 하이라이트 영상</b> : 경기 끝나고 <b>'요약'</b> 또는 <b>'주요장면'</b> 누르면 최종 스코어·수훈 선수 요약과 함께 공식 하이라이트 VOD로 원터치 이동</p>
        <p>• <b>승부예측 연승 보너스 & 월간 예측왕 랭킹</b> : 경기 승리팀 적중 시 +50P, 3연승(+30P)·5연승(+50P) 추가 보너스 및 <b>'승부예측 랭킹'</b> 월간 TOP 리더보드</p>
        <p>• <b>10개 구단 맞춤 뉴스 & #팀 vs 팀 검색</b> : 내 응원팀 뉴스/일정 맞춤 브리핑 및 '#KT vs LG', '#SK' 맞대결 전적 즉시 검색</p>
        <p><br></p>
        <p>광고나 유료 결제 같은 거 일절 없고 순수하게 농구 편하게 보려고 만든 봇이니까 농갤러들 직관 가거나 중계 볼 때 편하게 써봐라.</p>
        <p>써보고 추가했으면 하는 기능이나 피드백 댓글로 남겨주면 바로 반영해봄.</p>
        """.strip()
    return title, html_body


async def send_cdp_cmd(ws, msg_id: int, method: str, params: dict | None = None) -> dict:
    """Send CDP command and wait specifically for response with matching id."""
    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
        resp = json.loads(raw)
        if resp.get("id") == msg_id:
            return resp


async def post_to_dcinside(gallery_id: str, title: str, html_body: str, password: str = "kbl2026!") -> str:
    """Post the promotional article to DC Inside gallery via Chrome CDP."""
    is_minor = gallery_id in ("basketballkorea",) or "mgallery" in gallery_id
    base_prefix = "mgallery/board" if is_minor else "board"
    write_url = f"https://gall.dcinside.com/{base_prefix}/write/?id={gallery_id}"
    list_url = f"https://gall.dcinside.com/{base_prefix}/lists/?id={gallery_id}"

    req = urllib.request.Request(f"{CDP_URL}/json/new?{write_url}", method="PUT")
    tab = json.loads(urllib.request.urlopen(req).read().decode())
    tid = tab["id"]
    ws_url = tab["webSocketDebuggerUrl"]
    urllib.request.urlopen(f"{CDP_URL}/json/activate/{tid}")
    await asyncio.sleep(4.0)

    try:
        async with websockets.connect(ws_url, max_size=50_000_000) as ws:
            fill_js = f"""
            (() => {{
                window.__alerts = [];
                window.alert = (m) => {{ window.__alerts.push(m); }};
                window.confirm = (m) => {{ window.__alerts.push("CONFIRM:" + m); return true; }};

                const pw = document.querySelector("#password");
                if (pw) {{
                    pw.value = {json.dumps(password)};
                    pw.dispatchEvent(new Event("input", {{bubbles: true}}));
                }}
                const subj = document.querySelector("#subject");
                if (subj) {{
                    subj.value = {json.dumps(title)};
                    subj.dispatchEvent(new Event("input", {{bubbles: true}}));
                }}
                const htmlContent = {json.dumps(html_body)};
                const editor = document.querySelector(".note-editable");
                if (editor) {{
                    editor.innerHTML = htmlContent;
                    editor.dispatchEvent(new Event("input", {{bubbles: true}}));
                    editor.dispatchEvent(new Event("keyup", {{bubbles: true}}));
                }}
                if (window.jQuery && jQuery("#memo").length) {{
                    try {{ jQuery("#memo").summernote("code", htmlContent); }} catch (e) {{}}
                }}
                const cfInput = document.querySelector("[name=cf-turnstile-response]");
                const parent = cfInput ? cfInput.parentElement : null;
                if (parent) parent.scrollIntoView({{block: "center"}});
                const r = parent ? parent.getBoundingClientRect() : null;
                return JSON.stringify({{
                    coords: r ? {{ top: r.top, left: r.left, right: r.right, bottom: r.bottom }} : null,
                    token: cfInput?.value || ""
                }});
            }})()
            """
            resp = await send_cdp_cmd(ws, 1, "Runtime.evaluate", {"expression": fill_js, "returnByValue": True})
            info = json.loads(resp["result"]["result"]["value"])
            print(f"[{gallery_id}] Form filled. Token present: {bool(info.get('token'))}")

            # 2. Click Cloudflare Turnstile checkbox if token is not yet populated
            if not info.get("token") and info.get("coords"):
                cx = int(info["coords"]["right"] - 300 + 28)
                cy = int(info["coords"]["top"] + 33)
                points = [(cx, cy), (748, 677), (750, 687), (750, 692)]
                token_val = ""
                for px, py in points:
                    print(f"[{gallery_id}] Clicking Turnstile at ({px}, {py})...")
                    for idx, ev_type in enumerate(("mouseMoved", "mousePressed", "mouseReleased"), start=10):
                        params = {"type": ev_type, "x": px, "y": py}
                        if ev_type != "mouseMoved":
                            params["button"] = "left"
                            params["clickCount"] = 1
                        await send_cdp_cmd(ws, idx, "Input.dispatchMouseEvent", params)

                    for _ in range(6):
                        await asyncio.sleep(0.6)
                        check_resp = await send_cdp_cmd(ws, 20, "Runtime.evaluate", {
                            "expression": 'document.querySelector("[name=cf-turnstile-response]")?.value || ""',
                            "returnByValue": True,
                        })
                        token_val = check_resp.get("result", {}).get("result", {}).get("value", "")
                        if token_val:
                            print(f"[{gallery_id}] Turnstile solved (len={len(token_val)})")
                            break
                    if token_val:
                        break
                else:
                    print(f"[{gallery_id}] Warning: Turnstile token not acquired")

            # 3. Trigger write button anti-bot interaction counters and submit form
            submit_js = """
            (async () => {
                const btn = document.querySelector("#write_wrap button.write");
                for (let i = 0; i < 5; i++) {
                    jQuery(btn).trigger("keydown");
                    jQuery(btn).trigger("mousedown");
                    jQuery(btn).trigger("contextmenu");
                }
                btn.click();
                await new Promise(r => setTimeout(r, 4500));
                return JSON.stringify({url: location.href, alerts: window.__alerts});
            })()
            """
            try:
                sub_res = await send_cdp_cmd(ws, 99, "Runtime.evaluate", {
                    "expression": submit_js,
                    "awaitPromise": True,
                    "returnByValue": True,
                })
                print(f"[{gallery_id}] Submit response:", sub_res.get("result", {}).get("result", {}).get("value"))
            except Exception as e:
                print(f"[{gallery_id}] Submit wait exception:", e)
    finally:
        try:
            urllib.request.urlopen(f"{CDP_URL}/json/close/{tid}")
        except Exception:
            pass

    await asyncio.sleep(3.0)
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = httpx.get(list_url, headers=headers, verify=False, timeout=10.0)
    matches = re.findall(
        r'<tr[^>]*class="ub-content[^"]*"[^>]*>.*?<td class="gall_num">(\d+)</td>.*?<a[^>]*>(.*?)</a>',
        r.text,
        re.S,
    )
    for num, raw_tit in matches[:15]:
        clean_tit = re.sub(r"<[^>]+>", "", raw_tit).strip()
        if (title[:12] in clean_tit) or ("KBL" in clean_tit and "봇" in clean_tit) or ("야구봇" in clean_tit):
            return f"https://gall.dcinside.com/{base_prefix}/view/?id={gallery_id}&no={num}"
    return list_url


def main() -> None:
    parser = argparse.ArgumentParser(description="KBL 프로농구봇 홍보 에이전트")
    parser.add_argument("--gallery", type=str, default="nba", help="대상 디시 갤러리 ID (nba, lotto_new2, basketball, wkbl)")
    parser.add_argument("--title", type=str, default=None, help="커스텀 게시글 제목")
    parser.add_argument("--password", type=str, default="kbl2026!", help="비회원 게시글 비밀번호")
    parser.add_argument("--dry-run", action="store_true", help="게시하지 않고 원고만 출력")
    parser.add_argument("--post", action="store_true", help="디시인사이드 갤러리에 즉시 게시")
    args = parser.parse_args()

    title, body = generate_promo_post(gallery_id=args.gallery, custom_title=args.title)
    if args.dry_run or not args.post:
        print(f"=== [KBL봇 홍보 에이전트 원고 미리보기 - {args.gallery}] ===")
        print("제목:", title)
        print("본문 HTML:\n", body)
        return

    url = asyncio.run(post_to_dcinside(gallery_id=args.gallery, title=title, html_body=body, password=args.password))
    print(f"[{args.gallery}] 게시 완료 URL:", url)


if __name__ == "__main__":
    main()
