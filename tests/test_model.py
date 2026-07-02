"""Sanity tests for the Poisson prediction model."""
from src.model import compute_strengths, predict


ROWS = [
    {"canonical_team": "Strong", "games": 3, "goals_for": 9, "goals_against": 1},
    {"canonical_team": "Weak", "games": 3, "goals_for": 1, "goals_against": 9},
    {"canonical_team": "Even", "games": 3, "goals_for": 4, "goals_against": 4},
]


def test_probabilities_sum_to_one():
    strengths, avg = compute_strengths(ROWS)
    p = predict("Strong", "Weak", strengths, avg)
    total = p["home_win"] + p["draw"] + p["away_win"]
    assert abs(total - 1.0) < 1e-6


def test_stronger_team_favoured():
    strengths, avg = compute_strengths(ROWS)
    p = predict("Strong", "Weak", strengths, avg)
    assert p["home_win"] > p["away_win"]
    assert p["exp_home_goals"] > p["exp_away_goals"]


def test_zero_game_team_excluded():
    rows = ROWS + [{"canonical_team": "NoData", "games": 0, "goals_for": 0, "goals_against": 0}]
    strengths, _ = compute_strengths(rows)
    assert "NoData" not in strengths
