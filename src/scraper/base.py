"""Polite, resilient HTTP client shared by all scraper layers.

Handles the boring-but-critical reliability work that keeps a scheduled scraper
alive against live sites: rate limiting, exponential backoff with jitter,
robots.txt compliance, and a real User-Agent.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests

log = logging.getLogger("scraper.http")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class ClientConfig:
    user_agent: str = "WC2026-Bot/1.0 (portfolio project)"
    min_delay_seconds: float = 3.0
    max_retries: int = 4
    backoff_base_seconds: float = 2.0
    timeout_seconds: float = 30.0
    respect_robots: bool = True


class HttpClient:
    def __init__(self, config: ClientConfig | None = None):
        self.config = config or ClientConfig()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.config.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        self._last_request_at = 0.0
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}

    # -- rate limiting ------------------------------------------------------
    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.config.min_delay_seconds - elapsed
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.5))  # jitter avoids lockstep

    # -- robots.txt ---------------------------------------------------------
    def _allowed_by_robots(self, url: str) -> bool:
        if not self.config.respect_robots:
            return True
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            self._robots[root] = self._load_robots(root)
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(self.config.user_agent, url)

    def _load_robots(self, root: str) -> robotparser.RobotFileParser | None:
        """Fetch robots.txt with OUR user-agent (not urllib's default, which some
        sites — e.g. Wikipedia — block). Follows the common convention: a 200 is
        parsed; any other status means "no robots restrictions"; a network error
        is treated as unknown (fail open, but logged)."""
        rp = robotparser.RobotFileParser()
        try:
            resp = self.session.get(urljoin(root, "/robots.txt"), timeout=self.config.timeout_seconds)
        except requests.RequestException as exc:
            log.warning("could not fetch robots.txt for %s: %s", root, exc)
            return None
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            log.info("robots.txt for %s returned %s; assuming no restrictions", root, resp.status_code)
            rp.parse([])
        return rp

    # -- fetch --------------------------------------------------------------
    def get(self, url: str) -> requests.Response | None:
        """GET with retry/backoff. Returns None on permanent failure (never raises)."""
        if not self._allowed_by_robots(url):
            log.warning("blocked by robots.txt, skipping: %s", url)
            return None

        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            self._respect_rate_limit()
            try:
                resp = self.session.get(url, timeout=self.config.timeout_seconds)
                self._last_request_at = time.monotonic()
                if resp.status_code == 200:
                    return resp
                if resp.status_code in RETRYABLE_STATUS:
                    raise requests.HTTPError(f"retryable status {resp.status_code}")
                log.warning("non-retryable status %s for %s", resp.status_code, url)
                return None
            except requests.RequestException as exc:
                last_exc = exc
                self._last_request_at = time.monotonic()
                backoff = self.config.backoff_base_seconds * (2 ** (attempt - 1))
                backoff += random.uniform(0, 1)
                log.warning(
                    "attempt %d/%d failed for %s: %s (retry in %.1fs)",
                    attempt,
                    self.config.max_retries,
                    url,
                    exc,
                    backoff,
                )
                time.sleep(backoff)

        log.error("gave up on %s after %d attempts: %s", url, self.config.max_retries, last_exc)
        return None


def client_config_from(defaults: dict, source_cfg: dict) -> ClientConfig:
    """Merge global defaults with per-source overrides into a ClientConfig."""
    merged = {**defaults, **source_cfg}
    return ClientConfig(
        user_agent=merged.get("user_agent", ClientConfig.user_agent),
        min_delay_seconds=merged.get("min_delay_seconds", ClientConfig.min_delay_seconds),
        max_retries=merged.get("max_retries", ClientConfig.max_retries),
        backoff_base_seconds=merged.get("backoff_base_seconds", ClientConfig.backoff_base_seconds),
        timeout_seconds=merged.get("timeout_seconds", ClientConfig.timeout_seconds),
        respect_robots=merged.get("respect_robots", ClientConfig.respect_robots),
    )
