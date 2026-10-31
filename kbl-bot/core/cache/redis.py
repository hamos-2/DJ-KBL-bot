"""Async Redis client factory, snapshot caching, and atomic lock helpers."""

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
