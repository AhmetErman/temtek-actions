"""Shared Google-Translate helpers for the English and Turkish passes.

Two things here are deliberate and easy to undo by accident:

**Turkish is translated from the original language, not from our English.**
Where an article still carries its Japanese or Chinese source text we go
``ja -> tr`` directly; a ``ja -> en -> tr`` relay compounds the errors of two
machine translations and is noticeably worse. Only text we generated ourselves
in English (``Gemini_Summary``) is translated out of English.

**Every call is chunked and wrapped in a join-timeout.**
``GoogleTranslator.translate_batch()`` can hang forever, and the GitHub Actions
jobs run under a ``timeout-minutes`` cap, so a stalled call has to fail rather
than burn the whole job budget. Chunking also keeps one bad string from
costing a whole run's worth of translations.

Failures degrade to an empty string for the affected item and are logged; they
never raise into the caller, because a translation problem must not cost us the
scrape that produced the text.
"""
import html
import re
import urllib.parse
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

from deep_translator import GoogleTranslator

# deep_translator's translate_batch() is a plain serial loop that issues one
# HTTP request per string and raises on the first failure, throwing away the
# translations it already had. So we drive translate() ourselves, one string per
# task, across a small thread pool: each string then succeeds or fails on its
# own, and the run goes about six times faster than the serial loop.
WORKERS = 6

# Per-string timeout. The whole-run cap lives in config.TRANSLATION_TIMEOUT.
CHUNK_TIMEOUT = 30

# Progress is reported every this many strings.
REPORT_EVERY = 100

# The endpoint's real limit is on the URL-encoded request, not on characters:
# a Latin character encodes to ~1 byte but a CJK one to ~8, so 4,800 characters
# of English go through while 2,500 characters of Chinese do not. Measured
# empirically — ~16k encoded bytes succeeds, ~20k fails — so budget below that.
MAX_ENCODED = 14000

# Belt and braces for pathological input; the encoded budget is what actually
# binds for every real language we handle.
MAX_CHARS = 20000

# Retries per string, with exponential backoff. Google throttles a long backfill
# and reports it as "No translation was found using the current translator" —
# a message that reads like a bad input string but clears on its own after a
# wait, so the answer is to back off rather than to skip the text.
RETRIES = 3
RETRY_WAIT = 4

# Source languages we know how to name. Anything else — including the empty
# string that _is_valid_entry() leaves on a record with no language — goes to
# "auto", because asking for en->tr on Japanese text does not fail loudly: it
# returns the input unchanged, or worse, a fluent-looking mistranslation.
KNOWN_SOURCES = {"ja", "zh-CN", "zh-TW", "zh", "en", "de", "fr", "it", "es",
                 "ko", "nl", "pl", "pt", "ru", "tr"}


def source_lang(value):
    """Map a record's language field onto a source usable by the translator."""
    value = (value or "").strip()
    return value if value in KNOWN_SOURCES else "auto"


class _Strip(HTMLParser):
    """Collect the text of an HTML fragment, dropping tags and scripts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def fit_to_budget(text, budget=MAX_ENCODED):
    """Trim text until it fits the endpoint's URL-encoded size limit.

    Truncating beats skipping: several Chinese feeds put the whole article body
    in the RSS summary, and the alternative is showing nothing at all. The cut
    lands on a sentence or word boundary where one is near, and is marked with
    an ellipsis so a shortened summary is visibly shortened.
    """
    if len(urllib.parse.quote(text)) <= budget:
        return text
    lo, hi = 0, len(text)
    while lo < hi:                          # longest prefix that still fits
        mid = (lo + hi + 1) // 2
        if len(urllib.parse.quote(text[:mid])) <= budget - 8:
            lo = mid
        else:
            hi = mid - 1
    cut = text[:lo]
    for stop in ("。", ". ", "！", "？", "\n"):
        idx = cut.rfind(stop)
        if idx > lo * 0.6:                  # only if it does not lose too much
            return cut[:idx + len(stop)].strip() + "…"
    idx = cut.rfind(" ")
    if idx > lo * 0.6:
        cut = cut[:idx]
    return cut.strip() + "…"


def clean_text(value):
    """Normalise a scraped field into something worth translating.

    Some feeds (36Kr especially) put the entire article body, markup and all,
    into the RSS summary. Sent as-is that produces either a length rejection or
    a Turkish translation of HTML tags, so the markup comes off first — which
    also brings most over-long summaries back under the API's limit.
    """
    if not isinstance(value, str) or not value.strip():
        return ""
    text = value
    if "<" in text and ">" in text:
        parser = _Strip()
        try:
            parser.feed(text)
            parser.close()
            text = "".join(parser.parts)
        except Exception:                   # noqa: BLE001 - malformed markup
            text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _noop(msg):
    pass


def _call_with_timeout(fn, timeout):
    """Run fn() in a daemon thread; raise TimeoutError if it outlives timeout.

    deep_translator offers no timeout of its own and its socket can block
    indefinitely, so a thread we are willing to abandon is the only way to put
    a ceiling on it.
    """
    box = {}

    def run():
        try:
            box["value"] = fn()
        except Exception as exc:            # noqa: BLE001 - reported to caller
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise TimeoutError(f"translation timed out after {timeout}s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


_local = threading.local()


def _translator(source, target):
    """One GoogleTranslator per thread — the instances are not shareable."""
    key = (source, target)
    if getattr(_local, "key", None) != key:
        _local.key = key
        _local.tr = GoogleTranslator(source=source, target=target)
    return _local.tr


def _translate_one(text, source, target):
    """Translate a single string, retrying a throttled request."""
    for attempt in range(RETRIES):
        try:
            return _call_with_timeout(
                lambda: _translator(source, target).translate(text),
                CHUNK_TIMEOUT) or ""
        except Exception:                   # noqa: BLE001 - fault isolation
            if attempt + 1 < RETRIES:
                time.sleep(RETRY_WAIT * (2 ** attempt))
    return ""


def batch_translate(texts, source, target, log=_noop, workers=WORKERS,
                    timeout=CHUNK_TIMEOUT):
    """Translate a list of strings, returning a list of the same length.

    Empty and over-long strings never leave for the API and come back as "" —
    deep_translator raises on the former and rejects the latter. Everything
    else is translated independently, so one failure costs one string and the
    next incremental run picks it up.
    """
    out = [""] * len(texts)
    todo = []
    for i, raw in enumerate(texts):
        text = clean_text(raw)
        if not text or len(text) > MAX_CHARS:
            continue
        todo.append((i, fit_to_budget(text)))
    if not todo:
        return out

    done = 0
    lock = threading.Lock()

    def work(item):
        nonlocal done
        idx, text = item
        value = _translate_one(text, source, target)
        with lock:
            out[idx] = value
            done += 1
            if len(todo) > REPORT_EVERY and done % REPORT_EVERY == 0:
                log(f"    {source}->{target}: {done}/{len(todo)}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo))

    failed = sum(1 for i, _ in todo if not out[i])
    if failed:
        log(f"    {source}->{target}: {failed}/{len(todo)} still untranslated "
            f"(a re-run will retry them)")
    return out


def translate_fields(records, fields, target, source_key="language",
                     log=_noop, checkpoint=None):
    """Translate several fields across a list of records, grouped by language.

    ``fields`` maps an output key to the record key holding the text, e.g.
    ``{"title": "title", "summary": "summary"}``. Records are grouped by their
    ``source_key`` so each language costs one set of requests rather than one
    per record. Returns ``{index: {output_key: translated}}``.

    A record with no usable language goes to "auto" rather than to some
    assumed default: guessing English for a Japanese headline does not fail,
    it silently returns the headline untranslated or invents a plausible
    Turkish sentence from nothing.
    """
    by_lang = {}
    for i, rec in enumerate(records):
        by_lang.setdefault(source_lang(rec.get(source_key)), []).append(i)

    result = {}
    for lang, idxs in by_lang.items():
        if lang == target:                  # already in the target language
            continue
        log(f"  {lang} -> {target}: {len(idxs)} records")
        for out_key, rec_key in fields.items():
            texts = [records[i].get(rec_key) or "" for i in idxs]
            if not any(t.strip() for t in texts if isinstance(t, str)):
                continue
            log(f"   field '{out_key}'")
            values = batch_translate(texts, lang, target, log=log)
            for i, value in zip(idxs, values):
                if value:
                    result.setdefault(i, {})[out_key] = value
            # Hand back what is finished so the caller can save. A long backfill
            # that dies in its last group should not lose the earlier ones.
            if checkpoint:
                checkpoint(result)
    return result
