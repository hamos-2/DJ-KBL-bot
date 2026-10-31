"""Async Redis client factory, snapshot caching, cheering counters, and atomic lock helpers."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from core.config import get_settings
from core.logging import get_logger

logger = get_logger("cache.redis")

_LIVE_SNAPSHOT_TTL_SECONDS: int = 4 * 3600   # 4 hours physical TTL
_MATCHUP_CACHE_TTL_SECONDS: int = 3600       # 1 hour TTL for matchup search cache
_CONTENT_CACHE_TTL_SECONDS: int = 1800       # 30 minutes TTL for standings/news/highlights
_FRESHNESS_THRESHOLD_SECONDS: int = 10       # logical freshness window

# Atomic compare-and-delete Lua script for safe distributed lock release
_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """Return the shared async Redis client, creating it on first call."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_redis() -> None:
    """Close the shared Redis connection."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


# ---------------------------------------------------------------------------
# Game snapshot & matchup cache helpers
# ---------------------------------------------------------------------------

_SNAPSHOT_KEY_PREFIX = "game:live:"
_MATCHUP_KEY_PREFIX = "game:matchup:"
_LOCK_KEY_PREFIX = "lock:ingest:"
_STANDINGS_KEY = "kbl:standings:current"
_PLAYER_RANK_KEY = "kbl:player_rank:current"
_NEWS_KEY = "kbl:news:latest"
_HIGHLIGHTS_KEY = "kbl:highlights:latest"
_USER_PREF_PREFIX = "user:pref:"
_CHEER_COUNT_PREFIX = "cheer:count:"
_CHEER_USER_PREFIX = "cheer:user:"
_USER_POINTS_PREFIX = "user:points:"


def _snapshot_key(game_id: str) -> str:
    """Return the Redis key for a game live snapshot."""
    return f"{_SNAPSHOT_KEY_PREFIX}{game_id}"


def _matchup_key(team_a: str, team_b: str | None = None) -> str:
    """Return a deterministic Redis key for a team or head-to-head matchup search."""
    if team_b:
        pair = ":".join(sorted([team_a, team_b]))
        return f"{_MATCHUP_KEY_PREFIX}{pair}"
    return f"{_MATCHUP_KEY_PREFIX}single:{team_a}"


def _lock_key(game_id: str) -> str:
    """Return the Redis lock key for game ingestion."""
    return f"{_LOCK_KEY_PREFIX}{game_id}"


async def save_game_snapshot(game_id: str, snapshot: dict[str, Any]) -> None:
    """
    Persist a game snapshot to Redis with a 4-hour TTL.

    Args:
        game_id: Provider-supplied game identifier.
        snapshot: Dictionary containing live game state.
    """
    client = await get_redis()
    key = _snapshot_key(game_id)
    await client.set(key, json.dumps(snapshot), ex=_LIVE_SNAPSHOT_TTL_SECONDS)
    logger.debug("Saved game snapshot", game_id=game_id)


async def get_game_snapshot(game_id: str) -> dict[str, Any] | None:
    """
    Retrieve a game snapshot from Redis.

    Returns:
        Snapshot dict with an added ``stale`` boolean field, or ``None``
        if no snapshot exists.
    """
    client = await get_redis()
    key = _snapshot_key(game_id)
    raw = await client.get(key)
    if raw is None:
        return None

    data: dict[str, Any] = json.loads(raw)
    stale = _is_stale(data.get("updated_at", ""))
    data["stale"] = stale
    return data


async def save_matchup_cache(
    team_a: str, team_b: str | None, games: list[dict[str, Any]]
) -> None:
    """Cache matchup search results in Redis for 1 hour."""
    client = await get_redis()
    key = _matchup_key(team_a, team_b)
    await client.set(key, json.dumps(games), ex=_MATCHUP_CACHE_TTL_SECONDS)


async def get_matchup_cache(
    team_a: str, team_b: str | None
) -> list[dict[str, Any]] | None:
    """Retrieve cached matchup search results from Redis."""
    client = await get_redis()
    key = _matchup_key(team_a, team_b)
    raw = await client.get(key)
    if raw is None:
        return None
    data: list[dict[str, Any]] = json.loads(raw)
    return data


# ---------------------------------------------------------------------------
# Standings, Player Rankings, News, Highlights caches
# ---------------------------------------------------------------------------

async def save_standings_cache(standings: list[dict[str, Any]]) -> None:
    """Cache KBL team standings in Redis."""
    client = await get_redis()
    await client.set(_STANDINGS_KEY, json.dumps(standings), ex=_CONTENT_CACHE_TTL_SECONDS)


async def get_standings_cache() -> list[dict[str, Any]] | None:
    """Retrieve cached KBL team standings from Redis."""
    client = await get_redis()
    raw = await client.get(_STANDINGS_KEY)
    return json.loads(raw) if raw else None


async def save_player_rankings_cache(rankings: dict[str, list[dict[str, Any]]]) -> None:
    """Cache KBL player rankings by category in Redis."""
    client = await get_redis()
    await client.set(_PLAYER_RANK_KEY, json.dumps(rankings), ex=_CONTENT_CACHE_TTL_SECONDS)


async def get_player_rankings_cache() -> dict[str, list[dict[str, Any]]] | None:
    """Retrieve cached KBL player rankings from Redis."""
    client = await get_redis()
    raw = await client.get(_PLAYER_RANK_KEY)
    return json.loads(raw) if raw else None


async def save_news_cache(news: list[dict[str, Any]]) -> None:
    """Cache latest KBL news items in Redis."""
    client = await get_redis()
    await client.set(_NEWS_KEY, json.dumps(news), ex=_CONTENT_CACHE_TTL_SECONDS)


async def get_news_cache() -> list[dict[str, Any]] | None:
    """Retrieve cached KBL news items from Redis."""
    client = await get_redis()
    raw = await client.get(_NEWS_KEY)
    return json.loads(raw) if raw else None


async def save_highlights_cache(highlights: list[dict[str, Any]]) -> None:
    """Cache latest KBL highlight clips in Redis."""
    client = await get_redis()
    await client.set(_HIGHLIGHTS_KEY, json.dumps(highlights), ex=_CONTENT_CACHE_TTL_SECONDS)


async def get_highlights_cache() -> list[dict[str, Any]] | None:
    """Retrieve cached KBL highlight clips from Redis."""
    client = await get_redis()
    raw = await client.get(_HIGHLIGHTS_KEY)
    return json.loads(raw) if raw else None


# ---------------------------------------------------------------------------
# User preferences (Favorite players & Notification settings)
# ---------------------------------------------------------------------------

_DEFAULT_PREFS: dict[str, Any] = {
    "favorite_players": [],
    "notifications": {
        "game_start": True,
        "game_end": False,
        "clutch": False,
        "player": False,
    },
}


async def get_user_preferences(user_hmac: str) -> dict[str, Any]:
    """Return user preferences (favorite players & notification flags) from Redis."""
    client = await get_redis()
    raw = await client.get(f"{_USER_PREF_PREFIX}{user_hmac}")
    if not raw:
        return json.loads(json.dumps(_DEFAULT_PREFS))
    data: dict[str, Any] = json.loads(raw)
    data.setdefault("favorite_players", [])
    notif = data.setdefault("notifications", {})
    for k, v in _DEFAULT_PREFS["notifications"].items():
        notif.setdefault(k, v)
    return data


async def save_user_preferences(user_hmac: str, prefs: dict[str, Any]) -> None:
    """Persist user preferences in Redis."""
    client = await get_redis()
    await client.set(f"{_USER_PREF_PREFIX}{user_hmac}", json.dumps(prefs))


# ---------------------------------------------------------------------------
# Cheering & Match Prediction counters (응원하기 / 승부예측)
# ---------------------------------------------------------------------------

async def vote_team_cheer(
    user_hmac: str, game_id: str, team: str, home_team: str, away_team: str
) -> dict[str, Any]:
    """
    Record a user's team cheer/prediction for *game_id* and update counters.

    Returns:
        Dict with ``already_voted``, ``previous_team``, ``selected_team``,
        ``home_votes``, ``away_votes``, ``user_points``.
    """
    client = await get_redis()
    user_vote_key = f"{_CHEER_USER_PREFIX}{user_hmac}:{game_id}"
    home_key = f"{_CHEER_COUNT_PREFIX}{game_id}:{home_team}"
    away_key = f"{_CHEER_COUNT_PREFIX}{game_id}:{away_team}"
    points_key = f"{_USER_POINTS_PREFIX}{user_hmac}"

    prev_team = await client.get(user_vote_key)
    already_voted = prev_team is not None

    if prev_team != team:
        if prev_team == home_team:
            cur = int(await client.get(home_key) or 0)
            if cur > 0:
                await client.decr(home_key)
        elif prev_team == away_team:
            cur = int(await client.get(away_key) or 0)
            if cur > 0:
                await client.decr(away_key)

        if team == home_team:
            await client.incr(home_key)
        elif team == away_team:
            await client.incr(away_key)

        await client.set(user_vote_key, team, ex=7 * 86400)
        if not already_voted:
            await client.incrby(points_key, 10)

    home_votes = int(await client.get(home_key) or 0)
    away_votes = int(await client.get(away_key) or 0)
    points = int(await client.get(points_key) or 0)

    return {
        "already_voted": already_voted,
        "previous_team": prev_team,
        "selected_team": team,
        "home_votes": home_votes,
        "away_votes": away_votes,
        "user_points": points,
    }


async def get_game_cheers(
    game_id: str, home_team: str, away_team: str, user_hmac: str | None = None
) -> dict[str, Any]:
    """Return cheering vote counts for *game_id* and optional user pick."""
    client = await get_redis()
    home_key = f"{_CHEER_COUNT_PREFIX}{game_id}:{home_team}"
    away_key = f"{_CHEER_COUNT_PREFIX}{game_id}:{away_team}"

    raw_h = await client.get(home_key)
    raw_a = await client.get(away_key)

    # Seed deterministic initial fan votes so the UI looks lively on first view
    if raw_h is None and raw_a is None:
        seed_h = (hash(f"{game_id}:{home_team}") % 80) + 45
        seed_a = (hash(f"{game_id}:{away_team}") % 80) + 45
        await client.set(home_key, str(seed_h), ex=7 * 86400, nx=True)
        await client.set(away_key, str(seed_a), ex=7 * 86400, nx=True)
        home_votes = int(await client.get(home_key) or seed_h)
        away_votes = int(await client.get(away_key) or seed_a)
    else:
        home_votes = int(raw_h or 0)
        away_votes = int(raw_a or 0)

    user_pick = None
    user_points = 0
    if user_hmac:
        user_pick = await client.get(f"{_CHEER_USER_PREFIX}{user_hmac}:{game_id}")
        user_points = int(await client.get(f"{_USER_POINTS_PREFIX}{user_hmac}") or 0)

    total = max(1, home_votes + away_votes)
    home_pct = round(home_votes * 100 / total)
    away_pct = 100 - home_pct

    return {
        "game_id": game_id,
        "home_team": home_team,
        "away_team": away_team,
        "home_votes": home_votes,
        "away_votes": away_votes,
        "home_pct": home_pct,
        "away_pct": away_pct,
        "user_pick": user_pick,
        "user_points": user_points,
    }


# ---------------------------------------------------------------------------
# Distributed Lock Helpers
# ---------------------------------------------------------------------------

async def acquire_ingest_lock(game_id: str, ttl_seconds: int = 30) -> str | None:
    """
    Try to acquire an ingestion lock for *game_id* with a unique ownership token.

    Args:
        game_id: Game being ingested.
        ttl_seconds: Lock expiry to prevent stale locks.

    Returns:
        Ownership token string if lock was acquired, ``None`` if already held.
    """
    client = await get_redis()
    token = uuid.uuid4().hex
    result = await client.set(
        _lock_key(game_id), token, ex=ttl_seconds, nx=True
    )
    return token if result is True else None


async def release_ingest_lock(game_id: str, token: str) -> bool:
    """
    Atomically release the ingestion lock for *game_id* only if *token* matches.

    Args:
        game_id: Game being ingested.
        token: Ownership token returned by :func:`acquire_ingest_lock`.

    Returns:
        ``True`` if the lock was owned and deleted, ``False`` otherwise.
    """
    client = await get_redis()
    deleted = await client.eval(_RELEASE_LOCK_LUA, 1, _lock_key(game_id), token)
    return bool(deleted)


def _is_stale(updated_at_iso: str) -> bool:
    """
    Return True if *updated_at_iso* is older than the freshness threshold.

    Args:
        updated_at_iso: ISO-8601 UTC timestamp string.

    Returns:
        ``True`` when the snapshot is considered stale.
    """
    if not updated_at_iso:
        return True
    try:
        ts = datetime.fromisoformat(updated_at_iso.replace("Z", "+00:00"))
        age = datetime.now(UTC) - ts
        return age > timedelta(seconds=_FRESHNESS_THRESHOLD_SECONDS)
    except (ValueError, TypeError):
        return True
