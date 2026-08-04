# Filling the technology matrix — plan

State at time of writing: **289 of 384 cells (75%) are `unknown`.** Not because the
data is hard, but because `tech_matrix.py` has never run at scale — it holds 5
source URLs and its URL-guessing stage found 0 of 48 product pages.

The scanner itself is proven. Plain `urllib` with browser headers reads
lg.com, bosch-home.co.uk, beko.co.uk, haier-europe.com and samsung.com — every
one of which returns 403 to the WebFetch tool. So the missing piece is **one real
product-page URL per model**, nothing more.

Two jobs, in order. Job 1 is cheap and should be finished before Job 2 is built,
because Job 1 determines how much of Job 2 is actually needed.

---

## Job 1 — harvest source URLs from search, then scan

**Goal:** populate `tech_sources.json` with a verified product-page URL for each
of the 48 models, then run the existing scan.

**Why search rather than URL templates:** the template approach failed outright.
Brand URL shapes vary per market (`/uk/laundry/washing-machines/{slug}/` vs
`/en/product/laundry/.../{MODEL}`), retailer slugs embed marketing copy, and
brand site-search pages are JS-rendered so a fetch never contains the model.

**Method** (~48 lookups, one per model):

1. Query `"<MODEL>" <brand> <category>` and take candidate URLs from the results.
2. Prefer, in order: the brand's own product page → a major EU retailer product
   page (Coolblue, MediaMarkt, Currys, ao.com, Marks Electrical, Euronics,
   Galaxus, Unieuro) → a price-comparison listing.
3. **Verify before accepting**: fetch the URL and require the model identifier to
   appear in the page text. `run_discover()` already enforces this; it is the
   check that stops a template resolving to a generic category page.
4. Record 2–3 URLs per model where available. `run_scan()` already treats a
   feature as present if *any* listed page names it, and only records an absence
   once every listed page has been read — which blunts the single-page risk.

**Then:** `python tech_matrix.py --scan --apply`.

**Expected yield:** the scan resolves every cell for every model whose page was
read. Cells stay `unknown` only where no page could be read at all.

**Known risk, and why it is acceptable:** the absence-means-no rule will convert
a large number of unknowns to `no` in a single sweep, and some will be wrong —
brand pages omit features they do have, especially on retailer listings that
truncate spec tables. This is why Job 1 ends with a re-run of the audit agent
over every newly-written `yes`, and a spot-check of `no` values on flagships.
The audit that ran on 2026-08-04 found a 20-cell error rate against a much
smaller filled set, so budget for real corrections rather than a rubber stamp.

**Effort:** ~48 search lookups + one unattended scan. Half a session.

---

## Job 2 — scrape market sites for what brand pages do not say

Only build this for what Job 1 leaves genuinely unresolved. Retailer listings are
worth scraping for two things brand pages are bad at:

- **Structured spec tables.** Retailers publish `Auto dosing: Yes` style
  attribute tables; brand pages bury the same fact in marketing prose. A parsed
  table gives a *positive* `no`, which is far stronger than absence-means-no.
- **Cross-market coverage.** A model absent from the UK site is often live on
  Coolblue (NL), MediaMarkt (DE) or Unieuro (IT). This also finally supplies the
  Price / Market columns that EPREL cannot, matching the original
  `eprel_washer_dryer_benchmark.xlsx`.

### Target sites, in priority order

| Site | Market | Why | Access |
|---|---|---|---|
| Coolblue | NL/BE | clean `<table>` spec blocks, model in URL slug | server-rendered, fetched OK during research |
| MediaMarkt | DE/AT | very complete attribute tables | server-rendered; expect rate limiting |
| Currys / ao.com / Marks Electrical | UK | good spec tables | **403 to plain fetch** — needs care |
| Euronics / Unieuro / Galaxus | IE/IT/CH | fills gaps for EU-only SKUs | mixed; Galaxus timed out in the audit |

### Architecture — follow `company_scrapers/`, do not invent a new pattern

```
tech_market_config.py     per-site: search URL template, product-URL regex,
                          spec-table selector strategy, enabled flag
tech_market/base.py       generic engine: search by model -> pick the product
                          URL -> parse the spec table into {label: value}
tech_market/<site>.py     only where a site needs its own quirk (JSON-LD,
                          embedded __NEXT_DATA__, etc.)
```

Reuse from what already exists:
- `tech_matrix.KEYWORDS` — the alias lists map a retailer's spec label onto our
  technology keys. Extend, do not duplicate.
- `tech_matrix.fetch_text` / `_Text` — stdlib HTML-to-text, already works.
- `eprel_scraper.fetch_page` retry-and-backoff shape for throttling.
- `company_scrapers/base.py` fault isolation: one site failing must never stop
  the run.

### Parsing rule that makes this worth doing

A retailer attribute table yields a **tri-state**, not a binary:

- label present, value truthy (`Yes`, `Ja`, `✓`, `Aanwezig`) → `yes`
- label present, value falsy (`No`, `Nee`, `-`) → **`no` with evidence** ← the win
- label absent entirely → leave as-is; fall back to Job 1's weaker rule

Store the raw label/value pair in `tech_evidence.json` alongside the URL so the
Sources panel can quote the table row verbatim.

### Constraints to respect

- **robots.txt and rate limits.** One request per 1–2 s per host, cached
  aggressively; this dataset changes monthly at most, so re-scraping should be
  rare. Check each site's robots.txt before enabling it in config.
- **No new dependencies.** stdlib `urllib` + `HTMLParser`, as everywhere else in
  this repo. If a site genuinely needs a browser, mark it `enabled: False` with a
  note — the same Phase-2 convention `company_config.PHASE2_NOTES` already uses.
- **Bot-protected sites are a `Phase 2`, not a blocker.** Currys/ao.com return
  403; record the reason and move on rather than escalating to a headless
  browser for a handful of cells.

### Verification, not optional

1. `check_range_leak()` must stay clean — no claim may be brand-level once a
   brand contributes two models to a category.
2. Re-run the audit agent over every cell the scrape changes to `yes`.
3. Cross-check retailer values against EPREL where they overlap (capacity, spin,
   energy class). A retailer page that disagrees with the registry on a spec is a
   page that has matched the wrong SKU — drop its technology values too.

**Effort:** ~2 sessions for the engine and the first two sites, assuming Job 1
has already cut the unknown count substantially.

---

## Sequencing

1. Job 1 harvest + scan + audit. Reassess the unknown count.
2. Only then scope Job 2 against what actually remains — likely dishwashers and
   condenser washer-dryers, which is where brand pages are thinnest.
3. Add a scheduled refresh only once the numbers are stable. Product technology
   changes far more slowly than the news feeds, so a manual `workflow_dispatch`
   is probably right rather than a cron.
