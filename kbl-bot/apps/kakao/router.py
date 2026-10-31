"""Kakao OpenBuilder Skill endpoint router — Full Pro Basketball Bot (10 core features)."""

import hmac
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.kakao.builder import (
    build_cheering_response,
    build_error_response,
    build_favorite_players_response,
    build_game_results_response,
    build_health_response,
    build_highlights_response,
    build_home_menu_response,
    build_kbl_schedule_response,
    build_live_score_response,
    build_matchup_search_response,
    build_my_schedule_response,
    build_news_response,
    build_player_rankings_response,
    build_settings_response,
    build_team_standings_response,
    build_today_games_response,
)
from apps.kakao.schemas import KakaoSkillPayload, KakaoSkillResponse
from core.cache.redis import (
    get_game_cheers,
    get_redis,
    get_user_preferences,
    save_user_preferences,
    vote_team_cheer,
)
from core.config import get_settings
from core.db.models import User
from core.db.session import get_db
from core.exceptions import GameNotFoundError, KBLBotError
from core.logging import get_logger
from services.content.kbl_data import KBL_PLAYERS, search_kbl_players
from services.game.service import GameService
from services.ingestion.worker import IngestionWorker
from services.search.parser import KBL_TEAMS, normalize_team_name, parse_matchup_query
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
    u_compact = re.sub(r"\s+", "", u)
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
        return build_home_menu_response(fav_team, prefs.get("favorite_players", []))

    # 1. Settings & Onboarding (#응원팀, #알림, 설정)
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
        or ("알림" in u_compact and any(k in u_compact for k in ("시작", "종료", "클러치", "접전", "on", "off", "ON", "OFF")))
    ):
        prefs = await get_user_preferences(user_hmac)
        notifs = prefs.setdefault("notifications", {})
        notice_msg = None
        if "시작" in u:
            notifs["game_start"] = not notifs.get("game_start", True)
            state_str = "ON" if notifs["game_start"] else "OFF"
            notice_msg = f"경기 시작 10분 전 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        elif "종료" in u:
            notifs["game_end"] = not notifs.get("game_end", False)
            state_str = "ON" if notifs["game_end"] else "OFF"
            notice_msg = f"경기 종료 결과 알림이 [{state_str}]으로 변경되었습니다."
            await save_user_preferences(user_hmac, prefs)
        elif "클러치" in u or "접전" in u:
            notifs["clutch"] = not notifs.get("clutch", False)
            state_str = "ON" if notifs["clutch"] else "OFF"
            notice_msg = f"4쿼터 접전(클러치) 알림이 [{state_str}]으로 변경되었습니다."
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

    # 2. Cheering & Match Prediction (응원하기 / 승부예측 / #응원)
    if (
        u.startswith("#응원")
        or (u.startswith("응원") and not u.startswith("응원팀"))
        or u_compact in ("응원하기", "응원", "승부예측", "예측", "투표")
    ):
        today_games = await game_service.get_today_games(db)
        if not today_games:
            today_games = await game_service.get_kbl_schedule(db, days=7, limit=4)

        vote_notice = None
        if (u.startswith("#응원") or u.startswith("응원")) and not u.startswith("#응원팀") and not u.startswith("응원팀") and u_compact not in ("응원하기", "응원"):
            raw_pick = re.sub(r"^#?응원(하기)?\s*", "", u).strip()
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
                    vote_res = await vote_team_cheer(
                        user_hmac,
                        str(target_game["game_id"]),
                        norm_pick,
                        target_game["home_team"],
                        target_game["away_team"],
                    )
                    vote_notice = (
                        f"[{norm_pick}] 승리 응원 투표가 완료되었습니다! "
                        f"(내 포인트: {vote_res['user_points']}P)"
                    )
                else:
                    vote_notice = f"예정된 [{norm_pick}] 경기가 없어 응원 목록을 표시합니다."

        cheer_list = []
        user_points = 0
        for g in today_games[:4]:
            c_info = await get_game_cheers(
                str(g["game_id"]),
                g["home_team"],
                g["away_team"],
                user_hmac=user_hmac,
            )
            user_points = c_info["user_points"]
            cheer_list.append(c_info)

        return build_cheering_response(cheer_list, notice=vote_notice, user_points=user_points)

    # 3. Favorite Players & Player Search (관심선수 / #관심선수 / #선수)
    if (
        u_compact.startswith("관심선수")
        or u.startswith("#관심선수")
        or u.startswith("#선수")
        or u.startswith("선수검색")
    ):
        prefs = await get_user_preferences(user_hmac)
        fav_players: list[str] = prefs.get("favorite_players", [])
        notice_msg = None

        arg = re.sub(r"^#?(관심선수|선수검색|선수)\s*", "", u).strip()
        if arg:
            if arg in ("초기화", "전체삭제", "비우기"):
                prefs["favorite_players"] = []
                await save_user_preferences(user_hmac, prefs)
                return build_favorite_players_response(
                    [], KBL_PLAYERS[:5], notice="내 관심선수 목록이 초기화되었습니다."
                )

            is_delete = arg.startswith("삭제") or arg.startswith("해제")
            clean_name = re.sub(r"^(삭제|해제|추가|등록)\s*", "", arg).strip()
            matched = search_kbl_players(clean_name)
            exact = matched[0]["name"] if matched else clean_name

            if is_delete:
                if exact in fav_players:
                    fav_players.remove(exact)
                    prefs["favorite_players"] = fav_players
                    await save_user_preferences(user_hmac, prefs)
                    notice_msg = f"[{exact}] 선수가 관심선수에서 해제되었습니다."
                else:
                    notice_msg = f"[{exact}] 선수는 관심선수 목록에 없습니다."
            else:
                if exact not in fav_players:
                    fav_players.append(exact)
                    prefs["favorite_players"] = fav_players
                    await save_user_preferences(user_hmac, prefs)
                    notice_msg = f"[{exact}] 선수가 내 관심선수로 등록되었습니다!"
                else:
                    notice_msg = f"[{exact}] 선수는 이미 관심선수로 등록되어 있습니다."
            return build_favorite_players_response(fav_players, matched, notice=notice_msg)

        return build_favorite_players_response(fav_players, KBL_PLAYERS[:5])

    # 4. Team Standings (팀순위)
    if u_compact in ("팀순위", "순위", "구단순위", "정규리그순위", "kbl순위", "KBL순위"):
        standings = await game_service.get_team_standings(db)
        return build_team_standings_response(standings, favorite_team=fav_team)

    # 5. Player Rankings (선수순위 / 개인순위 / 득점순위 / 리바운드순위 / 어시스트순위)
    if (
        "선수순위" in u_compact
        or "개인순위" in u_compact
        or u_compact in ("득점순위", "리바운드순위", "어시스트순위", "3점슛순위", "스틸순위")
    ):
        cat = "pts"
        if "리바" in u_compact:
            cat = "reb"
        elif "어시" in u_compact:
            cat = "ast"
        elif "3점" in u_compact:
            cat = "tpm"
        elif "스틸" in u_compact:
            cat = "stl"
        rankings = await game_service.get_player_rankings(category=cat)
        return build_player_rankings_response(rankings, category=cat)

    # 6. News (뉴스 / 팀별 맞춤 뉴스)
    if (
        "뉴스" in u_compact
        or "소식" in u_compact
        or "기사" in u_compact
    ):
        requested_team = None
        for t in KBL_TEAMS:
            if t in u_compact:
                requested_team = t
                break
        target_team = requested_team or fav_team
        news_items = await game_service.get_latest_news(db, team=target_team)
        return build_news_response(news_items, favorite_team=target_team)

    # 7. Highlights (주요장면 / 하이라이트 / 영상)
    if u_compact in ("주요장면", "하이라이트", "영상", "명장면", "경기영상"):
        highlights = await game_service.get_latest_highlights(db)
        return build_highlights_response(highlights)

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

    # 11. Today Games (오늘 경기 / 실시간 점수)
    if u_compact in ("오늘경기", "오늘농구", "오늘농구경기", "실시간점수", "스코어", "라이브"):
        today_g = await game_service.get_today_games(db)
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
        logger.warning("Domain error in today-games", error=str(exc))
        return _json_200(build_error_response(exc.user_message))
    except Exception as exc:
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
        logger.warning("Domain error in match-search", error=str(exc))
        return _json_200(build_error_response(exc.user_message))
    except Exception as exc:
        logger.error("Unexpected error in match-search", exc_info=exc)
        return _json_200(build_error_response())


@router.post("/live-score")
async def live_score(
    payload: KakaoSkillPayload,
    game_service: Annotated[GameService, Depends(_get_game_service)],
    x_kakao_skill_secret: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    """
    Return the Redis-cached live score for the active game.

    Reads ONLY from Redis — never calls the provider directly.
    Always returns HTTP 200.
    """
    if not _verify_skill_secret(x_kakao_skill_secret):
        return _json_200(build_error_response("인증되지 않은 스킬 요청입니다."))

    game_id = str(payload.action.params.get("game_id", "MOCK-LIVE-001"))
    try:
        snapshot = await game_service.get_live_snapshot(game_id)
        return _json_200(build_live_score_response(snapshot))
    except GameNotFoundError as exc:
        logger.warning("Live snapshot not found", game_id=game_id)
        return _json_200(build_error_response(exc.user_message))
    except KBLBotError as exc:
        logger.warning("Domain error in live-score", error=str(exc))
        return _json_200(build_error_response(exc.user_message))
    except Exception as exc:
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
