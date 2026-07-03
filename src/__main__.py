"""Pipeline entrypoint: `python -m src`.

scrape -> validate -> store -> export -> log the run. Designed so a few broken
rows or one dead page degrade gracefully instead of killing the whole run.
"""
from __future__ import annotations

import logging

from . import storage, validator
from .config import load_config
from .scraper.dataset import DatasetScraper, cross_validate
from .scraper.knockout import KnockoutScraper
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

    # Knockout bracket
    ko_started = storage._now()
    knockouts = KnockoutScraper(source_cfg, defaults).scrape()
    storage.upsert_knockout(conn, knockouts, source=source_key)
    storage.export_table(conn, "knockout_matches")
    storage.log_run(
        conn, "knockout", ko_started, records=len(knockouts), failures=0,
        status="ok" if knockouts else "empty",
    )
    log.info("knockout matches stored=%d", len(knockouts))

    # Model-input enrichment (Elo prior + xG form) from the community dataset
    ds_cfg = cfg["sources"].get("wc2026_dataset")
    if ds_cfg:
        ds_started = storage._now()
        model_inputs = DatasetScraper(ds_cfg, defaults).scrape()
        if model_inputs:
            cross_validate(model_inputs, [r["canonical_team"] for r in clean])
            storage.upsert_model_inputs(conn, model_inputs, source="wc2026_dataset")
            storage.export_table(conn, "model_inputs")
        storage.log_run(
            conn, "dataset", ds_started, records=len(model_inputs), failures=0,
            status="ok" if model_inputs else "empty",
        )
        log.info("model inputs (elo+xg) stored=%d", len(model_inputs))

    # Dynamic (JS-rendered) layer: content built client-side by JavaScript and
    # absent from the raw HTML, extracted with headless Selenium. Fully isolated in
    # try/except — a missing browser or a render timeout must NOT break the
    # scheduled Wikipedia/dataset refresh.
    dyn_cfg = cfg["sources"].get("dynamic_js")
    if dyn_cfg:
        dyn_started = storage._now()
        try:
            from .scraper.dynamic_render import DynamicRenderScraper

            raw = DynamicRenderScraper(dyn_cfg, defaults).scrape()
            clean_dyn: list[dict] = []
            dyn_failures = 0
            for rec in raw:
                cleaned, errors = validator.validate_quote(rec)
                if errors:
                    dyn_failures += 1
                    log.warning("dynamic validation issues: %s", errors)
                    if not cleaned.get("quote"):
                        continue  # unusable row — drop it, keep going
                clean_dyn.append(cleaned)
            stored = storage.upsert_dynamic_quotes(conn, clean_dyn, source="quotes_js")
            storage.export_table(conn, "dynamic_quotes")
            storage.log_run(
                conn, "dynamic_js", dyn_started, records=stored, failures=dyn_failures,
                status="ok" if stored else "empty",
            )
            log.info("dynamic (JS-rendered) layer: records stored=%d failures=%d", stored, dyn_failures)
        except Exception as exc:  # non-fatal: log and move on
            log.error("dynamic layer failed (non-fatal): %s", exc)
            storage.log_run(conn, "dynamic_js", dyn_started, records=0, failures=0, status="failed")


if __name__ == "__main__":
    run()
