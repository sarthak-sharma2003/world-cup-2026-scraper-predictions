"""Runtime data loader for the dashboard.

Fetches the latest committed exports straight from GitHub (the `main` branch), so
the deployed app tracks the scheduled scrape within minutes — instead of only
updating when Streamlit Community Cloud happens to redeploy. Falls back to the
local files for offline/dev use.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import streamlit as st

_RAW_BASE = (
    "https://raw.githubusercontent.com/sarthak-sharma2003/"
    "world-cup-2026-scraper-predictions/main/data/exports"
)
_LOCAL = Path(__file__).parent / "data" / "exports"


@st.cache_data(ttl=600, show_spinner=False)  # re-fetch at most every 10 minutes
def load_json(name: str) -> list[dict]:
    """Load an export (e.g. "team_stats") — live from GitHub, else local fallback."""
    try:
        req = urllib.request.Request(f"{_RAW_BASE}/{name}.json", headers={"User-Agent": "wc2026-dashboard"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        path = _LOCAL / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
