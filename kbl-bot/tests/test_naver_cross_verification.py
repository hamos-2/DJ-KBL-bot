"""Tests for Naver Sports (seasonCode=49) lineup cross-verification."""

from __future__ import annotations

from services.roster.naver_verifier import (
    NAVER_SEASON_CODE_2026_2027,
    cross_verify_lineup,
    normalize_naver_team,
)
from apps.kakao.builder import build_lineup_response


def test_normalize_naver_team() -> None:
    assert normalize_naver_team("고양소노") == "소노"
    assert normalize_naver_team("서울 SK") == "SK"
    assert normalize_naver_team("울산현대모비스") == "현대모비스"
    assert normalize_naver_team("대구 한국가스공사") == "한국가스공사"


def test_cross_verify_lineup_enriches_and_validates() -> None:
    naver_mock = [
        {"name": "이우석", "team": "현대모비스", "pos": "G", "no": "11", "gp": 14, "pts": 16.3, "is_retire": False},
        {"name": "박무빈", "team": "현대모비스", "pos": "G", "no": "3", "gp": 14, "pts": 6.8, "is_retire": False},
        {"name": "서명진", "team": "현대모비스", "pos": "G", "no": "7", "gp": 14, "pts": 6.3, "is_retire": False},
        {"name": "이승현", "team": "현대모비스", "pos": "F", "no": "33", "gp": 14, "pts": 8.2, "is_retire": False},
        {"name": "오마리 스펠맨", "team": "현대모비스", "pos": "F", "no": "4", "gp": 5, "pts": 25.4, "is_retire": False},
    ]
    starters = [
        {"pos": "G", "name": "이우석", "no": "11"},
        {"pos": "G", "name": "박무빈", "no": "3"},
        {"pos": "G", "name": "서명진", "no": "7"},
        {"pos": "F", "name": "이승현", "no": "33"},
        {"pos": "F", "name": "오마리 스펠맨", "no": ""},  # missing no enriched from Naver
    ]
    res = cross_verify_lineup("현대모비스", starters, naver_players=naver_mock, is_official_daum=True)
    assert res["verified"] is True
    assert res["source"] == "naver+daum"
    assert res["season_code"] == NAVER_SEASON_CODE_2026_2027
    assert res["discrepancies"] == []
    assert res["verified_starters"][4]["no"] == "4"
    assert "네이버 시즌49 교차검증" in res["badge"]


def test_cross_verify_blocks_retired_and_wrong_team_players() -> None:
    naver_mock = [
        {"name": "김낙현", "team": "SK", "pos": "G", "no": "4", "gp": 14, "pts": 9.7, "is_retire": False},
        {"name": "김선형", "team": "KT", "pos": "G", "no": "5", "gp": 0, "pts": 0.0, "is_retire": False},
    ]
    starters = [
        {"pos": "G", "name": "김낙현", "no": "4"},
        {"pos": "G", "name": "김선형", "no": "5"},
        {"pos": "F", "name": "함지훈", "no": "12"},
    ]
    res = cross_verify_lineup("SK", starters, naver_players=naver_mock, is_official_daum=False)
    assert res["verified"] is False
    names = [s["name"] for s in res["verified_starters"]]
    assert "김선형" not in names
    assert "함지훈" not in names
    assert any("함지훈" in d for d in res["discrepancies"])
    assert any("김선형" in d for d in res["discrepancies"])


def test_build_lineup_response_includes_naver_verification_and_updated_roster() -> None:
    resp = build_lineup_response(today_games=[], target_team="현대모비스", base_url="https://example.com")
    payload = resp.model_dump()
    card = payload["template"]["outputs"][0]["carousel"]["items"][0]
    desc = card["description"]
    assert "오마리 스펠맨" in desc
    assert "제로드 존스" in desc
    assert "시즌49" in desc
