"""Dynamic (JavaScript-rendered) scraping layer — Selenium headless Chrome.

The other sources in this project (Wikipedia, dataset CSVs) ship their data in the
initial HTML. This layer handles the harder case: pages whose content is injected
client-side by JavaScript and is simply *absent* from the raw HTML response. It
renders such a page in a real headless browser, waits for the JS-built content to
appear, paginates, and parses the resulting DOM — then feeds the same
validation -> SQLite -> CSV/JSON pipeline as every other source.

Demonstration target: https://quotes.toscrape.com/js/ — a well-known,
robots-permitted scraping sandbox whose records exist ONLY after JavaScript runs
(a plain ``requests.get`` returns an empty container, so a browser is genuinely
required). The rich football stats sites that would be more on-theme (FBref,
Understat, Sofascore) are each walled by Cloudflare or ``robots.txt``; scraping
them would mean anti-bot evasion or ignoring robots — both against this project's
compliance stance — so this layer proves the JS-rendering capability against a
source that explicitly permits it.

Politeness (User-Agent, per-source rate limit, robots.txt) is reused from base.
"""
from __future__ import annotations

import logging
import time

from bs4 import BeautifulSoup

from .base import HttpClient, client_config_from

log = logging.getLogger("scraper.dynamic")


class DynamicRenderScraper:
    """Renders a JS-built page and extracts its records. Contract matches the other
    scrapers: ``scrape() -> list[dict]``."""

    def __init__(self, source_cfg: dict, defaults: dict):
        self.base_url = source_cfg["base_url"].rstrip("/")
        self.path = source_cfg.get("path", "/")
        self.max_pages = int(source_cfg.get("max_pages", 1))
        self.config = client_config_from(defaults, source_cfg)
        # Reuse the shared HTTP client purely for its robots.txt + rate-limit logic.
        self._robots = HttpClient(self.config)

    # -- browser ------------------------------------------------------------
    def _make_driver(self):
        """Build a headless Chrome driver. Selenium is imported lazily so the offline
        unit tests (which only exercise ``_parse_quotes``) need no browser installed."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument(f"--user-agent={self.config.user_agent}")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        driver.set_page_load_timeout(self.config.timeout_seconds)
        return driver

    def _fetch_rendered(self, driver, url: str) -> str | None:
        """robots.txt check -> polite delay -> render -> wait for JS content -> HTML."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        if not self._robots._allowed_by_robots(url):
            log.warning("blocked by robots.txt, skipping: %s", url)
            return None
        time.sleep(self.config.min_delay_seconds)  # per-source rate limit between loads
        try:
            driver.get(url)
            # The .quote blocks don't exist until the page's JavaScript builds them.
            WebDriverWait(driver, self.config.timeout_seconds).until(
                EC.presence_of_element_located((By.CLASS_NAME, "quote"))
            )
        except Exception as exc:  # timeout / no JS content on this page — skip it
            log.warning("render failed for %s: %s", url, exc)
            return None
        return driver.page_source

    # -- parse (pure function; unit-tested offline) -------------------------
    @staticmethod
    def _parse_quotes(html: str) -> list[dict]:
        """Extract quote records from the JS-rendered markup. These ``.quote`` blocks
        are absent from the raw HTML — the parse only has anything to work on because
        the page was rendered in a browser first."""
        soup = BeautifulSoup(html, "html.parser")
        rows: list[dict] = []
        for q in soup.select("div.quote"):
            text_el = q.select_one(".text")
            author_el = q.select_one(".author")
            if text_el is None or author_el is None:
                continue  # incomplete/placeholder block
            tags = [t.get_text(strip=True) for t in q.select("a.tag")]
            rows.append(
                {
                    "quote": text_el.get_text(strip=True),
                    "author": author_el.get_text(strip=True),
                    "tags": ", ".join(tags),
                }
            )
        return rows

    # -- orchestration ------------------------------------------------------
    def scrape(self) -> list[dict]:
        try:
            driver = self._make_driver()
        except Exception as exc:  # no browser/driver available — degrade gracefully
            log.error("could not start headless browser: %s", exc)
            return []

        out: list[dict] = []
        try:
            for page in range(1, self.max_pages + 1):
                path = self.path if page == 1 else f"{self.path.rstrip('/')}/page/{page}/"
                html = self._fetch_rendered(driver, self.base_url + path)
                if not html:
                    continue
                rows = self._parse_quotes(html)
                log.info("dynamic: %d records from %s", len(rows), path)
                if not rows:
                    break  # ran past the last page
                out.extend(rows)
        finally:
            try:
                driver.quit()
            except Exception:
                pass
        return out
