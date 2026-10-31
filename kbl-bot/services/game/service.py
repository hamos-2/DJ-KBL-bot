"""Game domain service — strictly separates Read Path (DB/Redis) from Worker Ingestion."""

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache.redis import (
    get_game_snapshot,
    get_matchup_cache,
    save_game_snapshot,
    save_matchup_cache,
)
from core.db.models import Game
from core.exceptions import GameNotFoundError
from core.logging import get_logger
from services.provider.interface import SportsDataProvider

logger = get_logger("service.game")

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> date:
    """Return the current calendar date in Asia/Seoul (KST)."""
    return datetime.now(KST).date()


def kst_day_bounds_utc(target_date: date) -> tuple[datetime, datetime]:
    """
    Return the UTC start (inclusive) and end (exclusive) timestamps for *target_date* in KST.

    Args:
        target_date: Calendar date in KST.

    Returns:
        Tuple of ``(start_utc, end_utc)``.
    """
    start_kst = datetime.combine(target_date, datetime.min.time(), tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(UTC), end_kst.astimezone(UTC)


class GameService:
    """
    Handles game retrieval, matchup search, snapshot persistence, and stale detection.

    Read-path methods (:meth:`get_today_games`, :meth:`get_live_snapshot`,
    :meth:`search_matchup`) NEVER call the external provider directly.
    """

    def __init__(self, provider: SportsDataProvider) -> None:
        """
        Initialise GameService.

        Args:
            provider: Active SportsDataProvider adapter (used ONLY by background worker sync).
        """
        self._provider = provider

    # ------------------------------------------------------------------
    # Read Path (Kakao Skill endpoints — Redis & DB ONLY)
    # ------------------------------------------------------------------

    async def get_today_games(
        self, db: AsyncSession, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """
        Return today's KBL games from PostgreSQL overlaid with fresh Redis live snapshots.

        Strictly adheres to Rule 1 & Rule 2: never calls the external provider.

        Args:
            db: Async SQLAlchemy session.
            target_date: Optional KST date override (defaults to today in KST).

        Returns:
            List of canonical game dicts ordered by start_time.
        """
        query_date = target_date or today_kst()
        start_utc, end_utc = kst_day_bounds_utc(query_date)

        stmt = (
            select(Game)
            .where(Game.start_time >= start_utc, Game.start_time < end_utc)
            .order_by(Game.start_time.asc())
        )
        result = await db.execute(stmt)
        db_games = result.scalars().all()

        games_out: list[dict[str, Any]] = []
        for g in db_games:
            item = self._game_to_dict(g)
            # Overlay latest Redis snapshot if available
            snapshot = await get_game_snapshot(g.provider_id)
            if snapshot is not None:
                item.update(snapshot)
            games_out.append(item)
        return games_out

    async def get_live_snapshot(self, game_id: str) -> dict[str, Any]:
        """
        Return the cached Redis snapshot for *game_id*.

        This method NEVER calls the provider — it reads from Redis only.

        Args:
            game_id: Provider-supplied game identifier.

        Returns:
            Snapshot dict (may have ``stale=True`` if older than 10 s).

        Raises:
            GameNotFoundError: If no snapshot exists in Redis.
        """
        snapshot = await get_game_snapshot(game_id)
        if snapshot is None:
            raise GameNotFoundError(game_id)
        return snapshot

    async def search_matchup(
        self,
        db: AsyncSession,
        team_a: str,
        team_b: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Search upcoming (or most recent) games for *team_a* vs *team_b* (or *team_a* alone).

        Reads from Redis matchup cache first, then PostgreSQL, overlaying any live
        Redis snapshots. Never calls the external provider on the Read Path.

        Args:
            db: Async SQLAlchemy session.
            team_a: Canonical team code (e.g. ``"KT"``).
            team_b: Optional second canonical team code (e.g. ``"LG"``).
            limit: Maximum number of games to return.

        Returns:
            List of canonical game dicts (upcoming games prioritized).
        """
        cached = await get_matchup_cache(team_a, team_b)
        if cached is not None:
            for item in cached:
                snap = await get_game_snapshot(item["game_id"])
                if snap is not None:
                    item.update(snap)
            return cached[:limit]

        start_today_utc, _ = kst_day_bounds_utc(today_kst())

        if team_b:
            team_filter = or_(
                and_(Game.home_team == team_a, Game.away_team == team_b),
                and_(Game.home_team == team_b, Game.away_team == team_a),
            )
        else:
            team_filter = or_(Game.home_team == team_a, Game.away_team == team_a)

        # 1. Look for upcoming or today's games first
        upcoming_stmt = (
            select(Game)
            .where(team_filter, Game.start_time >= start_today_utc)
            .order_by(Game.start_time.asc())
            .limit(limit)
        )
        res = await db.execute(upcoming_stmt)
        rows = list(res.scalars().all())

        # 2. If no upcoming games in DB, include most recent finished games
        if not rows:
            recent_stmt = (
                select(Game)
                .where(team_filter)
                .order_by(Game.start_time.desc())
                .limit(limit)
            )
            res = await db.execute(recent_stmt)
            rows = list(res.scalars().all())

        games_out: list[dict[str, Any]] = []
        for g in rows:
            item = self._game_to_dict(g)
            snap = await get_game_snapshot(g.provider_id)
            if snap is not None:
                item.update(snap)
            games_out.append(item)

        if games_out:
            await save_matchup_cache(team_a, team_b, games_out)

        return games_out

    # ------------------------------------------------------------------
    # Ingestion Path (Called ONLY by background IngestionWorker)
    # ------------------------------------------------------------------

    async def sync_schedule_window(
        self,
        db: AsyncSession,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """
        Fetch schedule range from provider and upsert into PostgreSQL + Redis.

        Called exclusively by :class:`IngestionWorker`.
        """
        provider_games = await self._provider.get_schedule_range(start_date, end_date)
        for pg in provider_games:
            await self.upsert_game(db, pg)
            await save_game_snapshot(pg["game_id"], pg)
        await db.commit()
        logger.info(
            "Schedule window synced",
            start_date=str(start_date),
            end_date=str(end_date),
            count=len(provider_games),
        )
        return provider_games

    async def refresh_snapshot_from_provider(
        self, game_id: str, db: AsyncSession
    ) -> dict[str, Any]:
        """
        Poll the provider and refresh both Redis snapshot and PostgreSQL for *game_id*.

        Called ONLY from the background ingestion worker.
        """
        data = await self._provider.get_live_score(game_id)
        await save_game_snapshot(game_id, data)
        await self.upsert_game(db, data)
        await db.commit()
        logger.debug("Snapshot refreshed", game_id=game_id, status=data.get("status"))
        return data

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _game_to_dict(game: Game) -> dict[str, Any]:
        """Convert a Game ORM instance to a canonical dict."""
        return {
            "game_id": game.provider_id,
            "home_team": game.home_team,
            "away_team": game.away_team,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "period": game.period,
            "game_clock": game.game_clock,
            "arena": game.arena,
            "game_url": game.game_url,
            "status": game.status,
            "start_time": game.start_time.isoformat() if game.start_time else None,
            "updated_at": game.updated_at.isoformat() if game.updated_at else None,
        }

    @staticmethod
    async def upsert_game(db: AsyncSession, data: dict[str, Any]) -> None:
        """Insert or update a Game row from canonical dict *data*."""
        stmt = select(Game).where(Game.provider_id == str(data["game_id"]))
        result = await db.execute(stmt)
        game = result.scalar_one_or_none()

        start_time_raw = data.get("start_time")
        if isinstance(start_time_raw, str):
            start_time = datetime.fromisoformat(start_time_raw.replace("Z", "+00:00"))
        elif isinstance(start_time_raw, datetime):
            start_time = start_time_raw
        else:
            start_time = datetime.now(UTC)

        if game is None:
            game = Game(
                provider_id=str(data["game_id"]),
                home_team=data["home_team"],
                away_team=data["away_team"],
                home_score=data.get("home_score"),
                away_score=data.get("away_score"),
                period=data.get("period"),
                game_clock=data.get("game_clock"),
                arena=data.get("arena"),
                game_url=data.get("game_url"),
                status=data.get("status", "SCHEDULED"),
                start_time=start_time,
            )
            db.add(game)
        else:
            game.home_score = data.get("home_score")
            game.away_score = data.get("away_score")
            game.period = data.get("period")
            game.game_clock = data.get("game_clock")
            game.arena = data.get("arena", game.arena)
            game.game_url = data.get("game_url", game.game_url)
            game.status = data.get("status", game.status)
            game.updated_at = datetime.now(UTC)
