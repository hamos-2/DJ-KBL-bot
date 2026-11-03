"""Game domain service — strictly separates Read Path (DB/Redis) from Worker Ingestion."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache.redis import (
    get_game_snapshot,
    get_game_snapshots_bulk,
    get_highlights_cache,
    get_matchup_cache,
    get_news_cache,
    get_player_rankings_cache,
    get_redis,
    get_standings_cache,
    save_game_snapshot,
    save_matchup_cache,
    save_player_rankings_cache,
    save_standings_cache,
)
from core.db.models import Game
from core.exceptions import GameNotFoundError
from core.logging import get_logger
from core.season import get_current_season
from services.content.kbl_data import (
    build_highlights_from_games,
    compute_standings_from_games,
    get_default_player_rankings,
    parse_daum_news_html,
)
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


def _sort_news_by_team_relevance(
    news_items: list[dict[str, Any]], team: str
) -> list[dict[str, Any]]:
    """
    Sort news items so dedicated articles featuring *team*'s stars, head coach,
    or club name prominently appear at the top, pushing generic multi-game roundups down.
    """
    from services.content.kbl_data import get_team_lineup

    lineup = get_team_lineup(team) or {}
    coach = str(lineup.get("head_coach") or "")
    starters = [s.get("name", "") for s in lineup.get("starters", [])]
    player_keywords = set()
    for s in starters:
        for part in s.split():
            if len(part) >= 2:
                player_keywords.add(part)
    if coach and len(coach) >= 2:
        player_keywords.add(coach)

    def _score(item: dict[str, Any]) -> int:
        title = item.get("title", "")
        has_player = any(k in title for k in player_keywords)
        has_team_prominent = (
            title.startswith(f"[{team}")
            or title.startswith(f"'{team}")
            or f" {team} " in title
            or f"{team}," in title
            or f"{team}는" in title
            or f"{team}가" in title
            or f"{team}의" in title
        )
        if has_player and has_team_prominent:
            return 0
        if has_player:
            return 1
        if has_team_prominent:
            return 2
        if team in title:
            return 3
        return 4

    return sorted(news_items, key=_score)


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
        Uses a short 30-second Redis outline cache to avoid repeated DB scans.
        """
        query_date = target_date or today_kst()
        cache_key = f"game:today_outline:{query_date.isoformat()}"
        cached_outline = None
        try:
            client = await get_redis()
            raw = await client.get(cache_key)
            if raw:
                cached_outline = json.loads(raw)
        except Exception:
            pass

        if cached_outline is None:
            start_utc, end_utc = kst_day_bounds_utc(query_date)
            stmt = (
                select(Game)
                .where(Game.start_time >= start_utc, Game.start_time < end_utc)
                .order_by(Game.start_time.asc())
            )
            result = await db.execute(stmt)
            db_games = list(result.scalars().all())

            if not db_games:
                try:
                    provider_games = await self._provider.get_schedule(query_date)
                    for pg in provider_games:
                        await self._upsert_game(db, pg)
                        await save_game_snapshot(str(pg["game_id"]), pg)
                    await db.commit()
                    if provider_games:
                        return provider_games
                except Exception as exc:
                    logger.warning("Provider fallback for today games failed", error=str(exc))

            cached_outline = [self._game_to_dict(g) for g in db_games]
            if cached_outline:
                try:
                    client = await get_redis()
                    await client.set(cache_key, json.dumps(cached_outline), ex=30)
                except Exception:
                    pass

        snap_map = await get_game_snapshots_bulk([g["game_id"] for g in cached_outline])

        games_out: list[dict[str, Any]] = []
        for g in cached_outline:
            item = dict(g)
            snapshot = snap_map.get(g["game_id"])
            if snapshot is not None:
                item.update(snapshot)
            games_out.append(item)
        return games_out

    async def get_live_snapshot(self, game_id: str) -> dict[str, Any]:
        """
        Return the live snapshot for *game_id*, refreshing on-demand from provider if missing.
        Uses stale-while-revalidate to return cached data immediately (< 5ms) without blocking on HTTP.
        """
        snapshot = await get_game_snapshot(game_id)
        if snapshot is None:
            try:
                fresh = await self._provider.get_live_score(game_id)
                await save_game_snapshot(game_id, fresh)
                return fresh
            except Exception as exc:
                logger.warning("On-demand live score refresh failed", game_id=game_id, error=str(exc))
                raise GameNotFoundError(game_id)

        if snapshot.get("stale"):
            asyncio.create_task(self._background_refresh_snapshot(game_id))

        return snapshot

    async def _background_refresh_snapshot(self, game_id: str) -> None:
        """Asynchronously refresh snapshot in Redis without blocking user response."""
        try:
            fresh = await self._provider.get_live_score(game_id)
            await save_game_snapshot(game_id, fresh)
        except Exception as exc:
            logger.debug("Background snapshot refresh failed", game_id=game_id, error=str(exc))

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
            snap_map = await get_game_snapshots_bulk([str(item["game_id"]) for item in cached])
            for item in cached:
                snap = snap_map.get(str(item["game_id"]))
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

        # 3. If DB is empty, sync from provider on-demand
        if not rows and hasattr(self._provider, "get_schedule_range"):
            try:
                provider_games = await self._provider.get_schedule_range(
                    today_kst() - timedelta(days=7), today_kst() + timedelta(days=14)
                )
                for pg in provider_games:
                    await self._upsert_game(db, pg)
                    await save_game_snapshot(str(pg["game_id"]), pg)
                await db.commit()
                res = await db.execute(upcoming_stmt)
                rows = list(res.scalars().all())
            except Exception as exc:
                logger.warning("Matchup search provider fallback failed", error=str(exc))

        snap_map = await get_game_snapshots_bulk([g.provider_id for g in rows])
        games_out: list[dict[str, Any]] = []
        for g in rows:
            item = self._game_to_dict(g)
            snap = snap_map.get(g.provider_id)
            if snap is not None:
                item.update(snap)
            games_out.append(item)

        if games_out:
            await save_matchup_cache(team_a, team_b, games_out)

        return games_out

    async def get_kbl_schedule(
        self,
        db: AsyncSession,
        days: int = 7,
        team: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Return upcoming KBL schedule from today to ``today + days`` from PostgreSQL + Redis.
        """
        start_utc, _ = kst_day_bounds_utc(today_kst())
        _, end_utc = kst_day_bounds_utc(today_kst() + timedelta(days=days))

        stmt = select(Game).where(Game.start_time >= start_utc, Game.start_time < end_utc)
        if team:
            stmt = stmt.where(or_(Game.home_team == team, Game.away_team == team))
        stmt = stmt.order_by(Game.start_time.asc()).limit(limit)

        res = await db.execute(stmt)
        rows = list(res.scalars().all())

        if not rows and hasattr(self._provider, "get_schedule_range"):
            try:
                provider_games = await self._provider.get_schedule_range(
                    today_kst(), today_kst() + timedelta(days=days)
                )
                for pg in provider_games:
                    await self._upsert_game(db, pg)
                    await save_game_snapshot(str(pg["game_id"]), pg)
                await db.commit()
                res = await db.execute(stmt)
                rows = list(res.scalars().all())
            except Exception as exc:
                logger.warning("Schedule provider fallback failed", error=str(exc))

        snap_map = await get_game_snapshots_bulk([g.provider_id for g in rows])
        out: list[dict[str, Any]] = []
        for g in rows:
            item = self._game_to_dict(g)
            snap = snap_map.get(g.provider_id)
            if snap is not None:
                item.update(snap)
            out.append(item)
        return out

    async def get_recent_results(
        self,
        db: AsyncSession,
        team: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """
        Return recently finished (or currently live) KBL games from PostgreSQL + Redis.
        """
        stmt = select(Game).where(Game.status.in_(["FINAL", "LIVE"]))
        if team:
            stmt = stmt.where(or_(Game.home_team == team, Game.away_team == team))
        stmt = stmt.order_by(Game.start_time.desc()).limit(limit)

        res = await db.execute(stmt)
        rows = list(res.scalars().all())

        if not rows and hasattr(self._provider, "get_schedule_range"):
            try:
                provider_games = await self._provider.get_schedule_range(
                    today_kst() - timedelta(days=14), today_kst() + timedelta(days=1)
                )
                for pg in provider_games:
                    await self._upsert_game(db, pg)
                    await save_game_snapshot(str(pg["game_id"]), pg)
                await db.commit()
                res = await db.execute(stmt)
                rows = list(res.scalars().all())
            except Exception as exc:
                logger.warning("Recent results provider fallback failed", error=str(exc))
        snap_map = await get_game_snapshots_bulk([g.provider_id for g in rows])
        out: list[dict[str, Any]] = []
        for g in rows:
            item = self._game_to_dict(g)
            snap = snap_map.get(g.provider_id)
            if snap is not None:
                item.update(snap)
            out.append(item)
        return out

    # Alias for backwards compatibility
    get_kbl_results = get_recent_results

    async def get_team_standings(self, db: AsyncSession) -> list[dict[str, Any]]:
        """
        Return 10-team KBL standings from Redis cache, or query provider/DB if cache misses.
        """
        cached = await get_standings_cache()
        if cached:
            return cached

        # Try live official standings from provider first
        try:
            provider_standings = await self._provider.get_standings(get_current_season())
            if provider_standings and len(provider_standings) >= 10:
                await save_standings_cache(provider_standings)
                return provider_standings
        except Exception as exc:
            logger.warning("Failed to fetch live standings from provider, falling back to DB", error=str(exc))

        stmt = select(Game).where(Game.status == "FINAL").order_by(Game.start_time.asc())
        res = await db.execute(stmt)
        rows = [self._game_to_dict(g) for g in res.scalars().all()]
        standings = compute_standings_from_games(rows)
        await save_standings_cache(standings)
        return standings

    async def get_player_rankings(self, category: str = "pts") -> list[dict[str, Any]]:
        """
        Return top KBL player rankings for *category* (``pts``, ``ast``, ``reb``, ``stl``, ``blk``, ``tpm``).
        Ensures a minimum of 5 ranked players by blending live leaders with the verified league leaderboard.
        """
        cached = await get_player_rankings_cache()
        if not cached:
            # Try fetching from provider
            get_player_ranks_fn = getattr(self._provider, "get_player_rankings", None)
            if callable(get_player_ranks_fn):
                try:
                    cached = await get_player_ranks_fn()
                    if cached and any(cached.values()):
                        from core.cache.redis import save_player_rankings_cache
                        await save_player_rankings_cache(cached)
                except Exception as exc:
                    logger.warning("Failed to fetch player rankings from provider", error=str(exc))
            if not cached:
                cached = get_default_player_rankings()

        raw_list = cached.get(category, cached.get("pts", []))
        defaults = get_default_player_rankings().get(category, [])

        if len(raw_list) >= 5:
            return raw_list[:5]

        # Blend: live leader at #1 + distinct top default players for ranks 2..5
        combined = [dict(p) for p in raw_list]
        seen_names = {p["name"] for p in combined if "name" in p}
        for dp in defaults:
            if dp["name"] not in seen_names:
                item = dict(dp)
                item["rank"] = len(combined) + 1
                combined.append(item)
                seen_names.add(dp["name"])
            if len(combined) >= 5:
                break
        return combined

    async def get_latest_news(
        self, db: AsyncSession | None = None, team: str | None = None
    ) -> list[dict[str, Any]]:
        """Return cached latest KBL news items from Redis (optionally tailored to a specific team)."""
        cache_key = f"game:news:{team}" if team else "game:news:all"
        try:
            client = await get_redis()
            raw = await client.get(cache_key)
            if raw:
                return json.loads(raw)

            # Check pre-synced news cache from IngestionWorker
            raw_worker = await client.get("kbl:news:latest")
            if raw_worker:
                all_news = json.loads(raw_worker)
                if not team:
                    return all_news
                team_news = [
                    item for item in all_news
                    if team in item.get("title", "") or team in item.get("description", "")
                ]
                if len(team_news) >= 3:
                    team_news = _sort_news_by_team_relevance(team_news, team)
                    await client.set(cache_key, json.dumps(team_news), ex=600)
                    return team_news
        except Exception:
            pass

        recent = await self.get_recent_results(db, team=team, limit=8) if db is not None else []
        get_news_fn = getattr(self._provider, "get_news", None)
        if callable(get_news_fn):
            items = await get_news_fn(team=team, recent_games=recent)
        else:
            items = parse_daum_news_html("", recent, team=team)

        if items and team:
            items = _sort_news_by_team_relevance(items, team)

        if items:
            try:
                client = await get_redis()
                await client.set(cache_key, json.dumps(items), ex=600)
            except Exception:
                pass
        return items

    async def get_latest_highlights(
        self, db: AsyncSession, team: str | None = None
    ) -> list[dict[str, Any]]:
        """Return cached latest KBL highlight clips from Redis (optionally tailored to a specific team)."""
        cache_key = f"game:highlights:{team}" if team else "game:highlights:all"
        try:
            client = await get_redis()
            raw = await client.get(cache_key)
            if raw:
                return json.loads(raw)

            # Check pre-synced highlights cache from IngestionWorker
            raw_worker = await client.get("kbl:highlights:latest")
            if raw_worker:
                all_hl = json.loads(raw_worker)
                if not team:
                    return all_hl
                team_hl = [item for item in all_hl if team in item.get("title", "")]
                if len(team_hl) >= 2:
                    await client.set(cache_key, json.dumps(team_hl), ex=600)
                    return team_hl
        except Exception:
            pass

        recent = await self.get_recent_results(db, team=team, limit=6)
        items = build_highlights_from_games(recent, team=team)

        if items:
            try:
                client = await get_redis()
                await client.set(cache_key, json.dumps(items), ex=600)
            except Exception:
                pass
        return items

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
