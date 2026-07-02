"""Pipeline entrypoint: `python -m src`.

scrape -> validate -> store -> export -> log the run. Designed so a few broken
rows or one dead page degrade gracefully instead of killing the whole run.
"""
from __future__ import annotations

import logging

from . import storage, validator
from .config import load_config
from .scraper.wikipedia_static import WikipediaScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("pipeline")


def run() -> None:
    cfg = load_config()
    defaults = cfg.get("defaults", {})

    conn = storage.connect()
    storage.init_db(conn)

    source_key = "wikipedia"
    source_cfg = cfg["sources"][source_key]
    started_at = storage._now()

    raw = WikipediaScraper(source_cfg, defaults).scrape()
    log.info("scraped %d raw records", len(raw))

    clean: list[dict] = []
    failures = 0
    for rec in raw:
        cleaned, errors = validator.validate_team_stat(rec)
        if errors:
            failures += 1
            log.warning("validation issues for %r: %s", rec.get("team"), errors)
            if cleaned.get("canonical_team") is None:
                continue  # unusable row — drop it, keep going
        clean.append(cleaned)

    storage.upsert_team_stats(conn, clean, source=source_key)
    storage.export_table(conn, "team_stats")

    unique = conn.execute(
        "SELECT COUNT(*) FROM team_stats WHERE source = ?", (source_key,)
    ).fetchone()[0]
    status = "ok" if unique else "empty"
    storage.log_run(conn, source_key, started_at, records=unique, failures=failures, status=status)
    log.info(
        "done: scraped=%d unique_teams=%d validation_failures=%d status=%s",
        len(raw),
        unique,
        failures,
        status,
    )


if __name__ == "__main__":
    run()
