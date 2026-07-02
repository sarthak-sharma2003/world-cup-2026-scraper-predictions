"""Knockout bracket page — double-sided tree with advancement probabilities.

Click any tile to see that matchup's detail (expected goals, two-outcome
probabilities, each team's championship odds). Knockouts have no draws, so
the model resolves level games via the ET/penalty 50/50 split.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import streamlit as st

from src.knockout_model import current_match_probs, match_win_prob, simulate
from src.model import compute_strengths

ROOT = Path(__file__).resolve().parent.parent
TEAMS = ROOT / "data" / "exports" / "team_stats.json"
KO = ROOT / "data" / "exports" / "knockout_matches.json"

st.set_page_config(page_title="WC2026 Knockouts", page_icon="🏆", layout="wide")

# --- ISO2 codes for flag emoji (teams in the WC2026 knockouts) --------------
ISO2 = {
    "South Africa": "ZA", "Canada": "CA", "Brazil": "BR", "Japan": "JP",
    "Germany": "DE", "Paraguay": "PY", "Netherlands": "NL", "Morocco": "MA",
    "France": "FR", "Sweden": "SE", "Mexico": "MX", "Norway": "NO",
    "United States": "US", "Belgium": "BE", "Spain": "ES", "Portugal": "PT",
    "Croatia": "HR", "Argentina": "AR", "Switzerland": "CH", "Ecuador": "EC",
    "Ivory Coast": "CI", "DR Congo": "CD", "Iran": "IR", "Austria": "AT",
    "Bosnia": "BA", "Uruguay": "UY", "Colombia": "CO", "Senegal": "SN",
    "South Korea": "KR", "Australia": "AU", "Denmark": "DK", "Italy": "IT",
    "Nigeria": "NG", "Egypt": "EG", "Qatar": "QA", "Ghana": "GH",
    "Saudi Arabia": "SA", "Poland": "PL", "Serbia": "RS", "Peru": "PE",
    "Panama": "PA", "New Zealand": "NZ", "Jordan": "JO", "Uzbekistan": "UZ",
    "Cape Verde": "CV", "Curaçao": "CW", "Haiti": "HT", "Scotland": "GB-SCT",
}
_SPECIAL_FLAGS = {"GB-ENG": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f"}
ISO2["England"] = "GB-ENG"


def flag(team: str | None) -> str:
    if not team:
        return "⚪"
    code = ISO2.get(team)
    if not code:
        return "⚽"
    if code in _SPECIAL_FLAGS:
        return _SPECIAL_FLAGS[code]
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


@st.cache_data
def load_data():
    teams = json.loads(TEAMS.read_text())
    ko = json.loads(KO.read_text())
    return teams, ko


@st.cache_data
def compute(_teams, _ko):
    strengths, avg = compute_strengths(_teams)
    sim = simulate(_ko, strengths, avg, n=20000)
    probs = current_match_probs(_ko, strengths, avg)
    return strengths, avg, sim, probs


if not KO.exists():
    st.error("No knockout data yet. Run `python -m src` first.")
    st.stop()

teams, ko = load_data()
strengths, league_avg, sim, cur_probs = compute(teams, ko)
by_no = {m["match_no"]: m for m in ko}
champ = sim["champion"]

st.title("🏆 World Cup 2026 — Knockout Bracket")
last = max((m.get("scraped_at") or "" for m in ko), default="")
played = sum(1 for m in ko if m["status"] == "played")
st.caption(f"{played}/{len(ko)} matches played · advancement odds from 20,000 simulations · updated {last[:16]}")


# --- bracket structure: split into left/right halves of the tree ------------
def subtree_rounds(root: int) -> dict[int, list[int]]:
    lists: dict[int, list[int]] = defaultdict(list)

    def rec(no):
        if no is None or no not in by_no:
            return
        m = by_no[no]
        rec(m.get("home_from"))
        lists[m["round_idx"]].append(no)
        rec(m.get("away_from"))

    rec(root)
    return lists


left = subtree_rounds(101)   # semifinal 101 subtree
right = subtree_rounds(102)  # semifinal 102 subtree


def short_ref(ref: str) -> str:
    return ref.replace("Winner Match ", "W-M").replace("Loser Match ", "L-M")


def team_line(m: dict, side: str) -> str:
    team = m.get(f"{side}_team")
    ref = m.get(f"{side}_ref")
    label = team or short_ref(ref or "TBD")
    score = m.get(f"{side}_score")
    pens = m.get(f"{side}_pens")
    is_winner = bool(m.get("winner")) and m.get("winner") == team

    # right-hand value: score if played, else advance % if known, else nothing
    if score is not None:
        val = str(score) + (f" ({pens})" if pens is not None else "")
    elif team and m["match_no"] in cur_probs:
        val = f"{cur_probs[m['match_no']][team] * 100:.0f}%"
    else:
        val = ""

    cls = "team win" if is_winner else ("team" if team else "team tbd")
    return (
        f'<div class="{cls}"><span class="nm">{flag(team)} {label}</span>'
        f'<span class="val">{val}</span></div>'
    )


def tile(no: int) -> str:
    m = by_no[no]
    return (
        f'<a class="tilelink" target="_self" href="?match={no}">'
        f'<div class="tile">'
        f'<div class="date">{m.get("match_date") or ""} · {m["round"].replace("Round of","R")}</div>'
        f"{team_line(m, 'home')}{team_line(m, 'away')}"
        f"</div></a>"
    )


def column(nos: list[int]) -> str:
    return '<div class="col">' + "".join(tile(n) for n in nos) + "</div>"


CSS = """
<style>
.bracket { display:flex; align-items:stretch; gap:10px; overflow-x:auto; padding:8px 2px 16px; }
.col { display:flex; flex-direction:column; justify-content:space-around; min-width:150px; gap:8px; }
.col.final { justify-content:center; min-width:170px; }
.tilelink { text-decoration:none !important; }
.tile { background:var(--secondary-background-color,#f2f3f5); border:1px solid rgba(128,128,128,.25);
        border-radius:10px; padding:6px 8px; transition:border-color .15s, transform .1s; }
.tile:hover { border-color:#e0245e; transform:translateY(-1px); }
.date { font-size:10px; opacity:.6; margin-bottom:3px; }
.team { display:flex; justify-content:space-between; gap:8px; font-size:13px; padding:1px 0; color:var(--text-color,#111); }
.team .nm { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.team .val { font-variant-numeric:tabular-nums; opacity:.75; }
.team.win .nm { font-weight:700; }
.team.win .val { color:#1a9850; font-weight:700; opacity:1; }
.team.tbd { opacity:.5; font-style:italic; }
.champ-tile { text-align:center; padding:10px; border:2px solid #f4c542; border-radius:12px;
              background:rgba(244,197,66,.12); font-weight:700; }
</style>
"""

bracket_html = (
    '<div class="bracket">'
    + column(left[0]) + column(left[1]) + column(left[2]) + column(left[3])
    + '<div class="col final">' + tile(104) + "</div>"
    + column(right[3]) + column(right[2]) + column(right[1]) + column(right[0])
    + "</div>"
)

st.markdown(CSS + bracket_html, unsafe_allow_html=True)
st.caption("← Round of 32 · … · Final · … · Round of 32 →  |  click any match for detail")

# --- third place + detail / odds -------------------------------------------
col_detail, col_odds = st.columns([3, 2], gap="large")

with col_detail:
    sel = st.query_params.get("match")
    if sel and sel.isdigit() and int(sel) in by_no:
        m = by_no[int(sel)]
        h, a = m.get("home_team"), m.get("away_team")
        st.subheader(f"Match {m['match_no']} · {m['round']}")
        st.caption(f"{m.get('match_date') or 'TBD'} · {m.get('venue') or ''}")

        if m["status"] == "played":
            res = f"{flag(h)} {h}  {m['home_score']}–{m['away_score']}  {a} {flag(a)}"
            if m.get("home_pens") is not None:
                res += f"  (pens {m['home_pens']}–{m['away_pens']})"
            st.markdown(f"**Result:** {res}")
            st.success(f"Advanced: {flag(m['winner'])} **{m['winner']}**")
        elif h and a:
            p = match_win_prob(h, a, strengths, league_avg)
            st.markdown(f"**{flag(h)} {h}** vs **{a} {flag(a)}**")
            st.progress(p, text=f"{h} advances — {p*100:.0f}%")
            st.progress(1 - p, text=f"{a} advances — {(1-p)*100:.0f}%")
            hs, aw = strengths.get(h), strengths.get(a)
            if hs and aw:
                eh = hs.attack * aw.defense * league_avg
                ea = aw.attack * hs.defense * league_avg
                st.caption(f"Expected goals: {h} {eh:.2f} – {ea:.2f} {a}")
            c1, c2 = st.columns(2)
            c1.metric(f"{h} title odds", f"{champ.get(h,0)*100:.1f}%")
            c2.metric(f"{a} title odds", f"{champ.get(a,0)*100:.1f}%")
        else:
            st.info(f"Participants not decided yet: {m['home_ref']} vs {m['away_ref']}.")
            st.caption("Feeds from earlier matches — click those tiles to explore.")
    else:
        st.subheader("Match detail")
        st.info("Click any tile in the bracket above to see the matchup breakdown.")

    # third-place match
    if 103 in by_no:
        tp = by_no[103]
        with st.expander("🥉 Third-place match"):
            if tp["status"] == "played":
                st.write(f"{flag(tp['home_team'])} {tp['home_team']} {tp['home_score']}–{tp['away_score']} {tp['away_team']} {flag(tp['away_team'])}")
            else:
                st.write(f"{short_ref(tp['home_ref'])} vs {short_ref(tp['away_ref'])} · {tp.get('match_date') or 'TBD'}")

with col_odds:
    st.subheader("🏆 Championship odds")
    ranked = sorted(champ.items(), key=lambda x: -x[1])[:12]
    for team, p in ranked:
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;padding:2px 0;">'
            f'<span>{flag(team)} {team}</span><span style="font-variant-numeric:tabular-nums;">{p*100:.1f}%</span></div>',
            unsafe_allow_html=True,
        )
        st.progress(min(p / (ranked[0][1] or 1), 1.0))
    st.caption("From 20,000 Monte Carlo simulations of the remaining bracket.")
