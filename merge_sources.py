"""
Merge harvested product-page URLs into tech_sources.json, verifying each one.

The harvest stage (search) proposes URLs; this stage decides whether to trust
them. A URL is only accepted if the page actually fetches AND names the model —
the check that stops a plausible-looking URL resolving to a category or search
page, which would name every feature in the range and poison the scan.

    python merge_sources.py <harvest.json> [<harvest.json> ...]
    python merge_sources.py --recheck        # re-verify what is already stored

Harvest files map "category|brand|model" -> [urls].
"""
import argparse
import json
import os
import sys
import time

from tech_matrix import SOURCES_FILE, fetch_text

SLEEP = 1.0
def base_model(model):
    """Strip the trailing EPREL registration number, keep the rest of the id.

    Splitting on the first space would be wrong: plenty of ids contain spaces
    ("WAD 8536WBC EE", "C WD R47M WBS IT"), and truncating those to "WAD" makes
    the name check meaningless. The registration number is the distinguishing
    part — a long run of digits appended to the identifier.
    """
    parts = model.split()
    if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) >= 8:
        parts = parts[:-1]
    return " ".join(parts)


def names_model(text, model):
    """Does this page actually identify the model?

    Compared with punctuation and spacing stripped, because retailers write
    "WGB256A2GB", "WGB 256 A2 GB" and "wgb256a2gb" for the same machine.
    """
    if not text:
        return False
    flat = "".join(ch for ch in text.upper() if ch.isalnum())
    want = "".join(ch for ch in base_model(model).upper() if ch.isalnum())
    if len(want) < 5:                       # too short to be a safe signal
        return False
    if want in flat:
        return True
    # Retail SKUs append a market suffix (WF90F09C4S -> WF90F09C4SU1); accept the
    # page if it carries a longer id that starts with ours.
    return any(flat[i:i + len(want)] == want for i in range(len(flat) - len(want) + 1))


def verify(url, model, log=print):
    text = fetch_text(url, log=lambda m: None)
    if text is None:
        log(f"      unreachable  {url}")
        return False, "unreachable"
    if not names_model(text, model):
        log(f"      does not name {base_model(model)}  {url}")
        return False, "wrong-page"
    log(f"      OK ({len(text)} chars)  {url}")
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="harvest JSON files")
    ap.add_argument("--recheck", action="store_true",
                    help="re-verify URLs already in tech_sources.json")
    args = ap.parse_args()

    sources = {}
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, encoding="utf-8") as f:
            sources = json.load(f)

    proposed = {}
    for path in args.files:
        if not os.path.exists(path):
            print(f"  missing harvest file: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            for key, urls in json.load(f).items():
                proposed.setdefault(key, [])
                for u in urls or []:
                    if u not in proposed[key]:
                        proposed[key].append(u)
    if args.recheck:
        for key, urls in sources.items():
            proposed.setdefault(key, []).extend(u for u in urls if u not in proposed.get(key, []))

    accepted = rejected = 0
    for key, urls in sorted(proposed.items()):
        if not urls:
            continue
        model = key.split("|")[-1]
        print(f"  {key}")
        good = []
        for url in urls[:4]:
            ok, _ = verify(url, model)
            time.sleep(SLEEP)
            if ok:
                good.append(url)
            else:
                rejected += 1
        if good:
            sources[key] = good
            accepted += len(good)
        elif key in sources:
            del sources[key]           # every stored URL failed re-verification

    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=1, ensure_ascii=False)

    have = sum(1 for v in sources.values() if v)
    print(f"\n  accepted {accepted} URLs, rejected {rejected}; "
          f"{have} products now have a verified source page")


if __name__ == "__main__":
    main()
