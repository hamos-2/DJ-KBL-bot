"""Kakao OpenBuilder Skill endpoint router."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.kakao.builder import (
    build_error_response,
    build_health_response,
    build_live_score_response,
    build_matchup_search_response,
    build_today_games_response,
)
from apps.kakao.schemas import KakaoSkillPayload, KakaoSkillResponse
from core.cache.redis import get_redis
from core.config import get_settings
from core.db.session import get_db
from core.exceptions import GameNotFoundError, KBLBotError
from core.logging import get_logger
from services.game.service import GameService
from services.ingestion.worker import IngestionWorker
from services.search.parser import parse_matchup_query
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
    Return today's KBL game list to the Kakao user (or matchup if '#KT vs LG' was entered).

    Always returns HTTP 200. Business errors become friendly text bubbles.
    """
    if not _verify_skill_secret(x_kakao_skill_secret):
        return _json_200(build_error_response("인증되지 않은 스킬 요청입니다."))

    kakao_user_key = payload.user_request.user.id
    try:
        await user_service.get_or_create(db, kakao_user_key)

        # If the utterance starts with '#' or matches a team matchup query, handle it directly
        utterance = payload.user_request.utterance.strip()
        if utterance.startswith("#"):
            parsed = parse_matchup_query(utterance)
            if parsed is not None:
                games = await game_service.search_matchup(
                    db, parsed.team_a, parsed.team_b
                )
                return _json_200(build_matchup_search_response(parsed, games))

        games = await game_service.get_today_games(db)
        return _json_200(build_today_games_response(games))
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
    Search upcoming/recent KBL games by team or head-to-head query (e.g. '#KT vs LG').

    Reads strictly from Redis cache and PostgreSQL (populated from Daum Sports).
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
        await user_service.get_or_create(db, kakao_user_key)
        parsed = parse_matchup_query(raw_query)
        if parsed is None:
            return _json_200(
                build_error_response(
                    "검색할 구단명을 인식하지 못했습니다.\n예시: #KT vs LG, #SK vs KCC, #현대모비스"
                )
            )

        games = await game_service.search_matchup(db, parsed.team_a, parsed.team_b)
        return _json_200(build_matchup_search_response(parsed, games))
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
) -> JSONResponse:
    """
    Check DB, Redis, and Worker liveness and return a status bubble.

    Always returns HTTP 200.
    """
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
