"""
Fill the /products technology matrix from each model's own commercial page.

The rule this job encodes: **a feature a brand does not advertise on the
product's own page is a feature the product almost certainly does not have.**
So a page that fetches cleanly and mentions none of a technology's marketing
names resolves that cell to "no" — not to "unknown". "unknown" is reserved for
the case where no page could be read at all, which is the only honest reason to
not know.

    python tech_matrix.py --list                 # products and their source URLs
    python tech_matrix.py --scan                 # fetch + match, write evidence
    python tech_matrix.py --scan --only Bosch    # one brand
    python tech_matrix.py --apply                # write verdicts into products.json
    python tech_matrix.py --scan --apply         # both

Evidence (matched phrase, surrounding snippet, source URL, fetch date) is kept
in tech_evidence.json so every "yes" on the page is traceable and every "no" is
attributable to a specific page that failed to mention it.

Design follows the other scrapers here: stdlib only, browser-ish headers,
fault-isolated per product, progress printed with counts.
"""
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

PRODUCTS_FILE = "products.json"
EVIDENCE_FILE = "tech_evidence.json"
SOURCES_FILE = "tech_sources.json"      # product key -> [commercial page URLs]

REQUEST_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
REQUEST_TIMEOUT = 25
SLEEP_BETWEEN = 1.0

# Marketing names per technology. A cell is "yes" when any alias appears on the
# product's page. Keep these SPECIFIC: "steam" alone would match "steam iron" in
# a footer, so the aliases carry enough context to be about this machine.
KEYWORDS = {
    "washing-machine": {
        "autodose": ["i-dos", "idos", "autodose", "auto dose", "auto-dose",
                     "auto dosing", "automatic dosing", "auto dispense",
                     "autodos", "intellidose", "smart dosing", "dose assist"],
        "ai": ["ai wash", "ai dd", "ai direct drive", "artificial intelligence",
               "ai control", "sensorwash", "6th sense", "ai ecobubble",
               "fabric type", "load sensing", "ai energy"],
        "microplastic": ["microplastic", "micro plastic", "microfibre", "microfiber",
                         "less microfiber", "fibre catch", "fiber catch"],
        "steam": ["steam", "steamcure", "steamcare", "hygiene steam", "allergiene"],
        "directdrive": ["direct drive", "directdrive", "direct motion", "beltless",
                        "inverter direct drive", "ai dd"],
        "additem": ["addwash", "add wash", "add garment", "add item", "add laundry",
                    "mid-cycle", "mid cycle", "pause and add"],
        "dosescan": ["detergent scan", "dose scan", "scan detergent",
                     "detergent recognition", "home connect detergent"],
        "recycled": ["recycled tub", "recycledtub", "recycled plastic",
                     "recycled material", "ocean plastic"],
    },
    "washer-dryer": {
        "heatpump": ["heat pump", "heatpump", "ventless", "heat-pump"],
        "autodose": ["i-dos", "autodose", "auto dose", "auto dispense", "autodos",
                     "automatic dosing", "intellidose"],
        "ai": ["ai wash", "ai dd", "artificial intelligence", "6th sense",
               "sensorwash", "ai control", "ai laundry"],
        "nonstop": ["non-stop", "nonstop", "wash to dry", "wash and dry in one",
                    "one touch wash and dry", "wash & dry cycle", "full load wash and dry"],
        "autodry": ["auto dry", "autodry", "sensor dry", "dryness level",
                    "humidity sensor", "moisture sensor"],
        "steam": ["steam", "steamcare", "steamcure", "refresh"],
        "directdrive": ["direct drive", "direct motion", "beltless", "ai dd"],
        "microplastic": ["microplastic", "microfibre", "microfiber"],
    },
    "dryer": {
        "heatpump": ["heat pump", "heatpump", "heat-pump"],
        "ai": ["ai dry", "artificial intelligence", "ai control", "6th sense",
               "auto sensing", "ai super dry", "adaptive drying"],
        "steam": ["steam", "refresh", "de-wrinkle", "dewrinkle", "crease"],
        "selfclean": ["self-cleaning condenser", "self cleaning condenser",
                      "auto cleaning condenser", "autoclean condenser",
                      "self-clean condenser"],
        "reverse": ["reverse tumble", "reverse action", "both directions",
                    "anti-crease", "anticrease", "alternating drum"],
        "wifi": ["wi-fi", "wifi", "smartthings", "thinq", "home connect", "hon app",
                 "app control", "connected"],
        "heatex": ["maintenance-free", "maintenance free heat exchanger",
                   "no filter cleaning", "self-cleaning heat exchanger"],
        "rackdry": ["drying rack", "static rack", "wool rack", "shoe rack",
                    "rack dry", "basket dry"],
    },
    "dishwasher": {
        "autoopen": ["auto open", "autoopen", "auto-open", "airdry", "air dry",
                     "door opens automatically", "openassist", "autoair"],
        "zeolith": ["zeolith", "zeolite", "crystaldry", "crystal dry"],
        "autodose": ["autodos", "autodose", "auto dose", "powerdisk",
                     "automatic detergent", "auto dispense"],
        "thirdrack": ["third rack", "3rd rack", "cutlery drawer", "cutlery tray",
                      "third level", "flex rack"],
        "zonewash": ["zone wash", "zonewash", "half load", "intensive zone",
                     "power zone", "flexizone", "dual zone"],
        "ai": ["auto programme", "auto program", "sensor wash", "soil sensor",
               "turbidity", "6th sense", "ai wash", "automatic programme"],
        "softener": ["water softener", "softening", "salt", "water hardness"],
        "wifi": ["wi-fi", "wifi", "home connect", "smartthings", "thinq",
                 "hon app", "app control", "connected"],
    },
}


# --- fetching -------------------------------------------------------------

class _Text(HTMLParser):
    """Strip a page down to visible text (stdlib only, like the other scrapers)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        # Feature names often live in alt/title/aria-label, not body text.
        for key, val in attrs:
            if key in ("alt", "title", "aria-label", "content") and val:
                self.parts.append(val)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts))


def fetch_text(url, log=print):
    """Page text, or None if the site refuses us (bot protection, 404, timeout)."""
    try:
        req = urllib.request.Request(url, headers=REQUEST_HEADERS)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        log(f"      HTTP {e.code} {url}")
        return None
    except Exception as e:
        log(f"      {type(e).__name__}: {e} {url}")
        return None
    for enc in (charset, "utf-8", "latin-1"):
        try:
            html = raw.decode(enc, errors="strict")
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        html = raw.decode("utf-8", errors="replace")
    parser = _Text()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.text()


# --- matching -------------------------------------------------------------

def scan_text(text, category, model=None):
    """Match every technology's aliases against one page.

    Returns {tech: {"found": bool, "phrase": str, "snippet": str}}. A snippet is
    kept for each hit so a human (or a reviewing agent) can judge whether the
    match really refers to this machine.
    """
    low = " " + text.lower() + " "
    out = {}
    for tech, aliases in KEYWORDS[category].items():
        hit = None
        for alias in aliases:
            idx = low.find(alias)
            if idx >= 0:
                start, end = max(0, idx - 90), min(len(low), idx + len(alias) + 90)
                hit = {"found": True, "phrase": alias,
                       "snippet": text[start:end].strip()}
                break
        out[tech] = hit or {"found": False, "phrase": None, "snippet": None}
    return out


def product_key(p):
    return f"{p['category']}|{p['company']}|{p['model']}"


# Per-brand product-URL templates. {m} is the model id lowercased with spaces
# and punctuation stripped; {M} keeps the original case. Listing pages are
# deliberately NOT used as sources: they mention every feature in the range and
# would turn the whole matrix into false positives.
URL_TEMPLATES = {
    "LG": ["https://www.lg.com/uk/laundry/washing-machines/{m}/",
           "https://www.lg.com/uk/laundry/tumble-dryers/{m}/",
           "https://www.lg.com/uk/dishwashers/{m}/"],
    "Bosch": ["https://www.bosch-home.co.uk/en/product/laundry/washing-machines/front-load-washing-machines/{M}",
              "https://www.bosch-home.co.uk/en/product/laundry/dryers/heat-pump-dryers/{M}",
              "https://www.bosch-home.co.uk/en/product/dishwashers/free-standing-dishwashers/{M}"],
    "Haier": ["https://www.haier-europe.com/en_GB/product/{m}/"],
    "Beko": ["https://www.beko.co.uk/search?q={M}"],
    "Hisense": ["https://hisense.co.uk/search?q={M}"],
    "AEG": ["https://www.aeg.co.uk/search/?q={M}"],
    "Electrolux": ["https://www.electrolux.com/search/?q={M}"],
    "Whirlpool": ["https://www.whirlpool.co.uk/search?q={M}"],
    "Samsung": ["https://www.samsung.com/uk/search/?searchvalue={M}"],
    "Midea": ["https://www.midea.com/uk/search?q={M}"],
}


def candidate_urls(product):
    """Guess a product page from the brand's URL shape. Verified by fetching."""
    raw = product["model"].split()[0]                  # drop the trailing EPREL suffix
    slug = re.sub(r"[^a-z0-9]", "", raw.lower())
    return [t.format(m=slug, M=raw) for t in URL_TEMPLATES.get(product["company"], [])]


def run_discover(products, sources, only=None, log=print):
    """Try each brand's URL shapes and keep the ones that actually return a page
    naming this model — a template that resolves to a generic page is useless."""
    found = 0
    for p in products:
        key = product_key(p)
        if sources.get(key) or (only and only.lower() not in p["company"].lower()):
            continue
        raw = p["model"].split()[0]
        for url in candidate_urls(p):
            text = fetch_text(url, log=lambda m: None)
            time.sleep(SLEEP_BETWEEN)
            if text and raw.lower().replace(" ", "") in text.lower().replace(" ", ""):
                sources[key] = [url]
                found += 1
                log(f"  found  {p['company']:11s} {raw[:26]:28s} {url}")
                break
        else:
            log(f"  ----   {p['company']:11s} {raw[:26]:28s} no page names this model")
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=1, ensure_ascii=False)
    log(f"\n  discovered {found} product pages; {len(sources)} sources total")
    return sources


# --- job ------------------------------------------------------------------

def load(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def run_scan(products, sources, only=None, log=print):
    """Fetch each product's commercial pages and record what they mention."""
    evidence = load(EVIDENCE_FILE, {})
    scanned = skipped = 0
    for p in products:
        key = product_key(p)
        if only and only.lower() not in p["company"].lower():
            continue
        urls = sources.get(key) or ([p["productUrl"]] if p.get("productUrl") else [])
        if not urls:
            skipped += 1
            continue
        log(f"  {p['company']} {p['model'][:28]} ({p['category']})")
        per_tech = {}
        pages = []
        for url in urls:
            text = fetch_text(url, log=log)
            time.sleep(SLEEP_BETWEEN)
            if not text:
                continue
            pages.append(url)
            for tech, res in scan_text(text, p["category"], p["model"]).items():
                # First page that finds a feature wins; absence only counts
                # once every listed page has been read.
                if res["found"] and not per_tech.get(tech, {}).get("found"):
                    per_tech[tech] = dict(res, url=url)
                per_tech.setdefault(tech, dict(res, url=url))
        if not pages:
            log("      no page could be read - leaving this product unknown")
            skipped += 1
            continue
        scanned += 1
        found = [t for t, r in per_tech.items() if r["found"]]
        log(f"      read {len(pages)} page(s); mentions: {', '.join(found) or 'none'}")
        evidence[key] = {"pages": pages, "checked": time.strftime("%Y-%m-%d"),
                         "tech": per_tech}
    with open(EVIDENCE_FILE, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=1, ensure_ascii=False)
    log(f"\n  scanned {scanned} products, {skipped} left unknown (no readable page)")
    return evidence


def run_apply(data, evidence, log=print):
    """Turn evidence into matrix verdicts.

    Only cells this job can justify are touched: a mention becomes "yes", and a
    readable page that never mentions the feature becomes "no". Values already
    set to yes/partial/no by hand are left alone unless the page contradicts
    them, in which case the conflict is reported rather than silently resolved.
    """
    changed = conflicts = 0
    for p in data["products"]:
        ev = evidence.get(product_key(p))
        if not ev:
            continue
        for tech, res in ev["tech"].items():
            if tech not in p["tech"]:
                continue
            verdict = "yes" if res["found"] else "no"
            current = p["tech"][tech]
            if current == "unknown":
                p["tech"][tech] = verdict
                changed += 1
            elif current != verdict and not (current == "partial" and verdict == "yes"):
                conflicts += 1
                log(f"  ! {p['company']} {p['model'][:24]} {tech}: "
                    f"page says {verdict}, matrix says {current} (kept {current})")
    log(f"\n  filled {changed} cells, {conflicts} conflicts left for review")
    return data


def main():
    ap = argparse.ArgumentParser(description="Fill the technology matrix from product pages.")
    ap.add_argument("--discover", action="store_true", help="find product-page URLs per brand")
    ap.add_argument("--scan", action="store_true", help="fetch pages and record evidence")
    ap.add_argument("--apply", action="store_true", help="write verdicts into products.json")
    ap.add_argument("--only", help="restrict to one brand")
    ap.add_argument("--list", action="store_true", help="show products and their sources")
    args = ap.parse_args()

    data = load(PRODUCTS_FILE, {"products": []})
    sources = load(SOURCES_FILE, {})
    products = data.get("products", [])

    if args.list or not (args.scan or args.apply or args.discover):
        have = sum(1 for p in products if sources.get(product_key(p)))
        print(f"{len(products)} products, {have} with a source URL:\n")
        for p in products:
            key = product_key(p)
            urls = sources.get(key, [])
            print(f"  {'OK ' if urls else '   '} {p['category']:16s} {p['company']:11s} "
                  f"{p['model'][:30]:32s} {len(urls)} url(s)")
        return

    if args.discover:
        print("=== discovering product pages ===")
        sources = run_discover(products, sources, only=args.only)

    evidence = load(EVIDENCE_FILE, {})
    if args.scan:
        print("=== scanning commercial pages ===")
        evidence = run_scan(products, sources, only=args.only)
    if args.apply:
        print("\n=== applying verdicts ===")
        data = run_apply(data, evidence)
        with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        print(f"  wrote {PRODUCTS_FILE}")


if __name__ == "__main__":
    main()
