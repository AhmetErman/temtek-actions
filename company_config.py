"""
Configuration for the home-appliance company news tracker.

Each entry drives company_scrapers.base.scrape_company():
  - list_url_template : listing URL with a {page} placeholder for pagination
  - article_url_re    : regex identifying an article URL on the listing
  - exclude_re        : optional regex to drop nav/category links
  - language          : article language
  - enabled           : Phase-1 (server-rendered, full meta) vs Phase-2

Phase-1 companies have server-rendered listings AND article pages with Open
Graph / JSON-LD metadata, so they yield clean date/title/summary/image with the
current tools. Phase-2 companies are JS-rendered or bot-protected (no server
meta) and need API discovery / a headless browser - see PHASE2_NOTES.
"""

COMPANY_NEWS_FILE = "company_news.json"
COMPANY_ANALYSIS_FILE = "company_analysis.json"
BACKFILL_SINCE = "2023-01-01"

COMPANIES = {
    "Samsung": {
        "company": "Samsung",
        "language": "en",
        "enabled": True,
        "list_url_template": "https://news.samsung.com/global/category/products/home-appliances/page/{page}",
        "article_url_re": r"https://news\.samsung\.com/global/[a-z0-9\-]{12,}$",
        "exclude_re": r"/global/(category|tag|author|select-newsroom)|/medialibrary",
    },
    "BSH (Bosch/Siemens)": {
        "company": "BSH (Bosch/Siemens)",
        "language": "en",
        "enabled": True,
        "list_url_template": "https://press.bsh-group.com/blog_posts?page={page}",
        "article_url_re": r"https://press\.bsh-group\.com/blog_posts/[a-z0-9\-]{6,}$",
        "exclude_re": r"/blog_posts/tag/",
    },
    "Whirlpool": {
        "company": "Whirlpool",
        "language": "en",
        "enabled": True,
        "list_url_template": "https://whirlpool.mediaroom.com/?page={page}",
        "article_url_re": r"https://whirlpool\.mediaroom\.com/20\d\d-\d\d-\d\d-[A-Za-z0-9\-]+$",
    },
    "Midea": {
        "company": "Midea",
        "language": "en",
        "enabled": True,
        "list_url_template": "https://www.midea.com/global/news?page={page}",
        "article_url_re": r"https://www\.midea\.com/global/news/[a-z0-9\-]{8,}$",
    },
    # --- Phase 2: JS-rendered / bot-protected (no server-side meta) ---
    "Beko (Arçelik)": {
        "company": "Beko (Arçelik)",
        "language": "en",
        "enabled": False,
        "list_url_template": "https://www.bekocorporate.com/company/press-room/press-releases/?page={page}",
        "article_url_re": r"https://www\.bekocorporate\.com/company/press-room/press-releases/[a-z0-9\-]{6,}$",
    },
    "Electrolux": {
        "company": "Electrolux",
        "language": "en",
        "enabled": False,
        "list_url_template": "https://www.electroluxgroup.com/en/category/newsroom/press-releases/page/{page}/",
        "article_url_re": r"https://www\.electroluxgroup\.com/en/[a-z0-9\-]{12,}/$",
        "exclude_re": r"/en/category/",
    },
    # Haier Europe is WordPress: its HTML listing is JS-rendered, but the REST
    # API serves clean JSON back to 2023 -> scrapable with current tools.
    "Haier": {
        "company": "Haier",
        "language": "en",
        "enabled": True,
        "type": "wordpress",
        "api_url": "https://corporate.haier-europe.com/wp-json/wp/v2/posts",
    },
    "LG": {
        "company": "LG",
        "language": "en",
        "enabled": False,
        "list_url_template": "https://www.lg.com/global/newsroom/news/home-appliance-solution/?page={page}",
        "article_url_re": r"https://www\.lg\.com/global/newsroom/[a-z0-9\-]{8,}$",
    },
}

PHASE2_NOTES = {
    "Beko (Arçelik)": "Article pages JS-rendered (no OG/JSON-LD); listing has day+month only.",
    "Electrolux": "Listing times out / blocks the runner IP; retry via API or browser.",
    "Haier": "Listing article links injected via JS; only nav present server-side.",
    "LG": "JS-rendered + bot-protected (Akamai); plain fetch returns a stub.",
}


def enabled_companies():
    return {k: v for k, v in COMPANIES.items() if v.get("enabled")}
