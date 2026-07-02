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

Launch the dashboard:

```bash
streamlit run dashboard.py   # then open http://localhost:8501
```

Pages: **Home** (group standings + match predictor) and **Knockouts** (live
double-sided bracket with advancement probabilities; click any match for detail).

## Deploy (free public URL)
Hosted on **Streamlit Community Cloud** (free), which serves from this repo and
auto-redeploys whenever the scheduled scrape commits fresh data:
1. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub.
2. **Create app → Deploy a public app from GitHub.**
3. Repo `sarthak-sharma2003/world-cup-2026-scraper-predictions`, branch `main`,
   main file `dashboard.py`.
4. **Deploy.** Pick a subdomain → your public `*.streamlit.app` URL.

No secrets/config needed. Runtime deps: `streamlit`, `pandas` (see requirements.txt).

## Reliability & compliance
- Polite by default: real User-Agent, per-source rate limits, exponential backoff, robots.txt checks.
- Graceful degradation: bad rows are logged and skipped, not fatal; each run is recorded in `scrape_runs`.
- Config-driven selectors keep the codebase stable when a site tweaks its markup.

## Data sources & credits
- **Wikipedia** (`2026 FIFA World Cup`) — primary, self-scraped: group standings + full
  knockout bracket. robots.txt-compliant.
- **[FIFA World Cup 2026 Dataset](https://github.com/mominullptr/FIFA-World-Cup-2026-Dataset)**
  by *mominullptr* (also on Kaggle / Hugging Face) — enrichment: pre-tournament Elo & FIFA
  ranking prior, and per-match xG used as the form signal. Fetched from its public raw CSVs
  and **cross-validated against the Wikipedia scrape** (name reconciliation, e.g.
  "Congo DR" ⇄ "DR Congo"). Used under attribution; see the dataset's CITATION.cff.

## Prediction model
Poisson goal model where each team's attack/defense strength blends, geometrically:
a **pre-tournament Elo prior** with **tournament xG form** (`strength = form^0.4 · elo^0.6`).
Elo fixes ordering (pedigree), xG form adjusts for who's actually playing well, and using xG
instead of raw goals avoids rewarding lucky finishing. Knockouts use a two-outcome variant
(no draws; level games split 50/50 for ET/pens) plus a 20k-run Monte Carlo for championship odds.

## Status
Working: static scraper (group standings + knockout bracket) + validation + storage +
scheduled workflow + Streamlit dashboard (standings, match predictor, live knockout bracket
with Monte Carlo championship odds).
Next: dynamic (Selenium) source, JSON-endpoint source, Dixon-Coles upgrade, Apify/FBref comparison.
