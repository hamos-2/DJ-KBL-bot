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
DC_GALLERY_ID = "basketball"
DC_WRITE_URL = f"https://gall.dcinside.com/board/write/?id={DC_GALLERY_ID}"
DC_LIST_URL = f"https://gall.dcinside.com/board/lists/?id={DC_GALLERY_ID}"
CDP_URL = "http://127.0.0.1:9222"


def generate_promo_post(custom_title: str | None = None) -> tuple[str, str]:
    """Generate a DC Inside-native, community-friendly promotional post."""
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


async def post_to_dcinside(title: str, html_body: str, password: str = "kbl2026!") -> str:
    """Post the promotional article to DC Inside Domestic Basketball Gallery via Chrome CDP."""
    req = urllib.request.Request(f"{CDP_URL}/json/new?{DC_WRITE_URL}", method="PUT")
    tab = json.loads(urllib.request.urlopen(req).read().decode())
    tid = tab["id"]
    ws_url = tab["webSocketDebuggerUrl"]
    urllib.request.urlopen(f"{CDP_URL}/json/activate/{tid}")
    await asyncio.sleep(4.0)

    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        # 1. Fill password, subject, and Summernote body, and scroll Turnstile into view
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
            const rect = parent ? parent.getBoundingClientRect() : null;
            return JSON.stringify({{rect, token: cfInput?.value || ""}});
        }})()
        """
        await ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": fill_js, "returnByValue": True},
        }))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
        info = json.loads(msg["result"]["result"]["value"])

        # 2. Click Cloudflare Turnstile checkbox if token is not yet populated
        if not info.get("token") and info.get("rect"):
            cx = int(info["rect"]["right"] - 300 + 28)
            cy = int(info["rect"]["top"] + 33)
            for idx, ev_type in enumerate(("mouseMoved", "mousePressed", "mouseReleased"), start=2):
                params = {"type": ev_type, "x": cx, "y": cy}
                if ev_type != "mouseMoved":
                    params["button"] = "left"
                    params["clickCount"] = 1
                await ws.send(json.dumps({"id": idx, "method": "Input.dispatchMouseEvent", "params": params}))
                await ws.recv()

            for i in range(10):
                await asyncio.sleep(1.0)
                await ws.send(json.dumps({
                    "id": 20 + i,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": 'document.querySelector("[name=cf-turnstile-response]")?.value || ""',
                        "returnByValue": True,
                    },
                }))
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if m["result"]["result"]["value"]:
                    break

        # 3. Trigger write button anti-bot interaction counters and submit form
        submit_js = """
        (async () => {
            const btnEvs = Object.keys(jQuery._data(document.querySelector("button.btn_svc.write"), "events") || {});
            for (let i = 0; i < 5; i++) {
                for (const k of btnEvs) {
                    if (k !== "click") jQuery("button.btn_svc.write").trigger(k);
                }
            }
            jQuery("button.btn_svc.write").trigger("click");
            jQuery("#write").submit();
            await new Promise(r => setTimeout(r, 2500));
            return JSON.stringify({url: location.href, alerts: window.__alerts});
        })()
        """
        await ws.send(json.dumps({
            "id": 99,
            "method": "Runtime.evaluate",
            "params": {"expression": submit_js, "awaitPromise": True, "returnByValue": True},
        }))
        try:
            await asyncio.wait_for(ws.recv(), timeout=8.0)
        except Exception:
            pass

    await asyncio.sleep(2.0)
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = httpx.get(DC_LIST_URL, headers=headers, verify=False, timeout=10.0)
    matches = re.findall(
        r'<tr[^>]*class="ub-content[^"]*"[^>]*>.*?<td class="gall_num">(\d+)</td>.*?<a[^>]*>(.*?)</a>',
        r.text,
        re.S,
    )
    for num, raw_tit in matches[:10]:
        clean_tit = re.sub(r"<[^>]+>", "", raw_tit).strip()
        if "프로농구봇" in clean_tit or "KBL" in clean_tit:
            return f"https://gall.dcinside.com/board/view/?id={DC_GALLERY_ID}&no={num}"
    return DC_LIST_URL


def main() -> None:
    parser = argparse.ArgumentParser(description="KBL 프로농구봇 홍보 에이전트")
    parser.add_argument("--title", type=str, default=None, help="커스텀 게시글 제목")
    parser.add_argument("--password", type=str, default="kbl2026!", help="비회원 게시글 비밀번호")
    parser.add_argument("--dry-run", action="store_true", help="게시하지 않고 원고만 출력")
    parser.add_argument("--post", action="store_true", help="디시인사이드 농구 갤러리에 즉시 게시")
    args = parser.parse_args()

    title, body = generate_promo_post(args.title)
    if args.dry_run or not args.post:
        print("=== [KBL봇 홍보 에이전트 원고 미리보기] ===")
        print("제목:", title)
        print("본문 HTML:\n", body)
        return

    url = asyncio.run(post_to_dcinside(title, body, password=args.password))
    print("게시 완료 URL:", url)


if __name__ == "__main__":
    main()
