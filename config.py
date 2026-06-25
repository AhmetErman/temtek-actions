import os

# --- Scraper & Feed Configuration ---
RSS_SOURCES = {
    "ITmedia": {
        "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",
        "language": "ja"
    },
    "36Kr": {
        "url": "https://36kr.com/feed",
        "language": "zh-CN"
    },
    # White-goods specialist (washers/dryers, eco, hygiene cycles, smart appliances) - strongest fit for all categories
    "KadenWatch": {
        "url": "https://kaden.watch.impress.co.jp/data/rss/1.0/kdw/feed.rdf",
        "language": "ja"
    },
    # Senken Shimbun - textile/apparel trade paper, for Fabric Care & Textile Engineering
    "Senken": {
        "url": "https://senken.co.jp/posts/feed.xml",
        "language": "ja"
    }
}

# --- Custom HTML scrapers (for sites that do NOT publish RSS) ---
# cheaa (中国家电网) has no RSS feed, so we scrape its server-rendered section
# pages via cheaa_scraper.py. This is fully optional and fault-isolated: if it
# breaks (markup change, network error, etc.) the rest of the pipeline still
# runs. Set "enabled" to False to turn it off entirely.
CHEAA_SCRAPER = {
    "enabled": True,
    "language": "zh-CN",
    "max_per_section": 10,
    "fetch_summaries": True,   # fetch each article's meta description as summary
    "request_timeout": 20,     # seconds per HTTP request
    "sleep_between": 1.0,      # politeness delay (s) between article fetches
    "sections": {
        # source_name -> section listing URL
        "cheaa (Washer)": "https://washer.cheaa.com/",
        "cheaa (Smart Home)": "https://smarthome.cheaa.com/",
    },
}

# OFweek (维科网) also has no RSS. Same fault-isolated design via ofweek_scraper.py.
# Note: smarthome.ofweek.com skews business/market news (often -> "Other"); add
# more sections (e.g. https://iot.ofweek.com/) here if desired.
OFWEEK_SCRAPER = {
    "enabled": True,
    "language": "zh-CN",
    "max_per_section": 10,
    "request_timeout": 20,
    "sections": {
        "OFweek SmartHome": "https://smarthome.ofweek.com/",
    },
}

TARGET_LANGUAGE = "en"
CLASSIFIED_FILENAME = "tech_news_classified.json"
TRANSLATION_TIMEOUT = 300  # seconds

# --- Gemini API Configuration ---
# Models are ordered by priority (first is preferred, falls back to subsequent models on 503/429 errors)
GEMINI_MODELS = [
    "gemini-3.5-flash", 
    "gemini-3-flash-preview", 
    "gemini-3.1-flash-lite", 
    "gemini-2.5-flash"
]

GEMINI_BATCH_SIZE = 25

SYSTEM_PROMPT = """Classification Prompt
Task: You are classifying home-appliance news from Japan and China, with a focus on laundry (washing machines, dryers, washer-dryers) and related home appliances. Each item may be a news article, a product launch or feature announcement, or an R&D/technical text. Assign the single category that best fits its PRIMARY topic. Classify product and feature news too - not only formal R&D. Use the exact category name (as written below) as the label.

Categories & Descriptions:

Sustainability & Environmental Impact: The main point is an environmental benefit or resource saving. Energy/water efficiency and conservation (eco modes, efficiency ratings/standards, heat-pump drying efficiency), reduced ecological footprint, microfiber/microplastic filtration, recycled or sustainable materials, lower emissions, and recyclability/end-of-life.

Fabric Care & Textile Engineering: How washing/drying treats fabrics and garments. Care for delicates/wool/silk/technical fabrics, gentleness, drum/agitator design for fabric protection, wrinkle/crease reduction, steam refresh, color/shape preservation, garment longevity, and dedicated care programs (e.g., shoes, sportswear, down/bedding). Choose this for washing/drying performance and garment-care features.

Chemical Interaction & Smart Dosing: Detergents, softeners, and additives and how they interact with the machine. Automatic detergent/softener dispensing (auto-dose), dosing accuracy, detergent dissolution and rinsing, and chemistry-related cleaning performance.

Hygiene & Health Technologies: Sanitization and health. Anti-bacterial/anti-viral functions, allergen removal, high-temperature or steam hygiene cycles, sterilization, mold/odor prevention and removal, and self-cleaning for hygiene.

AI, IoT & Smart Sensors: Connectivity and intelligence APPLIED TO HOME APPLIANCES. App/remote control of appliances, smart-home or ecosystem integration, voice-assistant control of appliances, AI/ML cycle optimization and automatic programs, and appliance sensors (load/weight, turbidity/soil, fabric type, water level, vibration/noise detection). IMPORTANT: this category is only for AI/IoT/sensors built into or controlling home appliances. General AI/LLM/chatbot products, software development, cloud services, smartphones or operating systems, cybersecurity, and AI business/finance news do NOT belong here - classify those as Other.

Other: The primary topic is NOT one of the categories above. This includes corporate/financial news (earnings, M&A, partnerships with no specific product feature), retail/store openings, sales and promotions, macro policy and regulations, pure marketing/branding without a concrete feature, purely aesthetic/industrial design with no functional benefit, non-appliance topics, and general technology unrelated to home appliances - including general AI/LLM/chatbot products and announcements, software development, cloud computing, smartphones and operating systems, cybersecurity, fintech, and gaming.

Classification rules:
- Choose exactly ONE category - the PRIMARY focus.
- If the item describes a concrete appliance feature or capability, prefer the matching feature category over Other.
- Use Other for business, retail, policy, and generic marketing items even when they mention an appliance brand or product.
- Always use the exact category names above, including "Other"."""

# --- Layer-2: dynamic (unsupervised) subclassification of the "Other" bucket ---
# The fixed taxonomy above is never changed. Everything that lands in "Other" is
# passed to a SECOND Gemini pass (dynamic_subclassifier.py) that groups those
# items into reusable sub-topics it discovers on its own (e.g. "Generative AI",
# "Gaming"). Discovered sub-classes are stored in `store_file` and re-injected
# into the prompt below on every run, so the sub-taxonomy under "Other" GROWS
# over time without affecting the normal classes. Set "enabled" to False to skip.
DYNAMIC_SUBCLASS = {
    "enabled": True,
    "store_file": "dynamic_classes.json",
    "batch_size": 25,
    "base_instruction": """You are organizing the "Other" bucket of a home-appliance (laundry-focused) news classifier. Every item you receive was already judged NOT to be about a home-appliance feature, so these are general or off-topic news items - for example: general AI/software, smartphones and consumer electronics, gaming, sports, entertainment/media, finance and markets, automotive/EV, semiconductors, cybersecurity, social media, or policy.

Your job is to organize these items into specific, REUSABLE sub-topics so the opaque "Other" bucket becomes a structured sub-taxonomy.

Rules:
- You are given a list of EXISTING SUB-CLASSES with descriptions. For each news item, FIRST try to fit it into an existing sub-class and reuse its EXACT name. Strongly prefer reusing an existing sub-class over inventing a new one.
- Only if no existing sub-class reasonably fits, create ONE new sub-class: a concise name (1-3 words, Title Case) plus a one-sentence description. Make new sub-classes general enough to apply to many future articles - never about a single company or a one-off event.
- Set IsNew=true ONLY when you introduce a sub-class that is not already in the existing list; otherwise set IsNew=false and reuse the existing name verbatim.
- Assign RelationScore from 1 to 5 for how well the item fits its sub-class.
- Every item must receive exactly one sub-class. Never use "Other" as a sub-class name. Return every NewsIndex you were given.""",
}

# --- Weekly Teams trend digest (teams_digest.py) ---
# One-way digest posted to a Teams channel through a Power Automate "Workflows"
# webhook. Only posts RELEVANT items: a real (non-excluded) class with
# RelationScore >= min_relation_score. The webhook URL is read from the env var
# named below (a GitHub Actions secret) and must never be committed.
TEAMS_DIGEST = {
    "enabled": True,
    "webhook_env": "TEAMS_WEBHOOK_URL",
    "state_file": "teams_digest_state.json",
    "min_relation_score": 3,
    "max_items": 6,
    "exclude_categories": ["Other"],
    "title": "Weekly Tech News",
    "footer": "You can visit [https://temtek-actions.onrender.com/](https://temtek-actions.onrender.com/) for more…",
    "request_timeout": 20,
}
