import feedparser
import json
import time
import os
import threading
from deep_translator import GoogleTranslator
import config

def _translate_batch_with_timeout(translator, texts, timeout=300):
    """Wrapper to prevent GoogleTranslator.translate_batch() from hanging indefinitely."""
    if not texts:
        return []
        
    result = [None]
    error = [None]
    
    def _do_translate():
        try:
            result[0] = translator.translate_batch(texts)
        except Exception as e:
            error[0] = e
    
    thread = threading.Thread(target=_do_translate)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        raise TimeoutError(f"Batch translation timed out after {timeout}s")
    if error[0]:
        raise error[0]
    return result[0] or []

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
            
    if new_entries_to_process:
        print(f"\nFound {len(new_entries_to_process)} new articles. Batch translating...")
        
        # Group by language
        entries_by_lang = {}
        for entry in new_entries_to_process:
            lang = entry['language']
            if lang not in entries_by_lang:
                entries_by_lang[lang] = []
            entries_by_lang[lang].append(entry)
            
        translators = {}
        for lang, entries in entries_by_lang.items():
            if lang not in translators:
                translators[lang] = GoogleTranslator(source=lang, target=config.TARGET_LANGUAGE)
            translator = translators[lang]
            
            titles_to_translate = [entry['title'] for entry in entries]
            summaries_to_translate = [entry['summary'] for entry in entries]
            
            try:
                print(f"  -> Batch translating titles ({lang})...")
                titles_en = _translate_batch_with_timeout(translator, titles_to_translate, timeout=config.TRANSLATION_TIMEOUT)
            except Exception as e:
                print(f"Error batch translating titles ({lang}): {e}")
                titles_en = [""] * len(titles_to_translate)
                
            try:
                print(f"  -> Batch translating summaries ({lang})...")
                summaries_en = _translate_batch_with_timeout(translator, summaries_to_translate, timeout=config.TRANSLATION_TIMEOUT)
            except Exception as e:
                print(f"Error batch translating summaries ({lang}): {e}")
                summaries_en = [""] * len(summaries_to_translate)
                
            for i, entry in enumerate(entries):
                entry["title_en"] = titles_en[i] if titles_en and i < len(titles_en) else ""
                entry["summary_en"] = summaries_en[i] if summaries_en and i < len(summaries_en) else ""
                new_articles.append(entry)
    
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
        response_schema=""
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
    
    with open(classified_filename, "w", encoding="utf-8") as f_out:
        json.dump(existing_classified, f_out, indent=4, ensure_ascii=False)
        
    print(f"Classified data saved to {classified_filename}")

if __name__ == "__main__":
    scrape_and_translate()
