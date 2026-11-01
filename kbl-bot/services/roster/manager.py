"""Dynamic KBL Roster & Lineup Management Service.

Keeps all 10 KBL clubs' head coaches, starting 5s, active rosters, and player
statistics continuously updated during the regular season and playoffs.

Supports:
1. Automated periodic stats sync from live Daum leaderboard rankings.
2. In-season roster movements (trades, coach replacements, waivers, starting 5 rotations).
3. Redis persistence with fast in-memory query performance.
4. Strict constraint validation (retired legend Ham Ji-hoon excluded, Kim Sun-hyung excluded from SK).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from core.cache.redis import (
    append_roster_transaction_log,
    get_dynamic_roster_cache,
    save_dynamic_roster_cache,
)
from core.logging import get_logger
import services.content.kbl_data as kbl_data

logger = get_logger("service.roster")


class RosterIntegrityError(ValueError):
    """Raised when an operation would violate roster data integrity constraints."""
    pass


class RosterManager:
    """Central manager for active KBL rosters, starting lineups, and head coaches."""

    EXPECTED_TEAMS: set[str] = {
        "SK", "DB", "KT", "LG", "정관장", "KCC", "한국가스공사", "현대모비스", "소노", "삼성"
    }

    def __init__(self) -> None:
        # Working in-memory copies initialized from official baseline
        self._lineups: dict[str, dict[str, Any]] = copy.deepcopy(kbl_data.TEAM_LINEUPS)
        self._players: list[dict[str, Any]] = copy.deepcopy(kbl_data.KBL_PLAYERS)
        self._last_synced_at: str | None = None
        self._transactions: list[dict[str, Any]] = []

        # Validate initial baseline integrity immediately
        ok, errors = self.verify_roster_integrity()
        if not ok:
            raise RosterIntegrityError(f"Baseline roster integrity check failed: {errors}")

    # ---------------------------------------------------------------------------
    # Data Integrity & Invariant Validation
    # ---------------------------------------------------------------------------

    def verify_roster_integrity(self) -> tuple[bool, list[str]]:
        """
        Rigorously verify all 7 Golden Integrity Rules across all 10 clubs:
        1. 10-Club Totality: All 10 official KBL clubs must be present.
        2. Head Coach Integrity: Every club must have a valid non-empty head coach.
        3. Starting 5 Invariant: Every club must have exactly 5 starters.
        4. Schema & Position Invariant: Every starter has a valid position and uniform number.
        5. Zero Duplicate Starters: No player may be duplicated in any starter lineup.
        6. Exclusion Constraints: Retired Ham Ji-hoon must NEVER appear; Kim Sun-hyung NEVER at SK.
        7. Club-Player Coherence: Every starter exists in players with matching team code.
        8. Statistical Range Invariant: pts, reb, ast must be realistic non-negative floats.

        Returns:
            (is_valid: bool, error_list: list[str])
        """
        errors: list[str] = []

        # 1. 10-Club Totality
        existing_teams = set(self._lineups.keys())
        missing_teams = self.EXPECTED_TEAMS - existing_teams
        if missing_teams:
            errors.append(f"[Rule 1] Missing clubs in lineups: {missing_teams}")

        # Track starters across clubs for duplicate detection
        all_starter_names: set[str] = set()

        for team in self.EXPECTED_TEAMS:
            info = self._lineups.get(team)
            if not info:
                continue

            # 2. Head Coach
            coach = info.get("head_coach", "").strip()
            if not coach or len(coach) < 2:
                errors.append(f"[Rule 2] {team} has missing or invalid head coach: '{coach}'")

            # 3. Exactly 5 Starters
            starters = info.get("starters", [])
            if len(starters) != 5:
                errors.append(f"[Rule 3] {team} starters count is {len(starters)} (expected 5)")

            # Check individual starters
            team_starter_names: set[str] = set()
            for s in starters:
                name = s.get("name", "").strip()
                pos = s.get("pos", "").strip()
                no = str(s.get("no", "")).strip()

                # 4. Schema & Position
                if not name or len(name) < 2:
                    errors.append(f"[Rule 4] {team} has starter with invalid name: '{name}'")
                if pos not in ("G", "F", "C", "G/F", "F/C"):
                    errors.append(f"[Rule 4] {team} starter {name} has invalid pos: '{pos}'")
                if not no:
                    errors.append(f"[Rule 4] {team} starter {name} has missing uniform number")

                # 5. Duplicates within club
                if name in team_starter_names:
                    errors.append(f"[Rule 5] Duplicate starter in {team}: {name}")
                team_starter_names.add(name)

                # 5. Duplicates across clubs (allow homonyms like 이정현 if distinct teams/numbers exist in players)
                player_candidates = [p for p in self._players if p["name"] == name and p["team"] == team]
                if not player_candidates:
                    errors.append(f"[Rule 7] Starter {name} ({team}) not registered in active KBL_PLAYERS for {team}")
                elif len(player_candidates) > 1:
                    errors.append(f"[Rule 5] Duplicate player records for {name} within {team}")

                # 6. Exclusion constraints
                if name == "함지훈":
                    errors.append("[Rule 6] Critical invariant broken: Retired player 함지훈 found in starters")
                if team == "SK" and name == "김선형":
                    errors.append("[Rule 6] Critical invariant broken: 김선형 found in SK starters")

                # 7. Uniform number consistency
                if player_candidates:
                    p_rec = player_candidates[0]
                    if no and p_rec.get("no") and str(no) != str(p_rec.get("no")):
                        errors.append(
                            f"[Rule 4] Starter {name} ({team}) uniform number mismatch: lineup #{no} vs player #{p_rec.get('no')}"
                        )

        # 6. Exclusion constraints on player pool
        for p in self._players:
            p_name = p.get("name", "")
            p_team = p.get("team", "")
            if p_name == "함지훈":
                errors.append("[Rule 6] Critical invariant broken: Retired player 함지훈 found in active player pool")
            if p_team == "SK" and p_name == "김선형":
                errors.append("[Rule 6] Critical invariant broken: 김선형 registered with SK in active player pool")

            # 8. Stats Range
            for stat_k in ("pts", "reb", "ast", "stl", "blk"):
                val = p.get(stat_k)
                if val is not None:
                    try:
                        f_val = float(val)
                        if f_val < 0.0 or f_val > 50.0:
                            errors.append(f"[Rule 8] Player {p_name} has unrealistic {stat_k}: {f_val}")
                    except (ValueError, TypeError):
                        errors.append(f"[Rule 8] Player {p_name} has non-numeric {stat_k}: {val}")

        is_valid = len(errors) == 0
        return is_valid, errors

    # ---------------------------------------------------------------------------
    # Queries
    # ---------------------------------------------------------------------------

    def get_team_lineup(self, team: str) -> dict[str, Any] | None:
        """Return the lineup and head coach info for *team*."""
        if not team:
            return None
        t = team.strip()
        for k, info in self._lineups.items():
            if t == k or t in k or k in t:
                return copy.deepcopy(info)
        return None

    def get_players(self, team: str | None = None) -> list[dict[str, Any]]:
        """Return all active players, optionally filtered by canonical *team*."""
        if not team:
            return copy.deepcopy(self._players)
        t = team.strip()
        return [
            copy.deepcopy(p)
            for p in self._players
            if p.get("team") == t or (p.get("team") and t in p["team"])
        ]

    def get_player_by_name(self, name: str) -> dict[str, Any] | None:
        """Find a player by exact name or substring."""
        if not name:
            return None
        n = name.strip()
        for p in self._players:
            if p["name"] == n:
                return copy.deepcopy(p)
        for p in self._players:
            if n in p["name"]:
                return copy.deepcopy(p)
        return None

    def search_players(self, query: str) -> list[dict[str, Any]]:
        """Search players by name substring or team code."""
        import re
        cleaned = re.sub(r"^(#?\s*(관심선수|선수검색|선수|추가|등록|삭제)\s*)+", "", query.strip()).strip()
        if not cleaned:
            return copy.deepcopy(self._players[:5])
        matches = []
        for p in self._players:
            if cleaned in p["name"] or p["name"] in cleaned or cleaned.upper() == p["team"].upper():
                matches.append(copy.deepcopy(p))
        return matches

    # ---------------------------------------------------------------------------
    # In-Season Mutations
    # ---------------------------------------------------------------------------

    def update_head_coach(self, team: str, new_coach: str, reason: str = "") -> dict[str, Any]:
        """Update the head coach for a club (e.g. mid-season dismissal or interim appointment)."""
        norm_t = self._normalize_team(team)
        if norm_t not in self._lineups:
            raise ValueError(f"Unknown team: {team}")

        old_coach = self._lineups[norm_t].get("head_coach", "")
        self._lineups[norm_t]["head_coach"] = new_coach

        entry = {
            "type": "COACH_CHANGE",
            "team": norm_t,
            "old_coach": old_coach,
            "new_coach": new_coach,
            "reason": reason or "Mid-season head coach update",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._record_transaction(entry)
        self._sync_back_to_kbl_data()
        logger.info("Head coach updated", **entry)
        return entry

    def transfer_player(
        self,
        player_name: str,
        new_team: str,
        pos: str | None = None,
        back_number: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Transfer an existing player to a new team or register a newly acquired player."""
        norm_t = self._normalize_team(new_team)

        # Enforce user constraint: Kim Sun-hyung cannot be transferred to SK
        if player_name == "김선형" and norm_t == "SK":
            raise ValueError("Constraint violation: 김선형 cannot be registered with SK")

        found_player = next((p for p in self._players if p["name"] == player_name), None)
        old_team = found_player["team"] if found_player else None

        if found_player:
            found_player["team"] = norm_t
            if pos:
                found_player["pos"] = pos
            if back_number:
                found_player["no"] = back_number
        else:
            found_player = {
                "name": player_name,
                "team": norm_t,
                "pos": pos or "G/F",
                "no": back_number or "0",
                "pts": 10.0,
                "reb": 3.0,
                "ast": 2.0,
                "tpm": 1.0,
                "stl": 0.8,
                "blk": 0.3,
            }
            self._players.append(found_player)

        # If transferred, remove from old team starters if present
        if old_team and old_team in self._lineups:
            old_starters = self._lineups[old_team].get("starters", [])
            self._lineups[old_team]["starters"] = [
                s for s in old_starters if s.get("name") != player_name
            ]

        entry = {
            "type": "PLAYER_TRANSFER",
            "player": player_name,
            "old_team": old_team,
            "new_team": norm_t,
            "reason": reason or "Mid-season player transfer",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._record_transaction(entry)
        self._sync_back_to_kbl_data()
        logger.info("Player transferred", **entry)
        return entry

    def update_starters(
        self, team: str, starters: list[dict[str, str]], reason: str = ""
    ) -> dict[str, Any]:
        """Update the official starting 5 for a club (must contain exactly 5 players)."""
        norm_t = self._normalize_team(team)
        if norm_t not in self._lineups:
            raise ValueError(f"Unknown team: {team}")
        if len(starters) != 5:
            raise ValueError(f"Starters must contain exactly 5 players, got {len(starters)}")

        # Enforce constraints
        for s in starters:
            if s.get("name") == "함지훈":
                raise ValueError("Constraint violation: Retired player 함지훈 cannot be a starter")
            if s.get("name") == "김선형" and norm_t == "SK":
                raise ValueError("Constraint violation: 김선형 cannot be an SK starter")

        old_starters = [s["name"] for s in self._lineups[norm_t].get("starters", [])]
        self._lineups[norm_t]["starters"] = copy.deepcopy(starters)

        entry = {
            "type": "STARTERS_UPDATE",
            "team": norm_t,
            "old_starters": old_starters,
            "new_starters": [s["name"] for s in starters],
            "reason": reason or "Starting 5 tactical adjustment",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._record_transaction(entry)
        self._sync_back_to_kbl_data()
        logger.info("Starters updated", **entry)
        return entry

    def retire_or_waive_player(self, player_name: str, team: str, reason: str = "") -> dict[str, Any]:
        """Remove a retired or waived player from active rosters and starting 5s."""
        norm_t = self._normalize_team(team)
        self._players = [
            p for p in self._players if not (p["name"] == player_name and p["team"] == norm_t)
        ]
        if norm_t in self._lineups:
            starters = self._lineups[norm_t].get("starters", [])
            self._lineups[norm_t]["starters"] = [
                s for s in starters if s.get("name") != player_name
            ]

        entry = {
            "type": "PLAYER_WAIVED",
            "player": player_name,
            "team": norm_t,
            "reason": reason or "Player waiver / retirement",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._record_transaction(entry)
        self._sync_back_to_kbl_data()
        logger.info("Player waived", **entry)
        return entry

    # ---------------------------------------------------------------------------
    # Automated Live Ingestion Sync
    # ---------------------------------------------------------------------------

    def sync_with_live_leaderboard(
        self, rankings: dict[str, list[dict[str, Any]]]
    ) -> int:
        """
        Dynamically update player season stats (pts, ast, reb, blk, stl) from
        official Daum Search KBL leaderboards.

        Returns:
            Number of players whose stats were refreshed.
        """
        if not rankings:
            return 0

        updated_count = 0
        for cat, items in rankings.items():
            if not isinstance(items, list):
                continue
            for item in items:
                p_name = item.get("name")
                if not p_name or p_name == "?":
                    continue

                player = next((p for p in self._players if p["name"] == p_name), None)
                if player:
                    # Update statistical metric
                    if cat in ("pts", "ast", "reb", "stl", "blk"):
                        new_val = item.get(cat) or item.get("value")
                        if new_val is not None:
                            try:
                                player[cat] = float(new_val)
                                updated_count += 1
                            except (ValueError, TypeError):
                                pass

        self._last_synced_at = datetime.now(UTC).isoformat()
        self._sync_back_to_kbl_data()
        logger.debug("Leaderboard stats synced into active roster", updated_count=updated_count)
        return updated_count

    # ---------------------------------------------------------------------------
    # Redis Persistence
    # ---------------------------------------------------------------------------

    async def save_to_cache(self) -> None:
        """Save current in-memory lineups, players, and sync timestamp to Redis."""
        ok, errors = self.verify_roster_integrity()
        if not ok:
            logger.error("Refusing to persist invalid roster state to cache", errors=errors)
            return

        payload = {
            "lineups": self._lineups,
            "players": self._players,
            "last_synced_at": self._last_synced_at,
            "version": "1.0",
        }
        await save_dynamic_roster_cache(payload)
        logger.info("Roster state saved to Redis cache (integrity verified)", players_count=len(self._players))

    async def load_from_cache(self) -> bool:
        """
        Load dynamic roster overrides from Redis cache if present and valid.
        Automatically heals to clean baseline if cache fails integrity validation.
        Returns True if overrides were applied.
        """
        cached = await get_dynamic_roster_cache()
        if not cached:
            return False

        lineups = cached.get("lineups")
        players = cached.get("players")
        if lineups and isinstance(lineups, dict) and players and isinstance(players, list):
            prev_lineups, prev_players = self._lineups, self._players
            self._lineups = copy.deepcopy(lineups)
            self._players = copy.deepcopy(players)

            is_valid, errors = self.verify_roster_integrity()
            if not is_valid:
                logger.warning(
                    "Dynamic roster cache failed integrity validation; auto-healing to baseline",
                    errors=errors,
                )
                self._lineups = prev_lineups
                self._players = prev_players
                self._sync_back_to_kbl_data()
                await self.save_to_cache()
                return False

            self._last_synced_at = cached.get("last_synced_at")
            self._sync_back_to_kbl_data()
            logger.info("Restored dynamic roster from Redis cache (integrity verified)", players_count=len(self._players))
            return True

        return False

    # ---------------------------------------------------------------------------
    # Internal Helpers
    # ---------------------------------------------------------------------------

    def _record_transaction(self, entry: dict[str, Any]) -> None:
        """Record transaction locally and schedule async Redis append if loop is active."""
        ok, errors = self.verify_roster_integrity()
        if not ok:
            raise RosterIntegrityError(f"Roster transaction violates integrity invariants: {errors}")
        import asyncio
        self._transactions.append(entry)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(append_roster_transaction_log(entry))
            loop.create_task(self.save_to_cache())
        except RuntimeError:
            pass

    def _sync_back_to_kbl_data(self) -> None:
        """
        Synchronize dynamic working state back to module-level ``kbl_data.KBL_PLAYERS``
        and ``kbl_data.TEAM_LINEUPS`` so all existing builder imports reflect it immediately.
        """
        kbl_data.KBL_PLAYERS.clear()
        kbl_data.KBL_PLAYERS.extend(self._players)

        kbl_data.TEAM_LINEUPS.clear()
        kbl_data.TEAM_LINEUPS.update(self._lineups)

    @staticmethod
    def _normalize_team(team: str) -> str:
        """Normalize various club aliases to standard canonical keys."""
        from services.search.parser import normalize_team_name
        return normalize_team_name(team)


# Singleton instance
_roster_manager: RosterManager | None = None


def get_roster_manager() -> RosterManager:
    """Return the singleton RosterManager instance."""
    global _roster_manager
    if _roster_manager is None:
        _roster_manager = RosterManager()
    return _roster_manager
