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
