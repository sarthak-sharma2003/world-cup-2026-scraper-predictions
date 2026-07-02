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
    rows: list[dict],
    prior_games: float = 2.0,
    elo: dict[str, float] | None = None,
    xg: dict[str, dict] | None = None,
    elo_weight: float = 0.6,
    elo_scale: float = 300.0,
    elo_alpha: float = 0.85,
) -> tuple[dict[str, TeamStrength], float]:
    """Attack/defense strengths blending a pre-tournament Elo prior with tournament form.

    - Form: expected goals (xG) for/against per game when `xg` is supplied (chance
      quality, robust to lucky finishing), otherwise raw goals from `rows`. Bayesian
      shrinkage (`prior_games`) tames tiny-sample extremes.
    - Elo: a per-team pre-tournament strength prior. Off a 3-8 game tournament Elo is
      the more reliable signal, so it is weighted higher (`elo_weight`), but form still
      moves the number — a favourite playing badly is marked down, an overperformer up.

    Combined geometrically in multiplicative strength space:
        strength = form^(1 - elo_weight) * elo^elo_weight
    Returns (strengths, base_scoring_rate). With no `elo`/`xg` this is pure goals form.
    """
    def _rate_source():
        if xg:
            rates = [v["for"] / v["games"] for v in xg.values() if v.get("games")]
            return (sum(rates) / len(rates)) if rates else 1.0
        total_gf = sum((r.get("goals_for") or 0) for r in rows)
        total_games = sum((r.get("games") or 0) for r in rows)
        return (total_gf / total_games) if total_games else 1.0

    league_avg = _rate_source()

    elo_mean = 0.0
    if elo:
        vals = [elo[r.get("canonical_team") or r.get("team")]
                for r in rows if (r.get("canonical_team") or r.get("team")) in elo]
        elo_mean = sum(vals) / len(vals) if vals else 0.0

    strengths: dict[str, TeamStrength] = {}
    for r in rows:
        name = r.get("canonical_team") or r.get("team")

        # form (xG preferred, goals fallback), with shrinkage toward the mean
        if xg and name in xg and xg[name].get("games"):
            g = xg[name]["games"]
            f_for, f_against = xg[name]["for"], xg[name]["against"]
        else:
            g = r.get("games") or 0
            f_for, f_against = r.get("goals_for") or 0, r.get("goals_against") or 0
        if g == 0:
            continue
        adj = g + prior_games
        form_attack = ((f_for + prior_games * league_avg) / adj) / league_avg if league_avg else 1.0
        form_defense = ((f_against + prior_games * league_avg) / adj) / league_avg if league_avg else 1.0

        attack, defense = form_attack, form_defense
        if elo and name in elo:
            z = (elo[name] - elo_mean) / elo_scale
            w = elo_weight
            attack = form_attack ** (1 - w) * math.exp(elo_alpha * z) ** w
            defense = form_defense ** (1 - w) * math.exp(-elo_alpha * z) ** w

        strengths[name] = TeamStrength(team=name, attack=attack, defense=defense, games=g)
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
