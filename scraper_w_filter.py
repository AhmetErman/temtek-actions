import feedparser
import json
import time
import os
from deep_translator import GoogleTranslator

def scrape_and_translate():
    rss_sources = {
        "ITmedia": "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml",
        "Zenn": "https://zenn.dev/feed",
    }
    
    output_filename = "tech_news.json"
    
    # Load existing articles to avoid duplicates
    existing_urls = set()
    existing_articles = []
    
    if os.path.exists(output_filename):
        try:
            with open(output_filename, "r", encoding="utf-8") as f:
                existing_articles = json.load(f)
                for article in existing_articles:
                    if 'url' in article:
                        existing_urls.add(article['url'])
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"Could not read existing {output_filename}. Starting fresh.")
    
    translator = GoogleTranslator(source='ja', target='en')
    
    total_scraped = 0
    new_articles_saved = 0
    
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
                title_en = translator.translate(title)
                summary_en = translator.translate(summary)
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
            
            existing_articles.append(article_data)
            existing_urls.add(url)
            new_articles_saved += 1
            
            time.sleep(0.5) # Prevent rate limiting

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(existing_articles, f, indent=4, ensure_ascii=False)
    
    print(f"\n=== Summary ===")
    print(f"Total articles found (scraped) in feeds: {total_scraped}")
    print(f"New articles translated and saved: {new_articles_saved}")
    print(f"Data saved to {output_filename}")

    # === Classification Phase ===
    print("\n=== Starting Classification phase ===")
    classified_filename = "tech_news_classified.json"
    existing_classified = []
    classified_urls = set()
    
    if os.path.exists(classified_filename):
        try:
            with open(classified_filename, "r", encoding="utf-8") as f:
                existing_classified = json.load(f)
                for item in existing_classified:
                    if 'url' in item:
                        classified_urls.add(item['url'])
        except (json.JSONDecodeError, FileNotFoundError):
            pass
            
    unclassified_articles = [art for art in existing_articles if art.get('url') not in classified_urls]
    
    if unclassified_articles:
        print(f"Found {len(unclassified_articles)} new articles to classify.")
        
        api_key = os.getenv("GEMINI_API")
        if not api_key and os.path.exists(".env"):
            with open(".env", "r") as env_f:
                for line in env_f:
                    if line.startswith("GEMINI_API="):
                        api_key = line.strip().split("=", 1)[1]
                        break
        
        if not api_key:
            print("GEMINI_API key not found in environment or .env file. Skipping classification.")
        else:
            from gemini_filter import GeminiClassifier
            system_prompt = """Classification Prompt
Task: Please classify the given R&D project description or technical text into one of the following categories based on its primary focus. Use the category name as the label.

Categories & Descriptions:

Sustainability & Environmental Impact: Focuses on minimizing the ecological footprint of home appliances. This includes microfiber filtration systems to prevent ocean pollution, technologies for water and energy conservation (e.g., AquaTech), and the use of recycled materials in product components.

Fabric Care & Textile Engineering: Research dedicated to the physical and thermal effects of washing and drying on various textiles (silk, wool, technical fabrics). It covers garment longevity, color preservation, wrinkle reduction (e.g., SteamCure), and mechanical stress analysis on fibers.

Chemical Interaction & Smart Dosing: Studies regarding the synergy between detergents, additives, and machine hardware. This includes automated dosing systems (AutoDose), detergent dissolution efficiency, and the chemical impact of cleaning agents on different fabric types.

Hygiene & Health Technologies: Focuses on sanitization and allergen removal. This category covers high-temperature or steam-based cycles (Hygiene+) designed to eliminate bacteria, viruses, and allergens, as well as odor removal technologies that don't necessarily require water.

AI, IoT & Smart Sensors: Covers the digitalization of appliances. This includes HomeWhiz integration, machine learning algorithms for cycle optimization, sensor development for load sensing, turbidity detection, and noise/vibration control (Unbalanced Load detection).

Other: Choose this category if the text describes general mechanical design, supply chain innovations, structural durability tests, industrial design, or any other R&D activity that does not directly fit into the specific cleaning and textile categories listed above."""
            
            classifier = GeminiClassifier(
                api_key=api_key,
                model_name="gemma-4-31b-it", 
                batch_size=10,
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
                    
            print("Running Gemini Classification...")
            classified_results = classifier.process_list(unclassified_articles, progress_callback=print_progress)
            
            existing_classified.extend(classified_results)
            
            with open(classified_filename, "w", encoding="utf-8") as f_out:
                json.dump(existing_classified, f_out, indent=4, ensure_ascii=False)
                
            print(f"Classified data saved to {classified_filename}")
    else:
        print("No new articles to classify.")

if __name__ == "__main__":
    scrape_and_translate()
