"""PostgreSQL durability helpers for user preferences, prediction votes, and chunked FINAL settlement."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.cache.redis import (
    _current_kst_ym,
    _PREDICTION_ZSET_KEY,
    get_redis,
    save_user_preferences,
    settle_prediction_hit,
    update_user_streak,
)
from core.db.models import PredictionVote, UserAccountState
from core.db.session import get_session_factory
from core.logging import get_logger

logger = get_logger("service.user.persistence")


async def persist_user_preferences_db(
    db: AsyncSession, user_hmac: str, prefs: dict[str, Any]
) -> None:
    """Upsert favorite_players and notifications into PostgreSQL without blocking reads."""
    try:
        fav_json = json.dumps(prefs.get("favorite_players", []), ensure_ascii=False)
        notif_json = json.dumps(prefs.get("notifications", {}), ensure_ascii=False)
        now = datetime.now(UTC)
        stmt = (
            pg_insert(UserAccountState)
            .values(
                user_hmac=user_hmac,
                favorite_players_json=fav_json,
                notifications_json=notif_json,
                prediction_points=0,
                prediction_streak=0,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_hmac"],
                set_={
                    "favorite_players_json": fav_json,
                    "notifications_json": notif_json,
                    "updated_at": now,
                },
            )
        )
        await db.execute(stmt)
        await db.commit()
    except Exception as exc:
        logger.debug("Skipped DB preference persist (non-fatal)", error=str(exc))


async def hydrate_preferences_from_db(
    db: AsyncSession, user_hmac: str
) -> dict[str, Any] | None:
    """Restore user preferences into Redis from PostgreSQL if Redis cache missed."""
    try:
        res = await db.execute(
            select(UserAccountState).where(UserAccountState.user_hmac == user_hmac)
        )
        row = res.scalar_one_or_none()
        if row is None:
            return None
        prefs = {
            "favorite_players": json.loads(row.favorite_players_json or "[]"),
            "notifications": json.loads(row.notifications_json or "{}"),
        }
        await save_user_preferences(user_hmac, prefs)
        return prefs
    except Exception as exc:
        logger.debug("Skipped DB preference hydration", error=str(exc))
        return None


async def persist_prediction_vote_db(
    db: AsyncSession,
    user_hmac: str,
    game_id: str,
    selected_team: str,
    user_points: int,
) -> None:
    """Persist a user's match prediction vote and latest point balance in PostgreSQL."""
    try:
        now = datetime.now(UTC)
        vote_stmt = (
            pg_insert(PredictionVote)
            .values(
                user_hmac=user_hmac,
                game_id=str(game_id),
                selected_team=selected_team,
                settled=False,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_prediction_vote_user_game",
                set_={
                    "selected_team": selected_team,
                    "updated_at": now,
                },
            )
        )
        await db.execute(vote_stmt)

        acc_stmt = (
            pg_insert(UserAccountState)
            .values(
                user_hmac=user_hmac,
                favorite_players_json="[]",
                notifications_json="{}",
                prediction_points=int(user_points),
                prediction_streak=0,
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_hmac"],
                set_={
                    "prediction_points": int(user_points),
                    "updated_at": now,
                },
            )
        )
        await db.execute(acc_stmt)
        await db.commit()
    except Exception as exc:
        logger.debug("Skipped DB prediction vote persist (non-fatal)", error=str(exc))


async def hydrate_user_points_and_streak_from_db(
    db: AsyncSession, user_hmac: str
) -> tuple[int, int]:
    """Hydrate Redis points, streak, and ZSET from PostgreSQL when Redis evicted keys."""
    try:
        res = await db.execute(
            select(UserAccountState).where(UserAccountState.user_hmac == user_hmac)
        )
        row = res.scalar_one_or_none()
        if row is None:
            return 0, 0
        pts = int(row.prediction_points or 0)
        stk = int(row.prediction_streak or 0)
        client = await get_redis()
        if pts > 0:
            await client.setnx(f"user:points:{user_hmac}", str(pts))
            ym = _current_kst_ym()
            await client.zadd(_PREDICTION_ZSET_KEY, {user_hmac: pts})
            await client.zadd(f"kbl:prediction:zset:{ym}", {user_hmac: pts})
        if stk > 0:
            await client.setnx(f"user:streak:{user_hmac}", str(stk))
        return pts, stk
    except Exception as exc:
        logger.debug("Skipped DB points hydration", error=str(exc))
        return 0, 0


async def hydrate_user_vote_from_db(
    db: AsyncSession, user_hmac: str, game_id: str
) -> str | None:
    """Restore user's vote for *game_id* from PostgreSQL if Redis 7d TTL expired."""
    try:
        res = await db.execute(
            select(PredictionVote).where(
                PredictionVote.user_hmac == user_hmac,
                PredictionVote.game_id == str(game_id),
            )
        )
        row = res.scalar_one_or_none()
        if row is None:
            return None
        client = await get_redis()
        await client.set(f"cheer:user:{user_hmac}:{game_id}", row.selected_team, ex=7 * 86400, nx=True)
        return str(row.selected_team)
    except Exception:
        return None


async def persist_settlement_db(
    db: AsyncSession,
    user_hmac: str,
    game_id: str,
    is_hit: bool,
    total_points: int,
    streak: int,
    points_awarded: int,
) -> None:
    """Mark a PredictionVote settled and save updated user points/streak in PostgreSQL."""
    try:
        now = datetime.now(UTC)
        res = await db.execute(
            select(PredictionVote).where(
                PredictionVote.user_hmac == user_hmac,
                PredictionVote.game_id == str(game_id),
            )
        )
        vote = res.scalar_one_or_none()
        if vote is not None and not vote.settled:
            vote.settled = True
            vote.is_hit = is_hit
            vote.points_awarded = int(points_awarded)
            vote.updated_at = now

        acc_stmt = (
            pg_insert(UserAccountState)
            .values(
                user_hmac=user_hmac,
                favorite_players_json="[]",
                notifications_json="{}",
                prediction_points=int(total_points),
                prediction_streak=int(streak),
                updated_at=now,
            )
            .on_conflict_do_update(
                index_elements=["user_hmac"],
                set_={
                    "prediction_points": int(total_points),
                    "prediction_streak": int(streak),
                    "updated_at": now,
                },
            )
        )
        await db.execute(acc_stmt)
        await db.commit()
    except Exception as exc:
        logger.debug("Skipped DB settlement persist (non-fatal)", error=str(exc))


async def settle_game_predictions_chunked(
    game_data: dict[str, Any],
    chunk_size: int = 50,
    session_factory: Any = None,
) -> int:
    """
    Settle all unsettled PredictionVotes for a FINAL game in small chunks (default 50)
    with asyncio yields so 952 MiB OCI event loop & HTTP requests remain responsive.

    Returns total settled vote count.
    """
    if game_data.get("status") != "FINAL":
        return 0
    gid = str(game_data.get("game_id") or "").strip()
    h_team = str(game_data.get("home_team") or "")
    a_team = str(game_data.get("away_team") or "")
    h_score = game_data.get("home_score")
    a_score = game_data.get("away_score")
    if not gid or not h_team or not a_team or h_score is None or a_score is None:
        return 0
    if int(h_score) == int(a_score):
        return 0

    winner = h_team if int(h_score) > int(a_score) else a_team
    factory = session_factory or get_session_factory()
    settled_total = 0

    while True:
        async with factory() as db:
            res = await db.execute(
                select(PredictionVote)
                .where(PredictionVote.game_id == gid, PredictionVote.settled.is_(False))
                .limit(chunk_size)
            )
            votes = list(res.scalars().all())
            if not votes:
                break

            now = datetime.now(UTC)
            for vote in votes:
                u_hmac = vote.user_hmac
                is_hit = vote.selected_team == winner
                newly_awarded, cur_pts = await settle_prediction_hit(
                    u_hmac, gid, is_hit, bonus_points=50
                )
                streak_val, streak_bonus = await update_user_streak(u_hmac, is_hit)
                total_pts = cur_pts + streak_bonus
                awarded_pts = (50 if (is_hit and newly_awarded) else 0) + streak_bonus

                vote.settled = True
                vote.is_hit = is_hit
                vote.points_awarded = awarded_pts
                vote.updated_at = now

                acc_stmt = (
                    pg_insert(UserAccountState)
                    .values(
                        user_hmac=u_hmac,
                        favorite_players_json="[]",
                        notifications_json="{}",
                        prediction_points=int(total_pts),
                        prediction_streak=int(streak_val),
                        updated_at=now,
                    )
                    .on_conflict_do_update(
                        index_elements=["user_hmac"],
                        set_={
                            "prediction_points": int(total_pts),
                            "prediction_streak": int(streak_val),
                            "updated_at": now,
                        },
                    )
                )
                await db.execute(acc_stmt)
                settled_total += 1

            await db.commit()

        await asyncio.sleep(0)

    if settled_total > 0:
        logger.info(
            "Settled predictions on FINAL game",
            game_id=gid,
            winner=winner,
            settled_count=settled_total,
        )
    return settled_total
