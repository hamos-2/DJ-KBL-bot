"""Unit tests for RosterManager and dynamic in-season roster synchronization."""

import pytest
from services.roster.manager import RosterManager, get_roster_manager
import services.content.kbl_data as kbl_data


@pytest.fixture
def roster_mgr() -> RosterManager:
    """Return a fresh RosterManager instance for testing."""
    return RosterManager()


class TestRosterManagerBaseline:
    """Verify that RosterManager initializes with correct real-world official baseline."""

    def test_all_10_teams_present(self, roster_mgr: RosterManager) -> None:
        teams = ["SK", "DB", "KT", "LG", "정관장", "KCC", "한국가스공사", "현대모비스", "소노", "삼성"]
        for t in teams:
            lineup = roster_mgr.get_team_lineup(t)
            assert lineup is not None, f"Team {t} lineup missing"
            assert len(lineup["starters"]) == 5
            assert lineup["head_coach"]

    def test_verified_head_coaches(self, roster_mgr: RosterManager) -> None:
        assert roster_mgr.get_team_lineup("SK")["head_coach"] == "전희철"
        assert roster_mgr.get_team_lineup("DB")["head_coach"] == "김주성"
        assert roster_mgr.get_team_lineup("KT")["head_coach"] == "송영진"
        assert roster_mgr.get_team_lineup("LG")["head_coach"] == "조상현"
        assert roster_mgr.get_team_lineup("KCC")["head_coach"] == "전창진"
        assert roster_mgr.get_team_lineup("한국가스공사")["head_coach"] == "강혁"
        assert roster_mgr.get_team_lineup("현대모비스")["head_coach"] == "조동현"
        assert roster_mgr.get_team_lineup("정관장")["head_coach"] == "김상식"
        assert roster_mgr.get_team_lineup("소노")["head_coach"] == "김승기"
        assert roster_mgr.get_team_lineup("삼성")["head_coach"] == "김효범"

    def test_retired_player_exclusion(self, roster_mgr: RosterManager) -> None:
        players = roster_mgr.get_players()
        assert not any(p["name"] == "함지훈" for p in players)
        mobis_starters = [s["name"] for s in roster_mgr.get_team_lineup("현대모비스")["starters"]]
        assert "함지훈" not in mobis_starters

    def test_kim_sun_hyung_exclusion_from_sk(self, roster_mgr: RosterManager) -> None:
        sk_starters = [s["name"] for s in roster_mgr.get_team_lineup("SK")["starters"]]
        assert "김선형" not in sk_starters


class TestInSeasonMutations:
    """Verify dynamic mutations during the season (coach replacement, trades, starters)."""

    def test_update_head_coach(self, roster_mgr: RosterManager) -> None:
        # Simulate mid-season coach change (e.g. Sono interim coach)
        tx = roster_mgr.update_head_coach("소노", "김태술", reason="시즌 중 감독 대행 선임")
        assert tx["type"] == "COACH_CHANGE"
        assert tx["old_coach"] == "김승기"
        assert tx["new_coach"] == "김태술"
        assert roster_mgr.get_team_lineup("소노")["head_coach"] == "김태술"

        # Revert back to 김승기
        roster_mgr.update_head_coach("소노", "김승기", reason="원복")
        assert roster_mgr.get_team_lineup("소노")["head_coach"] == "김승기"

    def test_transfer_player(self, roster_mgr: RosterManager) -> None:
        # Simulate mid-season trade
        tx = roster_mgr.transfer_player("이정현", "소노", reason="소노 트레이드")
        assert tx["type"] == "PLAYER_TRANSFER"
        player = roster_mgr.get_player_by_name("이정현")
        assert player is not None
        assert player["team"] == "소노"

    def test_transfer_kim_sun_hyung_sk_prevented(self, roster_mgr: RosterManager) -> None:
        with pytest.raises(ValueError, match="Constraint violation"):
            roster_mgr.transfer_player("김선형", "SK")

    def test_update_starters_constraint_validation(self, roster_mgr: RosterManager) -> None:
        # Attempt to insert retired Ham Ji-hoon must raise
        illegal_starters = [
            {"pos": "G", "name": "서명진", "no": "3"},
            {"pos": "G", "name": "박무빈", "no": "28"},
            {"pos": "F", "name": "이우석", "no": "1"},
            {"pos": "C", "name": "함지훈", "no": "12"},
            {"pos": "C", "name": "게이지 프림", "no": "0"},
        ]
        with pytest.raises(ValueError, match="Retired player 함지훈"):
            roster_mgr.update_starters("현대모비스", illegal_starters)

    def test_retire_or_waive_player(self, roster_mgr: RosterManager) -> None:
        # Add a dummy player and waive them
        roster_mgr.transfer_player("테스트선수", "DB")
        assert roster_mgr.get_player_by_name("테스트선수") is not None

        roster_mgr.retire_or_waive_player("테스트선수", "DB")
        assert roster_mgr.get_player_by_name("테스트선수") is None


class TestLiveStatsSync:
    """Verify live leaderboard stats sync into player roster."""

    def test_sync_with_live_leaderboard(self, roster_mgr: RosterManager) -> None:
        mock_rankings = {
            "pts": [
                {"rank": 1, "name": "자밀 워니", "team": "SK", "pts": 22.5, "value": 22.5},
                {"rank": 2, "name": "허훈", "team": "KT", "pts": 18.2, "value": 18.2},
            ],
            "ast": [
                {"rank": 1, "name": "허훈", "team": "KT", "ast": 9.1, "value": 9.1},
                {"rank": 2, "name": "이선 알바노", "team": "DB", "ast": 8.0, "value": 8.0},
            ],
        }
        updated = roster_mgr.sync_with_live_leaderboard(mock_rankings)
        assert updated >= 4

        warney = roster_mgr.get_player_by_name("자밀 워니")
        assert warney["pts"] == 22.5

        heo_hoon = roster_mgr.get_player_by_name("허훈")
        assert heo_hoon["pts"] == 18.2
        assert heo_hoon["ast"] == 9.1
