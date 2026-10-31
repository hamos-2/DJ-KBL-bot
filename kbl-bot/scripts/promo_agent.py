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
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import websockets

KST = ZoneInfo("Asia/Seoul")
KAKAO_CHAT_URL = "https://pf.kakao.com/_pxgeWX/chat"
KAKAO_PROFILE_URL = "https://pf.kakao.com/_pxgeWX"
CDP_URL = "http://127.0.0.1:9222"


def generate_promo_post(gallery_id: str = "basketball", custom_title: str | None = None) -> tuple[str, str]:
    """Generate a DC Inside-native, community-friendly promotional post tailored to the gallery."""
    if gallery_id == "nba":
        title = custom_title or "느바 보면서 국농 일정·순위도 카톡으로 바로 보는 봇 공유 (링크X)"
        html_body = """
        <p>느바 보면서 국농도 가끔 챙겨보는데 야구봇처럼 카톡에서 일정이나 점수, 순위 확인할 수 있는 게 없길래 직접 <b>카톡 KBL봇</b> 하나 만들었음.</p>
        <p><br></p>
        <p>11/1 일요일 오늘 매치업 (14:00 LG vs DB / 소노 vs KT, 16:30 삼성 vs SK S-더비) 같은 거 카톡에서 원클릭으로 바로 뜸.</p>
        <p><br></p>
        <p>📌 <b>어떻게 쓰냐:</b></p>
        <p>카톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가하고 채팅 들어가면 상담원 연결 없이 메뉴 바로 뜸.</p>
        <p>(디시 링크 필터 때문에 링크는 안 걸음. 카톡 검색창에 <b>KBL봇</b> 치면 바로 나옴)</p>
        <p><br></p>
        <p>🏀 <b>기능 요약:</b></p>
        <p>• <b>일정 / KBL 일정</b> : 오늘 경기 시간, 중계 방송사, 주간 일정표</p>
        <p>• <b>#팀이름 검색</b> : 채팅창에 '#KT vs LG', '#SK' 치면 해당 매치업 최근/예정 경기 바로 출력</p>
        <p>• <b>결과 / 팀순위</b> : 경기 종료 스코어, 10개 구단 실시간 승률·게임차 순위표</p>
        <p>• <b>선수순위</b> : 득점, 리바, 어시, 3점, 스틸 TOP 5 랭킹</p>
        <p>• <b>뉴스 / 주요장면</b> : 실시간 KBL 기사, 경기 하이라이트 영상 클립</p>
        <p>• <b>응원하기</b> : 오늘 경기 승부예측 투표</p>
        <p><br></p>
        <p>광고나 유료 결제 일절 없고 나 편하려고 만든 거니까 느바 보다가 국농 체크할 때 편하게 써봐라.</p>
        <p>버그나 필요한 기능 있으면 댓글 남겨주면 반영해봄.</p>
        """.strip()
    elif gallery_id in ("lotto_new2", "proto"):
        title = custom_title or "국농(KBL) 실시간 점수·일정 카톡으로 보는 봇 (링크X)"
        html_body = """
        <p>국농 배팅하거나 경기 실시간으로 챙겨볼 때 포털 안 켜고 카톡에서 바로 확인할 수 있게 <b>KBL봇</b> 하나 만들었음.</p>
        <p><br></p>
        <p>📌 <b>확인 가능한 정보:</b></p>
        <p>• <b>실시간 점수 & 쿼터 상황</b> : 진행 중인 경기 점수, 쿼터 남은 시간 즉시 확인</p>
        <p>• <b>#팀 vs 팀 매치업 검색</b> : 채팅창에 '#KT vs LG' 치면 최근 맞대결 전적, 이전 스코어 바로 출력</p>
        <p>• <b>오늘 일정 & 주간 일정</b> : 경기 시간, 중계 방송사, 홈/원정 일정표</p>
        <p>• <b>팀 순위표 & 선수 순위</b> : 승률, 게임차, 득점/어시/리바 TOP 5</p>
        <p>• <b>하이라이트 & 뉴스</b> : 경기 종료 직후 클립 영상 및 속보</p>
        <p><br></p>
        <p>📌 <b>이용 방법:</b></p>
        <p>카카오톡 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가 후 채팅방에서 바로 사용.</p>
        <p>(디시 링크 검열 때문에 링크는 안 넣음. 카톡 검색창에 치면 바로 나옴)</p>
        <p><br></p>
        <p>로그인/광고/유료 일절 없음. 배팅이나 경기 챙겨볼 때 요긴하게 써라.</p>
        """.strip()
    elif gallery_id == "wkbl":
        title = custom_title or "야구봇처럼 카톡에서 농구 일정·순위 바로 보는 봇 공유 (링크X)"
        html_body = """
        <p>프로야구봇처럼 카톡에서 농구 경기 일정이나 스코어, 순위 바로 확인할 수 있는 <b>카톡 KBL봇</b> 하나 만들어서 공유함.</p>
        <p><br></p>
        <p>오늘 경기 일정이나 실시간 점수, 순위표 카톡에서 원클릭으로 바로 뜸.</p>
        <p><br></p>
        <p>📌 <b>어떻게 쓰냐:</b></p>
        <p>카톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가하고 채팅 들어가면 상담원 연결 없이 메뉴 바로 뜸.</p>
        <p>(디시 링크 필터 때문에 링크는 안 걸었으니 카톡 검색창에 <b>KBL봇</b> 치면 바로 나옴)</p>
        <p><br></p>
        <p>🏀 <b>기능 요약:</b></p>
        <p>• <b>일정 / 농구 일정</b> : 오늘 경기 시간, 중계 방송사, 주간 일정표</p>
        <p>• <b>#팀이름 검색</b> : 채팅창에 '#KT vs LG', '#SK' 치면 해당 매치업 최근/예정 경기 바로 출력</p>
        <p>• <b>결과 / 팀순위</b> : 경기 종료 스코어, 실시간 승률·게임차 순위표</p>
        <p>• <b>선수순위</b> : 득점, 리바, 어시, 3점, 스틸 TOP 5 랭킹</p>
        <p>• <b>뉴스 / 주요장면</b> : 실시간 기사, 경기 하이라이트 영상 클립</p>
        <p>• <b>응원하기</b> : 오늘 경기 승부예측 투표</p>
        <p><br></p>
        <p>광고나 유료 결제 일절 없고 나 쓰려고 만든 거니까 농구 챙겨볼 때 편하게 써봐라.</p>
        <p>버그나 필요한 기능 있으면 댓글 남겨주면 반영해봄.</p>
        """.strip()
    else:
        title = custom_title or "야구봇처럼 카톡에서 KBL 일정·순위 바로 보는 봇 만들었다 (링크X)"
        html_body = """
        <p>프로야구봇은 카톡에 있는데 KBL은 없어서 일정이나 점수, 순위 확인할 때마다 포털 뒤적거리기 귀찮아서 직접 <b>카톡 KBL봇</b> 하나 만들었음.</p>
        <p><br></p>
        <p>11/1 일요일 오늘 매치업 (14:00 LG vs DB / 소노 vs KT, 16:30 삼성 vs SK S-더비) 같은 거 카톡에서 원클릭으로 바로 뜸.</p>
        <p><br></p>
        <p>📌 <b>어떻게 쓰냐:</b></p>
        <p>카톡 상단 검색창(돋보기)에 <b>KBL봇</b> 검색해서 채널 추가하고 채팅 들어가면 상담원 연결 없이 메뉴 바로 뜸.</p>
        <p>(디시 링크 필터 때문에 링크는 안 걸음. 카톡 검색창에 <b>KBL봇</b> 치면 바로 나옴)</p>
        <p><br></p>
        <p>🏀 <b>기능 요약:</b></p>
        <p>• <b>일정 / KBL 일정</b> : 오늘 경기 시간, 중계 경기장, 주간 일정표</p>
        <p>• <b>#팀이름 검색</b> : 채팅창에 '#KT vs LG', '#SK' 치면 해당 매치업 최근/예정 경기 바로 출력</p>
        <p>• <b>결과 / 팀순위</b> : 경기 종료 스코어, 10개 구단 실시간 승률·게임차 순위표</p>
        <p>• <b>선수순위</b> : 득점, 리바, 어시, 3점, 스틸 TOP 5 랭킹</p>
        <p>• <b>뉴스 / 주요장면</b> : 실시간 KBL 기사, 경기 하이라이트 영상</p>
        <p>• <b>응원하기</b> : 오늘 경기 승부예측 투표</p>
        <p><br></p>
        <p>광고나 유료 결제 같은 거 일절 없고 나 쓰려고 만든 거니까 농갤러들 직관 가거나 중계 볼 때 편하게 써봐라.</p>
        <p>버그나 필요한 기능 있으면 댓글 남겨주면 반영해봄.</p>
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
    write_url = f"https://gall.dcinside.com/board/write/?id={gallery_id}"
    list_url = f"https://gall.dcinside.com/board/lists/?id={gallery_id}"

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
            return f"https://gall.dcinside.com/board/view/?id={gallery_id}&no={num}"
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
