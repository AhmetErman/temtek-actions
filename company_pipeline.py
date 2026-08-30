"""
Orchestrator for the home-appliance company news tracker.

  python company_pipeline.py            # incremental update (recent posts)
  python company_pipeline.py --backfill # deep crawl back to BACKFILL_SINCE

Steps: scrape each enabled company (fault-isolated) -> tag themes (keyword,
no API) -> dedup by URL -> save company_news.json -> compute and save
company_analysis.json (volume + theme aggregates powering the dashboard).
"""
import os
import json
import argparse
import datetime
from collections import Counter, defaultdict

import company_config as cc
from company_scrapers import scrape_company
from company_scrapers.wp import scrape_wordpress

# Keyword -> theme map (lowercased substring match on title + summary).
THEME_KEYWORDS = {
    "AI": ["ai ", " ai", "artificial intelligence", "machine learning",
           "generative", "genai", "bespoke ai", "ai home", "ai living"],
    "IoT & Connectivity": ["smart home", "connected", "connectivity", "iot",
                            "wi-fi", "wifi", "matter", "thinq", "smartthings",
                            "voice", "app control", "ecosystem"],
    "Sustainability & Energy": ["sustainab", "energy", "efficien", "eco ",
                                "eco-", "carbon", "recycl", "climate",
                                "emission", "water saving", "water-saving",
                                "renewable", "circular"],
    "Hygiene & Health": ["hygiene", "steam", "antibacterial", "anti-bacterial",
                         "allergen", "saniti", "health", "air quality",
                         "purif", "odor", "odour"],
    "Laundry": ["washing machine", "washer", "dryer", "laundry", "fabric",
                "detergent", "tumble"],
    "Refrigeration": ["refrigerat", "fridge", "freezer", "cooling", "cooler"],
    "Cooking & Kitchen": ["oven", "cooktop", "dishwasher", "kitchen", "cooking",
                          "range ", "hob", "microwave", "coffee"],
    "Design & Events": ["design", "award", "red dot", "reddot", "ces ",
                        "ces2", "ifa ", "ifa2", "eurocucina", "showcase",
                        "unveil", "launch"],
    "Business & Corporate": ["acquisition", "acquire", "results", "revenue",
                             "financial", "offering", "tender", "dividend",
                             "ceo", "appoint", "quarter", "earnings",
                             "partnership", "investment", "merger"],
}


def tag_themes(rec):
    text = ((rec.get("title") or "") + " " + (rec.get("summary") or "")).lower()
    themes = [t for t, kws in THEME_KEYWORDS.items()
              if any(k in text for k in kws)]
    return themes or ["Other"]


def quarter_of(date_str):
    try:
        y, m, _ = date_str.split("-")
        q = (int(m) - 1) // 3 + 1
        return f"{y}-Q{q}"
    except Exception:
        return None


def load_existing(path):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def build_analysis(records):
    totals = Counter(r["company"] for r in records)
    by_quarter = defaultdict(Counter)
    by_theme = defaultdict(Counter)
    date_range = {}
    for r in records:
        c = r["company"]
        q = quarter_of(r.get("date") or "")
        if q:
            by_quarter[c][q] += 1
        for th in r.get("themes", []):
            by_theme[c][th] += 1
        d = r.get("date")
        if d:
            dr = date_range.setdefault(c, {"earliest": d, "latest": d})
            dr["earliest"] = min(dr["earliest"], d)
            dr["latest"] = max(dr["latest"], d)

    companies = sorted(totals, key=lambda c: -totals[c])
    quarters = sorted({q for c in by_quarter for q in by_quarter[c]})
    themes = [t for t in THEME_KEYWORDS] + ["Other"]
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                 .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_articles": len(records),
        "companies": companies,
        "totals": dict(totals),
        "quarters": quarters,
        "by_quarter": {c: dict(by_quarter[c]) for c in by_quarter},
        "themes": themes,
        "by_theme": {c: dict(by_theme[c]) for c in by_theme},
        "date_range": date_range,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true",
                    help="deep crawl back to BACKFILL_SINCE")
    ap.add_argument("--since", default=cc.BACKFILL_SINCE)
    ap.add_argument("--max", type=int, default=None,
                    help="max articles per company")
    args = ap.parse_args()

    backfill = args.backfill
    max_articles = args.max or (250 if backfill else 30)
    max_pages = 40 if backfill else 3

    existing = load_existing(cc.COMPANY_NEWS_FILE)
    by_url = {r["url"]: r for r in existing if r.get("url")}
    existing_urls = set(by_url)
    print(f"Loaded {len(existing)} existing company articles.")

    def log(level, msg):
        print(f"  -> {msg}")

    new_count = 0
    for name, cfg in cc.enabled_companies().items():
        print(f"\nScraping {name} ({'backfill' if backfill else 'incremental'})...")
        if cfg.get("type") == "wordpress" or cfg.get("api_url"):
            recs = scrape_wordpress(cfg, since=args.since,
                                    existing_urls=existing_urls,
                                    max_articles=max_articles,
                                    max_pages=(20 if backfill else 2),
                                    sleep=0.3, log=log)
        else:
            recs = scrape_company(cfg, since=args.since,
                                  existing_urls=existing_urls,
                                  max_articles=max_articles, max_pages=max_pages,
                                  sleep=0.3, log=log)
        for r in recs:
            r["themes"] = tag_themes(r)
            by_url[r["url"]] = r
            new_count += 1

    merged = list(by_url.values())
    # Drop records with no usable date so the timeline/analysis stay clean.
    merged = [r for r in merged if r.get("date")]
    merged.sort(key=lambda r: r.get("date") or "", reverse=True)

    with open(cc.COMPANY_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"\nSaved {len(merged)} articles to {cc.COMPANY_NEWS_FILE} "
          f"(+{new_count} scraped this run).")

    analysis = build_analysis(merged)
    with open(cc.COMPANY_ANALYSIS_FILE, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"Saved analysis to {cc.COMPANY_ANALYSIS_FILE}")
    print("\nPer-company totals:")
    for c in analysis["companies"]:
        dr = analysis["date_range"].get(c, {})
        print(f"  {analysis['totals'][c]:4d}  {c}  "
              f"({dr.get('earliest','?')} -> {dr.get('latest','?')})")

    # Turkish for whatever this run added. Incremental, and fault-isolated so a
    # translation problem cannot cost us the scrape that just succeeded.
    try:
        import translate_data
        print("\n=== Turkish translation pass ===")
        translate_data.translate_company()
    except Exception as e:
        print(f"  -> Turkish translation skipped: {e}")


if __name__ == "__main__":
    main()
