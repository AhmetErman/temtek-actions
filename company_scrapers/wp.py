"""
WordPress REST API scraper for newsrooms built on WordPress.

Some companies block plain HTML scraping or render listings via JS, but still
expose the standard WP REST API (/wp-json/wp/v2/posts), which returns clean
JSON: title, date, excerpt, link and (with _embed) the featured image. This is
the cleanest possible source and reaches back to 2023 via simple pagination.

Used for Haier (corporate.haier-europe.com) and reusable for any WP newsroom.
Fault-isolated: never raises.
"""
import re
import json
import time
import html as _html
import urllib.request
from urllib.parse import urlencode

from .base import _UA


def _noop(*_a, **_k):
    pass


def _strip(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _get_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def scrape_wordpress(cfg, since="2023-01-01", existing_urls=None,
                     max_articles=200, per_page=50, max_pages=20,
                     sleep=0.3, timeout=25, log=None):
    """Scrape a WordPress newsroom via the REST API. Returns normalized records."""
    log = log or _noop
    if existing_urls is None:
        existing_urls = set()
    company = cfg["company"]
    lang = cfg.get("language", "en")
    api = cfg["api_url"]
    recs = []
    collected = 0
    try:
        for page in range(1, max_pages + 1):
            sep = "&" if "?" in api else "?"
            url = api + sep + urlencode({"per_page": per_page, "page": page,
                                         "_embed": "wp:featuredmedia",
                                         "orderby": "date", "order": "desc"})
            try:
                posts = _get_json(url, timeout)
            except Exception as e:
                # WP returns HTTP 400 once page > total pages -> normal stop.
                log("info", f"{company}: WP page {page} stop ({e})")
                break
            if not isinstance(posts, list) or not posts:
                break
            new_here = 0
            stop = False
            for p in posts:
                if collected >= max_articles:
                    stop = True
                    break
                link = (p.get("link") or "").split("#")[0]
                if not link or link in existing_urls:
                    continue
                existing_urls.add(link)
                date = (p.get("date") or "")[:10]
                if date and date < since:
                    stop = True
                    continue
                title = _strip((p.get("title") or {}).get("rendered"))
                if len(title) < 8:
                    continue
                summary = _strip((p.get("excerpt") or {}).get("rendered"))[:400]
                img = ""
                emb = (p.get("_embedded") or {}).get("wp:featuredmedia")
                if isinstance(emb, list) and emb and isinstance(emb[0], dict):
                    img = emb[0].get("source_url", "") or ""
                recs.append({"company": company, "title": title, "url": link,
                             "date": date, "summary": summary, "image": img,
                             "language": lang, "source_url": api})
                collected += 1
                new_here += 1
            log("success", f"{company}: WP page {page} -> +{new_here} "
                           f"(total {collected})")
            if sleep:
                time.sleep(sleep)
            if stop or collected >= max_articles or new_here == 0:
                break
    except Exception as e:
        log("error", f"{company}: WP scraper aborted: {e}")
    return recs
