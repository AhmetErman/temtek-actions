"""
Targeted EPREL queries — the research companion to eprel_scraper.py.

Unlike the bulk scraper (which pages a whole product group), this hits the API
with server-side filters, which DO work as long as you use the real API field
name for that product group:

    supplierOrTrademark=Bosch        # prefix match, so "LG" also finds "LG Electronics"
    modelIdentifier=WGB256A0GB       # prefix match too, so pick the literal hit
    energyClass=A                    # washing machines / dishwashers
    energyClassWashAndDry=A          # washer-dryers use their own field

(The class field per category comes from `eprel_config.CATEGORIES[...]["fields"]`,
so this stays correct if a category is added.)

Two jobs:

  * `candidates()` — every registration for one brand in one category, ranked
    exactly like the benchmark (energy class, then weighted energy). This is how
    you find a brand's genuinely best models before checking which are still on
    sale.
  * `lookup()` — one model by its exact identifier, returning the normalized
    record, so a researched product's specs come from the registry rather than
    from marketing copy.

    python eprel_lookup.py --category washing-machine --brand Bosch --top 15
    python eprel_lookup.py --category dishwasher --model SN87YX03CE
    python eprel_lookup.py --category dryer --brand Beko --class APPP --json
"""
import argparse
import json
import math
import sys
import time

import eprel_config as ec
from eprel_scraper import fetch_page, normalize, rank_and_trim, class_display

import urllib.parse
import urllib.request


def _get(group, **params):
    url = ec.API_BASE + group + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=ec.REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=ec.REQUEST_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _category(key):
    cfg = ec.CATEGORIES.get(key)
    if not cfg:
        raise SystemExit(f"unknown category '{key}'; pick one of {', '.join(ec.CATEGORIES)}")
    return cfg


def _class_field(cfg):
    """The API field carrying the headline energy class for this group."""
    return cfg["fields"].get("energyClass", "energyClass")


def _collect(group, params, max_pages=40, sleep=0.3):
    """Page through a filtered query, keeping the newest version per registration."""
    best, page = {}, 1
    while page <= max_pages:
        data = _get(group, _page=page, _limit=ec.PAGE_SIZE, **params)
        hits = data.get("hits") or []
        if not hits:
            break
        for h in hits:
            reg = h.get("eprelRegistrationNumber")
            if not reg:
                continue
            prev = best.get(reg)
            if prev is None or (h.get("versionNumber") or 0) > (prev.get("versionNumber") or 0):
                best[reg] = h
        if len(best) >= (data.get("size") or 0) or len(hits) < ec.PAGE_SIZE:
            break
        page += 1
        time.sleep(sleep)
    return list(best.values())


def candidates(category, brand, energy_class=None, top=20):
    """A brand's registrations in one category, best first.

    Ranked by the same rule as the benchmark: energy class, then weighted energy
    consumption ascending, with data-flagged records pushed behind clean ones.
    """
    cfg = _category(category)
    params = {"supplierOrTrademark": brand}
    if energy_class:
        params[_class_field(cfg)] = energy_class
    raw = _collect(cfg["group"], params)
    records = [normalize(h, category, cfg) for h in raw]
    records = [r for r in records if r.get("brand") and r.get("model")]
    return rank_and_trim(records, cfg, top)


def _norm(s):
    return "".join(ch for ch in str(s).upper() if ch.isalnum())


def lookup(category, model, brand=None):
    """One model by identifier. Returns the normalized record or None.

    `modelIdentifier` is prefix-matched by the API, not exact — querying
    "B5W5941BD" also returns "B5W5941BDG 457100046100". Prefer a literal match,
    then the shortest identifier (the plainest variant), then the newest version,
    so a query never silently resolves to some longer sibling SKU.
    """
    cfg = _category(category)
    params = {"modelIdentifier": model}
    if brand:
        params["supplierOrTrademark"] = brand
    raw = _collect(cfg["group"], params, max_pages=3)
    if not raw:
        return None
    want = _norm(model)
    raw.sort(key=lambda h: (0 if _norm(h.get("modelIdentifier")) == want else 1,
                            len(_norm(h.get("modelIdentifier"))),
                            -(h.get("versionNumber") or 0)))
    return normalize(raw[0], category, cfg)


def resolve(category, model, brand):
    """Map a retail SKU onto its EPREL registration.

    Retailers quote market-specific SKUs ("WF90F09C4SU1", "EW9W6F61SB 914600601")
    while EPREL registers the base identifier ("WF90F09C4S"). Exact match is
    tried first, then the brand's registrations are scanned for the longest
    identifier that prefixes the query (or that the query prefixes).

    Returns (record, how) where `how` is 'exact', 'prefix' or None.
    """
    rec = lookup(category, model, brand)
    if rec:
        return rec, ("exact" if _norm(rec.get("model")) == _norm(model) else "prefix")
    if not brand:
        return None, None
    target = _norm(model)
    best, best_len = None, 0
    for r in candidates(category, brand, top=10000):
        ident = _norm(r.get("model"))
        if not ident:
            continue
        if (target.startswith(ident) or ident.startswith(target)) and len(ident) > best_len:
            best, best_len = r, len(ident)
    return (best, "prefix") if best else (None, None)


def find_any(model, brand=None):
    """Look a model up across every category — useful when you know the model
    number but not which product group it was registered under."""
    for key in ec.CATEGORIES:
        rec = lookup(key, model, brand)
        if rec:
            return key, rec
    return None, None


# --- CLI ------------------------------------------------------------------

def _fmt_row(r, cfg):
    energy_key = cfg["sort"][1]
    cap = r.get("capacity")
    return (f"  {r['rank']:3d}. {r.get('classDetail',''):>8s}  "
            f"{str(r.get(energy_key,'—')):>6s}  "
            f"cap {str(cap):>4s}  "
            f"{r.get('brand',''):<12s} {r.get('model','')[:34]:<34s} "
            f"{r.get('registration','')}"
            + ("  ⚠" if r.get("dataFlag") else ""))


def main():
    ap = argparse.ArgumentParser(description="Targeted EPREL lookups.")
    ap.add_argument("--category", required=True, choices=sorted(ec.CATEGORIES))
    ap.add_argument("--brand", help="supplier/trademark, prefix-matched")
    ap.add_argument("--model", help="exact model identifier")
    ap.add_argument("--class", dest="energy_class",
                    help="energy class filter (A..G, or APPP/APP/AP for dryers)")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--json", action="store_true", help="emit full records as JSON")
    args = ap.parse_args()

    cfg = _category(args.category)

    if args.model:
        rec = lookup(args.category, args.model, args.brand)
        if not rec:
            print(f"not found in {cfg['group']}: {args.model}")
            sys.exit(1)
        if args.json:
            print(json.dumps(rec, indent=1, ensure_ascii=False))
        else:
            for col in cfg["columns"]:
                v = rec.get(col["key"])
                unit = f" {col['unit']}" if col.get("unit") else ""
                print(f"  {col['label']:32s} {'' if v is None else v}{unit}")
        return

    if not args.brand:
        ap.error("give --brand and/or --model")

    rows = candidates(args.category, args.brand, args.energy_class, args.top)
    if args.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
        return
    energy_col = next((c["label"] for c in cfg["columns"] if c["key"] == cfg["sort"][1]), "energy")
    print(f"\n{cfg['label']} — {args.brand} — {len(rows)} best of what EPREL lists "
          f"({cfg['regulation']})")
    print(f"  rank    class  {energy_col[:6]:>6s}  capacity  brand        model")
    for r in rows:
        print(_fmt_row(r, cfg))


if __name__ == "__main__":
    main()
