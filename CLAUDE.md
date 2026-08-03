# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`temtek-actions` is a **GitHub-Actions-driven data pipeline plus a Flask dashboard**. There is no
database and no service layer: the workflows run Python scripts on a schedule, the scripts commit
their output JSON back into the repo, and `app.py` just serves those JSON files. **The committed
JSON files are the product** — treat them as state, not as build artifacts.

Two independent pipelines live side by side (they share only `app.py` and the Gemini config style):

| Pipeline | Entry point | Output (committed) | Dashboard |
|---|---|---|---|
| Tech news (JP/CN RSS + scrapers, Gemini-classified) | `scraper_w_filter.py` | `tech_news_classified.json`, `dynamic_classes.json` | `/`, `/beyond` |
| Company newsroom tracker (competitor press releases) | `company_pipeline.py` | `company_news.json`, `company_analysis.json` | `/companies` |
| EPREL product database (EU energy-label registry) | `eprel_scraper.py` | `eprel_products.json` | `/products` |

A third script, `teams_digest.py`, reads `tech_news_classified.json` and posts a weekly Adaptive
Card to a Teams webhook (state in `teams_digest_state.json`). `products.json` / `/products` is a
hand-curated dataset, never scraped.

## Products page — two datasets, four categories

`/products` shows four product categories (washing machines, washer-dryers, dryers, dishwashers)
behind a tab bar. Each tab stacks **two independent datasets**:

1. **EPREL energy benchmark** (top) — scraped, `eprel_products.json`, top 1000 models per category
   (4000 rows, 2.8 MB) drawn from ~46k EU registrations.
2. **Curated technology comparison** (below) — hand-written, `products.json`, one flagship per brand,
   covering the features EPREL does *not* record (AI, auto-dosing, steam, connectivity).

They share only the four category keys (`washing-machine`, `washer-dryer`, `dryer`, `dishwasher`);
keep those in sync between `products.json`, `eprel_config.CATEGORIES` and the template.

### EPREL scraper (`eprel_scraper.py` + `eprel_config.py`)

EPREL is the EU's public product registry. Facts that shaped the design — don't undo them:

- The read API answers **403 without browser-like headers** (`eprel_config.REQUEST_HEADERS`).
- **No sort or filter parameter works.** Every `sortBy`/`order`/`energyClass` spelling is ignored,
  so ranking must happen locally over the *whole* product group. Deep pagination does work, and
  `_limit` silently truncates to 25 above 100.
- The same model appears once per **registration version**, so records are deduped on
  `eprelRegistrationNumber`, keeping the highest `versionNumber`.
- Ranking is energy class first, then weighted energy consumption ascending, capped at
  `TOP_N` (1000) per category. Because that figure is absolute rather than capacity-normalized,
  it mildly favours small machines — the table is sortable so any column can override it.
- Dryers sit under the **old regulation** (EU 392/2012): ladder `A+++…D` (EPREL spells it
  `APPP`/`APP`/`AP`) and the energy figure is `kWh/year`, not `kWh/100 cycles`. The other three use
  EU 2019/xxxx and the `A…G` ladder. `CLASS_ORDER` / `class_scale` carries this per category.
- `classDetail` renders `A-30%`: how far the model's EEI sits below the class ceiling, per the
  bounds in `eei_bounds`. Same notation as the original benchmark spreadsheet in `eprel/`.
- EPREL has **no heat-pump field**, so drying technology is inferred from the energy class
  (`drying_tech_from_class`) — it is an estimate and labelled as such in the UI.
- A few registrations declare a class that contradicts their own EEI. Those get
  `dataFlag: "eei-class-mismatch"`, sort behind clean records in the same class, and show a ⚠ in
  the table. They are flagged, never dropped.
- Brand names arrive in many spellings (`LG`, `LG Electronics`, `LG Electronics Inc.`);
  `canonical_brand()` + `BRAND_ALIASES` collapse them so filters aren't split.

- Some measurements were superseded by a `*V2` field with the original left null
  (`cleaningPerformanceIndexV2`, `washingEfficiencyIndexV2` — ~95% filled vs ~15%). A `fields`
  value may be a **list** of API keys, tried in order, for exactly this case.
- `/api/eprel` serves the whole 2.8 MB file, matching how `/api/news` serves its dataset. If page
  weight ever matters, split it into a per-category endpoint.

Adding a category or column is a `eprel_config.py` edit only — `columns[]` drives the rendered
table, and `fields{}` maps output keys to EPREL API field names.

Note that EPREL carries **no price or retailer data** — the Price (€) / Market URL columns in
`eprel/eprel_washer_dryer_benchmark.xlsx` came from a separate manual price lookup and have no
automated equivalent here.

### Curated dataset (`products.json`)

Fully data-driven — `templates/products.html` renders whatever the file declares, so a new category
or technology needs no code change:

- `categories[]` — each has `key`, `label`, `icon`, `blurb`, its own `specs[]` (spec fields, which
  differ per category: spin/motor for washers, place settings/noise for dishwashers) and its own
  `technologies[]` (`key`, `label`, `short`).
- `products[]` — each carries `category`, `company`, `model`, a `specs` object keyed by that
  category's spec keys, a `tech` object keyed by its technology keys, plus `highlight`/`url`.
- `status` is `researched` or `placeholder`. Placeholder rows are structural stubs (empty
  `specs`/`tech`) that the UI renders as `?` / "To research"; missing tech values are treated as
  `unknown`, so partially-filled rows are safe. Only the washing-machine rows are researched today.
- `tech` values: `yes` | `partial` | `no` | `unknown`.

Filling in a category means editing `products.json` only — no template or route changes.

See `COMPANY_TRACKER.md` for the company-tracker details (per-company scraping status, Phase-2
blockers, how to extend `products.json`).

## Commands

```bash
pip install -r requirements.txt

python scraper_w_filter.py          # full tech-news run: scrape → translate → classify → subclassify
python company_pipeline.py          # incremental company scrape
python company_pipeline.py --backfill --max 200   # deep crawl back to BACKFILL_SINCE (2023)
python app.py                       # dashboard at http://localhost:5000 (Flask dev; prod uses gunicorn on Render)

python teams_digest.py --dry-run    # build & print the card, never POST, never write state
python teams_digest.py --force --limit 6   # post top items ignoring state (test mode)

python eprel_scraper.py             # full EPREL refresh (~46k registrations, ~35 min)
python eprel_scraper.py --category dishwasher --top 500
python eprel_scraper.py --max-pages 3   # smoke test, a handful of API calls
python eprel_scraper.py --dry-run       # print the plan, no requests

python count_classes.py [file.json] # class distribution of a classified dataset
python dynamic_subclassifier.py --dry-run          # inspect the sub-taxonomy registry, no API calls
python dynamic_subclassifier.py --only-untagged    # incremental re-run of the Layer-2 pass
python reclassify.py                # re-run the PRIMARY classifier over the whole dataset → tech_news_reclassified.json
```

There is no test suite and no linter. Verification is done by running a script and reading its
stdout (every stage prints counts).

Env vars (loaded from the environment, or parsed line-by-line out of `.env` — there is no
`python-dotenv` dependency here): `GEMINI_API`, `TEAMS_WEBHOOK_URL`.

## Scheduled workflows

- `.github/workflows/action.yml` — tech-news scrape, `0 21 */2 * *`, commits the two news JSONs.
- `.github/workflows/company-news.yml` — company scrape, Sundays 22:00 UTC; `workflow_dispatch`
  input `backfill=true` switches to the deep crawl.
- `.github/workflows/teams-digest.yml` — Mondays 03:00 UTC (06:00 TRT); `mode=test` runs
  `--force` and deliberately writes no state.
- `.github/workflows/eprel-refresh.yml` — EPREL database, monthly on the 1st at 23:00 UTC;
  `workflow_dispatch` inputs pick a single `category` and the `top` cap. 90-min cap because a full
  refresh pages through every registration in four product groups.

All three commit with `[skip ci]` and skip the commit when the diff is empty. Every job has a
`timeout-minutes` cap — this is why `config.GEMINI_REQUEST_TIMEOUT` and
`config.TRANSLATION_TIMEOUT` exist (a stalled call must fail, not burn the job budget).

## Tech-news pipeline architecture

`scraper_w_filter.py::scrape_and_translate()` is the whole orchestration, run start-to-finish:

1. **Load existing** `tech_news_classified.json` and split it into already-classified items and an
   **unclassified backlog** (items a previous run scraped but failed to classify). URL is the dedup
   key throughout.
2. **Collect** from `config.RSS_SOURCES` (feedparser) plus the two custom HTML scrapers for sites
   with no RSS: `cheaa_scraper.py` and `ofweek_scraper.py`. Both are stdlib-only `HTMLParser`
   scrapers, gated by `enabled` in `config.py`, and wrapped in `try/except` — **a scraper failure
   must never stop the run.** Preserve that when adding sources.
3. **Validate/normalize** every entry through `_is_valid_entry()` before spending translation and
   API budget on it (empty summaries fall back to the title; `deep_translator` crashes on empty
   strings).
4. **Translate** JP/ZH → EN in per-language batches, wrapped in a thread + join-timeout because
   `GoogleTranslator.translate_batch()` can hang forever.
5. **Classify (Layer 1)** — backlog + new items go to `gemini_filter.GeminiClassifier`, which
   returns `Classification` / `RelationScore` / `Gemini_Summary` under a structured response schema.
   The classifier walks `config.GEMINI_MODELS` in order, advancing to the next model on 503/429.
6. **Normalize labels** via `taxonomy.normalize_classification()`, then **Layer 2**:
   `dynamic_subclassifier.DynamicSubclassifier` takes everything labelled `Other` and assigns an
   `OtherSubclass` from a registry it grows itself (`dynamic_classes.json`), which is re-injected
   into the prompt each run. Steps 6 is inside a `try/except` — a Layer-2 failure must not lose the
   Layer-1 result.
7. **Save** the merged list (append-only; new items go at the end — several consumers rely on this
   ordering to infer recency).

### Two-layer taxonomy — the core invariant

`taxonomy.HARD_CLASSES` is a **fixed, human-curated** 6-class taxonomy (5 real classes + `Other`)
and must not change implicitly; `config.SYSTEM_PROMPT` is its authoritative prose definition. When
class definitions change, update both together and re-run `reclassify.py` over the dataset.

The *dynamic* layer only ever operates below `Other`, so the top-level distribution stays
comparable over time while the opaque `Other` bucket gains structure. `normalize_classification()`
exists because Gemini drifts (`"other"`, `"IoT & Smart Sensors"`); always route raw model labels
through it rather than comparing strings directly, or the dashboard splits one category into
several buckets.

Article record shape (fields accumulate across stages):
`source, title, date, url, summary, language, title_en, summary_en, Classification, RelationScore,
Gemini_Summary` + `OtherSubclass` for `Other` items.

## Company tracker architecture

`company_config.py` is data-driven: each company is a listing-URL template + a regex identifying
article URLs. `company_scrapers/base.py` collects links from listing pages, then enriches each
article from *its own page's* Open Graph / JSON-LD / `<time>` metadata — that's what makes one
engine work across different sites. `company_scrapers/wp.py` handles newsrooms that block HTML
scraping but expose `/wp-json/wp/v2/posts` (Haier). `enabled: False` marks Phase-2 companies that
are JS-rendered or bot-protected; `PHASE2_NOTES` records why each one is blocked.

Theme tagging is **keyword-based** (`THEME_KEYWORDS` in `company_pipeline.py`), no API calls —
don't reach for Gemini here.

## Conventions

- Config lives in `config.py` / `company_config.py` as plain dicts with an `enabled` flag; new
  sources and features are added there, not by editing orchestration code.
- Every network/API stage is fault-isolated and prints progress through a `progress_callback` /
  `log(level, msg)` callable rather than raising.
- Dependencies are deliberately thin (stdlib `urllib` + `HTMLParser` for scraping). Don't
  introduce `requests`/`beautifulsoup4`/`pandas` to this repo without cause.
- Frontend is server-rendered Jinja templates + vanilla JS fetching the `/api/*` endpoints, with
  Chart.js for the company charts. No build step.
