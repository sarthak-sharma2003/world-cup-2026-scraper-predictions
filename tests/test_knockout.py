"""Tests for knockout parsing helpers and the two-outcome / Monte Carlo model."""
from src.knockout_model import match_win_prob, simulate
from src.model import compute_strengths
from src.scraper.knockout import KnockoutScraper


def test_parse_ref_team_vs_winner_reference():
    ref, team, feeder = KnockoutScraper._parse_ref("Winner Match 97")
    assert team is None and feeder == 97
    ref, team, feeder = KnockoutScraper._parse_ref("Brazil")
    assert team == "Brazil" and feeder is None


def test_parse_result_penalties():
    rec = {"home_team": "Germany", "away_team": "Paraguay"}
    KnockoutScraper._parse_result(rec, "1-1(a.e.t.)", "Germany 1-1 Paraguay Penalties X Y 3-4 venue")
    assert rec["home_score"] == 1 and rec["away_score"] == 1
    assert rec["home_pens"] == 3 and rec["away_pens"] == 4
    assert rec["winner"] == "Paraguay"


def test_parse_result_normal_win():
    rec = {"home_team": "Canada", "away_team": "South Africa"}
    KnockoutScraper._parse_result(rec, "2-0", "Canada 2-0 South Africa")
    assert rec["winner"] == "Canada"


def test_assign_numbers_covers_round_and_resolves_collisions():
    # Two boxes both claim "Match 83" (the live-page citation collision); the rest
    # are played (no reliable label). Every R32 slot 73-88 must be filled uniquely.
    recs = [{"round": "Round of 32", "match_no": None, "claimed_no": 83},
            {"round": "Round of 32", "match_no": None, "claimed_no": 83}]
    recs += [{"round": "Round of 32", "match_no": None, "claimed_no": None} for _ in range(14)]
    KnockoutScraper._assign_numbers(recs)
    assert sorted(m["match_no"] for m in recs) == list(range(73, 89))


ROWS = [
    {"canonical_team": "Strong", "games": 3, "goals_for": 9, "goals_against": 1},
    {"canonical_team": "Weak", "games": 3, "goals_for": 1, "goals_against": 9},
]


def test_match_win_prob_favours_stronger_and_no_draw():
    s, avg = compute_strengths(ROWS)
    p = match_win_prob("Strong", "Weak", s, avg)
    assert 0.5 < p < 1.0            # stronger favoured, still two-outcome
    assert abs(p + match_win_prob("Weak", "Strong", s, avg) - 1.0) < 1e-9


def test_simulate_respects_decided_matches():
    s, avg = compute_strengths(ROWS + [
        {"canonical_team": "C", "games": 3, "goals_for": 4, "goals_against": 4},
        {"canonical_team": "D", "games": 3, "goals_for": 4, "goals_against": 4},
    ])
    matches = [
        {"match_no": 101, "round": "Semifinals", "round_idx": 3,
         "home_team": "Strong", "away_team": "Weak", "home_from": None,
         "away_from": None, "winner": "Strong"},
        {"match_no": 102, "round": "Semifinals", "round_idx": 3,
         "home_team": "C", "away_team": "D", "home_from": None,
         "away_from": None, "winner": "C"},
        {"match_no": 104, "round": "Final", "round_idx": 4,
         "home_team": None, "away_team": None, "home_from": 101,
         "away_from": 102, "winner": "Strong"},
    ]
    sim = simulate(matches, s, avg, n=1000)
    assert sim["champion"]["Strong"] == 1.0   # fully decided -> deterministic
