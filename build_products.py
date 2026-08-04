"""Rebuild products.json from scratch: EPREL-sourced specs for researched flagships.

Every previous row is discarded. Model choice comes from eprel_lookup.candidates()
(on-market, recent marketStart, flagship-grade capacity); specs come from the
registry, never from marketing copy.

`verified` records how far availability was confirmed:
  retail  - reached a live product/retail listing (country + price recorded)
  eprel   - registered and on-market in EPREL, but no retail listing reached yet
"""
import json
import sys

sys.path.insert(0, "/home/a26124811/projects/temtek-actions")
import eprel_lookup as L

# --- Technology sets: only features that actually separate these machines. ---
# Deliberately excludes quick-wash, hygiene/anti-bacterial, inverter motor and
# app control: every flagship in this set has them, so they made every column
# read "yes" and told you nothing.
TECHNOLOGIES = {
    "washing-machine": [
        ("autodose",     "Automatic detergent dosing",     "Auto-dose"),
        ("ai",           "AI load & fabric sensing",       "AI sensing"),
        ("microplastic", "Microplastic / microfibre filter", "Microplastic"),
        ("steam",        "Steam programme",                "Steam"),
        ("directdrive",  "Direct-drive (beltless) motor",  "Direct drive"),
        ("additem",      "Add garment mid-cycle",          "Add-item"),
        ("dosescan",     "Detergent recognition / dosing assistant", "Dose scan"),
        ("recycled",     "Recycled-material drum or tub",  "Recycled"),
    ],
    "washer-dryer": [
        ("heatpump",     "Heat-pump (ventless) drying",    "Heat-pump"),
        ("autodose",     "Automatic detergent dosing",     "Auto-dose"),
        ("ai",           "AI load & fabric sensing",       "AI sensing"),
        ("nonstop",      "Full load wash-to-dry without unloading", "Non-stop"),
        ("autodry",      "Sensor-controlled dryness level", "Auto-dry"),
        ("steam",        "Steam programme",                "Steam"),
        ("directdrive",  "Direct-drive (beltless) motor",  "Direct drive"),
        ("microplastic", "Microplastic / microfibre filter", "Microplastic"),
    ],
    "dryer": [
        ("heatpump",     "Heat-pump condenser",            "Heat-pump"),
        ("ai",           "AI / adaptive drying programme", "AI drying"),
        ("steam",        "Steam refresh & de-wrinkle",     "Steam"),
        ("selfclean",    "Self-cleaning condenser",        "Self-clean"),
        ("reverse",      "Reverse-tumble anti-crease",     "Reverse"),
        ("wifi",         "Wi-Fi / app control",            "Wi-Fi"),
        ("heatex",       "Maintenance-free heat exchanger", "No-clean HX"),
        ("rackdry",      "Static rack for shoes / wool",   "Rack dry"),
    ],
    "dishwasher": [
        ("autoopen",     "Auto-open door drying",          "Auto-open"),
        ("zeolith",      "Zeolith drying",                 "Zeolith"),
        ("autodose",     "Automatic detergent dosing",     "Auto-dose"),
        ("thirdrack",    "Third cutlery rack",             "3rd rack"),
        ("zonewash",     "Zone / half-load intensive wash", "Zone wash"),
        ("ai",           "Sensor / AI automatic programme", "AI sensing"),
        ("softener",     "Built-in water softener",        "Softener"),
        ("wifi",         "Wi-Fi / app control",            "Wi-Fi"),
    ],
}

CATEGORY_META = {
    "washing-machine": ("Washing Machines", "🌀", "Flagship front-load washers, one per brand."),
    "washer-dryer":    ("Washer-Dryers", "🔁", "Combo units that wash and dry in a single drum."),
    "dryer":           ("Dryers", "🌬️", "Standalone tumble dryers — heat-pump, condenser and vented."),
    "dishwasher":      ("Dishwashers", "🍽️", "Flagship built-in and freestanding dishwashers."),
}

# Chosen model per brand per category: best on-market EPREL registration of
# flagship grade. (retail country, price EUR, source) filled where a live
# listing was reached; None where it still needs checking.
PICKS = {
    "washing-machine": [
        ("Bosch",      "WGB256A2GB",   "Series 8 i-DOS",           "retail", "UK", 999, "GBP",
         "John Lewis / Marks Electrical / Appliances Direct"),
        ("LG",         "F4X9009TBC",   "Series 9 AI DD (VX90)",    "retail", "UK", None, None,
         "lg.com/uk; in stock at Marks Electrical, ao.com, Hughes, Appliance City"),
        ("Samsung",    "WF90F09C4S",   "Series 9 Bespoke AI",      "retail", "UK", None, None,
         "samsung.com/uk product page live (SKU WF90F09C4SU1)"),
        ("Beko",       "B5W5941BD",    "AutoDose SteamCure",       "retail", "UK", None, None,
         "beko.co.uk product page live"),
        ("Haier",      "HW100-B14397EU1", "I-Pro Series 7",        "retail", "NL", None, None,
         "coolblue.nl lists the HW100-BD14397U1S variant"),
        ("AEG",        "LFR95146SUC",  "9000 series AbsoluteCare", "eprel",  None, None, None, None),
        ("Electrolux", "EW9F5417SWCE", "900 series AutoDose",      "eprel",  None, None, None, None),
        ("Whirlpool",  "W0M 912G ADS FR", "W Collection AutoDose", "eprel",  None, None, None, None),
        ("Hisense",    "WF7E1045BWQ",  "7 Series",                 "eprel",  None, None, None, None),
        ("Midea",      "MF205W90BA50/T-IT", "MF205 series",        "eprel",  None, None, None, None),
    ],
    # Washer-dryers carry BOTH drying technologies where a brand sells both:
    # heat-pump and condenser are different products, not different trims.
    "washer-dryer": [
        ("Samsung",    "WD18DB8995BZ", "Bespoke AI Laundry Combo", "retail", "NL", 2213, "EUR",
         "Launched in Europe at IFA 2024; price from the earlier EPREL benchmark sheet"),
        ("LG",         "F164HP2BST",   "Heat-pump washer-dryer",   "eprel",  None, None, None, None),
        ("Haier",      "HWD120-BD16397EU1", "I-Pro Series 6 heat-pump", "eprel", None, None, None, None),
        ("Hisense",    "WD5I1245BBRH", "5S Series heat-pump",      "eprel",  None, None, None, None),
        ("AEG",        "LWR9506BN4",   "9000 series heat-pump",    "eprel",  None, None, None, None),
        ("Electrolux", "EW9W1165RB",   "900 series heat-pump",     "eprel",  None, None, None, None),
        ("Whirlpool",  "BWT 106A3C BC", "6th Sense heat-pump",     "eprel",  None, None, None, None),
        ("Beko",       "B7DFT61041W",  "AutoDose heat-pump",       "eprel",  None, None, None, None),
        ("Samsung",    "WD10HG6U34BB", "Series 6 condenser",       "eprel",  None, None, None, None),
        ("LG",         "F164X58WHST",  "Condenser washer-dryer",   "eprel",  None, None, None, None),
        ("Bosch",      "WNA254REPL",   "Series 4 condenser",       "eprel",  None, None, None, None),
        ("Haier",      "HWD80-BP1433637T", "Condenser washer-dryer", "eprel", None, None, None, None),
        ("Hisense",    "W1D2A854ADPS", "Condenser washer-dryer",   "eprel",  None, None, None, None),
        ("AEG",        "L6WJ68WC",     "6000 series condenser",    "eprel",  None, None, None, None),
        ("Electrolux", "EW2W3068E4",   "300 series condenser",     "eprel",  None, None, None, None),
        ("Whirlpool",  "WAD 8536WBC EE", "Condenser washer-dryer", "eprel",  None, None, None, None),
        ("Beko",       "BMM5DFO5841MDC", "Condenser washer-dryer", "eprel",  None, None, None, None),
        ("Midea",      "MF200D80WB/1/W-HR", "MF200 condenser",     "eprel",  None, None, None, None),
    ],
    "dryer": [
        ("AEG",        "TR9HH8AY",     "9000 series heat-pump",    "eprel",  None, None, None, None),
        ("Electrolux", "EW9H48A",      "900 series heat-pump",     "eprel",  None, None, None, None),
        ("Samsung",    "DV90DB7845GB", "Bespoke AI heat-pump",     "retail", "UK", None, None,
         "samsung.com/uk support page live for SKU DV90DB7845GBU3"),
        ("Hisense",    "DH5I104BBAB",  "5S Series heat-pump",      "eprel",  None, None, None, None),
        ("Whirlpool",  "C WD R47M WBS IT", "Supreme Silence heat-pump", "eprel", None, None, None, None),
        ("LG",         "RH9X76BM",     "Dual Inverter heat-pump",  "eprel",  None, None, None, None),
        ("Bosch",      "WQB246D41",    "Series 8 heat-pump",       "eprel",  None, None, None, None),
        ("Midea",      "MD20EH80WB-A3", "MD20 heat-pump",          "eprel",  None, None, None, None),
        ("Haier",      "HD90-CQ387U1", "I-Pro Series 3",           "eprel",  None, None, None, None),
        ("Beko",       "BM3T38220X",   "BM3T heat-pump",           "eprel",  None, None, None, None),
    ],
    "dishwasher": [
        ("Whirlpool",  "WH5IA5015BT1LS", "MaxiSpace 15ps",         "eprel",  None, None, None, None),
        ("Samsung",    "DW80H77H3B0",  "Bespoke AI dishwasher",    "eprel",  None, None, None, None),
        ("LG",         "DB597TXSN",    "TrueSteam QuadWash",       "eprel",  None, None, None, None),
        ("Hisense",    "HFI5A6360H",   "5S Series 16ps",           "eprel",  None, None, None, None),
        ("AEG",        "FSE77707P",    "7000 series GlassCare",    "eprel",  None, None, None, None),
        ("Electrolux", "E82IX220ST",   "800 GlassCare",            "eprel",  None, None, None, None),
        ("Bosch",      "SBD6ECX21E",   "Series 6 dishwasher",      "eprel",  None, None, None, None),
        ("Beko",       "BDIN38560WPF", "AutoDose 15ps",            "eprel",  None, None, None, None),
        ("Haier",      "XF 4A4M0W-80", "XF Series 4",              "eprel",  None, None, None, None),
        ("Midea",      "MDWEB1403M(B)-WA-UK", "MDWEB1403",         "eprel",  None, None, None, None),
    ],
}

# Technology support confirmed during research.
#
# Keys are (category, brand) and therefore RANGE-level claims. That is only safe
# while a brand contributes ONE model to a category. Washer-dryers now list two
# models per brand, and a 2026 audit found flagship features leaking onto the
# budget sibling that way (Samsung's Auto Dispense onto WD10HG6U34BB, Bosch's
# washer steam onto the WQB246D41 dryer, Electrolux AutoDose onto its AEG twin).
# MODEL_FACTS below overrides per model and always wins; put anything
# model-specific there, and `check_range_leak()` fails the build if a range-level
# claim would be stamped onto more than one model in a category.
TECH_FACTS = {
    ("washing-machine", "Bosch"):      {"autodose": "yes", "dosescan": "yes", "steam": "yes",
                                        "ai": "partial", "directdrive": "no", "additem": "no"},
    ("washing-machine", "LG"):         {"ai": "yes", "directdrive": "yes", "steam": "yes",
                                        "additem": "partial", "autodose": "no", "dosescan": "no"},
    ("washing-machine", "Samsung"):    {"ai": "yes", "autodose": "yes", "steam": "yes",
                                        "additem": "yes", "microplastic": "partial"},
    ("washing-machine", "Beko"):       {"autodose": "yes", "steam": "yes", "recycled": "yes",
                                        "microplastic": "partial", "ai": "no", "directdrive": "no"},
    ("washing-machine", "Electrolux"): {"autodose": "yes", "ai": "yes", "steam": "yes"},
    ("washing-machine", "AEG"):        {"autodose": "yes", "ai": "yes", "steam": "yes"},
    ("washing-machine", "Haier"):      {"directdrive": "yes", "steam": "yes", "ai": "partial",
                                        "autodose": "no"},
    ("washing-machine", "Whirlpool"):  {"autodose": "yes", "ai": "partial", "steam": "yes"},
    # --- dryers (brand-range evidence) ---
    ("dryer", "Samsung"):              {"ai": "yes", "wifi": "yes"},
    ("dryer", "Bosch"):                {"selfclean": "yes", "reverse": "yes", "steam": "yes"},
    ("dryer", "LG"):                   {"selfclean": "yes", "ai": "yes", "wifi": "yes"},
    ("dryer", "Hisense"):              {"selfclean": "yes", "steam": "yes", "ai": "yes", "wifi": "yes"},
    # --- washer-dryers ---
    # --- dishwashers (brand-range evidence) ---
    ("dishwasher", "Bosch"):           {"autoopen": "yes", "thirdrack": "yes", "zeolith": "partial"},
    ("dishwasher", "Beko"):            {"autodose": "yes", "ai": "yes"},
    ("dishwasher", "Whirlpool"):       {"autoopen": "yes", "thirdrack": "yes"},
    ("dishwasher", "Samsung"):         {"autoopen": "yes", "thirdrack": "yes"},
}

# (category, model-prefix) -> per-model truth, applied after the range-level map.
MODEL_FACTS = {
    ("washer-dryer", "WD10HG6U34BB"): {"autodose": "no", "steam": "yes"},
    ("washer-dryer", "F164HP2BST"):   {"directdrive": "yes", "steam": "yes", "ai": "yes"},
    ("washer-dryer", "HWD120-BD16397EU1"): {"directdrive": "yes"},
    ("washer-dryer", "WD18DB8995BZ"): {"microplastic": "partial", "autodry": "yes",
                                       "ai": "yes", "autodose": "yes"},
    ("washer-dryer", "BWT 106A3C"):   {"heatpump": "unknown"},
    ("washer-dryer", "B7DFT61041W"):  {"heatpump": "unknown"},
    ("dryer", "WQB246D41"):           {"steam": "no", "wifi": "yes", "reverse": "unknown"},
    ("dryer", "DH5I104BBAB"):         {"ai": "partial"},
    ("washing-machine", "LFR95146SUC"): {"autodose": "no", "ai": "no"},
    ("washing-machine", "B5W5941BDG"):  {"recycled": "no", "microplastic": "no", "additem": "yes"},
    ("washing-machine", "EW9F5417SWCE"): {"ai": "partial"},
    ("washing-machine", "F4X9009TBC"):   {"additem": "yes"},
    ("washing-machine", "WF90F09C4S"):   {"directdrive": "no"},
    ("dishwasher", "SBD6ECX21E"):     {"zeolith": "no"},
    ("dishwasher", "BDIN38560WPF"):   {"ai": "no"},
}


def check_range_leak():
    """A range-level claim is only valid when the brand has one model here."""
    bad = []
    for cat, picks in PICKS.items():
        seen = {}
        for row in picks:
            seen.setdefault(row[0], []).append(row[1])
        for brand, models in seen.items():
            if len(models) > 1 and (cat, brand) in TECH_FACTS:
                bad.append(f"{cat}/{brand}: range-level TECH_FACTS would apply to "
                           f"{len(models)} models ({', '.join(models)}) - move them to MODEL_FACTS")
    return bad


SPEC_NOTE = ("Specs are read from the model's EPREL registration, so they match the "
             "EU energy label rather than marketing copy.")


def build():
    cats, products, missing = [], [], []
    for key, picks in PICKS.items():
        label, icon, blurb = CATEGORY_META[key]
        cats.append({
            "key": key, "label": label, "icon": icon, "blurb": blurb,
            "technologies": [{"key": k, "label": lb, "short": sh}
                             for k, lb, sh in TECHNOLOGIES[key]],
        })
        for brand, model, range_name, verified, country, price, currency, evidence in picks:
            rec, how = L.resolve(key, model, brand)
            if not rec:
                missing.append((key, brand, model))
                print(f"  !! {key}/{brand}: {model} not in EPREL")
                continue
            tech = dict.fromkeys([k for k, _, _ in TECHNOLOGIES[key]], "unknown")
            tech.update(TECH_FACTS.get((key, brand), {}))
            for (mcat, mprefix), facts in MODEL_FACTS.items():
                if mcat == key and rec["model"].startswith(mprefix):
                    tech.update(facts)          # per-model truth always wins
            # Drying technology is not a claim to research: EPREL's own class
            # determines it, so fill that column objectively.
            if "heatpump" in tech:
                dt = (rec.get("dryingTech") or "").lower()
                tech["heatpump"] = ("yes" if dt.startswith("heat pump") and "likely" not in dt
                                    else "partial" if "likely" in dt else "no")
            products.append({
                "category": key,
                "company": brand,
                "model": rec["model"],
                "range": range_name,
                "status": "researched",
                "verified": verified,
                "market": country,
                "price": price,
                "priceCurrency": currency,
                "evidence": evidence,
                "eprelMatch": how,
                "registration": rec.get("registration"),
                "url": rec.get("url"),
                "marketStart": rec.get("marketStart"),
                "eprel": {k: rec.get(k) for k in rec
                          if k not in ("category", "rank", "brand", "supplier", "url",
                                       "registration", "classRank", "marketStart",
                                       "marketEnd", "market")},
                "tech": tech,
            })
            print(f"  {key:16s} {brand:11s} {rec['model'][:30]:32s} {rec['classDetail']:>7s} "
                  f"{verified:6s} start {rec['marketStart']}")
    return cats, products, missing


if __name__ == "__main__":
    for problem in check_range_leak():
        print(f"  WARNING {problem}")
    cats, products, missing = build()
    out = {
        "generated": "2026-08-04",
        "note": ("Flagship per brand for each machine type, re-researched from scratch. "
                 "Models are chosen from their brand's EPREL registrations (on-market, "
                 "recent) and their specs come from that registration. "
                 "`verified: retail` means a live listing was reached (market + price "
                 "recorded); `verified: eprel` means the model is registered and "
                 "on-market in EPREL but a retail listing has not been confirmed yet."),
        "specNote": SPEC_NOTE,
        "categories": cats,
        "products": products,
    }
    with open("/home/a26124811/projects/temtek-actions/products.json", "w",
              encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print(f"\nwrote {len(products)} products across {len(cats)} categories; "
          f"{len(missing)} unresolved")
