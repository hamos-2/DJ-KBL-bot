"""Unit tests for P1 fan experience enhancements (today boxscore, streaks/H2H, real leaderboard rank)."""

from apps.kakao.builder import (
    build_favorite_players_response,
    build_matchup_search_response,
    build_prediction_leaderboard_response,
    build_single_player_response,
)
from services.content.kbl_data import compute_team_streaks_and_h2h
from services.search.parser import MatchupQuery


def test_compute_team_streaks_and_h2h() -> None:
    """Computes streak, L5, and pairwise season H2H from finished games."""
    games = [
        {"status": "FINAL", "home_team": "SK", "away_team": "KT", "home_score": 82, "away_score": 78, "start_time": "2026-11-01T10:00:00Z"},
        {"status": "FINAL", "home_team": "KT", "away_team": "SK", "home_score": 70, "away_score": 75, "start_time": "2026-11-05T10:00:00Z"},
        {"status": "FINAL", "home_team": "SK", "away_team": "DB", "home_score": 88, "away_score": 80, "start_time": "2026-11-10T10:00:00Z"},
        {"status": "FINAL", "home_team": "KT", "away_team": "LG", "home_score": 74, "away_score": 79, "start_time": "2026-11-11T10:00:00Z"},
    ]
    res = compute_team_streaks_and_h2h(games)
    assert res["teams"]["SK"]["streak"] == "3연승"
    assert res["teams"]["SK"]["l5"] == "3승0패"
    assert res["teams"]["KT"]["streak"] == "3연패"
    assert res["h2h"]["KT:SK"] == {"SK": 2, "KT": 0}


def test_single_and_favorite_player_cards_render_today_boxscore() -> None:
    """Today's cached live/final stats appear cleanly alongside season averages."""
    player = {"name": "자밀 워니", "team": "SK", "pos": "C", "no": "34", "pts": 22.1, "reb": 11.2, "ast": 3.4, "tpm": 0.4, "stl": 1.1}
    today_stats = {"name": "자밀 워니", "team": "SK", "opp": "KT", "status": "LIVE", "period": 3, "pts": 21, "reb": 9, "ast": 4}

    single = build_single_player_response(player, is_favorite=True, today_stats=today_stats)
    desc = single.template.outputs[0]["basicCard"]["description"]
    assert "🔴 오늘 3Q vs KT: 21점 9리바 4어시" in desc
    assert "시즌 평균: 22.1점 | 11.2리바 | 3.4어시" in desc

    fav_resp = build_favorite_players_response(["자밀 워니"], favorite_team="SK", today_stats_map={"자밀 워니": today_stats})
    first_item = fav_resp.template.outputs[0]["listCard"]["items"][0]
    assert "21점 9리바 4어시" in first_item["description"]


def test_matchup_search_displays_h2h_and_streak() -> None:
    """Matchup search header renders season H2H for 2-team queries and streak/L5 for 1-team queries."""
    analytics = {
        "teams": {"KT": {"streak": "2연승", "l5": "4승1패"}},
        "h2h": {"KT:SK": {"SK": 2, "KT": 1}},
    }
    q2 = MatchupQuery(raw_query="SK vs KT", team_a="SK", team_b="KT")
    resp2 = build_matchup_search_response(q2, [], analytics=analytics)
    assert "(2승1패)" in resp2.template.outputs[0]["listCard"]["header"]["title"]

    q1 = MatchupQuery(raw_query="KT", team_a="KT", team_b=None)
    resp1 = build_matchup_search_response(q1, [], analytics=analytics)
    hdr1 = resp1.template.outputs[0]["listCard"]["header"]["title"]
    assert "2연승" in hdr1 and "4승1패" in hdr1


def test_prediction_leaderboard_shows_real_rank_and_team_toggle() -> None:
    """Leaderboard uses computed user_rank (not hardcoded 12) and toggles team vs global views."""
    rankings = [{"rank": 1, "nickname": "SK 레전드#4821", "team": "SK", "points": 850, "streak": 8}]
    resp = build_prediction_leaderboard_response(
        rankings=rankings,
        user_points=320,
        user_rank=7,
        streak=4,
        favorite_team="SK",
        user_hmac="abc123",
    )
    lc = resp.template.outputs[0]["listCard"]
    descs = [i["description"] for i in lc["items"]]
    assert any("7위" in d and "320P" in d for d in descs)
    btn_labels = [b["label"] for b in lc["buttons"]]
    assert "SK 팬 랭킹" in btn_labels

    team_resp = build_prediction_leaderboard_response(
        rankings=rankings,
        user_points=850,
        user_rank=1,
        favorite_team="SK",
        user_hmac="abc123",
        team_filter="SK",
    )
    team_lc = team_resp.template.outputs[0]["listCard"]
    assert "[SK] 팬 랭킹" in team_lc["header"]["title"]
    assert any(b["label"] == "전체 팬 랭킹" for b in team_lc["buttons"])
