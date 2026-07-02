# World Cup 2026 — Live Prediction Dashboard

A scheduled, multi-source football scraper feeding a Dixon-Coles model into a
public, live-updating World Cup 2026 prediction dashboard.

**Live dashboard:** _(link once deployed)_
**Scheduled run history (reliability proof):** _(link to the Actions tab once pushed)_

Built as a portfolio piece demonstrating production scraping craft — reliable batch
pipelines, dynamic-content handling, and cross-source data integrity.

---

## What this proves (scraping craft)

| Capability | Where it lives |
|---|---|
| Static HTML parsing (BeautifulSoup) | [`src/scraper/fbref_static.py`](src/scraper/fbref_static.py) |
| Dynamic / JS-rendered pages (Selenium) | _planned:_ `src/scraper/dynamic_render.py` |
| Reverse-engineered AJAX/JSON endpoint | _planned:_ `src/scraper/json_endpoint.py` |
| Rate limiting + retry/backoff + robots.txt | [`src/scraper/base.py`](src/scraper/base.py) |
| Config-driven selectors (site change = one-line edit) | [`config/sources.yaml`](config/sources.yaml) |
| Validation + **cross-source name normalization** | [`src/validator.py`](src/validator.py) |
| Structured delivery (SQLite + CSV/JSON) | [`src/storage.py`](src/storage.py) |
| Scheduled reliability (public run history) | [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) |
| LLM extraction of unstructured notes | _planned:_ `src/scraper/llm_extract.py` |
| Apify actor comparison | _planned:_ `src/scraper/apify_compare.py` |

## Architecture

```
[ GitHub Actions cron ] ──► [ scraper ] ──► [ SQLite + CSV/JSON exports ]
   (public run history)      static/dynamic/JSON        │
                                                        ▼
                                       [ Dixon-Coles model ] ──► [ Streamlit dashboard ]
```

Data hierarchy (maps to the JD's "regions → companies → details"):
`Competition / Group → National Team → Player stats + Match detail`.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q            # data-integrity tests
python -m src        # run the scrape → validate → store → export pipeline
```

Outputs land in `data/exports/` (`team_stats.json`, `team_stats.csv`).

## Reliability & compliance
- Polite by default: real User-Agent, per-source rate limits, exponential backoff, robots.txt checks.
- Graceful degradation: bad rows are logged and skipped, not fatal; each run is recorded in `scrape_runs`.
- Config-driven selectors keep the codebase stable when a site tweaks its markup.

## Status
Scaffold complete: static scraper + validation + storage + scheduled workflow.
Next: dynamic (Selenium) source, JSON-endpoint source, Dixon-Coles model, Streamlit dashboard.
