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
import threading
import time
from html.parser import HTMLParser

from deep_translator import GoogleTranslator

# Chunk size for one translate_batch() call. Small enough that a failure or a
# timeout loses only a little work, large enough to keep the request count sane.
CHUNK_SIZE = 40

# Per-chunk timeout. The whole-run cap lives in config.TRANSLATION_TIMEOUT.
CHUNK_TIMEOUT = 120

# GoogleTranslator rejects anything longer than this in a single request.
MAX_CHARS = 4800

# Retries per chunk, with exponential backoff. Google throttles a long backfill
# and reports it as "No translation was found using the current translator" —
# a message that reads like a bad input string but clears on its own after a
# wait, so the answer is to back off rather than to skip the text.
RETRIES = 3
RETRY_WAIT = 4

# Pause between chunks. Cheap insurance: being throttled costs far more time in
# backoff than this spends across a whole run.
CHUNK_PAUSE = 0.6

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


def batch_translate(texts, source, target, log=_noop,
                    chunk_size=CHUNK_SIZE, timeout=CHUNK_TIMEOUT):
    """Translate a list of strings, returning a list of the same length.

    Empty and over-long strings are held out of the request and returned as
    "" — deep_translator raises on the former and rejects the latter, and one
    such string would otherwise fail the whole chunk it travels in.
    """
    out = [""] * len(texts)
    todo = []
    for i, raw in enumerate(texts):
        text = clean_text(raw)
        if text and len(text) <= MAX_CHARS:
            todo.append((i, text))
    if not todo:
        return out

    translator = GoogleTranslator(source=source, target=target)
    done = 0
    for start in range(0, len(todo), chunk_size):
        chunk = todo[start:start + chunk_size]
        payload = [t for _, t in chunk]

        got = None
        for attempt in range(RETRIES):
            try:
                got = _call_with_timeout(
                    lambda: translator.translate_batch(payload), timeout)
                break
            except Exception as exc:        # noqa: BLE001 - fault isolation
                if attempt + 1 < RETRIES:
                    time.sleep(RETRY_WAIT * (2 ** attempt))
                    continue
                log(f"    {source}->{target}: chunk of {len(payload)} "
                    f"failed ({exc})")

        if got is None:
            # translate_batch fails all-or-nothing, so one throttled call would
            # otherwise cost every string travelling with it. Retry the chunk
            # item by item to salvage the rest; whatever still fails is left
            # blank and picked up by the next incremental run.
            got = []
            for text in payload:
                try:
                    got.append(_call_with_timeout(
                        lambda: translator.translate(text), timeout))
                except Exception:           # noqa: BLE001 - one lost string
                    got.append("")
                time.sleep(CHUNK_PAUSE)
            salvaged = sum(1 for v in got if v)
            log(f"    {source}->{target}: salvaged {salvaged}/{len(payload)} "
                f"one at a time")

        for (idx, _), value in zip(chunk, got or []):
            out[idx] = value or ""
        done += len(chunk)
        if len(todo) > chunk_size:
            log(f"    {source}->{target}: {done}/{len(todo)}")
        time.sleep(CHUNK_PAUSE)
    return out


def translate_fields(records, fields, target, source_key="language",
                     log=_noop):
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
    return result
