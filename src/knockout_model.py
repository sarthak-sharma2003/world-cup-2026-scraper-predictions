"""Knockout prediction: two-outcome match probabilities + Monte Carlo bracket sim.

Knockouts have no draws — a level game is resolved by extra time / penalties.
We model that as: P(A advances) = P(A wins in 90) + 0.5 * P(draw). The bracket
is then simulated many times, respecting already-played results, to produce each
team's probability of reaching each round and winning the tournament.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict

from .model import TeamStrength, _poisson_pmf


def match_win_prob(
    home: str,
    away: str,
    strengths: dict[str, TeamStrength],
    league_avg: float,
    max_goals: int = 8,
) -> float:
    """Probability that `home` advances past `away` (draw split 50/50 for ET/pens)."""
    hs, aw = strengths.get(home), strengths.get(away)
    if hs is None or aw is None:
        return 0.5
    exp_home = hs.attack * aw.defense * league_avg
    exp_away = aw.attack * hs.defense * league_avg

    p_home = p_draw = p_away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = _poisson_pmf(i, exp_home) * _poisson_pmf(j, exp_away)
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away or 1.0
    return (p_home + 0.5 * p_draw) / total


THIRD_PLACE = "Match for third place"
FINAL_NO = 104


def current_match_probs(
    matches: list[dict], strengths: dict[str, TeamStrength], league_avg: float
) -> dict[int, dict[str, float]]:
    """For matches whose two teams are already known but not yet played, the
    head-to-head advance probabilities (used to annotate the bracket tiles)."""
    out: dict[int, dict[str, float]] = {}
    for m in matches:
        h, a = m.get("home_team"), m.get("away_team")
        if h and a and not m.get("winner"):
            p = match_win_prob(h, a, strengths, league_avg)
            out[m["match_no"]] = {h: p, a: 1 - p}
    return out


def simulate(
    matches: list[dict],
    strengths: dict[str, TeamStrength],
    league_avg: float,
    n: int = 20000,
    seed: int = 42,
) -> dict:
    """Monte Carlo the remaining bracket. Returns championship odds + per-round
    reach probabilities per team."""
    rng = random.Random(seed)
    order = sorted(matches, key=lambda m: (m["round_idx"], m["match_no"]))

    prob_cache: dict[tuple[str, str], float] = {}

    def wp(h: str, a: str) -> float:
        key = (h, a)
        if key not in prob_cache:
            prob_cache[key] = match_win_prob(h, a, strengths, league_avg)
        return prob_cache[key]

    champion: Counter = Counter()
    reach: dict[str, Counter] = defaultdict(Counter)

    for _ in range(n):
        winner: dict[int, str] = {}
        loser: dict[int, str] = {}
        for m in order:
            no = m["match_no"]
            if m["round"] == THIRD_PLACE:
                h = loser.get(m["home_from"])
                a = loser.get(m["away_from"])
            else:
                h = m.get("home_team") or winner.get(m["home_from"])
                a = m.get("away_team") or winner.get(m["away_from"])
            if not h or not a:
                continue
            reach[m["round"]][h] += 1
            reach[m["round"]][a] += 1
            if m.get("winner"):
                win = m["winner"]
            else:
                win = h if rng.random() < wp(h, a) else a
            winner[no] = win
            loser[no] = a if win == h else h
        if FINAL_NO in winner:
            champion[winner[FINAL_NO]] += 1

    return {
        "n": n,
        "champion": {t: c / n for t, c in champion.items()},
        "reach": {rnd: {t: c / n for t, c in ctr.items()} for rnd, ctr in reach.items()},
    }
