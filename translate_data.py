"""Backfill Turkish for everything already scraped.

Writes **sidecar** files rather than whole translated copies of the datasets:

    tech_news_tr.json      {url: {title, summary, gemini}}
    company_news_tr.json   {url: {title, summary}}
    dynamic_classes_tr.json {english class name: Turkish name}

A sidecar holds only the three language-dependent fields; classification,
scores, dates and URLs stay in the one file that owns them. A full parallel
copy would double a 5.8 MB file that is committed on every scrape, and — worse
— would go stale in its *classification* fields the moment `reclassify.py` or
the dynamic subclassifier changed a label, with nothing to detect the drift.

The script is incremental by default: anything already present in a sidecar is
left alone, so a re-run after a failed pass costs only the missing items, and
the scheduled scrape can call the same code for its handful of new articles.
Progress is saved after every source-language group for the same reason.

    python translate_data.py                 # fill in whatever is missing
    python translate_data.py --force         # retranslate everything
    python translate_data.py --only news     # english | news | company | classes
    python translate_data.py --limit 50      # smoke test
"""
import argparse
import json
import os

import config
import translation

NEWS_FILE = config.CLASSIFIED_FILENAME
NEWS_TR_FILE = "tech_news_tr.json"
COMPANY_FILE = "company_news.json"
COMPANY_TR_FILE = "company_news_tr.json"
CLASSES_FILE = "dynamic_classes.json"
CLASSES_TR_FILE = "dynamic_classes_tr.json"

TARGET = "tr"


def log(msg):
    print(msg, flush=True)


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        log(f"  could not read {path}: {exc}")
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def needs(entry, keys):
    """True if the sidecar entry is missing any field we can supply."""
    return not entry or any(not entry.get(k) for k in keys)


def translate_news(force=False, limit=None):
    """Turkish for the tech-news dataset.

    Titles and summaries come from the original Japanese/Chinese; the Gemini
    label was written in English by us, so that one is translated out of
    English.
    """
    articles = load_json(NEWS_FILE, [])
    if not articles:
        log(f"  {NEWS_FILE} is empty or missing — nothing to do.")
        return
    side = {} if force else load_json(NEWS_TR_FILE, {})

    pending = []
    for art in articles:
        url = art.get("url")
        if not url:
            continue
        have = side.get(url)
        wants = ["title"]
        if (art.get("summary") or "").strip():
            wants.append("summary")
        gem = art.get("Gemini_Summary")
        if gem and gem != "N/A":
            wants.append("gemini")
        if force or needs(have, wants):
            pending.append(art)
    if limit:
        pending = pending[:limit]

    log(f"\n=== Tech news ===")
    log(f"  {len(articles)} articles, {len(side)} already translated, "
        f"{len(pending)} to do")
    if not pending:
        return

    # Pass 1: title + summary, straight out of the source language. Saved after
    # every language/field group, so an interrupted run keeps what it finished.
    def save_progress(partial):
        for i, values in partial.items():
            side.setdefault(pending[i].get("url"), {}).update(values)
        save_json(NEWS_TR_FILE, side)

    translation.translate_fields(
        pending, {"title": "title", "summary": "summary"},
        TARGET, log=log, checkpoint=save_progress)
    log(f"  saved {len(side)} entries")

    # Pass 2: the Gemini label, which only ever exists in English.
    with_gem = [a for a in pending
                if a.get("Gemini_Summary") and a["Gemini_Summary"] != "N/A"]
    if with_gem:
        log(f"  Gemini labels: {len(with_gem)}")
        values = translation.batch_translate(
            [a["Gemini_Summary"] for a in with_gem], "en", TARGET, log=log)
        for art, value in zip(with_gem, values):
            if value:
                side.setdefault(art["url"], {})["gemini"] = value
        save_json(NEWS_TR_FILE, side)

    log(f"  {NEWS_TR_FILE}: {len(side)} entries")


def translate_english(force=False, limit=None):
    """Repair missing English in the tech-news dataset itself.

    ``title_en`` / ``summary_en`` are what the dashboard renders, and when one
    is blank the page falls back to the raw Japanese or Chinese — which is
    exactly what a reader sees as "the news is in the wrong language". Older
    runs lost whole language groups at a time, because the batch helper they
    used raised on the first failure and threw away the rest of the group.

    Unlike the Turkish stages this writes back into the base file rather than a
    sidecar: these two fields already live there and are the ones the UI reads.
    """
    articles = load_json(NEWS_FILE, [])
    if not articles:
        log(f"  {NEWS_FILE} is empty or missing — nothing to do.")
        return

    pending = []
    for art in articles:
        wants_title = not (art.get("title_en") or "").strip()
        wants_sum = ((art.get("summary") or "").strip()
                     and not (art.get("summary_en") or "").strip())
        if force or wants_title or wants_sum:
            pending.append(art)
    if limit:
        pending = pending[:limit]

    log(f"\n=== English repair ===")
    log(f"  {len(articles)} articles, {len(pending)} missing English")
    if not pending:
        return

    def apply(partial):
        """Copy finished translations onto the records, never overwriting."""
        for i, values in partial.items():
            for key, value in values.items():
                if value and not (pending[i].get(key) or "").strip():
                    pending[i][key] = value

    def save_progress(partial):
        # Apply before saving, or the checkpoint writes the file unchanged and
        # an interrupted run loses everything it had already translated.
        apply(partial)
        save_json(NEWS_FILE, articles)      # records are edited in place

    got = translation.translate_fields(
        pending, {"title_en": "title", "summary_en": "summary"},
        "en", log=log, checkpoint=save_progress)
    apply(got)
    save_json(NEWS_FILE, articles)

    still = sum(1 for a in articles if not (a.get("title_en") or "").strip())
    log(f"  {NEWS_FILE}: {still} articles still without an English title")


def translate_company(force=False, limit=None):
    """Turkish for the competitor press releases (all English at source)."""
    items = load_json(COMPANY_FILE, [])
    if not items:
        log(f"  {COMPANY_FILE} is empty or missing — nothing to do.")
        return
    side = {} if force else load_json(COMPANY_TR_FILE, {})

    pending = [a for a in items
               if a.get("url") and (force or needs(side.get(a["url"]), ["title"]))]
    if limit:
        pending = pending[:limit]

    log(f"\n=== Company news ===")
    log(f"  {len(items)} releases, {len(side)} already translated, "
        f"{len(pending)} to do")
    if not pending:
        return

    def save_progress(partial):
        for i, values in partial.items():
            side.setdefault(pending[i]["url"], {}).update(values)
        save_json(COMPANY_TR_FILE, side)

    translation.translate_fields(
        pending, {"title": "title", "summary": "summary"},
        TARGET, log=log, checkpoint=save_progress)
    log(f"  {COMPANY_TR_FILE}: {len(side)} entries")


def translate_classes(force=False):
    """Turkish for the self-growing sub-class registry.

    These labels are invented by the model as new subjects appear, so they
    cannot live in the hand-written UI dictionary the way the six fixed
    classes do — they have to be translated as data.
    """
    reg = load_json(CLASSES_FILE, {})
    names = [c.get("name") for c in (reg.get("classes") or []) if c.get("name")]
    if not names:
        log("  no dynamic classes registered yet.")
        return
    side = {} if force else load_json(CLASSES_TR_FILE, {})

    todo = [n for n in names if force or not side.get(n)]
    log(f"\n=== Dynamic sub-classes ===")
    log(f"  {len(names)} classes, {len(todo)} to do")
    if not todo:
        return

    values = translation.batch_translate(todo, "en", TARGET, log=log)
    for name, value in zip(todo, values):
        if value:
            side[name] = value
    save_json(CLASSES_TR_FILE, side)
    log(f"  {CLASSES_TR_FILE}: {len(side)} entries")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="retranslate everything, not just what is missing")
    ap.add_argument("--only", choices=["english", "news", "company", "classes"],
                    help="run a single stage")
    ap.add_argument("--limit", type=int,
                    help="cap the number of records (smoke test)")
    args = ap.parse_args()

    stages = [args.only] if args.only else ["english", "news", "company", "classes"]
    for stage in stages:
        try:
            if stage == "english":
                translate_english(args.force, args.limit)
            elif stage == "news":
                translate_news(args.force, args.limit)
            elif stage == "company":
                translate_company(args.force, args.limit)
            else:
                translate_classes(args.force)
        except Exception as exc:            # noqa: BLE001 - one stage must not
            log(f"  {stage} stage failed: {exc}")   # take the others down
    log("\nDone.")


if __name__ == "__main__":
    main()
