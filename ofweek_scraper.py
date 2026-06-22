"""
Standalone HTML scraper for OFweek (维科网) section pages, e.g. the smart-home
portal smarthome.ofweek.com (智能家居网).

Like cheaa, OFweek publishes no RSS. This module fetches its server-rendered
section list pages and returns article entries in the *exact same shape* the
RSS path in ``scraper_w_filter.py`` produces::

    {"source", "title", "date", "url", "summary", "language"}

It is intentionally **self-contained** (it does not import the cheaa scraper)
so the two scrapers are fully independent: a break in one cannot affect the
other or the pipeline.

Design mirrors cheaa_scraper.py:
* **Dependency-free** - standard library only.
* **Fault-isolated** - the public entry point never raises; failures are
  logged and skipped, and whatever was collected is still returned.

Only the main article column (``<div class="detail">`` items) is collected,
excluding the ``<div class="recommend">`` sidebar. OFweek article pages carry
no meta description, so the summary is built from the list page's keyword tags
(falling back to the title), which keeps classification input non-empty without
an extra request per article.
"""

import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

# Article URLs look like: https://smarthome.ofweek.com/2026-06/ART-91009-8420-30690265.html
_ARTICLE_RE = re.compile(r"/\d{4}-\d{2}/ART-[0-9A-Za-z-]+\.html(?:[?#].*)?$")
_DATE_FULL_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATE_URL_RE = re.compile(r"/(\d{4})-(\d{2})/")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_MIN_TITLE_LEN = 6


def _noop(*_args, **_kwargs):
    pass


class _OfweekListParser(HTMLParser):
    """Collect article items from ``<div class="detail">`` blocks.

    Each emitted item is ``(href, title, keywords, blocktext)`` where blocktext
    is all text inside the block (used to recover the publication date).
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._div_depth = 0
        self._detail_depth = None
        self._in_detail = False
        self._cap_title = False
        self._cap_kw = False
        self._href = None
        self._title = []
        self._kw = []
        self._text = []
        self.items = []

    def _reset_item(self):
        self._href = None
        self._title = []
        self._kw = []
        self._text = []
        self._cap_title = False
        self._cap_kw = False

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            self._div_depth += 1
            if not self._in_detail:
                cls = (dict(attrs).get("class") or "").split()
                if "detail" in cls:
                    self._in_detail = True
                    self._detail_depth = self._div_depth
                    self._reset_item()
            return
        if not self._in_detail:
            return
        if tag == "a" and self._href is None:
            href = dict(attrs).get("href") or ""
            if _ARTICLE_RE.search(href):
                self._href = href
                self._cap_title = True
                self._title = []
        elif tag == "span":
            cls = (dict(attrs).get("class") or "").split()
            if "keywords" in cls:
                self._cap_kw = True
                self._kw = []

    def handle_endtag(self, tag):
        if tag == "a" and self._cap_title:
            self._cap_title = False
        elif tag == "span" and self._cap_kw:
            self._cap_kw = False
        elif tag == "div":
            if self._in_detail and self._div_depth == self._detail_depth:
                title = "".join(self._title).strip()
                if self._href and len(title) >= _MIN_TITLE_LEN:
                    self.items.append((
                        self._href, title,
                        "".join(self._kw).strip(),
                        "".join(self._text),
                    ))
                self._in_detail = False
                self._detail_depth = None
            self._div_depth = max(0, self._div_depth - 1)

    def handle_data(self, data):
        if not self._in_detail:
            return
        self._text.append(data)
        if self._cap_title:
            self._title.append(data)
        if self._cap_kw:
            self._kw.append(data)


def _decode(raw, header_charset):
    """Robustly decode bytes. Tries the HTTP header charset, the <meta charset>,
    then UTF-8 and GB18030. Some Chinese sites (e.g. OFweek) send a bogus charset
    like 'gb1323', so we never trust a single declaration."""
    m = re.search(rb'charset=["\']?\s*([\w-]+)', raw[:3000], re.I)
    meta = m.group(1).decode("ascii", "ignore") if m else None
    candidates = []
    for c in (header_charset, meta, "utf-8", "gb18030"):
        if c and c.lower() not in (x.lower() for x in candidates):
            candidates.append(c)
    for c in candidates:
        try:
            return raw.decode(c)  # strict: a wrong codec fails fast
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("gb18030", errors="replace")  # last resort


def _fetch(url, timeout):
    """Return decoded HTML for ``url`` (robust charset detection)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        header_charset = resp.headers.get_content_charset()
    return _decode(raw, header_charset)


def _date_of(block_text, url):
    """Full date from the list item if present, else year-month from the URL."""
    m = _DATE_FULL_RE.search(block_text or "")
    if m:
        return m.group(0)
    m = _DATE_URL_RE.search(url)
    return f"{m.group(1)}-{m.group(2)}" if m else ""


def _scrape_section(section_name, section_url, language, existing_urls,
                    max_items, timeout, log):
    entries = []
    try:
        parser = _OfweekListParser()
        parser.feed(_fetch(section_url, timeout))
    except Exception as e:
        log("error", f"ofweek: failed to fetch/parse {section_name}: {e}")
        return entries

    collected = 0
    for href, title, keywords, block_text in parser.items:
        if collected >= max_items:
            break
        url = urljoin(section_url, href)
        if url in existing_urls:
            continue
        existing_urls.add(url)

        # No meta description available; use keyword tags, fall back to title,
        # so the entry always has non-empty (translation-safe) summary text.
        summary = keywords if keywords else title

        entries.append({
            "source": section_name,
            "title": title,
            "date": _date_of(block_text, url),
            "url": url,
            "summary": summary,
            "language": language,
        })
        collected += 1

    log("success", f"ofweek: {section_name} -> {len(entries)} new article(s)")
    return entries


def scrape_ofweek_sections(sections, language="zh-CN", existing_urls=None,
                           max_per_section=10, timeout=20, log=None):
    """
    Scrape the given OFweek sections and return RSS-shaped article dicts.

    Parameters mirror cheaa_scraper.scrape_cheaa_sections (minus the per-article
    summary fetch, which OFweek does not support). Never raises: on failure it
    returns whatever it collected (possibly empty).
    """
    log = log or _noop
    if existing_urls is None:
        existing_urls = set()
    if not sections:
        return []

    all_entries = []
    try:
        for name, url in sections.items():
            if not url:
                continue
            all_entries.extend(_scrape_section(
                name, url, language, existing_urls, max_per_section, timeout, log,
            ))
    except Exception as e:  # absolute backstop - must not break the pipeline
        log("error", f"ofweek scraper aborted unexpectedly: {e}")

    return all_entries


if __name__ == "__main__":
    def _print_log(level, msg):
        print(f"[{level}] {msg}")

    test_sections = {
        "OFweek SmartHome": "https://smarthome.ofweek.com/",
    }
    results = scrape_ofweek_sections(test_sections, max_per_section=8, log=_print_log)
    print(f"\nTotal collected: {len(results)}\n")
    for r in results:
        print(f"- [{r['source']}] {r['date']}  {r['title'][:50]}")
        print(f"    {r['url']}")
        print(f"    summary: {r['summary'][:80]}")
