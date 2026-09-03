import feedparser
import json
import time
import os
import config
import translation

def _is_valid_entry(entry):
    """Guard against malformed input from any source (RSS or custom scrapers).

    A usable article needs a non-empty string ``url`` and ``title``. Optional
    text fields are normalized to strings so downstream translation never
    crashes on None/non-string values. Returns False for anything unusable.
    """
    if not isinstance(entry, dict):
        return False
    url = entry.get('url')
    title = entry.get('title')
    if not isinstance(url, str) or not url.strip():
        return False
    if not isinstance(title, str) or not title.strip():
        return False
    for key in ('source', 'title', 'summary', 'date', 'language'):
        val = entry.get(key)
        if val is None:
            entry[key] = ''
        elif not isinstance(val, str):
            entry[key] = str(val)
    # deep_translator chokes on empty strings; fall back to the title.
    if not entry.get('summary', '').strip():
        entry['summary'] = entry['title']
    return True

def scrape_and_translate():
    classified_filename = config.CLASSIFIED_FILENAME
    
    # Load existing classified articles to avoid duplicates
    existing_urls = set()
    existing_classified = []
    unclassified_backlog = []
    
    if os.path.exists(classified_filename):
        try:
            with open(classified_filename, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                for article in existing_data:
                    if 'url' in article:
                        existing_urls.add(article['url'])
                    
                    if article.get('Classification') and article.get('Classification') != "N/A":
                        existing_classified.append(article)
                    else:
                        unclassified_backlog.append(article)
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"Could not read existing {classified_filename}. Starting fresh.")
    
    total_scraped = 0
    new_articles = []
    new_entries_to_process = []
    
    for source_name, source_info in config.RSS_SOURCES.items():
        feed_url = source_info['url']
        source_lang = source_info['language']
        
        print(f"\nFetching data from: {source_name}...")
        feed = feedparser.parse(feed_url)

        if feed.bozo:
            print(f"  -> Error fetching {source_name}. Skipping.")
            continue

        entries = feed.entries
        print(f"  -> Found {len(entries)} articles in feed.")
        total_scraped += len(entries)

        for entry in entries:
            url = entry.get('link', '')
            
            # Skip if already exists based on URL
            if url in existing_urls:
                continue
                
            title = entry.get('title', 'No Title Available')
            summary = entry.get('summary', 'No Summary Available')
            
            # deep_translator crashes on completely empty strings
            if not title or not title.strip(): title = "No Title Available"
            if not summary or not summary.strip(): summary = "No Summary Available"
            
            new_entries_to_process.append({
                "source": source_name,
                "title": title,
                "date": entry.get('published', entry.get('updated', 'No Date Available')),
                "url": url,
                "summary": summary,
                "language": source_lang
            })
            existing_urls.add(url)

    # === Custom HTML scrapers (sites without RSS, e.g. cheaa) ===
    # Fully optional and isolated: any failure here is logged and skipped so the
    # RSS articles still get translated and classified.
    cheaa_cfg = getattr(config, "CHEAA_SCRAPER", None)
    if cheaa_cfg and cheaa_cfg.get("enabled"):
        try:
            from cheaa_scraper import scrape_cheaa_sections
            print("\nScraping cheaa sections (no RSS available)...")
            cheaa_entries = scrape_cheaa_sections(
                sections=cheaa_cfg.get("sections", {}),
                language=cheaa_cfg.get("language", "zh-CN"),
                existing_urls=existing_urls,
                max_per_section=cheaa_cfg.get("max_per_section", 10),
                fetch_summaries=cheaa_cfg.get("fetch_summaries", True),
                timeout=cheaa_cfg.get("request_timeout", 20),
                sleep_between=cheaa_cfg.get("sleep_between", 1.0),
                log=lambda level, msg: print(f"  -> {msg}"),
            )
            new_entries_to_process.extend(cheaa_entries)
            total_scraped += len(cheaa_entries)
        except Exception as e:
            print(f"  -> cheaa scraper unavailable, skipping: {e}")

    ofweek_cfg = getattr(config, "OFWEEK_SCRAPER", None)
    if ofweek_cfg and ofweek_cfg.get("enabled"):
        try:
            from ofweek_scraper import scrape_ofweek_sections
            print("\nScraping OFweek sections (no RSS available)...")
            ofweek_entries = scrape_ofweek_sections(
                sections=ofweek_cfg.get("sections", {}),
                language=ofweek_cfg.get("language", "zh-CN"),
                existing_urls=existing_urls,
                max_per_section=ofweek_cfg.get("max_per_section", 10),
                timeout=ofweek_cfg.get("request_timeout", 20),
                log=lambda level, msg: print(f"  -> {msg}"),
            )
            new_entries_to_process.extend(ofweek_entries)
            total_scraped += len(ofweek_entries)
        except Exception as e:
            print(f"  -> OFweek scraper unavailable, skipping: {e}")

    # Drop/normalize any malformed entries from ANY source before we spend time
    # translating and classifying them.
    before = len(new_entries_to_process)
    new_entries_to_process = [e for e in new_entries_to_process if _is_valid_entry(e)]
    dropped = before - len(new_entries_to_process)
    if dropped:
        print(f"  -> Dropped {dropped} malformed entr{'y' if dropped == 1 else 'ies'}.")

    if new_entries_to_process:
        print(f"\nFound {len(new_entries_to_process)} new articles. Translating to English...")

        # Same engine as the Turkish pass. It matters which one is used here:
        # deep_translator's translate_batch() is a serial loop that raises on the
        # first failure and discards everything it already translated, so one
        # throttled request used to blank out an entire language group's titles
        # in a single run — which is what left raw Japanese and Chinese headlines
        # on the English page. translation.batch_translate() isolates each
        # string, auto-detects a missing language, strips HTML and caps on the
        # API's real (URL-encoded) size limit.
        got = translation.translate_fields(
            new_entries_to_process,
            {"title_en": "title", "summary_en": "summary"},
            config.TARGET_LANGUAGE,
            log=lambda m: print(m, flush=True),
        )
        for i, entry in enumerate(new_entries_to_process):
            values = got.get(i, {})
            entry["title_en"] = values.get("title_en", "")
            entry["summary_en"] = values.get("summary_en", "")
            new_articles.append(entry)

        blank = sum(1 for e in new_articles if not (e.get("title_en") or "").strip())
        if blank:
            print(f"  -> {blank} titles could not be translated; "
                  f"the English backfill stage will retry them.")

    print(f"\n=== Scrape Summary ===")
    print(f"Total articles found in feeds: {total_scraped}")
    print(f"New articles translated: {len(new_articles)}")

    # === Classification Phase ===
    articles_to_classify = unclassified_backlog + new_articles
    
    if not articles_to_classify:
        print("No articles to classify.")
        return
    
    print(f"\n=== Starting Classification phase ===")
    print(f"Found {len(articles_to_classify)} articles to classify ({len(unclassified_backlog)} from backlog, {len(new_articles)} new).")
    
    api_key = os.getenv("GEMINI_API")
    if not api_key and os.path.exists(".env"):
        with open(".env", "r") as env_f:
            for line in env_f:
                if line.startswith("GEMINI_API="):
                    api_key = line.strip().split("=", 1)[1]
                    break
    
    if not api_key:
        print("GEMINI_API key not found in environment or .env file. Skipping classification.")
        # Still save unclassified articles so they aren't lost
        existing_classified.extend(articles_to_classify)
        with open(classified_filename, "w", encoding="utf-8") as f_out:
            json.dump(existing_classified, f_out, indent=4, ensure_ascii=False)
        print(f"Saved {len(articles_to_classify)} unclassified articles to {classified_filename}")
        return
    
    from gemini_filter import GeminiClassifier
    
    classifier = GeminiClassifier(
        api_key=api_key,
        model_name=config.GEMINI_MODELS,
        batch_size=config.GEMINI_BATCH_SIZE,
        system_prompt=config.SYSTEM_PROMPT,
        response_schema="",
        request_timeout=getattr(config, "GEMINI_REQUEST_TIMEOUT", 90),
    )
    
    def print_progress(msg_type, *args):
        if msg_type == "success":
            print(f"  -> {args[0]}")
        elif msg_type == "warning":
            print(f"  -> Warning: {args[0]}")
        elif msg_type == "error":
            print(f"  -> Error: {args[0]}")
        elif msg_type == "progress":
            print(f"  -> Progress: {args[0]}/{args[1]}")
        elif msg_type == "eta":
            print(f"  -> ETA: ~{args[0]:.1f} min")
            
    print("Running Gemini Classification...")
    classified_results = classifier.process_list(articles_to_classify, progress_callback=print_progress)

    existing_classified.extend(classified_results)

    # === Normalize labels + Layer-2 dynamic subclassification of "Other" ===
    # Fault-isolated: any problem here must not lose the primary classification.
    try:
        from taxonomy import normalize_classification
        for art in existing_classified:
            if art.get("Classification") is not None:
                art["Classification"] = normalize_classification(art["Classification"])

        dyn_cfg = getattr(config, "DYNAMIC_SUBCLASS", None)
        if dyn_cfg and dyn_cfg.get("enabled"):
            from dynamic_subclassifier import DynamicSubclassifier
            # Only subclass "Other" items that don't already carry a sub-class.
            todo = [a for a in existing_classified
                    if a.get("Classification") == "Other" and not a.get("OtherSubclass")]
            if todo:
                print(f"\n=== Layer-2: dynamic subclassification of {len(todo)} 'Other' items ===")
                sub = DynamicSubclassifier(
                    api_key=api_key,
                    models=config.GEMINI_MODELS,
                    batch_size=dyn_cfg.get("batch_size", 25),
                    store_path=dyn_cfg.get("store_file", "dynamic_classes.json"),
                    base_instruction=dyn_cfg.get("base_instruction", ""),
                    request_timeout=getattr(config, "GEMINI_REQUEST_TIMEOUT", 90),
                )
                sub.subclassify(todo, progress_callback=print_progress)
                sub.recount(existing_classified)
                sub.save()
                print(f"  -> sub-taxonomy now has {len(sub.registry['classes'])} classes.")
    except Exception as e:
        print(f"  -> Dynamic subclassification skipped: {e}")

    with open(classified_filename, "w", encoding="utf-8") as f_out:
        json.dump(existing_classified, f_out, indent=4, ensure_ascii=False)

    print(f"Classified data saved to {classified_filename}")

    # === Turkish pass ===
    # translate_data is incremental, so this only touches what this run added:
    # the articles just classified, plus any sub-class the Layer-2 pass invented.
    # Fault-isolated like every other stage — the dashboard falls back to English
    # for anything untranslated, so a failure here must not fail the scrape.
    try:
        import translate_data
        print("\n=== Translation passes ===")
        # English first: title_en/summary_en are what the dashboard renders, so
        # a gap there shows the reader a raw Japanese or Chinese headline.
        translate_data.translate_english()
        translate_data.translate_news()
        translate_data.translate_classes()
    except Exception as e:
        print(f"  -> Translation pass skipped: {e}")


if __name__ == "__main__":
    scrape_and_translate()
