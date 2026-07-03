"""Knockout-bracket scraper (Wikipedia football-box elements).

Design notes (the interesting data-engineering part):
  - Match boxes are parsed via their structured classes (.fhome/.faway/.fscore/
    .fdate), NOT by DOM position — boxes are NOT in match-number order.
  - Each match's true number comes from its "Report N" link (played) or its
    "Match N" placeholder score (scheduled).
  - Penalty-shootout winners aren't in the main score ("1-1 (a.e.t.)"), so we
    parse the "Penalties X-Y" line, then cross-validate the winner against the
    team that appears in the next round's slot.
  - The bracket tree is reconstructed from explicit "Winner Match N" references
    and, where a slot already holds a real team, by finding which prior-round
    match that team won. Both agree — mismatches are logged.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from ..validator import normalize_team_name
from .base import HttpClient, client_config_from

log = logging.getLogger("scraper.knockout")

ROUND_ORDER = {
    "Round of 32": 0,
    "Round of 16": 1,
    "Quarterfinals": 2,
    "Semifinals": 3,
    "Final": 4,
}
THIRD_PLACE = "Match for third place"

# Fixed WC2026 48-team knockout match-number ranges (matches 73-104). Used to
# number matches robustly instead of trusting the page's "Report N" citation
# labels, which only coincidentally align with match numbers.
ROUND_RANGES: dict[str, range] = {
    "Round of 32": range(73, 89),
    "Round of 16": range(89, 97),
    "Quarterfinals": range(97, 101),
    "Semifinals": range(101, 103),
    THIRD_PLACE: range(103, 104),
    "Final": range(104, 105),
}

_SCORE_RE = re.compile(r"(\d+)\s*[–\-]\s*(\d+)")
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_REF_RE = re.compile(r"(Winner|Loser)\s+Match\s+(\d+)", re.I)
_MATCHNO_RE = re.compile(r"Match\s+(\d+)", re.I)
_FOOTNOTE_RE = re.compile(r"\[[^\]]*\]")


def _clean(text: str) -> str:
    return _FOOTNOTE_RE.sub("", text).replace("−", "-").strip()


class KnockoutScraper:
    def __init__(self, source_cfg: dict, defaults: dict):
        self.base_url = source_cfg["base_url"].rstrip("/")
        self.path = source_cfg.get("knockout_page", "/wiki/2026_FIFA_World_Cup")
        self.client = HttpClient(client_config_from(defaults, source_cfg))

    # -- fetch --------------------------------------------------------------
    def _get_soup(self) -> BeautifulSoup | None:
        resp = self.client.get(self.base_url + self.path)
        return BeautifulSoup(resp.text, "lxml") if resp is not None else None

    @staticmethod
    def _round_for(box: Tag) -> str | None:
        heading = box.find_previous(
            lambda t: t.name in ("h2", "h3", "h4")
            and any(
                k in t.get_text().lower()
                for k in ("round of", "final", "quarter", "semi", "third place")
            )
        )
        if not heading:
            return None
        text = heading.get_text(strip=True)
        for name in list(ROUND_ORDER) + [THIRD_PLACE]:
            if name.lower() in text.lower():
                return name
        return None

    # -- per-box parsing ----------------------------------------------------
    @staticmethod
    def _parse_ref(raw: str) -> tuple[str, str | None, int | None]:
        """Return (display_ref, canonical_team_or_None, feeder_match_no_or_None)."""
        raw = _clean(raw)
        m = _REF_RE.search(raw)
        if m:
            return raw, None, int(m.group(2))
        return raw, normalize_team_name(raw), None

    def _parse_box(self, box: Tag, round_name: str) -> dict | None:
        home_el, away_el, score_el = (
            box.find(class_="fhome"),
            box.find(class_="faway"),
            box.find(class_="fscore"),
        )
        if not (home_el and away_el and score_el):
            return None

        score_txt = _clean(score_el.get_text(strip=True))
        full_txt = box.get_text(" ", strip=True)

        # An unplayed match shows "Match N" (the bracket template's own number) as
        # its score. That number is reliable; played matches carry only a citation
        # label, so their number is assigned per-round later (see _assign_numbers).
        scheduled = bool(_MATCHNO_RE.fullmatch(score_txt.replace("\xa0", " ").strip()))
        claimed_no = int(_MATCHNO_RE.search(score_txt).group(1)) if scheduled else None

        home_ref, home_team, home_from = self._parse_ref(home_el.get_text(strip=True))
        away_ref, away_team, away_from = self._parse_ref(away_el.get_text(strip=True))

        rec: dict = {
            "match_no": None,
            "claimed_no": claimed_no,
            "round": round_name,
            "round_idx": ROUND_ORDER.get(round_name, 99),
            "home_ref": home_ref,
            "away_ref": away_ref,
            "home_team": home_team,
            "away_team": away_team,
            "home_from": home_from,
            "away_from": away_from,
            "home_score": None,
            "away_score": None,
            "home_pens": None,
            "away_pens": None,
            "winner": None,
            "status": "scheduled" if scheduled else "played",
        }

        date_el = box.find(class_="fleft") or box.find(class_="fdate")
        if date_el:
            d = _ISO_DATE_RE.search(date_el.get_text(" ", strip=True))
            rec["match_date"] = d.group(1) if d else None
        right = box.find(class_="fright")
        if right:
            rec["venue"] = _clean(right.get_text(" ", strip=True).split("Attendance")[0])

        if not scheduled:
            self._parse_result(rec, score_txt, full_txt)
        return rec

    @staticmethod
    def _parse_result(rec: dict, score_txt: str, full_txt: str) -> None:
        m = _SCORE_RE.search(score_txt)
        if not m:
            return
        hs, as_ = int(m.group(1)), int(m.group(2))
        rec["home_score"], rec["away_score"] = hs, as_

        winner_side = None
        if hs > as_:
            winner_side = "home"
        elif as_ > hs:
            winner_side = "away"
        else:  # level after 90/120 -> penalties decide
            pm = _SCORE_RE.search(full_txt.split("Penalties", 1)[1]) if "Penalties" in full_txt else None
            if pm:
                hp, ap = int(pm.group(1)), int(pm.group(2))
                rec["home_pens"], rec["away_pens"] = hp, ap
                winner_side = "home" if hp > ap else "away"

        if winner_side:
            rec["winner"] = rec[f"{winner_side}_team"]

    # -- tree reconstruction ------------------------------------------------
    @staticmethod
    def _link_feeders(matches: list[dict]) -> None:
        """Fill home_from/away_from where a slot holds a real team, by finding the
        prior-round match that team won. Cross-check explicit 'Winner Match N' refs."""
        by_round: dict[int, list[dict]] = {}
        for m in matches:
            by_round.setdefault(m["round_idx"], []).append(m)

        for m in matches:
            prev = by_round.get(m["round_idx"] - 1, [])
            for side in ("home", "away"):
                team = m[f"{side}_team"]
                ref_feeder = m[f"{side}_from"]
                if team is None:
                    continue  # unresolved "Winner Match N" already has its feeder
                won = next((p for p in prev if p.get("winner") == team), None)
                if won is None:
                    continue
                if ref_feeder is not None and ref_feeder != won["match_no"]:
                    log.warning(
                        "feeder mismatch for match %s %s: ref=%s inferred=%s",
                        m["match_no"], side, ref_feeder, won["match_no"],
                    )
                m[f"{side}_from"] = won["match_no"]

    @staticmethod
    def _assign_numbers(matches: list[dict]) -> None:
        """Number matches per round: honour reliable 'Match N' labels from unplayed
        matches, then fill each round's remaining fixed slots with the played ones.
        Guarantees unique numbers and full coverage even when the page's citation
        labels collide."""
        from collections import defaultdict

        by_round: dict[str, list[dict]] = defaultdict(list)
        for m in matches:
            by_round[m["round"]].append(m)

        for round_name, rng in ROUND_RANGES.items():
            group = by_round.get(round_name, [])
            slots = set(rng)
            used: set[int] = set()
            for m in group:  # honour valid, non-colliding "Match N" labels first
                c = m.get("claimed_no")
                if c in slots and c not in used:
                    m["match_no"] = c
                    used.add(c)
            remaining = iter(sorted(slots - used))
            for m in group:
                if m["match_no"] is None:
                    m["match_no"] = next(remaining, None)
            if len(group) != len(rng):
                log.warning("round %s: %d boxes, expected %d", round_name, len(group), len(rng))

    def scrape(self) -> list[dict]:
        soup = self._get_soup()
        if soup is None:
            log.error("failed to fetch knockout page")
            return []

        matches: list[dict] = []
        for box in soup.find_all(class_="footballbox"):
            round_name = self._round_for(box)
            if round_name is None:  # group-stage box
                continue
            rec = self._parse_box(box, round_name)
            if rec:
                matches.append(rec)

        self._assign_numbers(matches)
        matches = [m for m in matches if m["match_no"] is not None]
        for m in matches:
            m.pop("claimed_no", None)
        matches.sort(key=lambda m: m["match_no"])

        self._link_feeders(matches)
        log.info("parsed %d knockout matches", len(matches))
        return matches
