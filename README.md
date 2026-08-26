# TemTek Technology Tracker Agent 

Automated competitive-intelligence pipeline for the home-appliance industry — scrapes and classifies tech news, tracks competitor press releases, and mirrors the EU's EPREL energy-label registry, all on a GitHub Actions schedule and served through a Flask dashboard (branded internally as the **Cleaning and Textile Squad News Tracker**).

[![Tech News Radar](https://github.com/AhmetErman/temtek-actions/actions/workflows/action.yml/badge.svg)](https://github.com/AhmetErman/temtek-actions/actions/workflows/action.yml)
[![Company Newsroom Tracker](https://github.com/AhmetErman/temtek-actions/actions/workflows/company-news.yml/badge.svg)](https://github.com/AhmetErman/temtek-actions/actions/workflows/company-news.yml)
[![EPREL Refresh](https://github.com/AhmetErman/temtek-actions/actions/workflows/eprel-refresh.yml/badge.svg)](https://github.com/AhmetErman/temtek-actions/actions/workflows/eprel-refresh.yml)
[![Teams Digest](https://github.com/AhmetErman/temtek-actions/actions/workflows/teams-digest.yml/badge.svg)](https://github.com/AhmetErman/temtek-actions/actions/workflows/teams-digest.yml)

## Contents
- [What this is](#what-this-is)
- [Dashboard](#dashboard)
- [Pipelines in detail](#pipelines-in-detail)
- [How it fits together](#how-it-fits-together)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Scheduled automation](#scheduled-automation)
- [Project structure](#project-structure)
- [Design notes](#design-notes)
- [Further documentation](#further-documentation)

## What this is

There is no database and no backend service layer. GitHub Actions workflows run Python scripts on a schedule, each script commits its own output straight back into the repo as JSON, and `app.py` just reads those files and serves them. **The committed JSON files are the product, not build artifacts.**

Three independent pipelines feed the dashboard:

| Pipeline | Tracks | Entry point | Commits | Dashboard |
|---|---|---|---|---|
| **Tech News Radar** | JP/CN appliance-tech RSS + 2 site scrapers, translated and classified by Gemini | `scraper_w_filter.py` | `tech_news_classified.json`, `dynamic_classes.json` | `/`, `/beyond` |
| **Company Newsroom Tracker** | Press releases from 8 major appliance competitors since 2023 | `company_pipeline.py` | `company_news.json`, `company_analysis.json` | `/companies` |
| **EPREL Product Database** | The EU's public energy-label registry (~46,000 registrations) | `eprel_scraper.py` | `eprel_products.json` | `/eprel` |

Two more pieces round it out: `teams_digest.py` posts a weekly summary of the tech news to a Microsoft Teams webhook, and `/products` serves a hand-curated flagship comparison (`products.json`) that is never scraped.

The pipelines are live — most of this repo's commit history is automated data refreshes (`[skip ci]`), not manual edits.

## Dashboard

| Route | Page title | Shows |
|---|---|---|
| `/` | Cleaning and Textile Squad News Tracker | Tech news classified into the 5 core categories |
| `/beyond` | Beyond Our Focus | Everything classified as `Other` — wider tech/world news outside the core taxonomy |
| `/companies` | Company News — Appliance Tracker | Competitor press-release feed + charts (volume, theme focus, activity over time) |
| `/products` | Appliance Tech Comparison | Curated flagship-vs-flagship technology matrix across 4 machine categories |
| `/eprel` | EPREL Database — Appliance Energy Benchmark | Sortable/filterable browser over the scraped EU registry, with an in-browser Excel export |

## Pipelines in detail

### 1. Tech News Radar
`scraper_w_filter.py` runs the whole flow start to finish:

1. Loads the existing dataset and splits off any backlog that was scraped previously but never classified.
2. Collects new items — RSS feeds (`ITmedia`, `36Kr`, `KadenWatch`, `Senken`) via `feedparser`, plus two dependency-free `HTMLParser` scrapers for sites with no feed: `cheaa_scraper.py` (CHEAA's washer and smart-home sections) and `ofweek_scraper.py` (OFweek smart home). Every collector is fault-isolated so one source failing never stops the run.
3. Translates Japanese/Chinese entries to English (`deep_translator`, batched, with a hard timeout).
4. **Classifies (Layer 1)** with Gemini (`gemini_filter.py`), walking a fallback chain of models on rate-limit/server errors, into a fixed taxonomy (`taxonomy.py`):
   - Sustainability & Environmental Impact
   - Fabric Care & Textile Engineering
   - Chemical Interaction & Smart Dosing
   - Hygiene & Health Technologies
   - AI, IoT & Smart Sensors
   - *Other*
5. **Sub-classifies (Layer 2)** — `dynamic_subclassifier.py` takes everything tagged `Other` and assigns it a finer sub-label from a registry it grows itself (`dynamic_classes.json`), so the top-level taxonomy stays stable while the catch-all bucket still gains structure.
6. Appends the results back to `tech_news_classified.json` (append-only, so ordering doubles as a recency signal).

### 2. Company Newsroom Tracker
`company_pipeline.py` watches newsroom pages for 8 appliance makers since 2023:

| Company | Method | Status |
|---|---|---|
| Samsung, BSH (Bosch/Siemens), Whirlpool, Midea | HTML listing pages, enriched via Open Graph / JSON-LD metadata | ✅ active |
| Haier | WordPress REST API (`/wp-json/wp/v2/posts`) | ✅ active |
| Beko (Arçelik) | JS-rendered SPA | ⏳ Phase 2 |
| Electrolux | Blocks the CI runner's IP | ⏳ Phase 2 |
| LG | JS-rendered + Akamai bot protection | ⏳ Phase 2 |

`company_scrapers/base.py` is the generic engine — collect article links from a listing page, then enrich each from its own page's metadata; `company_scrapers/wp.py` handles WordPress newsrooms. Theme tagging is plain keyword matching, no AI calls. `company_pipeline.py --backfill` does a deep crawl back to 2023 instead of the normal incremental run. Full per-company notes live in `COMPANY_TRACKER.md`.

### 3. EPREL Product Database
`eprel_scraper.py` pages through the EU's energy-label registry across four machine types (washing machines, washer-dryers, dryers, dishwashers), keeping the top 1,000 per category ranked by energy class, then weighted energy consumption. Along the way it works around a long list of registry quirks — browser-header requirements, a sort parameter that's silently ignored, per-category filter field names, de-duplication by registration number, the older A+++–D ladder that dryers still use, and flagging (never dropping) records whose declared class contradicts their own efficiency index. `eprel_lookup.py` is the companion tool for targeted, single-brand/single-model queries using the API's real filters.

### 4. Teams Weekly Digest
`teams_digest.py` reads `tech_news_classified.json` and posts an Adaptive Card of the week's top items to a Teams channel via incoming webhook, tracking what it has already posted in `teams_digest_state.json` so nothing repeats.

### 5. Curated Product Comparison
`products.json` compares each brand's flagship model across the same four categories on features EPREL doesn't record — AI load sensing, auto-dosing, steam, connectivity, and more. `build_products.py` regenerates it, sourcing model choice and specs from EPREL data rather than marketing copy. Only washing machines are fully researched today; the other three categories are placeholder rows. A separate, still-early system (`tech_matrix.py`, `tech_evidence.json`) aims to back every cell with a quoted source from brand/retailer pages — see `TECH_MATRIX_PLAN.md` for where that stands.

## How it fits together

```
RSS feeds ──┐
CHEAA/OFweek ┴─► scraper_w_filter.py ─► tech_news_classified.json ─┬─► "/" + "/beyond"
                   (translate, Gemini)      dynamic_classes.json    └─► teams_digest.py ─► Teams

newsroom pages ─┐
WP REST API ─────┴─► company_pipeline.py ─► company_news.json ─────► "/companies"
                                             company_analysis.json

EPREL registry ──────► eprel_scraper.py ────► eprel_products.json ──► "/eprel"

products.json (curated, EPREL-sourced specs) ─────────────────────────► "/products"
```

Every JSON output above is read by `app.py` and rendered through server-side Jinja templates plus vanilla JS (Chart.js for the company charts) — no frontend build step.

## Tech stack

- **Automation** — GitHub Actions, cron-scheduled with `workflow_dispatch` for manual runs
- **Backend** — Flask (dev server locally; `gunicorn` in production, deployed on Render)
- **AI classification** — Google Gemini (`google-genai`)
- **Translation** — `deep-translator`
- **Scraping** — stdlib `urllib` + `HTMLParser` only, by design — no `requests`, `beautifulsoup4`, or `pandas`
- **Frontend** — server-rendered Jinja2 templates, vanilla JS, Chart.js — no build step
- **Storage** — none; committed JSON files are the database

## Getting started

```bash
pip install -r requirements.txt
```

Two environment variables, read from the environment or parsed line-by-line out of a `.env` file:

| Variable | Used by |
|---|---|
| `GEMINI_API` | Tech News Radar classification |
| `TEAMS_WEBHOOK_URL` | Teams weekly digest |

```bash
# Dashboard
python app.py                                        # http://localhost:5000

# Tech News Radar
python scraper_w_filter.py                           # full run: scrape → translate → classify → subclassify

# Company Newsroom Tracker
python company_pipeline.py                           # incremental
python company_pipeline.py --backfill --max 200      # deep crawl back to 2023

# EPREL
python eprel_scraper.py                               # full refresh, ~46k registrations, ~35 min
python eprel_scraper.py --category dishwasher --top 500
python eprel_scraper.py --dry-run                     # print the plan, no requests

# Teams digest
python teams_digest.py --dry-run                      # build & print the card, no POST, no state write
python teams_digest.py --force --limit 6              # post top items ignoring state (test mode)
```

There's no test suite and no linter — each script prints its own progress and counts, and that stdout is the verification.

## Scheduled automation

| Workflow | Schedule | Commits |
|---|---|---|
| `action.yml` | Every 2 days, 21:00 UTC | `tech_news_classified.json`, `dynamic_classes.json` |
| `company-news.yml` | Sundays, 22:00 UTC | `company_news.json`, `company_analysis.json` |
| `eprel-refresh.yml` | 1st of the month, 23:00 UTC | `eprel_products.json` |
| `teams-digest.yml` | Mondays, 03:00 UTC (06:00 TRT) | `teams_digest_state.json` |

Every workflow commits with `[skip ci]` and skips the commit entirely when the diff is empty; every job runs under a `timeout-minutes` cap so a stalled call fails the job instead of burning the schedule's budget.

## Project structure

```
├── app.py                     Flask dashboard — all routes + /api/* endpoints
├── config.py                  RSS sources, Gemini models/prompt, feature flags
│
├── scraper_w_filter.py        Tech News Radar orchestration
├── cheaa_scraper.py           Feed-less scraper: CHEAA
├── ofweek_scraper.py          Feed-less scraper: OFweek
├── gemini_filter.py           Layer-1 Gemini classifier
├── taxonomy.py                Fixed 6-class taxonomy + label normalization
├── dynamic_subclassifier.py   Layer-2 classifier for the "Other" bucket
│
├── company_pipeline.py        Company Newsroom Tracker orchestration
├── company_config.py          Per-company scrape config + Phase-2 notes
├── company_scrapers/
│   ├── base.py                  Generic listing-page + metadata scraper
│   └── wp.py                    WordPress REST API scraper (Haier)
│
├── eprel_scraper.py           Bulk EPREL registry scraper
├── eprel_lookup.py            Targeted, filtered EPREL queries
├── eprel_config.py            Categories, table columns, field mappings
├── eprel/                     Manually curated benchmark spreadsheets (price data)
│
├── teams_digest.py            Weekly Adaptive Card poster
├── products.json              Hand-curated flagship comparison
├── build_products.py          Regenerates products.json from EPREL data
├── tech_matrix.py             Evidence-backed technology-matrix scanner (WIP)
│
├── templates/                 Jinja2 templates for every dashboard page
├── static/app.css
└── .github/workflows/         The four scheduled Actions described above
```

*(JSON outputs are committed alongside the code that writes them and are omitted here for brevity.)*

## Design notes

- **JSON as the database** — every pipeline treats its output JSON as durable state, reading it back in on the next run rather than starting fresh.
- **Fault isolation** — every network/API stage is wrapped so one source failing (a dead feed, a blocked scraper, a rate-limited model) never stops the whole run.
- **Thin dependencies, on purpose** — scraping is stdlib-only; adding `requests`, `beautifulsoup4`, or `pandas` is a deliberate non-goal.
- **Config over code** — new RSS feeds, companies, or EPREL categories are added as data in `config.py` / `company_config.py` / `eprel_config.py`, not by touching orchestration logic.

## Further documentation

- [`CLAUDE.md`](./CLAUDE.md) — full architecture notes, EPREL registry quirks, and pipeline internals
- [`COMPANY_TRACKER.md`](./COMPANY_TRACKER.md) — per-company scraping status and how to extend it
- [`TECH_MATRIX_PLAN.md`](./TECH_MATRIX_PLAN.md) — the plan for finishing the technology-matrix evidence system
