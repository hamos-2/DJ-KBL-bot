"""KBL Bot FastAPI application entry point with lifespan management and Kakao HTTP 200 guard."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from sqlalchemy import text

from apps.kakao.builder import build_error_response
from apps.kakao.router import router as kakao_router, set_services
from core.cache.redis import close_redis, get_redis
from core.config import get_settings
from core.db.models import Base
from core.db.session import dispose_engine, get_engine
from core.exceptions import StartupError
from core.logging import configure_logging, get_logger
from core.security.crypto import CryptoService
from services.game.service import GameService
from services.ingestion.worker import IngestionWorker
from services.provider.daum import DaumSportsDataProvider
from services.provider.interface import SportsDataProvider
from services.provider.mock import MockSportsDataProvider
from services.user.service import UserService

_logger = get_logger("main")


def _build_provider(mode: str) -> SportsDataProvider:
    """Instantiate the configured SportsDataProvider ('daum' or 'mock')."""
    if mode.strip().lower() == "mock":
        return MockSportsDataProvider()
    return DaumSportsDataProvider()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager.

    Startup order:
    1. Configure logging
    2. Validate environment variables
    3. Verify PostgreSQL connectivity and create tables
    4. Verify Redis connectivity
    5. Start background ingestion worker (Daum Sports or Mock)

    Shutdown order:
    1. Stop ingestion worker
    2. Close Redis connections
    3. Dispose SQLAlchemy engine
    """
    settings = get_settings()
    configure_logging(settings.log_level)
    _logger.info(
        "Starting KBL Bot",
        env=settings.app_env,
        provider_mode=settings.provider_mode,
    )

    # 1. Validate secrets
    if not settings.master_encryption_key or not settings.hmac_secret_key:
        raise StartupError("MASTER_ENCRYPTION_KEY and HMAC_SECRET_KEY must be set")

    # 2. PostgreSQL
    engine = get_engine()
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)
        _logger.info("PostgreSQL connected and tables verified")
    except Exception as exc:
        raise StartupError(f"PostgreSQL connection failed: {exc}") from exc

    # 3. Redis
    try:
        redis = await get_redis()
        await redis.ping()
        _logger.info("Redis connected")
    except Exception as exc:
        raise StartupError(f"Redis connection failed: {exc}") from exc

    # 4. Build service graph
    crypto = CryptoService(
        master_key_hex=settings.master_encryption_key,
        hmac_secret_hex=settings.hmac_secret_key,
    )
    provider = _build_provider(settings.provider_mode)
    game_service = GameService(provider=provider)
    user_service = UserService(crypto=crypto)
    worker = IngestionWorker(
        provider=provider,
        live_interval=settings.worker_live_interval_seconds,
        scheduled_interval=settings.worker_scheduled_interval_seconds,
        lookahead_days=settings.worker_lookahead_days,
    )

    # 5. Inject services into router and start worker
    set_services(game_service, user_service, worker)

    # 6. Load dynamic in-season roster state from Redis cache
    from services.roster.manager import get_roster_manager
    roster_mgr = get_roster_manager()
    try:
        loaded = await roster_mgr.load_from_cache()
        if loaded:
            _logger.info("Restored dynamic in-season roster updates from Redis")
    except Exception as exc:
        _logger.warning("Could not load dynamic roster cache", error=str(exc))

    worker.start()
    _logger.info("Ingestion worker started", provider=type(provider).__name__)

    yield

    # Shutdown
    _logger.info("Shutting down KBL Bot")
    await worker.stop()
    aclose_fn = getattr(provider, "aclose", None)
    if callable(aclose_fn):
        await aclose_fn()
    await close_redis()
    await dispose_engine()
    _logger.info("Shutdown complete")


app = FastAPI(
    title="KBL Bot API",
    description="KBL 프로농구 카카오톡 챗봇 백엔드 MVP (Daum Sports 연동)",
    version="1.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(kakao_router)


@app.exception_handler(RequestValidationError)
async def kakao_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Guarantee HTTP 200 SkillResponse even when Kakao payload fails Pydantic validation (Rule 3).
    """
    if request.url.path.startswith("/integrations/kakao"):
        _logger.warning("Kakao payload validation error", errors=str(exc.errors()))
        err_resp = build_error_response("요청 형식을 처리할 수 없습니다.")
        return JSONResponse(content=err_resp.model_dump(), status_code=200)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def kakao_unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """
    Guarantee HTTP 200 SkillResponse even when a dependency (e.g. get_db) raises an error (Rule 3).
    """
    if request.url.path.startswith("/integrations/kakao"):
        _logger.error("Unhandled error on Kakao route", exc_info=exc)
        err_resp = build_error_response()
        return JSONResponse(content=err_resp.model_dump(), status_code=200)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/health", tags=["internal"])
async def internal_health() -> JSONResponse:
    """Internal HTTP health probe for Docker / load balancer."""
    return JSONResponse(content={"status": "ok", "service": "kbl-bot"})


@app.get("/robots.txt", tags=["seo"])
async def robots_txt() -> Response:
    """Serve robots.txt for search engines."""
    robots_file = STATIC_DIR / "robots.txt"
    if robots_file.is_file():
        return PlainTextResponse(content=robots_file.read_text(encoding="utf-8"))
    return PlainTextResponse(content="User-agent: *\nAllow: /\n")


@app.get("/sitemap.xml", tags=["seo"])
async def sitemap_xml() -> Response:
    """Serve sitemap.xml for search engines."""
    sitemap_file = STATIC_DIR / "sitemap.xml"
    if sitemap_file.is_file():
        return Response(content=sitemap_file.read_text(encoding="utf-8"), media_type="application/xml")
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://hamos-2.github.io/DJ-KBL-bot/</loc></url></urlset>',
        media_type="application/xml",
    )


@app.get("/", tags=["internal"])
async def root(request: Request) -> Response:
    """
    Root endpoint — returns SEO landing page for browsers & Googlebot,
    or service JSON for API clients.
    """
    accept = request.headers.get("accept", "")
    if "text/html" in accept or "*/*" in accept or not accept:
        index_file = STATIC_DIR / "index.html"
        if index_file.is_file():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))

    return JSONResponse(content={"service": "KBL Bot API", "version": "1.1.0"})
