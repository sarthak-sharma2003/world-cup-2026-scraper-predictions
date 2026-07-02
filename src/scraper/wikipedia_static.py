"""Wikipedia static-HTML scraper (BeautifulSoup).

Generic wikitable parser driven by config:
  - selects tables by a *header signature* (e.g. any table whose header row
    contains both "Pld" and "Pts") rather than by position — so inserting an
    unrelated table above them doesn't break us;
  - maps columns by header label, not index — so re-ordered columns don't break us.

This is the compliant static-HTML source (Wikipedia's robots.txt permits article
fetches), replacing FBref, which sits behind a Cloudflare bot challenge.
"""
from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup, Tag

from .base import HttpClient, client_config_from

log = logging.getLogger("scraper.wikipedia")

_FOOTNOTE = re.compile(r"\[[^\]]*\]")  # strip "[a]", "[note 1]" citation markers


def _clean(text: str) -> str:
    text = _FOOTNOTE.sub("", text)
    text = text.replace("−", "-")  # unicode minus -> ASCII hyphen
    return text.strip()


class WikipediaScraper:
    def __init__(self, source_cfg: dict, defaults: dict):
        self.cfg = source_cfg
        self.base_url = source_cfg["base_url"].rstrip("/")
        self.client = HttpClient(client_config_from(defaults, source_cfg))

    def _get_soup(self, path: str) -> BeautifulSoup | None:
        resp = self.client.get(self.base_url + path)
        return BeautifulSoup(resp.text, "lxml") if resp is not None else None

    @staticmethod
    def _header_labels(table: Tag) -> list[str]:
        first = table.find("tr")
        return [c.get_text(strip=True) for c in first.find_all(["th", "td"])] if first else []

    @staticmethod
    def _team_from_cell(cell: Tag) -> str | None:
        # The team cell is a flag <a> (image, no text) followed by the country <a>.
        # Take the first anchor that actually has text; fall back to raw text.
        for a in cell.find_all("a"):
            txt = a.get_text(strip=True)
            if txt:
                return txt
        return _clean(cell.get_text(strip=True)) or None

    def _parse_table(self, table: Tag, spec: dict) -> list[dict]:
        labels = self._header_labels(table)
        field_idx = {
            our: labels.index(header)
            for our, header in spec["fields"].items()
            if header in labels
        }
        team_prefix = spec.get("team_column", "Team")
        team_idx = next((i for i, l in enumerate(labels) if l.startswith(team_prefix)), None)

        records: list[dict] = []
        for tr in table.find_all("tr")[1:]:  # skip header row
            cells = tr.find_all(["th", "td"])
            # Allow one missing trailing cell (e.g. a rowspanned "Qualification" column).
            if len(cells) < len(labels) - 1:
                continue

            rec: dict = {"record_type": spec.get("record_type", "unknown")}
            if team_idx is not None and team_idx < len(cells):
                rec["team"] = self._team_from_cell(cells[team_idx])
            for our, idx in field_idx.items():
                rec[our] = _clean(cells[idx].get_text(strip=True)) if idx < len(cells) else None

            if not rec.get("team"):
                continue
            records.append(rec)
        return records

    def scrape(self) -> list[dict]:
        results: list[dict] = []
        for page_key, page in self.cfg.get("pages", {}).items():
            soup = self._get_soup(page["path"])
            if soup is None:
                log.error("failed to fetch page %s (%s)", page_key, page["path"])
                continue
            all_tables = soup.find_all("table", class_="wikitable")
            for spec in page.get("tables", []):
                signature = set(spec.get("select_by_headers", []))
                matched = [
                    t for t in all_tables if signature.issubset(set(self._header_labels(t)))
                ]
                log.info(
                    "matched %d tables for record_type=%s on %s",
                    len(matched),
                    spec.get("record_type"),
                    page_key,
                )
                for table in matched:
                    results.extend(self._parse_table(table, spec))
        return results
