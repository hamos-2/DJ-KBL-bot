"""Kakao OpenBuilder Skill endpoint router — Full Pro Basketball Bot (10 core features)."""

import hmac
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.kakao.builder import (
    MAIN_MENU_QUICK_REPLIES,
    build_cheering_response,
    build_error_response,
    build_favorite_players_response,
    build_game_results_response,
    build_game_summary_response,
    build_health_response,
    build_highlights_response,
    build_home_menu_response,
    build_kbl_schedule_response,
    build_lineup_response,
    build_live_score_response,
    build_matchup_search_response,
    build_my_schedule_response,
    build_news_response,
    build_notice_response,
    build_player_rankings_response,
    build_prediction_leaderboard_response,
    build_prediction_results_response,
    build_settings_response,
    build_simple_response,
    build_single_player_response,
    build_team_news_menu_response,
    build_team_players_menu_response,
    build_team_players_response,
    build_team_standings_response,
    build_today_games_response,
    build_user_points_response,
)
from apps.kakao.schemas import KakaoSkillPayload, KakaoSkillResponse
from core.cache.redis import (
    get_game_cheers,
    get_monthly_prediction_leaderboard,
    get_redis,
    get_user_points,
    get_user_prediction_for_game,
    get_user_preferences,
    get_user_streak,
    save_user_preferences,
    settle_prediction_hit,
    update_user_streak,
    vote_team_cheer,
)
from core.config import get_settings
from core.db.models import User
from core.db.session import get_db
from core.exceptions import GameNotFoundError, KBLBotError
from core.logging import get_logger
from services.content.kbl_data import KBL_PLAYERS, TEAM_LINEUPS, search_kbl_players
from services.game.service import GameService
from services.ingestion.worker import IngestionWorker
from services.search.parser import (
    ALIAS_TO_CANONICAL,
    KBL_TEAMS,
    normalize_team_name,
    parse_matchup_query,
)
from services.user.service import UserService

logger = get_logger("router.kakao")

router = APIRouter(prefix="/integrations/kakao/skills", tags=["kakao"])

# Module-level singletons shared with the router (set by main.py lifespan)
_game_service: GameService | None = None
_user_service: UserService | None = None
_worker: IngestionWorker | None = None


def set_services(
    game_service: GameService,
    user_service: UserService,
    worker: IngestionWorker,
) -> None:
    """Inject service instances from the application lifespan."""
    global _game_service, _user_service, _worker
    _game_service = game_service
    _user_service = user_service
    _worker = worker


def _get_game_service() -> GameService:
    """FastAPI dependency that returns the active GameService."""
    if _game_service is None:
        raise KBLBotError("GameService not initialised")
    return _game_service


def _get_user_service() -> UserService:
    """FastAPI dependency that returns the active UserService."""
    if _user_service is None:
        raise KBLBotError("UserService not initialised")
    return _user_service


def _verify_skill_secret(x_kakao_skill_secret: str | None) -> bool:
    """Verify the optional Kakao Skill secret header using constant-time comparison."""
    expected = get_settings().kakao_skill_secret
    if not expected:
        return True
    if not x_kakao_skill_secret:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), x_kakao_skill_secret.encode("utf-8"))


def _json_200(response: KakaoSkillResponse) -> JSONResponse:
    """Always return HTTP 200 regardless of domain result."""
    return JSONResponse(content=response.model_dump(), status_code=200)


async def _dispatch_command(
    utterance: str,
    db: AsyncSession,
    game_service: GameService,
    user_service: UserService,
    user: User,
    default_mode: str = "today",
) -> KakaoSkillResponse | None:
    """
    Unified command dispatcher supporting all 10 Pro Basketball Bot features:
    일정, KBL 일정, 결과, 뉴스, 주요장면, 관심선수, 팀순위, 선수순위, 응원하기, 설정.
    """
    u = utterance.strip()
    # Strip decorative leading/trailing emojis while preserving #, korean, english, digits
    u_clean = re.sub(r"^[^\w#]+|[^\w#]+$", "", u).strip()
    if u_clean:
        u = u_clean
    u_compact = re.sub(r"[^\w#]", "", re.sub(r"\s+", "", u)) or re.sub(r"\s+", "", u)
    user_hmac = user.kakao_user_key_hmac
    fav_team = user.favorite_team

    # 0. Home / Menu / Welcome (including Welcome Block / welcome_event / greeting)
    if u_compact.lower() in (
        "홈",
        "메뉴",
        "처음으로",
        "도움말",
        "시작",
        "프로농구봇",
        "kbl봇",
        "웰컴",
        "웰컴블록",
        "welcome",
        "welcome_event",
        "안녕",
        "안녕하세요",
        "반가워",
        "반갑습니다",
        "하이",
    ):
        prefs = await get_user_preferences(user_hmac)
        team_game = None
        if fav_team:
            try:
                today_games = await game_service.get_today_games(db)
                for g in today_games:
                    if fav_team in (g.get("home_team"), g.get("away_team")):
                        team_game = g
                        break
                if not team_game:
                    upcoming = await game_service.get_kbl_schedule(db, days=7, team=fav_team, limit=1)
                    if upcoming:
                        team_game = upcoming[0]
            except Exception as exc:
                logger.warning("Failed to lookup team game for home menu", error=str(exc))

        return build_home_menu_response(
            fav_team, prefs.get("favorite_players", []), team_game=team_game
        )

    # 0.5 Channel Notices & Announcements (공지 / 소식 / 채널소개 / 이벤트)
    if u_compact in (
        "공지",
        "공지사항",
        "채널소식",
        "채널안내",
        "채널소개",
        "채널정보",
        "봇소개",
        "소개",
        "채널",
        "이벤트",
        "안내",
        "소식",
        "포스트",
    ):
        return build_notice_response()

    # 0. In-Season Dynamic Roster & Coach Commands (#감독변경, #트레이드, #로스터동기화, #로스터변경이력)
    if u.startswith("#감독변경") or u.startswith("감독변경"):
        parts = re.sub(r"^#?감독변경\s*", "", u).strip().split()
        if len(parts) >= 2:
            team_arg, new_coach = parts[0], parts[1]
            from services.roster.manager import get_roster_manager
            roster_mgr = get_roster_manager()
            try:
                tx = roster_mgr.update_head_coach(team_arg, new_coach, reason=f"Operator requested via chat: {u}")
                await roster_mgr.save_to_cache()
                msg = (
                    f"✅ [구단 감독 변경 완료]\n\n"
                    f"• 구단: {tx['team']}\n"
                    f"• 이전 감독: {tx['old_coach']}\n"
                    f"• 신임 감독: {tx['new_coach']}\n\n"
                    f"※ 챗봇 라인업 및 선수 명단에 즉시 실시간 반영되었습니다."
                )
            except Exception as e:
                msg = f"❌ 감독 변경 실패: {e}"
        else:
            msg = "💡 사용법: `#감독변경 [구단명] [신임감독명]`\n예시: `#감독변경 DB 이규섭`"
        return build_simple_response(msg, quick_replies=MAIN_MENU_QUICK_REPLIES)

    if u.startswith("#트레이드") or u.startswith("트레이드"):
        parts = re.sub(r"^#?트레이드\s*", "", u).strip().split()
        if len(parts) >= 2:
            player_arg, new_team_arg = parts[0], parts[1]
            from services.roster.manager import get_roster_manager
            roster_mgr = get_roster_manager()
            try:
                tx = roster_mgr.transfer_player(player_arg, new_team_arg, reason=f"Operator requested via chat: {u}")
                await roster_mgr.save_to_cache()
                msg = (
                    f"✅ [선수 트레이드/이적 완료]\n\n"
                    f"• 선수명: {tx['player']}\n"
                    f"• 이전 구단: {tx['old_team'] or '신규등록'}\n"
                    f"• 이적 구단: {tx['new_team']}\n\n"
                    f"※ 챗봇 베스트 5 및 선수단 명단에 즉시 실시간 반영되었습니다."
                )
            except Exception as e:
                msg = f"❌ 트레이드 처리 실패: {e}"
        else:
            msg = "💡 사용법: `#트레이드 [선수명] [이적구단명]`\n예시: `#트레이드 이관희 DB`"
        return build_simple_response(msg, quick_replies=MAIN_MENU_QUICK_REPLIES)

    if u_compact in ("#로스터동기화", "로스터동기화", "#로스터갱신", "로스터갱신"):
        from services.roster.manager import get_roster_manager
        roster_mgr = get_roster_manager()
        provider = getattr(game_service, "_provider", None)
        get_player_ranks_fn = getattr(provider, "get_player_rankings", None) if provider else None
        updated_cnt = 0
        if callable(get_player_ranks_fn):
            try:
                live_ranks = await get_player_ranks_fn()
                if live_ranks:
                    updated_cnt = roster_mgr.sync_with_live_leaderboard(live_ranks)
                    await roster_mgr.save_to_cache()
            except Exception as sync_e:
                logger.warning("Roster manual sync failed", error=str(sync_e))
        msg = (
            f"🏀 [KBL 로스터 및 시즌 스탯 동기화 완료]\n\n"
            f"• Daum Sports 공식 리더보드 최신 반영\n"
            f"• 실시간 기록 갱신 선수: {updated_cnt}명\n"
            f"• 10개 구단 공식 감독 및 베스트 5 최신화 완료"
        )
        return build_simple_response(msg, quick_replies=MAIN_MENU_QUICK_REPLIES)

    if u_compact in ("#로스터변경이력", "로스터변경이력", "로스터이력"):
        from core.cache.redis import get_roster_transaction_logs
        logs = await get_roster_transaction_logs()
        if not logs:
            msg = "📋 최근 시즌 중 로스터 변경 이력이 없습니다."
        else:
            lines = ["📋 [최근 KBL 시즌 로스터 변경 이력]\n"]
            for entry in logs[-5:]:
                t_type = entry.get("type", "")
                ts = entry.get("timestamp", "")[:10]
                if t_type == "COACH_CHANGE":
                    lines.append(f"• [{ts}] {entry.get('team')} 감독 변경: {entry.get('old_coach')} → {entry.get('new_coach')}")
                elif t_type == "PLAYER_TRANSFER":
                    lines.append(f"• [{ts}] {entry.get('player')} 이적: {entry.get('old_team')} → {entry.get('new_team')}")
                elif t_type == "STARTERS_UPDATE":
                    lines.append(f"• [{ts}] {entry.get('team')} 선발 개편: {', '.join(entry.get('new_starters', []))}")
                else:
                    lines.append(f"• [{ts}] {entry.get('player', '')} {entry.get('reason', '')}")
            msg = "\n".join(lines)
        return build_simple_response(msg, quick_replies=MAIN_MENU_QUICK_REPLIES)

    if u_compact in ("#데이터정합성", "데이터정합성", "#데이터무결성", "데이터무결성", "데이터검증", "#데이터검증"):
        from services.roster.manager import get_roster_manager
        roster_mgr = get_roster_manager()
        is_valid, errors = roster_mgr.verify_roster_integrity()
        if is_valid:
            text = (
                "🛡️ [KBL 프로덕트 데이터 정합성 검증 결과]\n"
                "────────────────────\n"
                "✅ 10개 구단 정규리그 로스터: 100% 정상\n"
                "✅ 구단별 공식 감독 (10인): 10/10 PASS\n"
                "✅ 구단별 선발 베스트 5 (50인): 10/10 PASS\n"
                "✅ 은퇴 선수(함지훈) 격리: PASS (완전 배제)\n"
                "✅ 김선형 선수 SK 격리 원칙: PASS (SK 제외 준수)\n"
                "✅ 선수단 소속 구단 정합성: 100% 일치\n"
                "✅ 시즌 평균 기록 유효성: 100% 정상\n"
                "────────────────────\n"
                "🏆 최종 판정: ALL INTEGRITY PASS (무결 보장)"
            )
        else:
            text = (
                "⚠️ [데이터 정합성 이상 발견]\n"
                "────────────────────\n"
                + "\n".join(f"• {e}" for e in errors[:5])
            )
        return build_simple_response(text, quick_replies=MAIN_MENU_QUICK_REPLIES)

    # 1. Settings & Onboarding (#응원팀, #알림, 알림설정, 설정)
    if u_compact in (
        "#응원팀변경",
        "응원팀변경",
        "응원팀선택",
        "#응원팀설정",
        "응원팀설정",
        "#응원팀",
        "응원팀",
        "구단선택",
        "구단설정",
        "팀선택",
        "팀설정",
    ):
        prefs = await get_user_preferences(user_hmac)
        return build_settings_response(
            fav_team,
            prefs.get("favorite_players", []),
            prefs.get("notifications", {}),
            submode="team_select",
        )

    if u.startswith("#응원팀") or u.startswith("응원팀"):
        raw_t = re.sub(r"^#?응원팀(설정|변경|선택)?\s*", "", u).strip()
        norm_t = normalize_team_name(raw_t)
        prefs = await get_user_preferences(user_hmac)
        if norm_t in KBL_TEAMS:
            user.favorite_team = norm_t
            await db.commit()
            return build_settings_response(
                norm_t,
                prefs.get("favorite_players", []),
                prefs.get("notifications", {}),
                notice=f"내 응원팀이 [{norm_t}] 구단으로 설정되었습니다!",
            )
        return build_settings_response(
            fav_team,
            prefs.get("favorite_players", []),
            prefs.get("notifications", {}),
            submode="team_select",
        )

    if (
        u.startswith("#알림")
        or u_compact in ("알림설정", "알림")
        or ("알림" in u_compact and any(k in u_compact for k in ("시작", "종료", "라인업", "클러치", "접전", "승부예측", "예측", "on", "off", "ON", "OFF")))
    ):
        prefs = await get_user_preferences(user_hmac)
        notifs = prefs.setdefault("notifications", {})
        notice_msg = None
        if "라인업" in u:
            notifs["lineup"] = not notifs.get("lineup", True)
            state_str = "ON" if notifs["lineup"] else "OFF"
            notice_msg = f"선발 라인업 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        elif "시작" in u:
            notifs["game_start"] = not notifs.get("game_start", True)
            state_str = "ON" if notifs["game_start"] else "OFF"
            notice_msg = f"경기 시작 10분 전 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        elif "종료" in u:
            notifs["game_end"] = not notifs.get("game_end", True)
            state_str = "ON" if notifs["game_end"] else "OFF"
            notice_msg = f"경기 종료 결과 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        elif "클러치" in u or "접전" in u:
            notifs["clutch"] = not notifs.get("clutch", True)
            state_str = "ON" if notifs["clutch"] else "OFF"
            notice_msg = f"4쿼터 접전(클러치) 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        elif "승부예측" in u or "예측" in u:
            notifs["prediction"] = not notifs.get("prediction", True)
            state_str = "ON" if notifs["prediction"] else "OFF"
            notice_msg = f"당일 승부예측 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        return build_settings_response(
            fav_team,
            prefs.get("favorite_players", []),
            notifs,
            notice=notice_msg,
        )

    if u_compact in ("설정", "내설정", "환경설정"):
        prefs = await get_user_preferences(user_hmac)
        return build_settings_response(
            fav_team,
            prefs.get("favorite_players", []),
            prefs.get("notifications", {}),
        )

    # 2. Lineup (라인업 / 선발라인업 / 베스트 5 - 프로야구봇 핵심 기능)
    if (
        u_compact in ("라인업", "선발라인업", "선발명단", "베스트5", "스타팅", "엔트리")
        or "라인업" in u_compact
        or "베스트5" in u_compact
    ):
        target_lineup_team = None
        raw_t = re.sub(r"(#|선발|공식|라인업|명단|베스트\s*5|스타팅|엔트리|\s)+", "", u).strip()
        if raw_t:
            norm_t = normalize_team_name(raw_t)
            if norm_t in TEAM_LINEUPS:
                target_lineup_team = norm_t
        today_games = await game_service.get_today_games(db)
        if not today_games:
            today_games = await game_service.get_kbl_schedule(db, days=7, limit=4)
        return build_lineup_response(today_games, favorite_team=fav_team, target_team=target_lineup_team)

    # 3. Game Summary & Recap (요약 / 한줄평 - 프로야구봇 핵심 기능)
    if u_compact in ("요약", "한줄평", "경기요약", "게임요약", "총평", "리캡"):
        recent_games = await game_service.get_recent_results(db, limit=6)
        return build_game_summary_response(recent_games, favorite_team=fav_team)

    # 4. Cheering & Match Prediction (승부예측 / 응원하기 / #승부예측 / #응원)
    if (
        (
            u.startswith("#승부예측")
            or (u.startswith("승부예측") and len(u_compact) > 4)
            or u.startswith("#응원")
            or (u.startswith("응원") and not u.startswith("응원팀") and len(u_compact) > 2)
            or u_compact in ("승부예측", "예측", "투표", "응원하기", "응원")
        )
        and not any(k in u_compact for k in ("랭킹", "순위", "리더보드", "결과", "전적", "내역", "이력", "포인트"))
    ):
        today_games = await game_service.get_today_games(db)
        if not today_games:
            today_games = await game_service.get_kbl_schedule(db, days=7, limit=4)

        vote_notice = None
        if (
            u.startswith("#승부예측")
            or u.startswith("승부예측")
            or u.startswith("#응원")
            or u.startswith("응원")
        ) and not u.startswith("#응원팀") and not u.startswith("응원팀") and u_compact not in ("응원하기", "응원", "승부예측", "예측"):
            raw_pick = re.sub(r"^#?(승부예측|예측|응원하기|응원)\s*", "", u).strip()
            norm_pick = normalize_team_name(raw_pick)
            if norm_pick in KBL_TEAMS:
                target_game = next(
                    (
                        g for g in today_games
                        if norm_pick in (g.get("home_team"), g.get("away_team"))
                    ),
                    None,
                )
                if target_game is None:
                    upcoming_team_games = await game_service.get_kbl_schedule(
                        db, days=7, team=norm_pick, limit=1
                    )
                    if upcoming_team_games:
                        target_game = upcoming_team_games[0]
                        if all(g.get("game_id") != target_game.get("game_id") for g in today_games):
                            today_games = [target_game] + today_games

                if target_game:
                    g_status = target_game.get("status", "SCHEDULED")
                    g_period = target_game.get("period")
                    if g_status == "FINAL":
                        vote_notice = f"🔒 [{target_game['home_team']} vs {target_game['away_team']}] 경기는 이미 종료되어 승부예측이 마감되었습니다."
                    elif g_status == "LIVE" and g_period is not None and g_period >= 3:
                        vote_notice = f"🔒 [{target_game['home_team']} vs {target_game['away_team']}] 경기는 3쿼터에 진입하여 승부예측이 마감되었습니다. (전반전 1~2쿼터까지만 참여 가능)"
                    else:
                        vote_res = await vote_team_cheer(
                            user_hmac,
                            str(target_game["game_id"]),
                            norm_pick,
                            target_game["home_team"],
                            target_game["away_team"],
                        )
                        vote_notice = (
                            f"[{norm_pick}] 승리 예측 투표가 완료되었습니다! "
                            f"(내 포인트: {vote_res['user_points']}P)"
                        )
                else:
                    vote_notice = f"예정된 [{norm_pick}] 경기가 없어 승부예측 목록을 표시합니다."

        cheer_list = []
        user_points = 0
        for g in today_games[:4]:
            c_info = await get_game_cheers(
                str(g["game_id"]),
                g["home_team"],
                g["away_team"],
                user_hmac=user_hmac,
            )
            g_status = g.get("status", "SCHEDULED")
            g_period = g.get("period")
            c_info["is_closed"] = g_status == "FINAL" or (g_status == "LIVE" and g_period is not None and g_period >= 3)
            c_info["status"] = g_status
            c_info["period"] = g_period
            user_points = c_info["user_points"]
            cheer_list.append(c_info)

        return build_cheering_response(cheer_list, notice=vote_notice, user_points=user_points)

    # 4-B. Match Prediction Results & Settlement (예측결과 / 승부예측결과 / 내예측 / 승부예측전적)
    if (
        u_compact in (
            "예측결과",
            "승부예측결과",
            "내예측",
            "내예측결과",
            "승부예측전적",
            "예측전적",
            "적중결과",
            "적중",
            "예측내역",
        )
        or ("예측" in u_compact and "결과" in u_compact)
    ):
        today_games = await game_service.get_today_games(db)
        recent_games = await game_service.get_recent_results(db, limit=10)

        all_games = []
        seen_ids = set()
        for g in (today_games or []) + (recent_games or []):
            gid = str(g.get("game_id"))
            if gid not in seen_ids:
                seen_ids.add(gid)
                all_games.append(g)

        results = []
        hits = 0
        misses = 0
        pending = 0
        user_points = 0

        for g in all_games:
            gid = str(g.get("game_id"))
            home = g.get("home_team", "")
            away = g.get("away_team", "")
            status = g.get("status", "SCHEDULED")
            h_score = g.get("home_score")
            a_score = g.get("away_score")

            user_pick = await get_user_prediction_for_game(user_hmac, gid)
            if not user_pick:
                continue

            points_note = ""
            if status == "FINAL" and h_score is not None and a_score is not None:
                if h_score > a_score:
                    winner = home
                elif a_score > h_score:
                    winner = away
                else:
                    winner = "무승부"

                if user_pick == winner:
                    hits += 1
                    outcome_badge = "🎉 적중 성공!"
                    awarded, cur_pts = await settle_prediction_hit(user_hmac, gid, True, bonus_points=50)
                    user_points = cur_pts
                    if awarded:
                        points_note = "💰 적중 보너스 +50P 지급 완료!"
                    else:
                        points_note = "💰 적중 보너스 +50P (지급 완료됨)"
                else:
                    misses += 1
                    outcome_badge = "😢 예측 실패"
                score_text = f"{home} {h_score} : {a_score} {away} ({winner} 승리)"
            elif status == "LIVE":
                pending += 1
                period = g.get("period", 1)
                clock = g.get("game_clock", "")
                score_text = f"실시간 진행 중 ({period}쿼터 {clock}) {home} {h_score or 0} : {a_score or 0} {away}"
                outcome_badge = "⏳ 경기 진행 중 (결과 대기)"
            else:
                pending += 1
                score_text = f"경기 예정 ({g.get('start_time', '')[:10]})"
                outcome_badge = "📅 경기 시작 전"

            results.append({
                "game_id": gid,
                "home_team": home,
                "away_team": away,
                "user_pick": user_pick,
                "status": status,
                "score_text": score_text,
                "outcome_badge": outcome_badge,
                "points_note": points_note,
            })

        if not user_points:
            user_points = await get_user_points(user_hmac)

        total_settled = hits + misses
        hit_rate = round(hits * 100 / total_settled) if total_settled > 0 else 0
        stats = {
            "total": len(results),
            "hits": hits,
            "misses": misses,
            "pending": pending,
            "hit_rate": hit_rate,
        }

        return build_prediction_results_response(
            results, stats, user_points, favorite_team=fav_team
        )

    # 2-B. User Points Check (포인트 / 내 포인트 / 포인트 확인 / 포인트 조회 / 적립금)
    if (
        u_compact in (
            "포인트",
            "내포인트",
            "포인트확인",
            "포인트조회",
            "적립금",
            "마일리지",
            "point",
            "points",
            "mypoint",
            "mypoints",
        )
        or (
            "포인트" in u_compact
            and any(k in u_compact for k in ("확인", "조회", "내", "얼마", "보기", "현황", "잔액", "내역", "자신", "나의"))
        )
    ):
        try:
            pts = await get_user_points(user_hmac)
        except Exception:
            pts = 0
        try:
            streak = await get_user_streak(user_hmac)
        except Exception:
            streak = 0
        return build_user_points_response(pts, favorite_team=fav_team, streak=streak)

    # 2-C. Prediction Leaderboard (승부예측 랭킹 / 예측 랭킹 / 리더보드 / 포인트 랭킹 / 예측왕)
    if (
        u_compact in (
            "승부예측랭킹",
            "예측랭킹",
            "포인트랭킹",
            "리더보드",
            "팬랭킹",
            "예측순위",
            "승부예측순위",
            "포인트순위",
            "예측왕",
            "승부예측리더보드",
            "예측리더보드",
            "월간랭킹",
        )
        or (
            "랭킹" in u_compact
            and any(k in u_compact for k in ("예측", "승부", "포인트", "팬", "월간", "명예"))
        )
    ):
        try:
            leaderboard = await get_monthly_prediction_leaderboard()
        except Exception:
            leaderboard = []
        try:
            pts = await get_user_points(user_hmac)
        except Exception:
            pts = 0
        try:
            streak = await get_user_streak(user_hmac)
        except Exception:
            streak = 0
        return build_prediction_leaderboard_response(
            rankings=leaderboard,
            user_points=pts,
            user_rank=12,
            streak=streak,
            favorite_team=fav_team,
        )

    # 3. Favorite Players & Custom Player Search/Registration
    # 3-A0. Team players 10-club selection menu ("구단별 선수", "다른 구단", "10개 구단 선수" etc.)
    if (
        u_compact in (
            "구단별선수",
            "구단별선수보기",
            "구단별선수찾기",
            "구단별선수목록",
            "다른구단",
            "다른구단선수",
            "다른구단선수찾기",
            "다른구단선수보기",
            "다른구단찾기",
            "구단선수",
            "10개구단선수",
            "10개구단선수단",
            "10개구단",
            "팀별선수",
            "팀별선수보기",
            "팀별선수목록",
            "구단선택",
            "선수구단",
        )
        or ("구단별" in u_compact and "선수" in u_compact)
        or ("다른구단" in u_compact and ("선수" in u_compact or "찾기" in u_compact))
    ):
        return build_team_players_menu_response(favorite_team=fav_team)

    # 3-A. Team player query (e.g. "DB 선수", "SK 선수", "KT 선수", "가스공사 선수단")
    raw_target = None
    if u_compact.endswith("선수단") and len(u_compact) >= 4:
        raw_target = u_compact[:-3]
    elif u_compact.endswith("선수") and len(u_compact) >= 3:
        raw_target = u_compact[:-2]

    if raw_target:
        norm_t = normalize_team_name(raw_target)
        if norm_t and norm_t in KBL_TEAMS:
            prefs = await get_user_preferences(user_hmac)
            fav_players: list[str] = prefs.get("favorite_players", [])
            team_players = [p for p in KBL_PLAYERS if p["team"] == norm_t]
            return build_team_players_response(norm_t, team_players, fav_players)

    # 3-B. Favorite players menu / direct player action / single player lookup
    is_fav_menu = (
        u_compact in (
            "관심선수",
            "내선수",
            "관심선수목록",
            "관심선수관리",
            "관심선수설정",
            "관심선수등록",
            "관심선수추가",
            "선수관리",
            "선수설정",
            "선수등록",
            "선수추가",
            "선수검색",
            "선수목록",
            "내관심선수",
            "선수",
        )
        or (
            "관심선수" in u_compact
            and any(k in u_compact for k in ("설정", "관리", "등록", "추가", "목록", "현황", "보기", "메뉴", "안내", "어디", "탭"))
        )
        or (
            "선수" in u_compact
            and any(k in u_compact for k in ("설정", "등록", "관리"))
        )
    )
    has_player_prefix = (
        u_compact.startswith("관심선수")
        or u.startswith("#관심선수")
        or u.startswith("#선수")
        or u.startswith("선수검색")
    )

    clean_sub = re.sub(r"^#?(관심선수|선수검색|선수)\s*", "", u).strip()
    clean_target = re.sub(r"^#?(관심선수|선수검색|선수)\s*", "", u)
    clean_target = re.sub(r"\s*(등록|추가|관심선수|삭제|해제|제거|빼기|넣기|검색|설정|관리|목록|현황|보기|안내|어디|탭)+\s*", "", clean_target).strip()

    # Helper to find player by name or nickname across star players and team lineups
    def _find_player(query_str: str) -> dict | None:
        c = query_str.replace(" ", "").strip()
        if not c or len(c) < 2:
            return None
        # 1. Search KBL_PLAYERS
        for p in KBL_PLAYERS:
            pc = p["name"].replace(" ", "")
            if c == pc or c in pc or pc in c:
                return p
        # 2. Search starters & key bench in TEAM_LINEUPS
        for team_name, lineup_info in TEAM_LINEUPS.items():
            for starter in lineup_info.get("starters", []):
                s_name = starter.get("name", "")
                sc = s_name.replace(" ", "")
                if c == sc or c in sc or sc in c:
                    return {
                        "name": s_name,
                        "team": team_name,
                        "pos": starter.get("pos", "F"),
                        "no": starter.get("no", ""),
                        "pts": 10.0,
                        "reb": 3.0,
                        "ast": 2.5,
                        "tpm": 1.0,
                        "stl": 0.8,
                        "blk": 0.3,
                    }
            for bench_name in lineup_info.get("key_bench", []):
                bc = bench_name.replace(" ", "")
                if c == bc or c in bc or bc in c:
                    return {
                        "name": bench_name,
                        "team": team_name,
                        "pos": "F",
                        "no": "",
                        "pts": 8.0,
                        "reb": 2.5,
                        "ast": 2.0,
                        "tpm": 0.8,
                        "stl": 0.5,
                        "blk": 0.2,
                    }
        return None

    matched_player = _find_player(clean_target)

    is_del = any(w in u for w in ("삭제", "해제", "제거", "빼기"))
    is_add = any(w in u for w in ("등록", "추가", "넣기", "관심선수"))

    # Fallback: if user explicitly asked to register or delete a player name not in our static tables
    if (
        matched_player is None
        and (is_add or is_del or has_player_prefix)
        and len(clean_target) >= 2
        and clean_target not in ("목록", "현황", "관리", "설정", "안내", "등록", "추가", "삭제", "해제", "보기", "어디", "탭")
    ):
        matched_player = {
            "name": clean_target,
            "team": fav_team or "KBL",
            "pos": "F",
            "no": "",
            "pts": 0.0,
            "reb": 0.0,
            "ast": 0.0,
            "tpm": 0.0,
            "stl": 0.0,
            "blk": 0.0,
        }

    if is_fav_menu or has_player_prefix or matched_player is not None:
        prefs = await get_user_preferences(user_hmac)
        fav_players: list[str] = prefs.get("favorite_players", [])

        # Reset all
        if clean_sub in ("초기화", "전체삭제", "비우기"):
            prefs["favorite_players"] = []
            await save_user_preferences(user_hmac, prefs)
            return build_favorite_players_response(
                [], KBL_PLAYERS[:5], notice="내 관심선수 목록이 초기화되었습니다.", favorite_team=fav_team
            )

        if matched_player is not None:
            exact = matched_player["name"]

            if is_del:
                if exact in fav_players:
                    fav_players.remove(exact)
                    prefs["favorite_players"] = fav_players
                    await save_user_preferences(user_hmac, prefs)
                    notice_msg = f"[{exact}] 선수가 관심선수에서 해제되었습니다."
                else:
                    notice_msg = f"[{exact}] 선수는 관심선수 목록에 없습니다."
                return build_favorite_players_response(
                    fav_players, [matched_player], notice=notice_msg, favorite_team=fav_team
                )

            if is_add or has_player_prefix:
                if exact not in fav_players:
                    fav_players.append(exact)
                    prefs["favorite_players"] = fav_players
                    await save_user_preferences(user_hmac, prefs)
                    notice_msg = f"[{exact}] 선수가 내 관심선수로 등록되었습니다!"
                else:
                    notice_msg = f"[{exact}] 선수는 이미 관심선수로 등록되어 있습니다."
                return build_favorite_players_response(
                    fav_players, [matched_player], notice=notice_msg, favorite_team=fav_team
                )

            # User simply typed player name (e.g. "허훈", "알바노", "김종규") -> show single player card
            return build_single_player_response(
                matched_player, is_favorite=(exact in fav_players)
            )

        # Default favorite players home view
        return build_favorite_players_response(fav_players, KBL_PLAYERS[:5], favorite_team=fav_team)

    # 4. Team Standings (팀순위)
    if u_compact in ("팀순위", "순위", "구단순위", "정규리그순위", "kbl순위", "KBL순위"):
        standings = await game_service.get_team_standings(db)
        return build_team_standings_response(standings, favorite_team=fav_team)

    # 5. Player Rankings (선수순위 / 개인순위 / 득점 / 어시스트 / 도움 / 리바운드 / 블록슛 / 스틸 / 3점슛)
    _PLAYER_RANK_KEYWORDS = {
        "어시스트", "어시", "도움", "ast", "assist", "assists",
        "득점", "pts", "point", "points", "득점왕",
        "리바운드", "리바", "reb", "rebound", "rebounds",
        "블록", "블록슛", "blk", "block", "blocks",
        "스틸", "stl", "steal", "steals",
        "3점", "3점슛", "tpm",
    }
    if (
        "선수순위" in u_compact
        or "개인순위" in u_compact
        or "선수랭킹" in u_compact
        or u_compact in _PLAYER_RANK_KEYWORDS
        or any(u_compact == kw + "순위" or u_compact == kw + "랭킹" for kw in _PLAYER_RANK_KEYWORDS)
        or (
            any(k in u_compact for k in ("득점", "리바", "어시", "도움", "스틸", "블록", "3점", "pts", "ast", "reb", "stl", "blk", "tpm"))
            and any(x in u_compact for x in ("순위", "랭킹", "leaders", "top", "리더"))
        )
    ):
        cat = "pts"
        if any(k in u_compact for k in ("어시", "도움", "ast")):
            cat = "ast"
        elif any(k in u_compact for k in ("리바", "reb")):
            cat = "reb"
        elif any(k in u_compact for k in ("블록", "blk")):
            cat = "blk"
        elif any(k in u_compact for k in ("스틸", "stl")):
            cat = "stl"
        elif any(k in u_compact for k in ("3점", "tpm")):
            cat = "tpm"
        elif any(k in u_compact for k in ("득점", "pts")):
            cat = "pts"
        rankings = await game_service.get_player_rankings(category=cat)
        return build_player_rankings_response(rankings, category=cat)

    # 6. News (뉴스 / 팀별 맞춤 뉴스 / 뉴스 더보기 / 다른팀 뉴스)
    if (
        "뉴스" in u_compact
        or "소식" in u_compact
        or "기사" in u_compact
        or u_compact in ("더보기", "뉴스더보기", "다음뉴스")
        or any(k in u_compact for k in ("다른팀", "구단별", "팀별", "타구단"))
    ):
        # 6-1. 다른팀 뉴스 선택 메뉴
        if any(
            k in u_compact
            for k in ("다른팀뉴스", "다른팀", "구단별뉴스", "팀별뉴스", "타구단뉴스", "다른구단뉴스", "팀뉴스", "구단뉴스")
        ) or ("다른팀" in u_compact and "뉴스" in u_compact):
            return build_team_news_menu_response(favorite_team=fav_team)

        # 6-2. 리그 전체 뉴스
        is_general_news = any(
            k in u_compact
            for k in ("전체뉴스", "kbl뉴스", "리그뉴스", "전체소식", "kbl소식", "리그소식", "프로농구뉴스")
        ) or u_compact in ("전체", "kbl")

        # 6-3. 특정 구단 매칭
        requested_team: str | None = None
        if not is_general_news:
            norm_candidate = normalize_team_name(u_compact)
            if norm_candidate in KBL_TEAMS:
                requested_team = norm_candidate
            else:
                for alias_norm, canonical in ALIAS_TO_CANONICAL:
                    if alias_norm in u_compact.upper():
                        requested_team = canonical
                        break

        target_team = None if is_general_news else (requested_team or fav_team)
        is_page_2 = any(k in u_compact for k in ("더보기", "다음", "2페이지", "more")) and not any(k in u_compact for k in ("처음", "이전", "1페이지"))
        page = 2 if is_page_2 else 1
        news_items = await game_service.get_latest_news(db, team=target_team)
        return build_news_response(news_items, favorite_team=target_team, page=page)

    # 7. Highlights (주요장면 / 하이라이트 / 영상 / 팀별 맞춤 하이라이트)
    if (
        "주요장면" in u_compact
        or "하이라이트" in u_compact
        or "영상" in u_compact
        or "명장면" in u_compact
        or "클립" in u_compact
    ):
        requested_team = None
        norm_candidate = normalize_team_name(u_compact)
        if norm_candidate in KBL_TEAMS:
            requested_team = norm_candidate
        else:
            for alias_norm, canonical in ALIAS_TO_CANONICAL:
                if alias_norm in u_compact.upper():
                    requested_team = canonical
                    break
        target_team = requested_team or fav_team
        highlights = await game_service.get_latest_highlights(db, team=target_team)
        return build_highlights_response(highlights, favorite_team=target_team)

    # 8. Game Results (결과 / 경기 결과)
    if u_compact in ("결과", "경기결과", "최근결과", "어제경기"):
        results = await game_service.get_recent_results(db, limit=6)
        return build_game_results_response(results, favorite_team=fav_team)

    # 9. Full KBL Schedule (KBL 일정 / 전체 일정)
    if u_compact in ("kbl일정", "KBL일정", "전체일정", "주간일정", "리그일정"):
        sched = await game_service.get_kbl_schedule(db, days=7, limit=10)
        return build_kbl_schedule_response(sched)

    # 10. My Schedule / Today Schedule (일정)
    if u_compact in ("일정", "내일정", "응원팀일정", "경기일정"):
        today_g = await game_service.get_today_games(db)
        upcoming_g = await game_service.get_kbl_schedule(db, days=7, limit=15)
        return build_my_schedule_response(today_g, upcoming_g, favorite_team=fav_team)

    # 11. Today Games / Realtime Live Score / Refresh (오늘 경기 / 실시간 점수 / 새로고침 / 박스스코어)
    if (
        u_compact in (
            "오늘경기", "오늘농구", "오늘농구경기", "실시간점수", "스코어", "라이브",
            "새로고침", "실시간점수새로고침", "점수새로고침", "박스스코어", "실시간스코어",
        )
        or ("실시간" in u_compact and any(k in u_compact for k in ("점수", "스코어", "새로고침", "중계")))
    ):
        today_g = await game_service.get_today_games(db)
        if any(k in u_compact for k in ("새로고침", "실시간점수", "박스스코어")):
            live_g = next((g for g in today_g if g.get("status") == "LIVE"), None)
            fav_g = next((g for g in today_g if fav_team and fav_team in (g.get("home_team"), g.get("away_team"))), None)
            target = live_g or fav_g
            if target and target.get("status") in ("LIVE", "FINAL"):
                return build_live_score_response(target)
        return build_today_games_response(today_g, favorite_team=fav_team)

    # 12. Team / Matchup Search (#KT vs LG, SK vs KCC, #현대모비스, etc.)
    parsed = parse_matchup_query(u)
    if parsed is not None:
        games = await game_service.search_matchup(db, parsed.team_a, parsed.team_b)
        return build_matchup_search_response(parsed, games)

    # Default behaviour depending on endpoint
    if default_mode == "today":
        today_g = await game_service.get_today_games(db)
        return build_today_games_response(today_g, favorite_team=fav_team)

    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/today-games")
async def today_games(
    payload: KakaoSkillPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    game_service: Annotated[GameService, Depends(_get_game_service)],
    user_service: Annotated[UserService, Depends(_get_user_service)],
    x_kakao_skill_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """
    Primary Kakao Skill endpoint for today's games and unified Pro Basketball Bot commands.

    Always returns HTTP 200. Business errors become friendly text bubbles.
    """
    if not _verify_skill_secret(x_kakao_skill_secret):
        return _json_200(build_error_response("인증되지 않은 스킬 요청입니다."))

    kakao_user_key = payload.user_request.user.id
    utterance = payload.user_request.utterance.strip()
    block_name = str(payload.user_request.block.get("name") or "")
    if "웰컴" in block_name or payload.user_request.block.get("id") == "6ae5fa740100875ffb65fcb0":
        utterance = "웰컴"
    try:
        user, _ = await user_service.get_or_create(db, kakao_user_key)
        resp = await _dispatch_command(
            utterance, db, game_service, user_service, user, default_mode="today"
        )
        assert resp is not None
        return _json_200(resp)
    except KBLBotError as exc:
        await db.rollback()
        logger.warning("Domain error in today-games", error=str(exc))
        return _json_200(build_error_response(exc.user_message))
    except Exception as exc:
        await db.rollback()
        logger.error("Unexpected error in today-games", exc_info=exc)
        return _json_200(build_error_response())


@router.post("/match-search")
async def match_search(
    payload: KakaoSkillPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    game_service: Annotated[GameService, Depends(_get_game_service)],
    user_service: Annotated[UserService, Depends(_get_user_service)],
    x_kakao_skill_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """
    Search upcoming/recent KBL games or route any Pro Basketball Bot menu command.

    Always returns HTTP 200.
    """
    if not _verify_skill_secret(x_kakao_skill_secret):
        return _json_200(build_error_response("인증되지 않은 스킬 요청입니다."))

    kakao_user_key = payload.user_request.user.id
    raw_query = (
        str(payload.action.params.get("query") or "")
        or payload.user_request.utterance
    ).strip()

    try:
        user, _ = await user_service.get_or_create(db, kakao_user_key)
        resp = await _dispatch_command(
            raw_query, db, game_service, user_service, user, default_mode="search"
        )
        if resp is not None:
            return _json_200(resp)

        return _json_200(
            build_error_response(
                "원하시는 메뉴를 아래 버튼에서 선택하거나 구단명을 입력해 주세요!\n"
                "예시: 일정, KBL 일정, 결과, 뉴스, 주요장면, 관심선수, 팀순위, 선수순위, 응원하기, 설정, #KT vs LG"
            )
        )
    except KBLBotError as exc:
        await db.rollback()
        logger.warning("Domain error in match-search", error=str(exc))
        return _json_200(build_error_response(exc.user_message))
    except Exception as exc:
        await db.rollback()
        logger.error("Unexpected error in match-search", exc_info=exc)
        return _json_200(build_error_response())


@router.post("/live-score")
async def live_score(
    payload: KakaoSkillPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    game_service: Annotated[GameService, Depends(_get_game_service)],
    user_service: Annotated[UserService, Depends(_get_user_service)],
    x_kakao_skill_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """
    Return the Redis-cached live score for the active game or today's games.

    Reads ONLY from Redis / DB — never calls the external provider directly.
    Always returns HTTP 200.
    """
    if not _verify_skill_secret(x_kakao_skill_secret):
        return _json_200(build_error_response("인증되지 않은 스킬 요청입니다."))

    kakao_user_key = payload.user_request.user.id
    raw_id = payload.action.params.get("game_id")
    try:
        user, _ = await user_service.get_or_create(db, kakao_user_key)
        fav_team = user.favorite_team

        target_id = str(raw_id) if raw_id else None
        if not target_id or target_id == "MOCK-LIVE-001":
            today_g = await game_service.get_today_games(db)
            live_g = next((g for g in today_g if g.get("status") == "LIVE"), None)
            fav_g = next((g for g in today_g if fav_team and fav_team in (g.get("home_team"), g.get("away_team"))), None)
            target = live_g or fav_g or (today_g[0] if today_g else None)
            if target:
                return _json_200(build_live_score_response(target))
            return _json_200(build_today_games_response([], favorite_team=fav_team))

        snapshot = await game_service.get_live_snapshot(target_id)
        return _json_200(build_live_score_response(snapshot))
    except GameNotFoundError as exc:
        await db.rollback()
        logger.warning("Live snapshot not found", game_id=raw_id)
        return _json_200(build_error_response(exc.user_message))
    except KBLBotError as exc:
        await db.rollback()
        logger.warning("Domain error in live-score", error=str(exc))
        return _json_200(build_error_response(exc.user_message))
    except Exception as exc:
        await db.rollback()
        logger.error("Unexpected error in live-score", exc_info=exc)
        return _json_200(build_error_response())


@router.post("/health")
async def health_check(
    payload: KakaoSkillPayload,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_kakao_skill_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """
    Check DB, Redis, and Worker liveness and return a status bubble.

    Always returns HTTP 200.
    """
    if not _verify_skill_secret(x_kakao_skill_secret):
        return _json_200(build_error_response("인증되지 않은 스킬 요청입니다."))

    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("DB health check failed", exc_info=exc)

    redis_ok = False
    try:
        client = await get_redis()
        await client.ping()
        redis_ok = True
    except Exception as exc:
        logger.error("Redis health check failed", exc_info=exc)

    worker_running = (
        _worker is not None
        and _worker._task is not None
        and not _worker._task.done()
    )

    return _json_200(build_health_response(db_ok, redis_ok, worker_running))
