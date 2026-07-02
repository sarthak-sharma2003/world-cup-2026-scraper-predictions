"""World Cup 2026 prediction dashboard (Streamlit).

Run:  streamlit run dashboard.py
Reads the committed scrape exports (data/exports/team_stats.json), so it shows
whatever the last scheduled scrape produced.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from src.model import compute_strengths, predict

EXPORT = Path(__file__).parent / "data" / "exports" / "team_stats.json"
MODEL_INPUTS = Path(__file__).parent / "data" / "exports" / "model_inputs.json"


def load_model_inputs():
    """Elo prior + xG form from the enrichment dataset, if present."""
    if not MODEL_INPUTS.exists():
        return None, None
    mrows = json.loads(MODEL_INPUTS.read_text())
    elo = {r["team"]: r["elo"] for r in mrows if r.get("elo")}
    xg = {
        r["team"]: {"for": r["xg_for"], "against": r["xg_against"], "games": r["xg_games"]}
        for r in mrows if r.get("xg_games")
    }
    return elo, xg


st.set_page_config(page_title="World Cup 2026 Predictions", page_icon="⚽", layout="wide")
st.title("⚽ World Cup 2026 — Live Prediction Dashboard")

if not EXPORT.exists():
    st.error("No data yet. Run `python -m src` to scrape first.")
    st.stop()

rows = json.loads(EXPORT.read_text())
df = pd.DataFrame(rows)
df["points"] = df["wins"] * 3 + df["draws"]
df["gd"] = df["goals_for"] - df["goals_against"]

last_refresh = max((r.get("scraped_at") for r in rows), default="unknown")
st.caption(f"Source: Wikipedia · {len(rows)} teams · last refresh: {last_refresh}")

left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Team standings (scraped)")
    table = (
        df[["canonical_team", "games", "wins", "draws", "losses",
            "goals_for", "goals_against", "gd", "points"]]
        .sort_values(["points", "gd", "goals_for"], ascending=False)
        .reset_index(drop=True)
        .rename(columns={
            "canonical_team": "Team", "games": "P", "wins": "W", "draws": "D",
            "losses": "L", "goals_for": "GF", "goals_against": "GA",
            "gd": "GD", "points": "Pts",
        })
    )
    table.index += 1
    st.dataframe(table, use_container_width=True, height=560)

with right:
    st.subheader("Match predictor")
    elo, xg = load_model_inputs()
    strengths, league_avg = compute_strengths(rows, elo=elo, xg=xg)
    teams = sorted(strengths.keys())
    home = st.selectbox("Team A", teams, index=teams.index("Brazil") if "Brazil" in teams else 0)
    away = st.selectbox("Team B", teams, index=1)

    if home == away:
        st.info("Pick two different teams.")
    else:
        p = predict(home, away, strengths, league_avg)
        st.metric(f"{home} win", f"{p['home_win'] * 100:.0f}%")
        st.metric("Draw", f"{p['draw'] * 100:.0f}%")
        st.metric(f"{away} win", f"{p['away_win'] * 100:.0f}%")
        st.progress(p["home_win"], text=f"{home}")
        st.progress(p["draw"], text="Draw")
        st.progress(p["away_win"], text=f"{away}")
        st.caption(
            f"Expected goals: **{home} {p['exp_home_goals']:.2f} – "
            f"{p['exp_away_goals']:.2f} {away}**"
        )
        st.caption(
            "Poisson model: pre-tournament Elo prior blended with tournament xG form "
            "(Elo weighted 0.6). Draw shown here; knockouts use the two-outcome model."
        )
