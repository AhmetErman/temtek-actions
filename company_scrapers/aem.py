"""Adobe AEM "query index" scraper for newsrooms that publish a JSON index.

Some newsrooms are single-page apps whose article pages carry no server-side
metadata at all — fetching one returns ``<title>Not Found`` and a generic
Open Graph block, so `base.py` has nothing to read. A few of those sites still
publish the index the app itself consumes, as a plain JSON document:

    GET /{locale}/newsroom.json
    {"columns": [...], "data": [{path, title, published, description, ...}],
     "offset": 0, "limit": 7, "total": 7}

That is a better source than HTML scraping would ever be: titles, ISO-8601
publish dates and descriptions arrive already structured, with no parsing.

Used for Hisense (`www.hisense.com`), which publishes one index per locale.
Fault-isolated like every other scraper here: it never raises, and one locale
failing does not cost the others.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from .base import _UA


def _noop(*_a, **_k):
    pass


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _get_json(url, timeout=25):
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def scrape_aem_index(cfg, since="2023-01-01", existing_urls=None,
                     max_articles=200, sleep=0.4, timeout=25, log=None):
    """Read one JSON index per configured locale. Returns normalized records."""
    log = log or _noop
    if existing_urls is None:
        existing_urls = set()

    company = cfg["company"]
    base = cfg["base_url"].rstrip("/")
    template = cfg.get("index_template", "/{locale}/newsroom.json")
    locales = cfg.get("locales") or []
    lang_by_locale = cfg.get("locale_language") or {}
    default_lang = cfg.get("language", "en")

    recs = []
    for locale in locales:
        if len(recs) >= max_articles:
            break
        url = base + template.format(locale=locale)
        # limit is advisory — the index returns `total` rows regardless — but
        # asking for more than the default page keeps one request per locale.
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode({"limit": 500})
        try:
            payload = _get_json(url, timeout)
        except Exception as e:                  # noqa: BLE001 - fault isolation
            log("error", f"{company}: {locale} index failed ({e})")
            continue

        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            log("error", f"{company}: {locale} index has no data array")
            continue

        lang = lang_by_locale.get(locale, default_lang)
        added = skipped_old = 0
        for row in rows:
            if len(recs) >= max_articles:
                break
            path = (row.get("path") or "").strip()
            if not path:
                continue
            link = base + path if path.startswith("/") else path
            if link in existing_urls:
                continue

            # `published` is ISO-8601; `date` is a fallback some rows carry.
            raw = (row.get("published") or row.get("date") or "").strip()
            date = raw[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", raw) else ""
            if date and date < since:
                skipped_old += 1
                continue

            title = _clean(row.get("title"))
            if len(title) < 8:
                continue

            existing_urls.add(link)
            recs.append({
                "company": company,
                "title": title,
                "url": link,
                "date": date,
                "summary": _clean(row.get("description"))[:400],
                "image": (row.get("thumbnail") or "").strip(),
                "language": lang,
                "source_url": url.split("?")[0],
            })
            added += 1

        log("success", f"{company}: {locale} -> +{added} "
                       f"({len(rows)} in index"
                       + (f", {skipped_old} older than {since}" if skipped_old else "")
                       + ")")
        if sleep:
            time.sleep(sleep)

    # Undated rows sort last so the newest articles lead the feed.
    recs.sort(key=lambda r: r.get("date") or "", reverse=True)
    return recs
