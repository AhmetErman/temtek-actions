import os

# --- Scraper & Feed Configuration ---
RSS_SOURCES = {
    "ITmedia": {
        "url": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",
        "language": "ja"
    },
    "Zenn": {
        "url": "https://zenn.dev/feed",
        "language": "ja"
    },
    "36Kr": {
        "url": "https://36kr.com/feed",
        "language": "zh-CN"
    },
    "PingWest": {
        "url": "https://www.pingwest.com/feed",
        "language": "zh-CN"
    }
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
Task: Please classify the given R&D project description or technical text into one of the following categories based on its primary focus. Use the category name as the label.

Categories & Descriptions:

Sustainability & Environmental Impact: Focuses on minimizing the ecological footprint of home appliances. This includes microfiber filtration systems to prevent ocean pollution, technologies for water and energy conservation (e.g., AquaTech), and the use of recycled materials in product components.

Fabric Care & Textile Engineering: Research dedicated to the physical and thermal effects of washing and drying on various textiles (silk, wool, technical fabrics). It covers garment longevity, color preservation, wrinkle reduction (e.g., SteamCure), and mechanical stress analysis on fibers.

Chemical Interaction & Smart Dosing: Studies regarding the synergy between detergents, additives, and machine hardware. This includes automated dosing systems (AutoDose), detergent dissolution efficiency, and the chemical impact of cleaning agents on different fabric types.

Hygiene & Health Technologies: Focuses on sanitization and allergen removal. This category covers high-temperature or steam-based cycles (Hygiene+) designed to eliminate bacteria, viruses, and allergens, as well as odor removal technologies that don't necessarily require water.

IoT & Smart Sensors: Covers the digitalization of home appliances. This includes smart home integration, machine learning algorithms for cycle optimization, sensor development for load sensing, turbidity detection, and noise/vibration control (Unbalanced Load detection).

Other: Choose this category if the text describes general mechanical design, supply chain innovations, structural durability tests, industrial design, or any other R&D activity that does not directly fit into the specific cleaning and textile categories listed above."""
