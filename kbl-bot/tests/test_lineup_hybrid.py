"""Tests for Smart Hybrid Lineup Architecture (Parallel Fetch, Priority Sorting, Pre-warming & Caching)."""

import pytest
from apps.kakao.builder import build_lineup_response
from services.content.lineup_board import (
    _BOARD_IMAGE_MEMORY_CACHE,
    fetch_daum_match_lineup_sync,
    get_cached_board_image,
    get_cached_game_lineup,
    prewarm_daily_lineups,
    prewarm_match_lineup,
    set_cached_board_image,
    set_cached_game_lineup,
)


@pytest.fixture
def sample_three_games():
    """3 matches on a weekend day (SK vs DB, LG vs KT, 정관장 vs 소노)."""
    return [
        {
            "game_id": "80109240",
            "home_team": "LG",
            "away_team": "KT",
            "start_time": "2026-11-08T05:00:00Z",  # 14:00 KST
            "status": "SCHEDULED",
            "arena": "창원체육관",
        },
        {
            "game_id": "80109241",
            "home_team": "SK",
            "away_team": "DB",
            "start_time": "2026-11-08T05:00:00Z",  # 14:00 KST
            "status": "SCHEDULED",
            "arena": "잠실학생",
        },
        {
            "game_id": "80109242",
            "home_team": "정관장",
            "away_team": "소노",
            "start_time": "2026-11-08T07:00:00Z",  # 16:00 KST
            "status": "SCHEDULED",
            "arena": "안양체육관",
        },
    ]


def test_lineup_favorite_team_priority_sorting(sample_three_games):
    """When favorite_team is 'SK', SK vs DB must be placed at index 0 in carousel."""
    resp = build_lineup_response(
        sample_three_games,
        favorite_team="SK",
        base_url="https://activity-lexmark-insert-styles.trycloudflare.com",
    )
    items = resp.template.outputs[0]["carousel"]["items"]
    assert len(items) == 3

    # Card 0 must be SK vs DB
    assert "SK vs DB" in items[0]["title"]
    # Card 1 must be LG vs KT (14:00 KST)
    assert "LG vs KT" in items[1]["title"]
    # Card 2 must be 정관장 vs 소노 (16:00 KST)
    assert "정관장 vs 소노" in items[2]["title"]


def test_lineup_dynamic_quick_replies(sample_three_games):
    """Quick replies must contain dynamic jump buttons for today's matches and standard navigation."""
    resp = build_lineup_response(
        sample_three_games,
        favorite_team="SK",
        base_url="https://activity-lexmark-insert-styles.trycloudflare.com",
    )
    labels = [qr.label for qr in resp.template.quickReplies]

    # Verify match jump buttons exist
    assert "📋 SK vs DB" in labels
    assert "📋 LG vs KT" in labels
    assert "📋 정관장 vs 소노" in labels

    # Verify essential utility buttons
    assert "🔴 실시간 점수" in labels
    assert "🗳️ 승부예측" in labels
    assert "🏀 오늘 경기" in labels
    assert "🏆 팀순위" in labels

    # Maximum 10 buttons
    assert len(resp.template.quickReplies) <= 10


def test_single_team_lineup_returns_single_card(sample_three_games):
    """When a specific target_team is given, return exactly 1 focused card for that team."""
    resp = build_lineup_response(
        sample_three_games,
        target_team="정관장",
        base_url="https://activity-lexmark-insert-styles.trycloudflare.com",
    )
    items = resp.template.outputs[0]["carousel"]["items"]
    assert len(items) == 1
    assert "정관장" in items[0]["title"]
    assert "KCC" not in items[0]["title"]

    labels = [qr.label for qr in resp.template.quickReplies]
    assert "⭐ 정관장 선수단" in labels
    assert "📅 정관장 일정" in labels
    assert "📋 오늘 라인업" in labels


def test_game_lineup_memory_ttl_cache():
    """Test get_cached_game_lineup and set_cached_game_lineup."""
    dummy_data = ("SK", "DB", [{"name": "김낙현"}], [{"name": "이선 알바노"}], True)
    set_cached_game_lineup("test_gid_999", dummy_data, ttl=60.0)

    cached = get_cached_game_lineup("test_gid_999")
    assert cached is not None
    assert cached[0] == "SK"
    assert cached[1] == "DB"
    assert cached[4] is True


def test_board_image_memory_lru_cache():
    """Test in-memory image cache avoids repeated rendering."""
    test_sig = "test_image_signature_123"
    test_bytes = b"fake_png_header_and_data"

    set_cached_board_image(test_sig, test_bytes)
    assert get_cached_board_image(test_sig) == test_bytes


def test_prewarm_daily_lineups(sample_three_games):
    """Test prewarm_daily_lineups processes games concurrently and returns count."""
    count = prewarm_daily_lineups(sample_three_games)
    assert count == 3
