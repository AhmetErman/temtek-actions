"""
Standalone HTML scraper for 中国家电网 (cheaa.com) section pages.

cheaa does not publish RSS, so this module fetches its server-rendered
section pages (e.g. 洗衣机 / 智能家居) and returns article entries in the
*exact same shape* the RSS path in ``scraper_w_filter.py`` produces::

    {"source", "title", "date", "url", "summary", "language"}

Design goals
------------
* **Dependency-free** - uses only the Python standard library, so it adds no
  new failure modes to the pipeline and behaves identically locally and in CI.
* **Fault-isolated** - the public entry point never raises. A broken section,
  a markup change, a network error or a single bad article is swallowed and
  logged; whatever was successfully collected is still returned. If everything
  fails it returns an empty list, and the rest of the pipeline keeps running.

Only anchors inside the main content column (``<div class="mainC">``) are
collected, which excludes the cross-category "hot/recommended" sidebar.
"""

import re
import time
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

# Article URLs look like: https://<sub>.cheaa.com/2026/0602/655299.shtml
_ARTICLE_RE = re.compile(r"/\d{4}/\d{4}/\d+\.s?html(?:[?#].*)?$")
_DATE_RE = re.compile(r"/(\d{4})/(\d{2})(\d{2})/")
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_MIN_TITLE_LEN = 6  # skips image-only anchors which carry no text


def _noop(*_args, **_kwargs):
    pass


class _CheaaListParser(HTMLParser):
    """Collect ``(href, title)`` anchors found inside ``<div class="mainC">``."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._div_depth = 0
        self._main_depth = None      # div-depth at which mainC opened
        self._in_main = False
        self._capturing = False
        self._cur_href = None
        self._buf = []
        self.items = []              # list of (href, title)

    def handle_starttag(self, tag, attrs):
        if tag == "div":
            self._div_depth += 1
            if not self._in_main:
                cls = (dict(attrs).get("class") or "").split()
                if "mainC" in cls:
                    self._in_main = True
                    self._main_depth = self._div_depth
        elif tag == "a" and self._in_main and not self._capturing:
            href = dict(attrs).get("href") or ""
            if _ARTICLE_RE.search(href):
                self._capturing = True
                self._cur_href = href
                self._buf = []

    def handle_endtag(self, tag):
        if tag == "a" and self._capturing:
            title = "".join(self._buf).strip()
            if self._cur_href and len(title) >= _MIN_TITLE_LEN:
                self.items.append((self._cur_href, title))
            self._capturing = False
            self._cur_href = None
            self._buf = []
        elif tag == "div":
            if self._in_main and self._div_depth == self._main_depth:
                self._in_main = False
                self._main_depth = None
            self._div_depth = max(0, self._div_depth - 1)

    def handle_data(self, data):
        if self._capturing:
            self._buf.append(data)


class _MetaDescParser(HTMLParser):
    """Pull the ``<meta name="description">`` content from an article page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.description = ""

    def handle_starttag(self, tag, attrs):
        if tag != "meta" or self.description:
            return
        d = {k.lower(): (v or "") for k, v in attrs}
        if d.get("name", "").lower() == "description":
            self.description = d.get("content", "").strip()


def _decode(raw, header_charset):
    """Robustly decode bytes. Tries the HTTP header charset, the <meta charset>,
    then UTF-8 and GB18030. Some Chinese sites send a bogus/typo charset, so we
    never trust a single declaration."""
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
    return raw.decode("utf-8", errors="replace")  # last resort


def _fetch(url, timeout):
    """Return decoded HTML for ``url`` (robust charset detection)."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        header_charset = resp.headers.get_content_charset()
    return _decode(raw, header_charset)


def _date_from_url(url):
    """Derive an ISO date (YYYY-MM-DD) from the article URL path."""
    m = _DATE_RE.search(url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def _fetch_summary(url, timeout):
    """Best-effort article summary from its meta description. Never raises."""
    try:
        parser = _MetaDescParser()
        parser.feed(_fetch(url, timeout))
        return parser.description
    except Exception:
        return ""


def _scrape_section(section_name, section_url, language, existing_urls,
                    max_items, fetch_summaries, timeout, sleep_between, log):
    """Scrape a single section. Returns a list of entry dicts (may be empty)."""
    entries = []
    try:
        parser = _CheaaListParser()
        parser.feed(_fetch(section_url, timeout))
    except Exception as e:
        log("error", f"cheaa: failed to fetch/parse {section_name}: {e}")
        return entries

    collected = 0
    for href, title in parser.items:
        if collected >= max_items:
            break
        url = urljoin(section_url, href)
        if url in existing_urls:
            continue
        existing_urls.add(url)  # dedup within this run too

        summary = ""
        if fetch_summaries:
            summary = _fetch_summary(url, timeout)
            if sleep_between:
                time.sleep(sleep_between)  # be polite between article hits
        # deep_translator chokes on empty strings; fall back to the title.
        if not summary:
            summary = title

        entries.append({
            "source": section_name,
            "title": title,
            "date": _date_from_url(url),
            "url": url,
            "summary": summary,
            "language": language,
        })
        collected += 1

    log("success", f"cheaa: {section_name} -> {len(entries)} new article(s)")
    return entries


def scrape_cheaa_sections(sections, language="zh-CN", existing_urls=None,
                          max_per_section=10, fetch_summaries=True,
                          timeout=20, sleep_between=1.0, log=None):
    """
    Scrape the given cheaa sections and return RSS-shaped article dicts.

    Parameters
    ----------
    sections : dict[str, str]
        Mapping of ``source_name -> section_url``.
    existing_urls : set or None
        URLs already known to the pipeline; matching articles are skipped and
        newly seen URLs are added to this set (mutated in place).
    log : callable or None
        ``log(level, message)`` callback (level in success/warning/error).

    This function never raises: on any failure it returns whatever it managed
    to collect (possibly an empty list).
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
                name, url, language, existing_urls,
                max_per_section, fetch_summaries, timeout, sleep_between, log,
            ))
    except Exception as e:  # absolute backstop - must not break the pipeline
        log("error", f"cheaa scraper aborted unexpectedly: {e}")

    return all_entries


if __name__ == "__main__":
    # Standalone smoke test.
    def _print_log(level, msg):
        print(f"[{level}] {msg}")

    test_sections = {
        "cheaa-Washer": "https://washer.cheaa.com/",
        "cheaa-SmartHome": "https://smarthome.cheaa.com/",
    }
    results = scrape_cheaa_sections(
        test_sections, fetch_summaries=True, max_per_section=5, log=_print_log
    )
    print(f"\nTotal collected: {len(results)}\n")
    for r in results:
        print(f"- [{r['source']}] {r['date']}  {r['title'][:50]}")
        print(f"    {r['url']}")
        print(f"    summary: {r['summary'][:80]}")
