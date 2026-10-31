"""Background ingestion worker — polls the provider and refreshes Redis & PostgreSQL."""

import asyncio
import time
from datetime import timedelta
from typing import Any

from core.cache.redis import (
    acquire_ingest_lock,
    release_ingest_lock,
    save_game_snapshot,
)
from core.db.session import get_session_factory
from core.exceptions import ProviderError
from core.logging import get_logger
from services.game.service import GameService, today_kst
from services.provider.interface import SportsDataProvider

logger = get_logger("worker.ingestion")

# Game statuses
_STATUS_SCHEDULED = "SCHEDULED"
_STATUS_LIVE = "LIVE"
_STATUS_FINAL = "FINAL"


class IngestionWorker:
    """
    Polls the sports data provider and writes live snapshots to Redis & PostgreSQL.

    Polling intervals:
        - SCHEDULED games: every ``scheduled_interval`` seconds (default 60s)
        - LIVE games: every ``live_interval`` seconds (default 5s)
        - FINAL games: skipped once persisted as FINAL

    The worker detects state transitions (SCHEDULED→LIVE, LIVE→FINAL)
    and logs them at INFO level.
    """

    def __init__(
        self,
        provider: SportsDataProvider,
        live_interval: int = 5,
        scheduled_interval: int = 60,
        lookahead_days: int = 30,
        persist_db: bool = True,
    ) -> None:
        """
        Initialise the IngestionWorker.

        Args:
            provider: Active SportsDataProvider adapter.
            live_interval: Seconds between polls for LIVE games.
            scheduled_interval: Seconds between polls for SCHEDULED games & schedule sync.
            lookahead_days: Number of upcoming days to pre-sync into DB for matchup search.
            persist_db: Whether to upsert polled games into PostgreSQL.
        """
        self._provider = provider
        self._live_interval = live_interval
        self._scheduled_interval = scheduled_interval
        self._lookahead_days = lookahead_days
        self._persist_db = persist_db
        self._running = False
        self._task: asyncio.Task[None] | None = None
        # Track last known status per game to detect transitions
        self._last_status: dict[str, str] = {}
        # Track last monotonic poll timestamp per game to honour scheduled_interval
        self._last_polled_at: dict[str, float] = {}
        self._last_window_sync_at: float = 0.0

    def start(self) -> None:
        """Schedule the worker loop as a background asyncio task."""
        if self._running:
            logger.warning("IngestionWorker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="ingestion-worker")
        logger.info(
            "IngestionWorker started",
            live_interval=self._live_interval,
            scheduled_interval=self._scheduled_interval,
        )

    async def stop(self) -> None:
        """Signal the worker to stop and await task cleanup."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("IngestionWorker stopped")

    async def _run_loop(self) -> None:
        """Main polling loop — runs until :attr:`_running` is False."""
        logger.info("Ingestion loop entered")
        while self._running:
            try:
                await self._sync_upcoming_window_if_due()
                await self._poll_all_games()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Unexpected error in ingestion loop", exc_info=exc)
            await asyncio.sleep(self._live_interval)

    async def _sync_upcoming_window_if_due(self) -> None:
        """Sync the upcoming schedule window (today - 1d .. today + lookahead_days) periodically."""
        if not self._persist_db:
            return
        now_mono = time.monotonic()
        if (
            self._last_window_sync_at > 0.0
            and (now_mono - self._last_window_sync_at) < self._scheduled_interval
        ):
            return

        today = today_kst()
        start_d = today - timedelta(days=14)
        end_d = today + timedelta(days=self._lookahead_days)

        try:
            games = await self._provider.get_schedule_range(start_d, end_d)
            factory = get_session_factory()
            async with factory() as db:
                for g in games:
                    await GameService.upsert_game(db, g)
                    await save_game_snapshot(str(g["game_id"]), g)
                await db.commit()
            self._last_window_sync_at = now_mono
            logger.info(
                "Synced upcoming schedule window",
                start_date=str(start_d),
                end_date=str(end_d),
                count=len(games),
            )
        except Exception as exc:
            logger.error("Failed to sync upcoming schedule window", error=str(exc))

    async def _poll_all_games(self) -> None:
        """Fetch today's KST schedule and poll due games concurrently."""
        try:
            games: list[dict[str, Any]] = await self._provider.get_schedule(today_kst())
        except ProviderError as exc:
            logger.error("Provider error fetching schedule", error=str(exc))
            return

        now_mono = time.monotonic()
        coros = []

        for game in games:
            game_id: str = str(game["game_id"])
            status: str = game.get("status", _STATUS_SCHEDULED)

            if status == _STATUS_FINAL and self._last_status.get(game_id) == _STATUS_FINAL:
                # Already recorded as FINAL; no further polling needed
                continue

            interval = (
                self._live_interval
                if status == _STATUS_LIVE
                else self._scheduled_interval
            )
            last_polled = self._last_polled_at.get(game_id, 0.0)
            if last_polled > 0.0 and (now_mono - last_polled) < interval:
                continue

            self._last_polled_at[game_id] = now_mono
            coros.append(self._ingest_game(game_id, status))

        if coros:
            await asyncio.gather(*coros, return_exceptions=True)

    async def _ingest_game(self, game_id: str, current_status: str) -> None:
        """
        Acquire ownership-token lock, poll provider, save snapshot & DB row, detect transitions.

        Args:
            game_id: Provider game identifier.
            current_status: Known status before polling.
        """
        token = await acquire_ingest_lock(game_id, ttl_seconds=30)
        if token is None:
            logger.debug("Ingest lock held, skipping", game_id=game_id)
            return

        try:
            if current_status == _STATUS_LIVE:
                data = await self._provider.get_live_score(game_id)
            else:
                data = await self._provider.get_game(game_id)

            await save_game_snapshot(game_id, data)
            if self._persist_db:
                factory = get_session_factory()
                async with factory() as db:
                    await GameService.upsert_game(db, data)
                    await db.commit()

            self._detect_transition(game_id, data)

        except ProviderError as exc:
            logger.error(
                "Provider error during ingestion — keeping last snapshot",
                game_id=game_id,
                error=str(exc),
            )
        except Exception as exc:
            logger.error(
                "Unexpected error during game ingestion",
                game_id=game_id,
                exc_info=exc,
            )
        finally:
            await release_ingest_lock(game_id, token)

    def _detect_transition(
        self, game_id: str, data: dict[str, Any]
    ) -> None:
        """
        Compare the new status against the last known status and log transitions.

        Args:
            game_id: Provider game identifier.
            data: Latest canonical game dict from the provider.
        """
        new_status: str = data.get("status", _STATUS_SCHEDULED)
        last_status = self._last_status.get(game_id)

        if last_status is None:
            self._last_status[game_id] = new_status
            return

        if last_status != new_status:
            logger.info(
                "Game status transition detected",
                game_id=game_id,
                from_status=last_status,
                to_status=new_status,
                home_team=data.get("home_team"),
                away_team=data.get("away_team"),
            )
            self._last_status[game_id] = new_status
