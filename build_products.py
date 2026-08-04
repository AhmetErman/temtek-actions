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
        ("Bosch",      "WGB256A2GB",   "Series 8 i-DOS",           "retail", "UK", 1149,
         "John Lewis / Marks Electrical / Appliances Direct (GBP 999)"),
        ("LG",         "F4X9009TBC",   "Series 9 AI DD (VX90)",    "retail", "UK", None,
         "lg.com/uk; in stock at Marks Electrical, ao.com, Hughes, Appliance City"),
        ("Samsung",    "WF90F09C4S",   "Series 9 Bespoke AI",      "retail", "UK", None,
         "samsung.com/uk product page live (SKU WF90F09C4SU1)"),
        ("Beko",       "B5W5941BD",    "AutoDose SteamCure",       "retail", "UK", None,
         "beko.co.uk product page live"),
        ("Haier",      "HW100-B14397EU1", "I-Pro Series 7",        "retail", "NL", None,
         "coolblue.nl lists the HW100-BD14397U1S variant"),
        ("Electrolux", "EW9F5417SWCE", "900 series AutoDose",      "eprel",  None, None, None),
        ("Whirlpool",  "W0M 912G ADS FR", "W Collection AutoDose", "eprel",  None, None, None),
        ("Midea",      "MF205W90BA50/T-IT", "MF205 series",        "eprel",  None, None, None),
    ],
    "washer-dryer": [
        ("LG",         "F164HP2BST",   "Heat-pump washer-dryer",   "eprel",  None, None, None),
        ("Haier",      "HWD180-BD12LGNU1", "I-Pro Series 8 11kg",  "eprel",  None, None, None),
        ("Electrolux", "EW9W1165RB",   "900 series SteamCare",     "eprel",  None, None, None),
        ("Beko",       "B7DFT61041W",  "AutoDose washer-dryer",    "eprel",  None, None, None),
        ("Whirlpool",  "BWT 106A3C BC", "6th Sense washer-dryer",  "eprel",  None, None, None),
        ("Bosch",      "WNG24401BY",   "Series 6 washer-dryer",    "eprel",  None, None, None),
        ("Samsung",    "WD10HG6U34BB", "Series 6 washer-dryer",    "eprel",  None, None, None),
        ("Midea",      "MF205D80BA/W-ES", "MF205 washer-dryer",    "eprel",  None, None, None),
    ],
    "dryer": [
        ("Electrolux", "EW9H48A",      "900 series heat-pump",     "eprel",  None, None, None),
        ("Samsung",    "DV90DB7845GB", "Bespoke AI heat-pump",     "retail", "UK", None,
         "samsung.com/uk support page live for SKU DV90DB7845GBU3"),
        ("Whirlpool",  "C WD R47M WBS IT", "Supreme Silence heat-pump", "eprel", None, None, None),
        ("LG",         "RH9X76BM",     "Dual Inverter heat-pump",  "eprel",  None, None, None),
        ("Bosch",      "WQB246D41",    "Series 8 heat-pump",       "eprel",  None, None, None),
        ("Midea",      "MD20EH80WB-A3", "MD20 heat-pump",          "eprel",  None, None, None),
        ("Haier",      "HD90-CQ387U1", "I-Pro Series 3",           "eprel",  None, None, None),
        ("Beko",       "BM3T38220X",   "BM3T heat-pump",           "eprel",  None, None, None),
    ],
    "dishwasher": [
        ("Whirlpool",  "WH5IA5015BT1LS", "MaxiSpace 15ps",         "eprel",  None, None, None),
        ("Samsung",    "DW80H77H3B0",  "Bespoke AI dishwasher",    "eprel",  None, None, None),
        ("LG",         "DB597TXSN",    "TrueSteam QuadWash",       "eprel",  None, None, None),
        ("Electrolux", "E82IX220ST",   "800 GlassCare",            "eprel",  None, None, None),
        ("Bosch",      "SBD6ECX21E",   "Series 6 dishwasher",      "eprel",  None, None, None),
        ("Beko",       "BDIN38560WPF", "AutoDose 15ps",            "eprel",  None, None, None),
        ("Haier",      "XF 4A4M0W-80", "XF Series 4",              "eprel",  None, None, None),
        ("Midea",      "MDWEB1403M(B)-WA-UK", "MDWEB1403",         "eprel",  None, None, None),
    ],
}

# Technology support confirmed from brand/retailer sources during research.
# Anything absent stays "unknown" and renders as "?" — never guessed.
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
    ("washing-machine", "Haier"):      {"directdrive": "yes", "steam": "yes", "ai": "partial",
                                        "autodose": "no"},
    ("washing-machine", "Whirlpool"):  {"autodose": "yes", "ai": "partial", "steam": "yes"},
    ("dryer", "Samsung"):              {"heatpump": "yes", "ai": "yes", "wifi": "yes"},
    ("washer-dryer", "LG"):            {"heatpump": "yes", "directdrive": "yes", "steam": "yes"},
    ("washer-dryer", "Haier"):         {"heatpump": "yes", "directdrive": "yes"},
}

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
        for brand, model, range_name, verified, country, price, evidence in picks:
            rec, how = L.resolve(key, model, brand)
            if not rec:
                missing.append((key, brand, model))
                print(f"  !! {key}/{brand}: {model} not in EPREL")
                continue
            tech = dict.fromkeys([k for k, _, _ in TECHNOLOGIES[key]], "unknown")
            tech.update(TECH_FACTS.get((key, brand), {}))
            products.append({
                "category": key,
                "company": brand,
                "model": rec["model"],
                "range": range_name,
                "status": "researched",
                "verified": verified,
                "market": country,
                "price": price,
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
