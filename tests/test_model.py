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


def test_elo_prior_shifts_ordering():
    # Two teams with identical form but different Elo: higher Elo -> stronger.
    rows = [
        {"canonical_team": "Pedigree", "games": 3, "goals_for": 4, "goals_against": 4},
        {"canonical_team": "Upstart", "games": 3, "goals_for": 4, "goals_against": 4},
    ]
    elo = {"Pedigree": 2000, "Upstart": 1600}
    s, _ = compute_strengths(rows, elo=elo)
    assert s["Pedigree"].attack / s["Pedigree"].defense > s["Upstart"].attack / s["Upstart"].defense


def test_xg_used_instead_of_goals_when_provided():
    # A team that scored many goals but had poor xG should be rated on xG.
    rows = [
        {"canonical_team": "Lucky", "games": 3, "goals_for": 9, "goals_against": 1},
        {"canonical_team": "Solid", "games": 3, "goals_for": 4, "goals_against": 4},
    ]
    xg = {
        "Lucky": {"for": 3.0, "against": 6.0, "games": 3},   # weak underlying
        "Solid": {"for": 6.0, "against": 3.0, "games": 3},   # strong underlying
    }
    s, _ = compute_strengths(rows, xg=xg)
    assert s["Solid"].attack > s["Lucky"].attack
    assert s["Solid"].defense < s["Lucky"].defense
