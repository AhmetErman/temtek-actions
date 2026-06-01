import os
import json
import time
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

class GeminiClassifier:
    def __init__(self, api_key, model_name, batch_size, system_prompt, response_schema):
        self.api_key = api_key
        if isinstance(model_name, list):
            self.model_names = model_name
        else:
            self.model_names = [model_name]
        self.current_model_idx = 0
        self.batch_size = int(batch_size)
        
        # Default fallback prompt if empty
        base_prompt = system_prompt if system_prompt and system_prompt.strip() else \
            "You are a China and Japan Tech News expert. Classify news and provide a short summary."
            
        mandatory_instructions = (
            "\n\nYou will be given Title, and Summary for each news and classify each news's primary function related to its main topic.\n"
            "You must classify each news into one of the categories above, or 'other'.\n"
            "Additionally, assign an RelationScore from 1 to 5 indicating how closely the news's main topic aligns with the chosen Classification.\n"
            "Generate a descriptive Summary of maximum of five words that captures core topic.\n"
            "Return results as a ALWAYS JSON object containing ALL the news's index, classification, relation score and summary. Do not skip any news index. "
        )
        self.system_prompt = base_prompt + mandatory_instructions
            
        # Default fallback schema if empty
        DEFAULT_STRUCT = {
            "type": "OBJECT",
            "properties": {
                "news": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "NewsIndex": {"type": "INTEGER"},
                            "Classification": {"type": "STRING"},
                            "RelationScore": {"type": "INTEGER"},
                            "Summary": {"type": "STRING"}
                        },
                        "required": ["NewsIndex", "Classification", "RelationScore", "Summary"]
                    }
                }
            },
            "required": ["news"]
        }

        if not response_schema or (isinstance(response_schema, str) and not response_schema.strip()):
            self.response_schema = DEFAULT_STRUCT
        elif isinstance(response_schema, str):
            try:
                self.response_schema = json.loads(response_schema)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON in response_schema, falling back to default.")
                self.response_schema = DEFAULT_STRUCT
        else:
            self.response_schema = response_schema

        # Basic structural validation
        if not isinstance(self.response_schema, dict) or 'type' not in self.response_schema:
            logger.warning("Response schema missing 'type' field, falling back to default.")
            self.response_schema = DEFAULT_STRUCT
            
        self.client = genai.Client(api_key=self.api_key)
        self.is_running = False
        self._is_active = False  # True while process_dataframe thread is alive

    def validate_key(self):
        """Pings the model with a tiny request to validate key and get quotas."""
        # Due to Gemini API limitations regarding querying quota directly, 
        # we will do a minimal request and fetch ratelimits optionally if returned.
        # But `genai` doesn't natively expose headers cleanly in standard responses yet,
        # so simply a success indicates the key/model combo works!
        try:
            self.client.models.generate_content(
                model=self.model_name,
                contents="test"
            )
            return True, "Key is valid and model is accessible."
        except Exception as e:
            return False, str(e)

    def classify_batch(self, batch_data, max_retries=3, progress_callback=None):
        if not self.is_running:
            return {"news": []}

        news_text = "Analyze the following news and provide structured output for each.\n\n"
        for news in batch_data:
            desc = news.get('description', '')
            if not isinstance(desc, str):
                desc = ''
            news_text += (
                f"--- NEWS {news['index']} ---\n"
                f"Title: {news.get('title', '')}\n"
                f"Summary: {news.get('summary', '')}\n\n"
            )

        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=self.response_schema,
            system_instruction=self.system_prompt
        )

        for attempt in range(max_retries):
            if not self.is_running:
                break
                
            model_to_use = self.model_names[self.current_model_idx]
            try:
                response = self.client.models.generate_content(
                    model=model_to_use,
                    contents=news_text,
                    config=generation_config,
                )
                
                if response.text:
                    stripped = response.text.strip()
                    if not stripped.startswith('{'):
                        raise ValueError("API returned non-JSON string.")
                    # Use raw_decode to parse only the first JSON object,
                    # ignoring any trailing data the model may append
                    decoder = json.JSONDecoder()
                    result, _ = decoder.raw_decode(stripped)
                    return result
                raise ValueError("API response text is missing (possible block).")
                
            except Exception as e:
                logger.warning(f"Classification batch error (Attempt {attempt+1}/{max_retries}): {e}")
                err_str = str(e)
                if "503" in err_str or "429" in err_str:
                    if self.current_model_idx < len(self.model_names) - 1:
                        old_model = self.model_names[self.current_model_idx]
                        self.current_model_idx += 1
                        if progress_callback:
                            progress_callback("warning", f"Model {old_model} failed (503/429), switching to {self.model_names[self.current_model_idx]}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    if progress_callback:
                        progress_callback("warning", f"Batch failed, retrying in {wait_time}s... Error: {e}")
                    time.sleep(wait_time)
                else:
                    if progress_callback:
                        progress_callback("error", f"Batch completely failed after {max_retries} retries. Error: {e}")
                    
        return {"news": []}

    def process_dataframe(self, df, progress_callback=None):
        self.is_running = True
        self._is_active = True
        df = df.copy()
        try:
            # Initialize output columns safely
            if 'Classification' not in df.columns:
                df['Classification'] = None
            if 'RelationScore' not in df.columns:
                df['RelationScore'] = None
            if 'Summary' not in df.columns:
                df['Summary'] = None

            total_news = len(df)
            processed_count = 0
            start_time = time.time()

            for batch_start in range(0, total_news, self.batch_size):
                if not self.is_running:
                    break
                    
                batch_end = min(batch_start + self.batch_size, total_news)
                batch_indices = range(batch_start, batch_end)
                
                # Map columns fuzzily
                title_col = next((c for c in df.columns if 'title' in c.lower()), None)
                desc_col = next((c for c in df.columns if 'summary' in c.lower()), None)

                batch_data = []
                for i, idx in enumerate(batch_indices):
                    row = df.iloc[idx]
                    batch_data.append({
                        'index': i,
                        'title': row[title_col] if title_col else '',
                        'summary': row[desc_col] if desc_col else ''
                    })
                
                results = self.classify_batch(batch_data, max_retries=3, progress_callback=progress_callback)
                
                if results and 'news' in results:
                    for res in results['news']:
                        b_idx = res.get('NewsIndex')
                        if b_idx is not None and 0 <= b_idx < len(batch_data):
                            actual_idx = batch_start + b_idx
                            df.loc[actual_idx, 'Classification'] = res.get('Classification', 'N/A')
                            df.loc[actual_idx, 'RelationScore'] = res.get('RelationScore', -1)
                            df.loc[actual_idx, 'Summary'] = res.get('Summary', 'N/A')
                
                processed_count += len(batch_data)
                
                if progress_callback:
                    progress_callback("progress", processed_count, total_news)
                    elapsed = time.time() - start_time
                    avg_time = elapsed / processed_count
                    remaining = total_news - processed_count
                    eta_minutes = (avg_time * remaining) / 60
                    
                    progress_callback("eta", eta_minutes)
                    eta_str = f"~{eta_minutes:.1f} min left" if remaining > 0 else "Done"
                    progress_callback("success", f"[{processed_count}/{total_news}] Batch of {len(batch_data)} complete ({eta_str})")
                
                # Brief rate limit pause (skip if stopping)
                if self.is_running:
                    time.sleep(2)

            return df
        finally:
            self.is_running = False
            self._is_active = False

    def process_list(self, data_list, progress_callback=None):
        self.is_running = True
        self._is_active = True
        
        # We will modify a copy of the dictionaries, ensuring default N/A for failed classification
        output_list = []
        for item in data_list:
            new_item = dict(item)
            if 'Classification' not in new_item:
                new_item['Classification'] = 'N/A'
            output_list.append(new_item)
        
        try:
            total_news = len(output_list)
            processed_count = 0
            start_time = time.time()

            for batch_start in range(0, total_news, self.batch_size):
                if not self.is_running:
                    break
                    
                batch_end = min(batch_start + self.batch_size, total_news)
                batch_indices = range(batch_start, batch_end)
                
                batch_data = []
                for i, idx in enumerate(batch_indices):
                    row = output_list[idx]
                    # Map to the keys expected by classify_batch
                    # Specifically, try to use title_en and summary_en if available
                    title = row.get('title_en') or row.get('title', '')
                    summary = row.get('summary_en') or row.get('summary', '')
                    
                    batch_data.append({
                        'index': i,
                        'title': title,
                        'summary': summary
                    })
                
                results = self.classify_batch(batch_data, max_retries=3, progress_callback=progress_callback)
                
                if results and 'news' in results:
                    for res in results['news']:
                        b_idx = res.get('NewsIndex')
                        if b_idx is not None and 0 <= b_idx < len(batch_data):
                            actual_idx = batch_start + b_idx
                            output_list[actual_idx]['Classification'] = res.get('Classification', 'N/A')
                            output_list[actual_idx]['RelationScore'] = res.get('RelationScore', -1)
                            output_list[actual_idx]['Gemini_Summary'] = res.get('Summary', 'N/A')
                
                processed_count += len(batch_data)
                
                if progress_callback:
                    progress_callback("progress", processed_count, total_news)
                    elapsed = time.time() - start_time
                    avg_time = elapsed / processed_count
                    remaining = total_news - processed_count
                    eta_minutes = (avg_time * remaining) / 60
                    
                    progress_callback("eta", eta_minutes)
                    eta_str = f"~{eta_minutes:.1f} min left" if remaining > 0 else "Done"
                    progress_callback("success", f"[{processed_count}/{total_news}] Batch of {len(batch_data)} complete ({eta_str})")
                
                # Brief rate limit pause
                if self.is_running:
                    time.sleep(2)

            return output_list
        finally:
            self.is_running = False
            self._is_active = False

    @property
    def is_stopping(self):
        """True when stop was requested but the process hasn't finished yet."""
        return self._is_active and not self.is_running

    def stop(self):
        self.is_running = False
