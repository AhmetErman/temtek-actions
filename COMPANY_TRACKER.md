# Appliance Competitor Tracker

A second dashboard (`/companies`) that tracks press releases from top home-appliance
companies since 2023 and provides comparative analysis. It is fully separate from
the tech-news pipeline (`tech_news_classified.json` / `/`).

## How it works

```
listing pages ─┐
               ├─► company_scrapers ──► company_pipeline.py ──► company_news.json
WP REST API ───┘        (enrich +            (dedup +          company_analysis.json
                         theme tag)           analysis)               │
                                                                      ▼
                                              app.py  /companies  +  /api/company-*
                                                      templates/companies.html
```

- **`company_scrapers/base.py`** — generic engine: collect article URLs from a
  company's listing pages (per-company regex + pagination), then enrich each from
  its own page's Open Graph / JSON-LD / `<time>` metadata (uniform across sites).
  Fault-isolated: never raises.
- **`company_scrapers/wp.py`** — WordPress REST API scraper for newsrooms that block
  HTML scraping but expose `/wp-json/wp/v2/posts` (Haier).
- **`company_config.py`** — per-company settings + `enabled` flag + Phase-2 notes.
- **`company_pipeline.py`** — orchestrates scraping, keyword **theme tagging**
  (no API), dedup by URL, and builds `company_analysis.json` (volume per quarter,
  theme share, date ranges).
- **`templates/companies.html`** — the dashboard: stat cards, 3 Chart.js charts
  (releases by company, theme focus, activity over time) + a filterable feed.

## Running

```bash
python company_pipeline.py             # incremental (recent posts)
python company_pipeline.py --backfill  # deep crawl back to 2023 (BACKFILL_SINCE)
python app.py                          # serve dashboard at http://localhost:5000/companies
```

CI: `.github/workflows/company-news.yml` runs the incremental update weekly
(Sun 22:00 UTC) and commits the two JSON files. The `workflow_dispatch` input
`backfill=true` runs a deep crawl.

## Company tiers

| Company | Method | Status |
|---|---|---|
| Samsung | HTML listing + meta enrich | ✅ active |
| BSH (Bosch/Siemens) | HTML listing + meta enrich | ✅ active |
| Whirlpool | HTML listing (date in URL) | ✅ active |
| Midea | HTML listing + meta enrich | ✅ active |
| Haier | WordPress REST API | ✅ active |
| Beko (Arçelik) | JS SPA, no server meta | ⏳ Phase 2 (needs browser/API) |
| Electrolux | blocks the runner IP | ⏳ Phase 2 (retry from CI / API) |
| LG | JS + Akamai bot-protection | ⏳ Phase 2 (needs browser/Playwright) |

### Extending
- **Pagination depth:** BSH / Whirlpool / Midea currently scrape their first
  listing page only (their `?page=` param is ignored). Add the correct pagination
  URL in `company_config.py` to backfill them deeper.
- **Phase-2 companies:** connect the Chrome extension and use it to discover each
  site's JSON API (then hit it with the current tools), or add a Playwright-based
  scraper module for the bot-protected ones (LG).

## Products page (`/products`)

Four product categories (washing machines, washer-dryers, dryers, dishwashers)
behind a tab bar, each stacking two datasets — `app.py` route `/products`,
rendered by `templates/products.html`:

1. **EPREL energy benchmark** (`eprel_products.json`, `/api/eprel`) — the top
   1000 models per category scraped from the EU energy-label registry by
   `eprel_scraper.py`, ranked by energy class then weighted energy consumption.
   Sortable on every column, filterable by brand / class / tracked brands, with
   a "best per brand" toggle. This is the same shape as the hand-built
   `eprel/eprel_washer_dryer_benchmark.xlsx`, generated for all four categories.
2. **Curated technology comparison** (`products.json`, `/api/products`) — below
   the table: technology matrix, flagship cards and spec table. Each category
   brings its own spec fields and technology list, and rows marked
   `"status": "placeholder"` render as "to research".

- **Why curated, not scraped:** product-spec pages are JS-rendered, region-gated
  and bot-protected, so reliable uniform scraping isn't feasible. `products.json`
  holds each brand's flagship model per category (specs, highlight, source URL)
  plus a per-technology map (`yes`/`partial`/`no`/`unknown`).
- **The page:** category tabs, then a technology matrix (8 models × 10
  technologies) with a per-technology availability count, flagship product cards,
  and a spec table. Click a technology column to highlight it; filter by "has
  technology" or hide rows still awaiting research.
- **Editing:** just edit `products.json` — no code changes needed. Add a brand by
  appending a product object with its `category`; add a technology or spec field
  by extending that category's `technologies` / `specs`; add a whole category by
  appending to `categories`.
- **Research status:** washing machines are researched; washer-dryer, dryer and
  dishwasher rows are placeholders (8 brands each) waiting to be filled in.
- Data sourced 2026-06-15 from official product/newsroom pages (links in each
  product's `url`). Refresh periodically as flagships change.
