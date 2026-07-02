"""Simple Poisson match-prediction model from scraped team stats.

Deliberately lightweight (timeboxed): attack/defense strengths derived from
goals scored/conceded per game relative to the tournament average, then a
Poisson goal model gives win/draw/win probabilities. This is the natural
stepping stone to the planned Dixon-Coles upgrade (which adds a low-score
correlation correction + time decay).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class TeamStrength:
    team: str
    attack: float   # goals scored per game / league average
    defense: float  # goals conceded per game / league average
    games: int


def compute_strengths(
    rows: list[dict], prior_games: float = 2.0
) -> tuple[dict[str, TeamStrength], float]:
    """Attack/defense strengths with Bayesian shrinkage.

    `prior_games` adds that many pseudo-games at the league average, pulling
    tiny-sample extremes (e.g. "conceded 0 in 3 games") toward the mean so we
    don't emit absurd 0%/100% predictions off a 3-game group stage.
    """
    total_gf = sum((r.get("goals_for") or 0) for r in rows)
    total_games = sum((r.get("games") or 0) for r in rows)
    league_avg = (total_gf / total_games) if total_games else 1.0

    strengths: dict[str, TeamStrength] = {}
    for r in rows:
        games = r.get("games") or 0
        if games == 0:
            continue
        name = r.get("canonical_team") or r.get("team")
        gf = (r.get("goals_for") or 0) + prior_games * league_avg
        ga = (r.get("goals_against") or 0) + prior_games * league_avg
        adj_games = games + prior_games
        strengths[name] = TeamStrength(
            team=name,
            attack=(gf / adj_games) / league_avg if league_avg else 1.0,
            defense=(ga / adj_games) / league_avg if league_avg else 1.0,
            games=games,
        )
    return strengths, league_avg


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def predict(
    home: str,
    away: str,
    strengths: dict[str, TeamStrength],
    league_avg: float,
    max_goals: int = 8,
) -> dict:
    hs, aw = strengths[home], strengths[away]
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
    return {
        "home_win": p_home / total,
        "draw": p_draw / total,
        "away_win": p_away / total,
        "exp_home_goals": exp_home,
        "exp_away_goals": exp_away,
    }
