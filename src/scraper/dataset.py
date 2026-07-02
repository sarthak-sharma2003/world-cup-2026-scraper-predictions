"""Model-input enrichment from the community FIFA WC2026 dataset.

Source: https://github.com/mominullptr/FIFA-World-Cup-2026-Dataset (also on Kaggle /
Hugging Face), fetched from its raw CSV endpoints. It provides two things our
Wikipedia scrape doesn't:
  - a pre-tournament strength prior (Elo + FIFA ranking) per team;
  - per-match expected goals (xG), a far better form signal than raw goals
    (chance quality, not lucky finishing).

This is an *enrichment + cross-validation* source — the Wikipedia scraper remains
the primary, self-collected data. Team names are normalised to our canonical form
so the two sources reconcile (e.g. "Czechia" -> "Czech Republic").
"""
from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict

from ..validator import normalize_team_name
from .base import HttpClient, client_config_from

log = logging.getLogger("scraper.dataset")


class DatasetScraper:
    def __init__(self, source_cfg: dict, defaults: dict):
        self.base_url = source_cfg["base_url"].rstrip("/")
        self.teams_file = source_cfg.get("teams_file", "/teams.csv")
        self.matches_file = source_cfg.get("matches_file", "/matches_detailed.csv")
        self.client = HttpClient(client_config_from(defaults, source_cfg))

    def _fetch_csv(self, path: str) -> list[dict]:
        resp = self.client.get(self.base_url + path)
        if resp is None:
            log.error("failed to fetch %s", path)
            return []
        return list(csv.DictReader(io.StringIO(resp.text)))

    def scrape(self) -> list[dict]:
        teams = self._fetch_csv(self.teams_file)
        matches = self._fetch_csv(self.matches_file)
        if not teams:
            return []

        ratings: dict[str, dict] = {}
        for t in teams:
            name = normalize_team_name(t.get("team_name"))
            if not name:
                continue
            ratings[name] = {
                "team": name,
                "elo": _to_int(t.get("elo_rating")),
                "fifa_rank": _to_int(t.get("fifa_ranking_pre_tournament")),
                "xg_for": 0.0,
                "xg_against": 0.0,
                "xg_games": 0,
            }

        for m in matches:
            if (m.get("status") or "").lower() != "completed":
                continue
            home = normalize_team_name(m.get("home_team_name"))
            away = normalize_team_name(m.get("away_team_name"))
            hx, ax = _to_float(m.get("home_xg")), _to_float(m.get("away_xg"))
            if hx is None or ax is None:
                continue
            for team, gf, ga in ((home, hx, ax), (away, ax, hx)):
                r = ratings.get(team)
                if r is None:
                    continue
                r["xg_for"] += gf
                r["xg_against"] += ga
                r["xg_games"] += 1

        log.info(
            "dataset: %d teams, xG aggregated from %d completed matches",
            len(ratings),
            sum(1 for m in matches if (m.get("status") or "").lower() == "completed"),
        )
        return list(ratings.values())


def cross_validate(dataset_rows: list[dict], scraped_teams: list[str]) -> None:
    """Log teams that don't reconcile between the dataset and our own scrape —
    a cross-source consistency check, not a hard failure."""
    ds = {r["team"] for r in dataset_rows}
    scraped = set(scraped_teams)
    only_scraped = scraped - ds
    only_dataset = ds - scraped
    if only_scraped:
        log.warning("in scrape but not dataset: %s", ", ".join(sorted(only_scraped)))
    if only_dataset:
        log.info("in dataset but not our knockout/group scrape: %d teams", len(only_dataset))
    log.info("cross-validated %d teams present in both sources", len(scraped & ds))


def _to_int(v) -> int | None:
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float | None:
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None
