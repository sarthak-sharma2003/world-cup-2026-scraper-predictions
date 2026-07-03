# World Cup 2026 — Live Prediction Dashboard

A scheduled, multi-source football scraper feeding a prediction model into a
public, live-updating World Cup 2026 dashboard.

**▶ Live dashboard:** https://world-cup-2026-scraper-predictions.streamlit.app/
**Scheduled run history (reliability proof):** https://github.com/sarthak-sharma2003/world-cup-2026-scraper-predictions/actions

Built as a portfolio piece demonstrating production scraping craft — reliable batch
pipelines, robots-compliant fetching, and cross-source data integrity.

---

## What this does (all working)

| Capability | Where it lives |
|---|---|
| Static HTML parsing (BeautifulSoup) — group standings | [`src/scraper/wikipedia_static.py`](src/scraper/wikipedia_static.py) |
| Knockout bracket scraping + self-validating tree reconstruction | [`src/scraper/knockout.py`](src/scraper/knockout.py) |
| Rate limiting + retry/backoff + robots.txt compliance | [`src/scraper/base.py`](src/scraper/base.py) |
| Config-driven selectors (site change = one-line edit) | [`config/sources.yaml`](config/sources.yaml) |
| Validation + **cross-source name normalization** | [`src/validator.py`](src/validator.py) |
| **Cross-source consistency check** (Wikipedia ⇄ dataset) | [`src/scraper/dataset.py`](src/scraper/dataset.py) |
| Structured delivery (SQLite + CSV/JSON) | [`src/storage.py`](src/storage.py) |
| Scheduled reliability (public run history) | [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml) |
| **Dynamic / JS-rendered extraction** (Selenium headless Chrome, content absent from raw HTML) | [`src/scraper/dynamic_render.py`](src/scraper/dynamic_render.py) |
| Prediction model (Elo prior + xG form, Monte Carlo) | [`src/model.py`](src/model.py), [`src/knockout_model.py`](src/knockout_model.py) |

The **dynamic / JS-rendered layer** ([`src/scraper/dynamic_render.py`](src/scraper/dynamic_render.py))
renders a JavaScript-built page in headless Chrome and parses content that is absent
from the raw HTML (a plain `requests.get` gets an empty container). It runs against a
robots-permitted scraping sandbox: the richer football sources that would be more
on-theme (FBref, Understat, Sofascore) are each walled by Cloudflare or `robots.txt`,
and this project will not do anti-bot evasion or ignore robots.

**Planned (not yet built):** an Apify actor to reach the Cloudflare-protected FBref,
LLM extraction of unstructured notes, and a Dixon-Coles model upgrade.

## Architecture

```
[ GitHub Actions cron ] ─► [ scrapers ] ─────────────► [ SQLite + CSV/JSON exports ]
  (public run history)   Wikipedia static (standings)          │
                         Wikipedia knockout bracket            │
                         dataset enrichment (Elo + xG)         │
                                                               ▼
                                    [ Poisson model: Elo prior × xG form ]
                                    [ + Monte Carlo championship odds ]
                                                               ▼
                                            [ Streamlit dashboard (public URL) ]
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q            # data-integrity + model tests
python -m src        # scrape → validate → store → export pipeline
```

Outputs land in `data/exports/` (`team_stats`, `knockout_matches`, `model_inputs`; each as JSON + CSV).

Launch the dashboard:

```bash
streamlit run dashboard.py   # then open http://localhost:8501
```

Pages: **Home** (group standings + match predictor) and **Knockouts** (live
double-sided bracket with advancement probabilities; click any match for detail).

## Deploy (free public URL)
Hosted on **Streamlit Community Cloud** (free), serving from this repo and
auto-redeploying whenever the scheduled scrape commits fresh data. To redeploy your
own copy: [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub →
Create app from this repo, branch `main`, main file `dashboard.py`. No secrets needed;
runtime deps are just `streamlit` + `pandas`.

## Prediction model
Poisson goal model where each team's attack/defense strength blends, geometrically,
a **pre-tournament Elo prior** with **tournament xG form** (`strength = form^0.4 · elo^0.6`).
Elo fixes ordering (pedigree), xG form adjusts for who's actually playing well, and using xG
instead of raw goals avoids rewarding lucky finishing. Knockouts use a two-outcome variant
(no draws; level games split 50/50 for ET/pens) plus a 20k-run Monte Carlo for championship odds.

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
