"""
Generic, fault-isolated engine for scraping home-appliance company newsrooms.

Strategy: collect article URLs from listing pages (per-company URL pattern +
pagination), then enrich each article from its own page's Open Graph / JSON-LD /
<time> metadata. Article pages are far more uniform than listing pages, so this
keeps per-company config tiny (just URL patterns) while extraction stays robust.

The public entry point `scrape_company()` never raises: any failure is logged
and skipped, and whatever was collected is returned.
"""
import re
import time
import urllib.request
from urllib.parse import urljoin
from lxml import html as LH

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_ISO = re.compile(r"(20\d\d)-(\d{2})-(\d{2})")
_DATE_IN_URL = re.compile(r"/(20\d\d)[-/](\d{2})[-/](\d{2})")


def _noop(*_a, **_k):
    pass


def _decode(raw, header_charset):
    m = re.search(rb'charset=["\']?\s*([\w-]+)', raw[:3000], re.I)
    meta = m.group(1).decode("ascii", "ignore") if m else None
    for c in (header_charset, meta, "utf-8", "gb18030"):
        if c:
            try:
                return raw.decode(c)
            except (LookupError, UnicodeDecodeError):
                continue
    return raw.decode("utf-8", errors="replace")


def fetch(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        cs = resp.headers.get_content_charset()
    return _decode(raw, cs)


def date_from_url(url):
    m = _DATE_IN_URL.search(url)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def extract_links(listing_html, base_url, article_url_re, exclude_re=None):
    """Return ordered unique [(absolute_url, anchor_title)] matching the pattern."""
    doc = LH.fromstring(listing_html)
    rx = re.compile(article_url_re)
    ex = re.compile(exclude_re) if exclude_re else None
    out, seen = [], set()
    for a in doc.xpath("//a[@href]"):
        full = urljoin(base_url, a.get("href", "")).split("#")[0].rstrip("/")
        if not rx.search(full):
            continue
        if ex and ex.search(full):
            continue
        if full in seen:
            continue
        seen.add(full)
        title = (a.get("title") or a.text_content() or "").strip()
        title = re.sub(r"\s+", " ", title)
        out.append((full, title))
    return out


def _meta_date(doc):
    for xp in ('//meta[@property="article:published_time"]/@content',
               '//meta[@property="og:published_time"]/@content',
               '//meta[@property="article:modified_time"]/@content',
               '//meta[@itemprop="datePublished"]/@content',
               '//meta[@name="publishdate"]/@content',
               '//meta[@name="date"]/@content',
               '//time/@datetime'):
        v = doc.xpath(xp)
        if v:
            m = _ISO.search(v[0])
            if m:
                return m.group(0)
    for s in doc.xpath('//script[@type="application/ld+json"]/text()'):
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', s)
        if m:
            mm = _ISO.search(m.group(1))
            if mm:
                return mm.group(0)
    return None


def enrich(url, anchor_title, timeout=20):
    """Fetch the article page and pull title/date/summary/image from meta tags."""
    rec = {"url": url, "title": anchor_title or "", "date": date_from_url(url),
           "summary": "", "image": ""}
    try:
        doc = LH.fromstring(fetch(url, timeout))
    except Exception:
        return rec

    def meta(*xps):
        for xp in xps:
            v = doc.xpath(xp)
            if v and v[0].strip():
                return v[0].strip()
        return None

    t = meta('//meta[@property="og:title"]/@content',
             '//meta[@name="twitter:title"]/@content')
    if t:
        rec["title"] = re.sub(r"\s+", " ", t)
    desc = meta('//meta[@property="og:description"]/@content',
                '//meta[@name="description"]/@content',
                '//meta[@name="twitter:description"]/@content')
    if desc:
        rec["summary"] = re.sub(r"\s+", " ", desc)
    img = meta('//meta[@property="og:image"]/@content',
               '//meta[@property="og:image:url"]/@content',
               '//meta[@name="twitter:image"]/@content')
    if img:
        rec["image"] = urljoin(url, img)
    if not rec["date"]:
        rec["date"] = _meta_date(doc)
    if not rec["title"]:
        h = doc.xpath("//h1")
        if h:
            rec["title"] = re.sub(r"\s+", " ", h[0].text_content().strip())
    return rec


def scrape_company(cfg, since="2023-01-01", existing_urls=None,
                   max_articles=150, max_pages=40, sleep=0.4, timeout=25,
                   log=None):
    """
    Scrape one company's newsroom. Returns normalized records:
      {company, title, url, date, summary, image, language, source_url}

    Walks listing pages (cfg["list_url_template"].format(page=N)) collecting
    article URLs, enriches each new one from its page meta, and stops at the
    `since` date or the `max_articles`/`max_pages` caps. Never raises.
    """
    log = log or _noop
    if existing_urls is None:
        existing_urls = set()
    company = cfg["company"]
    lang = cfg.get("language", "en")
    art_re = cfg["article_url_re"]
    exc_re = cfg.get("exclude_re")
    tmpl = cfg["list_url_template"]
    p0 = cfg.get("page_start", 1)
    recs = []
    collected = 0
    old_streak = 0  # consecutive articles older than `since`
    try:
        for page in range(p0, p0 + max_pages):
            list_url = tmpl.format(page=page)
            try:
                html = fetch(list_url, timeout)
            except Exception as e:
                log("warning", f"{company}: listing page {page} failed: {e}")
                break
            links = extract_links(html, list_url, art_re, exc_re)
            if not links:
                log("info", f"{company}: no article links on page {page}; stop")
                break
            new_here = 0
            stop = False
            for url, title in links:
                if collected >= max_articles:
                    stop = True
                    break
                if url in existing_urls:
                    continue
                existing_urls.add(url)
                rec = enrich(url, title, timeout)
                if sleep:
                    time.sleep(sleep)
                date = rec.get("date") or ""
                if date and date < since:
                    # Tolerate a stray mis-parsed old date; only treat the
                    # backfill horizon as reached after several in a row.
                    old_streak += 1
                    if old_streak >= 6:
                        stop = True
                    continue
                old_streak = 0
                if not rec.get("title") or len(rec["title"]) < 8:
                    continue
                rec.update({"company": company, "language": lang,
                            "source_url": list_url})
                recs.append(rec)
                collected += 1
                new_here += 1
            log("success",
                f"{company}: page {page} -> +{new_here} (total {collected})")
            if stop or collected >= max_articles:
                break
            # No new articles on a later page => pagination exhausted or the
            # page param is ignored (same list returned). Stop to avoid looping.
            if new_here == 0 and page > p0:
                break
    except Exception as e:
        log("error", f"{company}: aborted unexpectedly: {e}")
    return recs
