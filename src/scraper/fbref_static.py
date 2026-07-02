"""FBref static-HTML scraper (BeautifulSoup).

Two FBref-specific craft details worth calling out in the README:
  1. Many FBref stat tables are wrapped in HTML comments to deter scrapers —
     we un-comment them before parsing.
  2. We parse cells by their `data-stat` attribute rather than column position,
     so re-ordered columns don't break us.
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup, Comment

from .base import HttpClient, client_config_from

log = logging.getLogger("scraper.fbref")


class FbrefScraper:
    def __init__(self, source_cfg: dict, defaults: dict):
        self.cfg = source_cfg
        self.base_url = source_cfg["base_url"].rstrip("/")
        self.client = HttpClient(client_config_from(defaults, source_cfg))

    def _get_soup(self, path: str) -> BeautifulSoup | None:
        resp = self.client.get(self.base_url + path)
        if resp is None:
            return None
        soup = BeautifulSoup(resp.text, "lxml")
        # Surface tables that FBref hides inside HTML comments.
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            if "<table" in comment:
                comment.replace_with(BeautifulSoup(comment, "lxml"))
        return soup

    @staticmethod
    def _parse_table(soup: BeautifulSoup, table_spec: dict) -> list[dict]:
        table = soup.find("table", id=table_spec["table_id"])
        if table is None:
            log.warning("table id=%s not found on page", table_spec["table_id"])
            return []

        fields: dict[str, str] = table_spec["fields"]
        body = table.find("tbody")
        if body is None:
            return []

        records: list[dict] = []
        for tr in body.find_all("tr"):
            classes = tr.get("class") or []
            if "thead" in classes:  # repeated header rows inside the body
                continue

            record = {"record_type": table_spec.get("record_type", "unknown")}
            for our_field, data_stat in fields.items():
                cell = tr.find(attrs={"data-stat": data_stat})
                text = cell.get_text(strip=True) if cell is not None else None
                record[our_field] = text or None

            # Skip spacer / fully-empty rows.
            if all(record[f] is None for f in fields):
                continue
            records.append(record)

        return records

    def scrape(self) -> list[dict]:
        results: list[dict] = []
        for page_key, page in self.cfg.get("pages", {}).items():
            soup = self._get_soup(page["path"])
            if soup is None:
                log.error("failed to fetch page %s (%s)", page_key, page["path"])
                continue
            for table_spec in page.get("tables", []):
                rows = self._parse_table(soup, table_spec)
                log.info("parsed %d rows from %s/%s", len(rows), page_key, table_spec["table_id"])
                results.extend(rows)
        return results
