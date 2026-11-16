"""QA tests for real-time lineup change detection, auto-sync, and cache invalidation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import services.content.kbl_data as kbl_data
from services.content.lineup_board import (
    get_cached_board_image,
    get_cached_game_lineup,
    invalidate_lineup_caches,
    set_cached_board_image,
    set_cached_game_lineup,
)
from services.ingestion.worker import IngestionWorker
from services.roster.manager import RosterManager


def test_sync_from_official_match_lineup_detects_change_and_preserves_integrity() -> None:
    """When a club's official starting 5 changes (including a brand-new replacement),
    RosterManager updates starters, moves displaced starter to bench, registers the
    new player, and passes all 7 Golden Integrity Rules."""
    mgr = RosterManager()
    # Suppose LG has a brand new injury replacement '테스트용병' starting in place of '정인덕'
    new_lg_starters = [
        {"pos": "GD", "name": "양준석", "no": "5"},
        {"pos": "GD", "name": "유기상", "no": "1"},
        {"pos": "FD", "name": "양홍석", "no": "11"},
        {"pos": "FD", "name": "테스트용병", "no": "99"},
        {"pos": "CT", "name": "아셈 마레이", "no": "50"},
    ]
    res = mgr.sync_from_official_match_lineup("LG", new_lg_starters, reason="QA realtime injury replacement")
    assert res["changed"] is True
    assert "테스트용병" in res["new_starters"]
    assert "정인덕" in mgr.get_team_lineup("LG")["key_bench"]
    assert any(p["name"] == "테스트용병" and p["team"] == "LG" for p in mgr.get_players("LG"))

    ok, errors = mgr.verify_roster_integrity()
    assert ok is True, f"Integrity errors: {errors}"

    # Idempotent: calling again with the exact same lineup returns changed=False
    res_again = mgr.sync_from_official_match_lineup("LG", new_lg_starters)
    assert res_again["changed"] is False


def test_sync_from_official_match_lineup_blocks_quarantined_players() -> None:
    """Real-time lineup sync must never allow Ham Ji-hoon or Kim Sun-hyung (at SK)."""
    mgr = RosterManager()
    bad_sk = [
        {"pos": "G", "name": "김선형", "no": "5"},
        {"pos": "G", "name": "김낙현", "no": "4"},
        {"pos": "F", "name": "안영준", "no": "8"},
        {"pos": "F", "name": "오세근", "no": "41"},
        {"pos": "C", "name": "자밀 워니", "no": "34"},
    ]
    res = mgr.sync_from_official_match_lineup("SK", bad_sk)
    assert res["changed"] is False
    assert res.get("skipped") is True

    bad_mobis = [
        {"pos": "G", "name": "이우석", "no": "11"},
        {"pos": "G", "name": "박무빈", "no": "3"},
        {"pos": "G", "name": "서명진", "no": "7"},
        {"pos": "F", "name": "함지훈", "no": "12"},
        {"pos": "F", "name": "오마리 스펠맨", "no": "4"},
    ]
    res2 = mgr.sync_from_official_match_lineup("현대모비스", bad_mobis)
    assert res2["changed"] is False
    assert res2.get("skipped") is True


def test_sync_from_naver_season_roster_updates_stats_and_adds_new_player() -> None:
    mgr = RosterManager()
    naver_mock = [
        {
            "name": "오마리 스펠맨",
            "team": "현대모비스",
            "pos": "F",
            "no": "4",
            "gp": 6,
            "pts": 27.1,
            "reb": 9.0,
            "ast": 3.5,
            "tpm": 4.8,
            "stl": 0.4,
            "blk": 1.5,
            "is_retire": False,
        },
        {
            "name": "신규아쿼",
            "team": "삼성",
            "pos": "G",
            "no": "21",
            "gp": 1,
            "pts": 12.0,
            "reb": 2.5,
            "ast": 4.0,
            "tpm": 2.0,
            "stl": 1.0,
            "blk": 0.1,
            "is_retire": False,
        },
    ]
    res = mgr.sync_from_naver_season_roster(naver_mock)
    assert res["updated"] >= 1
    assert res["added"] == 1
    spellman = next(p for p in mgr.get_players("현대모비스") if p["name"] == "오마리 스펠맨")
    assert spellman["pts"] == 27.1
    assert any(p["name"] == "신규아쿼" and p["team"] == "삼성" for p in mgr.get_players("삼성"))


def test_invalidate_lineup_caches_evicts_game_and_board_png() -> None:
    set_cached_game_lineup("80109999", ("SK", "DB", [], [], True), ttl=120.0)
    set_cached_board_image("sig_test", b"PNG_BYTES")
    assert get_cached_game_lineup("80109999") is not None
    assert get_cached_board_image("sig_test") == b"PNG_BYTES"

    invalidate_lineup_caches("80109999")
    assert get_cached_game_lineup("80109999") is None
    assert get_cached_board_image("sig_test") is None


@pytest.mark.asyncio
async def test_ingestion_worker_sync_realtime_lineups_persists_and_updates_kbl_data() -> None:
    """End-to-end QA: IngestionWorker detects official match lineup change,
    updates RosterManager & kbl_data.TEAM_LINEUPS, saves to Redis, and clears board cache."""
    mock_provider = AsyncMock()
    mock_provider.get_schedule.return_value = [
        {"game_id": "80109991", "home_team": "LG", "away_team": "삼성", "status": "LIVE"}
    ]
    worker = IngestionWorker(provider=mock_provider, persist_db=False)

    fresh_mgr = RosterManager()
    orig_lg = [dict(s) for s in kbl_data.TEAM_LINEUPS["LG"]["starters"]]

    updated_lg_live = [
        {"pos": "G", "name": "양준석", "no": "5"},
        {"pos": "G", "name": "유기상", "no": "1"},
        {"pos": "F", "name": "양홍석", "no": "11"},
        {"pos": "G", "name": "윤원상", "no": "10"},  # 윤원상 replaces 정인덕
        {"pos": "C", "name": "아셈 마레이", "no": "50"},
    ]
    samsung_live = [
        {"pos": "G", "name": "한호빈", "no": "5"},
        {"pos": "G", "name": "이관희", "no": "2"},
        {"pos": "F", "name": "저스틴 구탕", "no": "18"},
        {"pos": "F", "name": "이규태", "no": "23"},
        {"pos": "C", "name": "케렘 칸터", "no": "35"},
    ]

    try:
        with (
            patch("services.roster.manager.get_roster_manager", return_value=fresh_mgr),
            patch.object(fresh_mgr, "save_to_cache", new=AsyncMock()) as mock_save,
            patch("services.roster.naver_verifier.fetch_naver_season_players", new=AsyncMock(return_value=[])),
            patch(
                "services.content.lineup_board.fetch_daum_match_lineup_sync",
                return_value=("LG", "삼성", updated_lg_live, samsung_live, True),
            ),
        ):
            changed = await worker._sync_realtime_lineups_if_due(force=True)
            assert changed is True
            mock_save.assert_awaited_once()
            lg_names = [s["name"] for s in kbl_data.TEAM_LINEUPS["LG"]["starters"]]
            assert "윤원상" in lg_names
            assert "정인덕" not in lg_names
    finally:
        # Restore kbl_data baseline so subsequent tests aren't mutated
        kbl_data.TEAM_LINEUPS["LG"]["starters"] = orig_lg
