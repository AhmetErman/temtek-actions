"""
EPREL product-database scraper.

Pages through the EU EPREL registry for every product group defined in
`eprel_config.CATEGORIES`, dedupes registrations, ranks each category by energy
class then weighted energy consumption, and writes the best `TOP_N` per category
to `eprel_products.json` (served by app.py at /api/eprel and rendered as the
benchmark table on /products).

    python eprel_scraper.py                        # full refresh, all categories
    python eprel_scraper.py --category dishwasher  # one category
    python eprel_scraper.py --max-pages 3          # smoke test (few API calls)
    python eprel_scraper.py --dry-run              # print the plan, no requests

Design notes (why it works this way):
  * EPREL's read API answers 403 without browser-like headers, ignores every
    sort/filter parameter we could find, and silently truncates `_limit` above
    100. Ranking therefore has to happen locally, over the whole group.
  * The same model appears once per registration *version*, so records are
    deduped on eprelRegistrationNumber keeping the highest versionNumber.
  * Each category is fault-isolated: a failing group logs and is skipped so the
    others still produce data (same rule as the news scrapers in this repo).
"""
import argparse
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

import eprel_config as ec


# --- helpers -------------------------------------------------------------

def _log(level, msg):
    print(f"  -> {msg}", flush=True)


def class_rank(label, scale):
    """Position on the category's energy ladder; unknown classes sort last."""
    order = ec.CLASS_ORDER.get(scale, [])
    try:
        return order.index(label)
    except (ValueError, AttributeError):
        return len(order) + 1


def class_display(label):
    """EPREL spells the old ladder APPP/APP/AP; show it as A+++/A++/A+."""
    return ec.CLASS_LABELS.get(label, label)


def refine_class(label, eei, bounds):
    """Render a class as e.g. 'A-30%': how far below the class ceiling the
    model's EEI actually sits, rounded to 10%. Falls back to the bare letter
    when there is no EEI, no bound, or the margin is not positive."""
    disp = class_display(label)
    if not disp or not isinstance(eei, (int, float)) or not bounds:
        return disp or ""
    bound = bounds.get(label)
    if not bound:
        return disp
    margin = 1 - (eei / bound)
    pct = int(math.floor(margin * 10 + 0.5)) * 10   # nearest 10%
    return f"{disp}-{pct}%" if pct > 0 else disp


def drying_tech_from_class(label):
    """EPREL exposes no heat-pump flag, so infer it from the wash-and-dry class
    (only heat-pump washer-dryers reach the top classes)."""
    if label in ("A", "B"):
        return "Heat Pump"
    if label == "C":
        return "Heat Pump (likely)"
    if label == "D":
        return "Condenser"
    if label in ("E", "F", "G"):
        return "Conventional"
    return ""


def dryer_tech(dryer_type, label):
    """Same idea for standalone dryers, but the vented ones are explicit."""
    if dryer_type == "AIRVENTED":
        return "Air-vented"
    if label in ("APPP", "APP"):
        return "Heat Pump"
    if label == "AP":
        return "Heat Pump (likely)"
    if dryer_type == "CONDENSER":
        return "Condenser"
    return (dryer_type or "").replace("_", " ").title()


def eei_matches_class(label, eei, bounds):
    """EPREL's class letter is derived from the EEI by regulation, so the two
    must agree. A handful of registrations declare a top class alongside an EEI
    that belongs several classes lower; those get flagged and ranked behind
    clean records rather than dropped (see `dataFlag`)."""
    if not bounds or not isinstance(eei, (int, float)) or label not in bounds:
        return True
    return eei <= bounds[label] * 1.001          # tolerance for rounding


def duration_text(minutes):
    """460 -> '7 hours, 40 mins' (matches the benchmark spreadsheet)."""
    if not isinstance(minutes, (int, float)) or minutes <= 0:
        return ""
    m = int(round(minutes))
    return f"{m // 60} hours, {m % 60} mins"


def _iso(ts):
    """EPREL timestamps are seconds; some are far-future placeholders."""
    if not isinstance(ts, (int, float)) or ts <= 0:
        return None
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(ts))
    except (ValueError, OSError):
        return None


def market_status(start_iso, end_iso, today=None):
    """Availability straight from the registry's placed-on-market window.

    'on-market'    still sold: started, and no end date or an end date ahead of us
    'upcoming'     registered but the start date has not arrived
    'withdrawn'    the supplier declared an end date that has passed

    Suppliers often park the end date decades out, so this proves withdrawal but
    not continued retail presence — treat 'on-market' as necessary, not sufficient.
    """
    today = today or time.strftime("%Y-%m-%d")
    if end_iso and end_iso < today:
        return "withdrawn"
    if start_iso and start_iso > today:
        return "upcoming"
    return "on-market"


def pretty_enum(value):
    """FREE_STANDING -> Free standing."""
    if not isinstance(value, str):
        return value
    return value.replace("_", " ").capitalize()


def canonical_brand(raw):
    """Collapse EPREL supplier/trademark spellings onto one brand name.

    The same brand registers under several names ('LG Electronics',
    'LG Electronics Inc.', 'HISENSE', 'Hisense Germany GmbH'), which would
    otherwise split a brand across several rows of every filter and chart."""
    if not raw:
        return ""
    name = " ".join(raw.split())
    key = name.lower().strip(" .,")
    for alias, canonical in ec.BRAND_ALIASES.items():
        if key == alias or key.startswith(alias + " "):
            return canonical
    # Generic cleanup for everything not explicitly tracked. A comma almost
    # always introduces a legal form ("Gorenje, d.o.o."), so cut there first,
    # then strip trailing legal/filler words until nothing more comes off.
    key = key.split(",")[0].strip(" .")
    changed = True
    while changed:
        changed = False
        for suffix in ec.BRAND_SUFFIXES:
            if key.endswith(" " + suffix):
                key = key[: -(len(suffix) + 1)].strip(" .")
                changed = True
    return key.title() if key else name


# --- API ------------------------------------------------------------------

def fetch_page(group, page, limit=None, log=_log):
    """One page of a product group. Retries 403/5xx with backoff (EPREL answers
    403 when it throttles). Returns the decoded body or raises."""
    limit = limit or ec.PAGE_SIZE
    url = ec.API_BASE + group + "?" + urllib.parse.urlencode({"_page": page, "_limit": limit})
    last_err = None
    for attempt in range(ec.MAX_RETRIES):
        try:
            req = urllib.request.Request(url, headers=ec.REQUEST_HEADERS)
            with urllib.request.urlopen(req, timeout=ec.REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (403, 429, 500, 502, 503, 504):
                wait = 2 ** attempt
                log("warning", f"{group} page {page}: HTTP {e.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            raise
        except Exception as e:                      # network hiccup, timeout, bad JSON
            last_err = e
            wait = 2 ** attempt
            log("warning", f"{group} page {page}: {e}, retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"{group} page {page} failed after {ec.MAX_RETRIES} attempts: {last_err}")


def collect_group(key, cfg, max_pages=None, log=_log):
    """Page through a whole product group, keeping the newest version of each
    registration. Returns (records, total_reported_by_api)."""
    group = cfg["group"]
    best = {}                                        # registration -> raw hit
    page, total, scanned = 1, None, 0

    while True:
        if max_pages and page > max_pages:
            log("info", f"{group}: stopping at --max-pages {max_pages}")
            break
        data = fetch_page(group, page, log=log)
        hits = data.get("hits") or []
        if total is None:
            total = data.get("size")
            pages = math.ceil(total / ec.PAGE_SIZE) if total else "?"
            log("info", f"{group}: {total} registrations to scan (~{pages} pages)")
        if not hits:
            break
        scanned += len(hits)
        for h in hits:
            reg = h.get("eprelRegistrationNumber")
            if not reg:
                continue
            prev = best.get(reg)
            if prev is None or (h.get("versionNumber") or 0) > (prev.get("versionNumber") or 0):
                best[reg] = h
        if page == 1 or page % 25 == 0:
            log("progress", f"{group}: page {page}, {scanned} scanned, {len(best)} unique")
        if total and scanned >= total:
            break
        page += 1
        time.sleep(ec.SLEEP_BETWEEN)

    log("success", f"{group}: scanned {scanned}, {len(best)} unique registrations")
    return list(best.values()), total


# --- normalization --------------------------------------------------------

def normalize(hit, key, cfg):
    """Flatten one EPREL hit into the record shape the dashboard renders."""
    rec = {"category": key}
    for out_key, api_key in cfg["fields"].items():
        # A list means "try these API fields in order": EPREL supersedes some
        # measurements with a *V2 field and leaves the original null.
        if isinstance(api_key, (list, tuple)):
            rec[out_key] = next((hit[k] for k in api_key
                                 if hit.get(k) not in (None, "")), None)
        else:
            rec[out_key] = hit.get(api_key)

    rec["supplier"] = (hit.get("supplierOrTrademark") or "").strip()
    rec["brand"] = canonical_brand(rec["supplier"])
    rec["model"] = (hit.get("modelIdentifier") or "").strip()
    rec["registration"] = hit.get("eprelRegistrationNumber")
    rec["url"] = ec.PRODUCT_URL.format(group=cfg["group"], registration=rec["registration"])

    cls = rec.get("energyClass")
    rec["energyClass"] = cls
    rec["classLabel"] = class_display(cls)
    rec["classDetail"] = refine_class(cls, rec.get("eei"), cfg.get("eei_bounds"))
    rec["classRank"] = class_rank(cls, cfg["class_scale"])

    if "energyClassWash" in rec:                     # washer-dryers carry two labels
        rec["classDetailWash"] = refine_class(
            rec.get("energyClassWash"), rec.get("eeiWash"), cfg.get("eei_bounds_secondary"))

    if cfg.get("drying_tech_from_class"):
        rec["dryingTech"] = drying_tech_from_class(cls)
    elif "dryerType" in rec:
        rec["dryingTech"] = dryer_tech(rec.get("dryerType"), cls)

    rec["marketStart"] = _iso(rec.pop("marketStartTS", None))
    rec["marketEnd"] = _iso(rec.pop("marketEndTS", None))
    rec["market"] = market_status(rec["marketStart"], rec["marketEnd"])

    rec["programTimeText"] = duration_text(rec.get("programTime"))
    for enum_key in ("design", "dryerType"):
        if rec.get(enum_key):
            rec[enum_key] = pretty_enum(rec[enum_key])

    # Data-quality flags. Flagged records are kept and shown, but ranked behind
    # clean ones — a handful of bogus registrations otherwise take rank 1.
    energy = rec.get(cfg["sort"][1])
    if isinstance(energy, (int, float)) and energy <= 0:
        rec["dataFlag"] = "invalid-energy"        # a registered appliance cannot use 0 kWh
    elif not eei_matches_class(cls, rec.get("eei"), cfg.get("eei_bounds")):
        rec["dataFlag"] = "eei-class-mismatch"

    return rec


def rank_and_trim(records, cfg, top_n):
    """Energy class first, then weighted energy consumption (lower is better).
    Records missing the energy figure, or whose declared EEI contradicts their
    declared class, sort behind the clean ones inside the same class."""
    _, energy_key = cfg["sort"]

    def sort_key(r):
        energy = r.get(energy_key)
        has_energy = isinstance(energy, (int, float)) and energy > 0
        return (r.get("classRank", 99), 1 if r.get("dataFlag") else 0,
                0 if has_energy else 1,
                energy if has_energy else 0, r.get("brand", ""), r.get("model", ""))

    ranked = sorted(records, key=sort_key)[:top_n]
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


# --- orchestration --------------------------------------------------------

def scrape(categories=None, top_n=None, max_pages=None, log=_log):
    top_n = top_n or ec.TOP_N
    wanted = ec.enabled_categories()
    if categories:
        wanted = {k: v for k, v in wanted.items() if k in categories}

    out = {
        "generated": time.strftime("%Y-%m-%d"),
        "source": "EPREL — European Product Registry for Energy Labelling (public API)",
        "note": ("Best models per category, ranked by energy class then weighted energy "
                 f"consumption (lower is better), capped at {top_n} per category. "
                 "Energy classes shown as 'A-30%' indicate how far the model's EEI sits "
                 "below that class's upper bound."),
        "top_n": top_n,
        "tracked_brands": ec.TRACKED_BRANDS,
        "categories": {},
    }

    for key, cfg in wanted.items():
        print(f"\n=== {cfg['label']} ({cfg['group']}) ===", flush=True)
        try:
            hits, total = collect_group(key, cfg, max_pages=max_pages, log=log)
            records = [normalize(h, key, cfg) for h in hits]
            records = [r for r in records if r.get("brand") and r.get("model")]
            ranked = rank_and_trim(records, cfg, top_n)
            brands = Counter(r["brand"] for r in ranked)
            classes = Counter(r.get("classLabel") for r in ranked)
            out["categories"][key] = {
                "label": cfg["label"],
                "group": cfg["group"],
                "regulation": cfg.get("regulation", ""),
                "class_scale": cfg["class_scale"],
                "class_order": [class_display(c) for c in ec.CLASS_ORDER[cfg["class_scale"]]],
                "energy_note": cfg.get("energy_note", ""),
                "sort": cfg["sort"],
                "columns": cfg["columns"],
                "registered_total": total,
                "unique_models": len(records),
                "kept": len(ranked),
                "flagged": sum(1 for r in ranked if r.get("dataFlag")),
                "brand_counts": dict(brands.most_common()),
                "class_counts": dict(classes),
                "products": ranked,
            }
            log("success", f"{cfg['label']}: kept top {len(ranked)} of {len(records)} "
                           f"unique models across {len(brands)} brands")
            log("info", f"{cfg['label']}: class spread {dict(classes)}")
        except Exception as e:
            log("error", f"{cfg['label']} failed, skipping: {e}")

    return out


def merge_into_existing(new_data, path):
    """Keep categories that this run did not (re)scrape, so a single-category
    run never wipes the rest of the database."""
    if not os.path.exists(path):
        return new_data
    try:
        with open(path, "r", encoding="utf-8") as f:
            old = json.load(f)
    except Exception:
        return new_data
    merged = dict(old)
    merged.update({k: v for k, v in new_data.items() if k != "categories"})
    cats = dict(old.get("categories") or {})
    cats.update(new_data.get("categories") or {})
    merged["categories"] = cats
    return merged


def main():
    ap = argparse.ArgumentParser(description="Scrape the EPREL product registry.")
    ap.add_argument("--category", action="append", choices=sorted(ec.CATEGORIES),
                    help="only this category (repeatable); default is all enabled")
    ap.add_argument("--top", type=int, default=ec.TOP_N,
                    help=f"models kept per category (default {ec.TOP_N})")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="stop after N pages per category (smoke test)")
    ap.add_argument("--out", default=ec.OUTPUT_FILE)
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be scraped, make no requests")
    args = ap.parse_args()

    targets = ec.enabled_categories()
    if args.category:
        targets = {k: v for k, v in targets.items() if k in args.category}

    if args.dry_run:
        print(f"[dry-run] would scrape {len(targets)} categories into {args.out}, "
              f"top {args.top} each:")
        for k, cfg in targets.items():
            print(f"    - {k:16s} {cfg['group']:22s} sort by {cfg['sort']}")
        return

    started = time.time()
    data = scrape(categories=list(targets), top_n=args.top, max_pages=args.max_pages)
    if not data["categories"]:
        print("\nNo category produced data; leaving the existing file untouched.")
        return

    data = merge_into_existing(data, args.out)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)

    total = sum(len(c["products"]) for c in data["categories"].values())
    size_mb = os.path.getsize(args.out) / 1e6
    print(f"\n=== Saved {total} products across {len(data['categories'])} categories "
          f"to {args.out} ({size_mb:.1f} MB) in {time.time() - started:.0f}s ===")
    for k, c in data["categories"].items():
        print(f"  {c['kept']:5d}  {c['label']:18s} of {c['unique_models']} unique "
              f"({c['registered_total']} registered)")


if __name__ == "__main__":
    main()
