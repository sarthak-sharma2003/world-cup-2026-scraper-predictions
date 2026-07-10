"""World Cup 2026 prediction dashboard (Streamlit).

Run:  streamlit run dashboard.py
Loads the latest committed exports live from GitHub (see app_data.load_json), so
the deployed app tracks the scheduled scrape within ~10 min without needing a
Streamlit redeploy.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app_data import load_json
from src.model import compute_strengths, predict


def load_model_inputs():
    """Elo prior + xG form from the enrichment dataset, if present."""
    mrows = load_json("model_inputs")
    if not mrows:
        return None, None
    elo = {r["team"]: r["elo"] for r in mrows if r.get("elo")}
    xg = {
        r["team"]: {"for": r["xg_for"], "against": r["xg_against"], "games": r["xg_games"]}
        for r in mrows if r.get("xg_games")
    }
    return elo, xg


st.set_page_config(page_title="World Cup 2026 Predictions", page_icon="⚽", layout="wide")
st.title("⚽ World Cup 2026 — Live Prediction Dashboard")

rows = load_json("team_stats")
if not rows:
    st.error("No data available.")
    st.stop()
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
    st.dataframe(table, width="stretch", height=560)

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
