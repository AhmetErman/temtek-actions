"""
Configuration for the EPREL product database (eprel_scraper.py).

EPREL is the EU's public product registry. Its read API is unauthenticated but
only responds to browser-like headers, has no working server-side sort/filter,
and caps `_limit` at 100 — so the scraper simply pages through a whole product
group, dedupes, ranks locally and keeps the best `TOP_N`.

Each entry below is data-driven, in the same style as company_config.py:
  - group        : EPREL product-group slug (the API path segment)
  - class_scale  : which energy-class ladder applies (see CLASS_ORDER)
  - eei_bounds   : upper EEI bound per class, used to refine "A" into "A-30%"
                   (how far below the class ceiling the model actually sits)
  - fields       : output key -> EPREL API field name
  - columns      : the benchmark table rendered on /products, in order
  - enabled      : skip a group without deleting its definition

`sort` names the output keys used to rank a category: energy class first, then
weighted energy consumption (ascending — lower is better).
"""

API_BASE = "https://eprel.ec.europa.eu/api/products/"
PRODUCT_URL = "https://eprel.ec.europa.eu/screen/product/{group}/{registration}"
OUTPUT_FILE = "eprel_products.json"

# EPREL rejects requests without a browser-ish User-Agent (HTTP 403).
REQUEST_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://eprel.ec.europa.eu/screen/home",
}

PAGE_SIZE = 100          # API silently falls back to 25 above this
REQUEST_TIMEOUT = 45     # seconds
SLEEP_BETWEEN = 0.35     # politeness delay between pages
MAX_RETRIES = 4          # per page; EPREL answers 403 when it rate-limits
TOP_N = 1000             # best models kept per category

# Energy-class ladders, best first. "APPP" etc. are EPREL's spelling of A+++.
CLASS_ORDER = {
    "A_G": ["A", "B", "C", "D", "E", "F", "G"],
    "APPP_D": ["APPP", "APP", "AP", "A", "B", "C", "D"],
}

# Display names for the pre-2021 ladder.
CLASS_LABELS = {"APPP": "A+++", "APP": "A++", "AP": "A+"}

# One brand registers under many supplier/trademark spellings. Keys are matched
# lowercased, either exactly or as a leading word ("lg electronics inc." matches
# "lg electronics"). Longest-prefix wins is NOT applied — keep keys unambiguous.
BRAND_ALIASES = {
    "lg": "LG", "lg electronics": "LG",
    "samsung": "Samsung", "samsung electronics": "Samsung",
    "bosch": "Bosch", "robert bosch": "Bosch",
    "siemens": "Siemens",
    "neff": "Neff", "gaggenau": "Gaggenau", "constructa": "Constructa",
    "balay": "Balay", "profilo": "Profilo",
    "beko": "Beko", "arcelik": "Arçelik", "arçelik": "Arçelik",
    "grundig": "Grundig", "blomberg": "Blomberg", "altus": "Altus",
    "electrolux": "Electrolux", "aeg": "AEG", "zanussi": "Zanussi",
    "haier": "Haier", "candy": "Candy", "hoover": "Hoover",
    "whirlpool": "Whirlpool", "indesit": "Indesit", "hotpoint": "Hotpoint",
    "hotpoint/ariston": "Hotpoint/Ariston", "ariston": "Hotpoint/Ariston",
    "midea": "Midea", "toshiba": "Toshiba", "comfee": "Comfee",
    "hisense": "Hisense", "gorenje": "Gorenje", "sharp": "Sharp",
    "panasonic": "Panasonic", "miele": "Miele", "smeg": "Smeg",
    "vestel": "Vestel", "tcl": "TCL", "xiaomi": "Xiaomi", "mijia": "Xiaomi",
    "amica": "Amica", "hansa": "Hansa", "teka": "Teka", "fagor": "Fagor",
    "bauknecht": "Bauknecht", "ignis": "Ignis", "privileg": "Privileg",
    "asko": "Asko", "v-zug": "V-ZUG", "liebherr": "Liebherr",
    "infiniton": "Infiniton", "chiq": "CHiQ", "svan": "Svan",
    "franke": "Franke", "kuppersbusch": "Küppersbusch", "küppersbusch": "Küppersbusch",
}

# The brands this project actively tracks elsewhere (company_config.py /
# products.json), as canonical names. The dashboard offers a "tracked brands
# only" filter built from this list.
TRACKED_BRANDS = ["Samsung", "LG", "Bosch", "Siemens", "Electrolux", "AEG",
                  "Beko", "Arçelik", "Grundig", "Haier", "Candy", "Hoover",
                  "Whirlpool", "Hotpoint", "Indesit", "Midea", "Toshiba"]

# Legal-form and filler words stripped from untracked brand names.
BRAND_SUFFIXES = [
    "inc", "ltd", "limited", "llc", "gmbh", "co", "co ltd", "corp",
    "corporation", "s p a", "spa", "sa", "s a", "srl", "s r l", "bv", "b v",
    "nv", "n v", "as", "a s", "oy", "ab", "kft", "sp z o o", "d o o",
    "group", "europe", "international", "appliances", "appliance",
    "home appliances", "electronics", "electrical", "deutschland", "germany",
    "italia", "france", "espana", "españa", "polska", "hausgeraete",
    "hausgeräte", "trading", "technology", "technologies", "industries",
]


def _col(key, label, type="text", unit=None):
    c = {"key": key, "label": label, "type": type}
    if unit:
        c["unit"] = unit
    return c


CATEGORIES = {
    "washing-machine": {
        "label": "Washing Machines",
        "group": "washingmachines2019",
        "enabled": True,
        "regulation": "EU 2019/2014",
        "class_scale": "A_G",
        "energy_note": "Weighted energy consumption of the eco 40-60 programme, kWh per 100 cycles.",
        # EU 2019/2014 Annex II, washing: EEI upper bound per class.
        "eei_bounds": {"A": 52, "B": 60, "C": 69, "D": 80, "E": 91, "F": 102},
        "sort": ["energyClass", "energy100"],
        "fields": {
            "marketStartTS": "onMarketStartDateTS",
            "marketEndTS": "onMarketEndDateTS",
            "energyClass": "energyClass",
            "eei": "energyEfficiencyIndex",
            "energy100": "energyConsPer100Cycle",
            "capacity": "ratedCapacity",
            "spin": "spinSpeedRated",
            "spinClass": "spinClass",
            "water": "waterCons",
            "programTime": "programmeDurationRated",
            "noise": "noise",
            "noiseClass": "noiseClass",
            "design": "type",
            "smart": "isEnergySmartAppliance",
            # EPREL moved this measurement to a *V2 field and left the original null.
            "washIndex": ["washingEfficiencyIndexV2", "washingEfficiencyIndex"],
        },
        "columns": [
            _col("brand", "Brand"),
            _col("model", "Model"),
            _col("design", "Installation"),
            _col("capacity", "Capacity", "num", "kg"),
            _col("classDetail", "Energy Class", "class"),
            _col("eei", "EEI", "num"),
            _col("energy100", "Energy", "num", "kWh/100"),
            _col("programTimeText", "Eco Programme Time", "text"),
            _col("water", "Water", "num", "L/cycle"),
            _col("spin", "Spin Speed", "num", "rpm"),
            _col("spinClass", "Spin Class", "text"),
            _col("washIndex", "Wash Index", "num"),
            _col("noise", "Noise", "num", "dB"),
            _col("noiseClass", "Noise Class", "text"),
            _col("marketStart", "On Market Since", "text"),
            _col("url", "EPREL", "link"),
        ],
    },
    "washer-dryer": {
        "label": "Washer-Dryers",
        "group": "washerdriers2019",
        "enabled": True,
        "regulation": "EU 2019/2014",
        "class_scale": "A_G",
        "energy_note": "Weighted energy consumption of the full wash-and-dry cycle, kWh per 100 cycles.",
        # Wash&Dry bounds differ from the wash-only bounds; both are used below.
        "eei_bounds": {"A": 37, "B": 52, "C": 69, "D": 86, "E": 103, "F": 120},
        "eei_bounds_secondary": {"A": 52, "B": 60, "C": 69, "D": 80, "E": 91, "F": 102},
        "sort": ["energyClass", "energy100"],
        "drying_tech_from_class": True,
        "fields": {
            "marketStartTS": "onMarketStartDateTS",
            "marketEndTS": "onMarketEndDateTS",
            "energyClass": "energyClassWashAndDry",
            "eei": "energyEfficiencyIndexWashAndDry",
            "energy100": "energyConsumption100WashAndDry",
            "capacity": "ratedCapacityWashAndDry",
            "water": "waterConsumptionWashAndDry",
            "programTime": "programDurationRatedWashAndDry",
            "energyClassWash": "energyClassWash",
            "eeiWash": "energyEfficiencyIndexWash",
            "energy100Wash": "energyConsumption100Wash",
            "capacityWash": "ratedCapacityWash",
            "waterWash": "waterConsumptionWash",
            "spin": "spinSpeedRated",
            "spinClass": "spinClass",
            "noise": "noise",
            "noiseClass": "noiseClass",
            "design": "designType",
        },
        "columns": [
            _col("brand", "Brand"),
            _col("dryingTech", "Drying Technology (est.)"),
            _col("model", "Model"),
            _col("capacity", "Capacity Wash-Dry", "num", "kg"),
            _col("classDetail", "Energy Class (Wash & Dry)", "class"),
            _col("eei", "EEI (Wash & Dry)", "num"),
            _col("energy100", "Energy (W&D)", "num", "kWh/100"),
            _col("programTimeText", "Eco Programme Time W&D", "text"),
            _col("water", "Water Wash & Dry", "num", "L/cycle"),
            _col("capacityWash", "Capacity Wash", "num", "kg"),
            _col("classDetailWash", "Energy Class (Wash)", "class"),
            _col("eeiWash", "EEI (Wash)", "num"),
            _col("spin", "Spin Speed", "num", "rpm"),
            _col("waterWash", "Water Wash", "num", "L/cycle"),
            _col("marketStart", "On Market Since", "text"),
            _col("url", "EPREL", "link"),
        ],
    },
    "dryer": {
        "label": "Dryers",
        "group": "tumbledriers",
        "enabled": True,
        # Tumble dryers still sit under the old regulation, so the class ladder
        # is A+++..D and the headline energy figure is annual, not per 100 cycles.
        "regulation": "EU 392/2012",
        "class_scale": "APPP_D",
        "energy_note": "Weighted annual energy consumption (kWh/year) for the standard cotton programme.",
        "eei_bounds": {},
        "sort": ["energyClass", "energyAnnual"],
        "fields": {
            "marketStartTS": "onMarketStartDateTS",
            "marketEndTS": "onMarketEndDateTS",
            "energyClass": "energyClass",
            "energyAnnual": "weightedEnergyAnnual",
            "capacity": "capacityCotton",
            "dryerType": "type",
            "condensationClass": "condensationEnergyClass",
            "condensationEff": "weightedCondensationEfficiency",
            "programTime": "weightedProgrammeTime",
            "noise": "noise",
            "autoDry": "automaticDryingProcess",
            "builtIn": "builtIn",
            "energyFull": "energyConsELEFL",
            "energyPartial": "energyConsELEPL",
        },
        "columns": [
            _col("brand", "Brand"),
            _col("dryingTech", "Drying Technology (est.)"),
            _col("model", "Model"),
            _col("capacity", "Capacity", "num", "kg"),
            _col("classDetail", "Energy Class", "class"),
            _col("energyAnnual", "Energy", "num", "kWh/year"),
            _col("energyFull", "Energy Full Load", "num", "kWh"),
            _col("programTimeText", "Weighted Programme Time", "text"),
            _col("condensationClass", "Condensation Class", "text"),
            _col("noise", "Noise", "num", "dB"),
            _col("autoDry", "Auto-dry", "bool"),
            _col("marketStart", "On Market Since", "text"),
            _col("url", "EPREL", "link"),
        ],
    },
    "dishwasher": {
        "label": "Dishwashers",
        "group": "dishwashers2019",
        "enabled": True,
        "regulation": "EU 2019/2017",
        "class_scale": "A_G",
        "energy_note": "Weighted energy consumption of the eco programme, kWh per 100 cycles.",
        # EU 2019/2017 Annex II: EEI upper bound per class.
        "eei_bounds": {"A": 32, "B": 38, "C": 44, "D": 50, "E": 56, "F": 62},
        "sort": ["energyClass", "energy100"],
        "fields": {
            "marketStartTS": "onMarketStartDateTS",
            "marketEndTS": "onMarketEndDateTS",
            "energyClass": "energyClass",
            "eei": "energyEfficiencyIndex",
            "energy100": "energyCons100",
            "capacity": "ratedCapacity",
            "water": "waterCons",
            "programTime": "programmeDuration",
            "noise": "noise",
            "noiseClass": "noiseClass",
            # The original fields are only filled on ~15% of registrations; the
            # *V2 successors on ~95%. Try V2 first, fall back to the original.
            "cleaningIndex": ["cleaningPerformanceIndexV2", "cleaningPerformanceIndex"],
            "dryingIndex": ["dryingPerformanceIndexV2", "dryingPerformanceIndex"],
            "design": "type",
        },
        "columns": [
            _col("brand", "Brand"),
            _col("model", "Model"),
            _col("design", "Installation"),
            _col("capacity", "Place Settings", "num"),
            _col("classDetail", "Energy Class", "class"),
            _col("eei", "EEI", "num"),
            _col("energy100", "Energy", "num", "kWh/100"),
            _col("programTimeText", "Eco Programme Time", "text"),
            _col("water", "Water", "num", "L/cycle"),
            _col("cleaningIndex", "Cleaning Index", "num"),
            _col("dryingIndex", "Drying Index", "num"),
            _col("noise", "Noise", "num", "dB"),
            _col("noiseClass", "Noise Class", "text"),
            _col("marketStart", "On Market Since", "text"),
            _col("url", "EPREL", "link"),
        ],
    },
}


def enabled_categories():
    return {k: v for k, v in CATEGORIES.items() if v.get("enabled")}
