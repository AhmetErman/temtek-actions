import feedparser
import json
import time
import os
import threading
from deep_translator import GoogleTranslator


def _translate_with_timeout(translator, text, timeout=30):
    """Wrapper to prevent GoogleTranslator.translate() from hanging indefinitely."""
    result = [None]
    error = [None]
    
    def _do_translate():
        try:
            result[0] = translator.translate(text)
        except Exception as e:
            error[0] = e
    
    thread = threading.Thread(target=_do_translate)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        raise TimeoutError(f"Translation timed out after {timeout}s")
    if error[0]:
        raise error[0]
    return result[0] or ""

def scrape_and_translate():
    rss_sources = {
        "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",
        "Zenn": "https://zenn.dev/feed",
    }
    
    classified_filename = "tech_news_classified.json"
    
    # Load existing classified articles to avoid duplicates
    existing_urls = set()
    existing_classified = []
    
    if os.path.exists(classified_filename):
        try:
            with open(classified_filename, "r", encoding="utf-8") as f:
                existing_classified = json.load(f)
                for article in existing_classified:
                    if 'url' in article:
                        existing_urls.add(article['url'])
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"Could not read existing {classified_filename}. Starting fresh.")
    
    translator = GoogleTranslator(source='ja', target='en')
    
    total_scraped = 0
    new_articles = []
    
    for source_name, feed_url in rss_sources.items():
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
            
            print(f"  -> Translating new article: {title[:30]}...")
            
            try:
                title_en = _translate_with_timeout(translator, title)
                summary_en = _translate_with_timeout(translator, summary)
            except Exception as e:
                print(f"Error translating article: {e}")
                title_en = ""
                summary_en = ""
                
            article_data = {
                "source": source_name,
                "title": title,
                "title_en": title_en,
                "date": entry.get('published', entry.get('updated', 'No Date Available')),
                "url": url,
                "summary": summary,
                "summary_en": summary_en
            }
            
            new_articles.append(article_data)
            existing_urls.add(url)
            
            time.sleep(0.5) # Prevent rate limiting
    
    print(f"\n=== Scrape Summary ===")
    print(f"Total articles found in feeds: {total_scraped}")
    print(f"New articles translated: {len(new_articles)}")

    # === Classification Phase ===
    if not new_articles:
        print("No new articles to classify.")
        return
    
    print(f"\n=== Starting Classification phase ===")
    print(f"Found {len(new_articles)} new articles to classify.")
    
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
        existing_classified.extend(new_articles)
        with open(classified_filename, "w", encoding="utf-8") as f_out:
            json.dump(existing_classified, f_out, indent=4, ensure_ascii=False)
        print(f"Saved {len(new_articles)} unclassified articles to {classified_filename}")
        return
    
    from gemini_filter import GeminiClassifier
    system_prompt = """Classification Prompt
Task: Please classify the given R&D project description or technical text into one of the following categories based on its primary focus. Use the category name as the label.

Categories & Descriptions:

Sustainability & Environmental Impact: Focuses on minimizing the ecological footprint of home appliances. This includes microfiber filtration systems to prevent ocean pollution, technologies for water and energy conservation (e.g., AquaTech), and the use of recycled materials in product components.

Fabric Care & Textile Engineering: Research dedicated to the physical and thermal effects of washing and drying on various textiles (silk, wool, technical fabrics). It covers garment longevity, color preservation, wrinkle reduction (e.g., SteamCure), and mechanical stress analysis on fibers.

Chemical Interaction & Smart Dosing: Studies regarding the synergy between detergents, additives, and machine hardware. This includes automated dosing systems (AutoDose), detergent dissolution efficiency, and the chemical impact of cleaning agents on different fabric types.

Hygiene & Health Technologies: Focuses on sanitization and allergen removal. This category covers high-temperature or steam-based cycles (Hygiene+) designed to eliminate bacteria, viruses, and allergens, as well as odor removal technologies that don't necessarily require water.

IoT & Smart Sensors: Covers the digitalization of home appliances. This includes smart home integration, machine learning algorithms for cycle optimization, sensor development for load sensing, turbidity detection, and noise/vibration control (Unbalanced Load detection).

Other: Choose this category if the text describes general mechanical design, supply chain innovations, structural durability tests, industrial design, or any other R&D activity that does not directly fit into the specific cleaning and textile categories listed above."""
    
    classifier = GeminiClassifier(
        api_key=api_key,
        model_name="gemini-3.5-flash", 
        batch_size=50,
        system_prompt=system_prompt,
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
    classified_results = classifier.process_list(new_articles, progress_callback=print_progress)
    
    existing_classified.extend(classified_results)
    
    with open(classified_filename, "w", encoding="utf-8") as f_out:
        json.dump(existing_classified, f_out, indent=4, ensure_ascii=False)
        
    print(f"Classified data saved to {classified_filename}")

if __name__ == "__main__":
    scrape_and_translate()
