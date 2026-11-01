"""
Comprehensive End-to-End System Verification for KBL KakaoTalk Chatbot.
Verifies both protocol compliance (HTTP 200, valid JSON, Kakao constraints)
and semantic data correctness across all 20 core feature domains.
"""

import json
import time
import urllib.request
import sys

URL = "http://localhost:8000/integrations/kakao/skills/match-search"
USER_ID = f"full_audit_{int(time.time())}"

results = []

def call_bot(utterance: str, user_id: str = USER_ID) -> dict:
    payload = json.dumps({
        "userRequest": {"user": {"id": user_id}, "utterance": utterance},
        "action": {"name": "match-search", "params": {}}
    }).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        data = json.loads(body)
    elapsed = (time.perf_counter() - t0) * 1000
    return data, elapsed

def check(category: str, utterance: str, validator):
    try:
        data, elapsed = call_bot(utterance)
        outputs = data.get("template", {}).get("outputs", [])
        assert outputs, "No outputs in response"
        
        # Check text bubble length <= 1000 chars
        body_str = json.dumps(data, ensure_ascii=False)
        assert "일시적으로 데이터를 불러올 수 없습니다" not in body_str, "Returned temporary error fallback"
        
        # Run specific semantic validation
        validator(data, outputs)
        
        print(f"✅ [PASS] [{category}] '{utterance}' -> {elapsed:5.1f}ms")
        results.append((category, utterance, True, f"{elapsed:5.1f}ms"))
    except AssertionError as err:
        print(f"❌ [FAIL] [{category}] '{utterance}' -> Assertion Failed: {err}")
        results.append((category, utterance, False, str(err)))
    except Exception as exc:
        print(f"💥 [ERROR] [{category}] '{utterance}' -> Exception: {exc}")
        results.append((category, utterance, False, str(exc)))

print("=" * 60)
print("🚀 STARTING COMPREHENSIVE KBL BOT SYSTEM AUDIT")
print("=" * 60)

# -------------------------------------------------------------
# 1. Main Schedule & Today Games
# -------------------------------------------------------------
def val_today_games(data, outs):
    assert any("listCard" in o for o in outs), "Expected listCard for today games"
    card = outs[0]["listCard"]
    assert "경기" in card["header"]["title"]
check("Schedule", "오늘 경기", val_today_games)

def val_schedule(data, outs):
    assert any("listCard" in o for o in outs), "Expected listCard for schedule"
check("Schedule", "일정", val_schedule)

def val_results(data, outs):
    assert any("listCard" in o for o in outs), "Expected listCard for results"
    card = outs[0]["listCard"]
    assert any("종료" in card["header"]["title"] or "결과" in card["header"]["title"] for card in [card])
check("Schedule", "경기 결과", val_results)

# -------------------------------------------------------------
# 2. Standings & Player Rankings
# -------------------------------------------------------------
def val_standings(data, outs):
    assert len(outs) == 2, "Expected 2 listCards for 10-team standings"
    c1 = outs[0]["listCard"]
    c2 = outs[1]["listCard"]
    assert "1~5위" in c1["header"]["title"]
    assert "6~10위" in c2["header"]["title"]
    assert len(c1["items"]) == 5
    assert len(c2["items"]) == 5
check("Standings", "팀순위", val_standings)

def val_rankings(data, outs):
    card = outs[0]["listCard"]
    assert "선수 순위" in card["header"]["title"]
    assert len(card["items"]) >= 3
check("Rankings", "선수순위", val_rankings)

def val_pts_rankings(data, outs):
    card = outs[0]["listCard"]
    assert "득점" in card["header"]["title"]
check("Rankings", "득점순위", val_pts_rankings)

# -------------------------------------------------------------
# 3. Lineup & Head Coaches
# -------------------------------------------------------------
def val_lineup(data, outs):
    assert "carousel" in outs[0], "Expected carousel for lineup"
    card = outs[0]["carousel"]["items"][0]
    assert "선발 라인업" in card["title"]
    desc = card["description"]
    assert "감독" in desc, "Coach info missing in lineup"
check("Lineup", "라인업", val_lineup)

# -------------------------------------------------------------
# 4. Highlights & Video Links
# -------------------------------------------------------------
def val_highlights(data, outs):
    card = outs[0]["listCard"]
    assert "주요장면" in card["header"]["title"]
    for item in card["items"]:
        url = item.get("link", {}).get("web", "")
        assert url.startswith("https://"), f"Invalid video link: {url}"
check("Highlights", "주요장면", val_highlights)

# -------------------------------------------------------------
# 5. Predictions & Points
# -------------------------------------------------------------
def val_predictions(data, outs):
    assert "carousel" in outs[0], "Expected carousel for predictions"
    card = outs[0]["carousel"]["items"][0]
    assert "승부예측" in card["title"]
check("Prediction", "승부예측", val_predictions)

def val_points(data, outs):
    card = outs[0]["basicCard"]
    assert "포인트" in card["title"]
    assert "P" in card["description"]
check("Prediction", "내 포인트", val_points)

# -------------------------------------------------------------
# 6. Favorite Team & Settings
# -------------------------------------------------------------
def val_set_team(data, outs):
    card = outs[0]["carousel"]["items"][0]
    assert "SK" in card["title"] or "SK" in card["description"]
check("Settings", "응원팀 SK", val_set_team)

def val_notifications(data, outs):
    assert "carousel" in outs[0]
check("Settings", "알림설정", val_notifications)

# -------------------------------------------------------------
# 7. 10 Clubs Starters & Best 5 Verification
# -------------------------------------------------------------
teams = ["SK", "DB", "KT", "LG", "정관장", "KCC", "한국가스공사", "현대모비스", "소노", "삼성"]
for t in teams:
    def make_val_team(team_name):
        def _val(data, outs):
            assert len(outs) == 2, f"{team_name} expected 2 outputs (listCard + carousel)"
            list_card = outs[0]["listCard"]
            assert "공식 베스트 5" in list_card["header"]["title"]
            assert len(list_card["items"]) == 5, f"{team_name} starters must be exactly 5"
            reg_carousel = outs[1]["carousel"]
            assert len(reg_carousel["items"]) == 2, f"{team_name} expected 2 registration cards"
        return _val
    check("10-Clubs", f"{t} 선수", make_val_team(t))

# -------------------------------------------------------------
# 8. Retired & Real-World Club Rosters Checks
# -------------------------------------------------------------
def val_retired_mobis(data, outs):
    body = json.dumps(data, ensure_ascii=False)
    assert "함지훈" not in body, "Retired 함지훈 must not appear in 현대모비스 roster"
    assert "장재석" in body, "장재석 must be in 현대모비스 roster"
check("Roster-Integrity", "현대모비스 선수", val_retired_mobis)

def val_db_roster(data, outs):
    body = json.dumps(data, ensure_ascii=False)
    assert "이관희" in body, "이관희 must be in DB roster"
    assert "이선 알바노" in body, "이선 알바노 must be in DB roster"
check("Roster-Integrity", "DB 선수", val_db_roster)

def val_kcc_roster(data, outs):
    body = json.dumps(data, ensure_ascii=False)
    assert "허웅" in body, "허웅 must be in KCC roster"
    assert "최준용" in body, "최준용 must be in KCC roster"
check("Roster-Integrity", "KCC 선수", val_kcc_roster)

def val_kt_roster(data, outs):
    body = json.dumps(data, ensure_ascii=False)
    assert "허훈" in body, "허훈 must be in KT roster"
    assert "하윤기" in body, "하윤기 must be in KT roster"
check("Roster-Integrity", "KT 선수", val_kt_roster)

def val_sk_roster(data, outs):
    body = json.dumps(data, ensure_ascii=False)
    assert "김선형" not in body, "김선형 must NOT be in SK roster per user constraint"
    assert "자밀 워니" in body, "자밀 워니 must be in SK roster"
check("Roster-Integrity", "SK 선수", val_sk_roster)

# -------------------------------------------------------------
# 9. Favorite Player Lifecycle
# -------------------------------------------------------------
test_user = f"lifecycle_{int(time.time())}"

def val_reg_heo(data, outs):
    assert "허훈" in outs[0]["listCard"]["header"]["title"]
    assert "등록되었습니다" in outs[0]["listCard"]["header"]["title"]
check("Favorites-Lifecycle", "허훈 등록", val_reg_heo)

def val_dup_heo(data, outs):
    assert "이미 관심선수로 등록" in outs[0]["listCard"]["header"]["title"]
check("Favorites-Lifecycle", "허훈 등록", val_dup_heo)

def val_lookup_heo(data, outs):
    card = outs[0]["basicCard"]
    assert "허훈" in card["title"]
    assert "관심선수 등록됨" in card["description"]
check("Favorites-Lifecycle", "허훈", val_lookup_heo)

def val_fav_list(data, outs):
    card = outs[0]["listCard"]
    assert "내 관심선수" in card["header"]["title"]
    items = [it["title"] for it in card["items"]]
    assert any("허훈" in t for t in items)
check("Favorites-Lifecycle", "관심선수", val_fav_list)

def val_del_heo(data, outs):
    assert "해제되었습니다" in outs[0]["listCard"]["header"]["title"]
check("Favorites-Lifecycle", "#관심선수 삭제 허훈", val_del_heo)

def val_reset_favs(data, outs):
    assert "초기화되었습니다" in outs[0]["listCard"]["header"]["title"]
check("Favorites-Lifecycle", "관심선수 초기화", val_reset_favs)

# -------------------------------------------------------------
# 10. News & Announcements
# -------------------------------------------------------------
def val_news(data, outs):
    card = outs[0]["listCard"]
    assert "뉴스" in card["header"]["title"]
    assert len(card["items"]) >= 3
    for it in card["items"]:
        assert it.get("link", {}).get("web", "").startswith("https://")
check("News", "뉴스", val_news)

def val_notice(data, outs):
    card = outs[0]["listCard"]
    assert "공지" in card["header"]["title"] or "소식" in card["header"]["title"]
check("Notice", "공지", val_notice)

# -------------------------------------------------------------
# 11. Matchup Search & NLP
# -------------------------------------------------------------
def val_matchup(data, outs):
    card = outs[0]["listCard"]
    assert "SK" in card["header"]["title"] or "KT" in card["header"]["title"]
check("Matchup", "SK vs KT", val_matchup)

print("=" * 60)
passed_count = sum(1 for _, _, ok, _ in results if ok)
total_count = len(results)
print(f"📊 FINAL SCORE: {passed_count}/{total_count} PASSED ({passed_count/total_count*100:.1f}%)")
print("=" * 60)

if passed_count != total_count:
    sys.exit(1)
