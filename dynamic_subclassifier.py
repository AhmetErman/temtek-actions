"""
Layer-2 dynamic (unsupervised) subclassification of the 'Other' bucket.

The primary classifier (gemini_filter) sorts news into a FIXED home-appliance
taxonomy (taxonomy.HARD_CLASSES). Everything that does not fit becomes 'Other' -
a large, opaque bucket that can hide meaningful recurring themes.

This module runs a SECOND, unsupervised pass over the 'Other' items only. It
asks Gemini to group them into specific, reusable sub-topics (e.g. "Generative
AI", "Gaming", "Automotive & EV"). Discovered sub-classes are persisted to a
registry file (dynamic_classes.json) and fed back into the prompt on every run,
so the sub-taxonomy UNDER 'Other' grows over time. The fixed top-level classes
are never touched: this layer lives strictly below 'Other'.

Each processed article gains two fields (only when its class is 'Other'):
    OtherSubclass       - the dynamic sub-class name
    OtherSubclassScore  - 1-5 fit score

Design notes:
- Batches are processed SEQUENTIALLY and the growing registry is injected into
  each batch's prompt, so later batches reuse the sub-classes earlier ones
  discovered instead of inventing near-duplicates.
- Fault-isolated: a failure in here is logged and never propagated into the main
  scrape/classify pipeline.

Standalone (re)classify the whole existing dataset:
    python dynamic_subclassifier.py            # process config.CLASSIFIED_FILENAME
    python dynamic_subclassifier.py --dry-run  # no API calls; show what it would do
    python dynamic_subclassifier.py --file other.json --no-backup
"""
import os
import json
import time
import argparse
import datetime
from collections import Counter

import config
from taxonomy import normalize_classification

try:
    from google import genai
    from google.genai import types
    _GENAI_OK = True
except Exception:  # pragma: no cover - import guard
    _GENAI_OK = False


_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "NewsIndex": {"type": "INTEGER"},
                    "Subclass": {"type": "STRING"},
                    "IsNew": {"type": "BOOLEAN"},
                    "NewClassDescription": {"type": "STRING"},
                    "RelationScore": {"type": "INTEGER"},
                },
                "required": ["NewsIndex", "Subclass", "IsNew", "RelationScore"],
            },
        }
    },
    "required": ["items"],
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- registry (dynamic_classes.json) I/O ---------------------------------

def load_registry(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                reg = json.load(f)
            if isinstance(reg, dict) and isinstance(reg.get("classes"), list):
                return reg
        except Exception:
            pass
    return {"version": 1, "updated_at": None, "classes": []}


def save_registry(path, registry):
    registry["updated_at"] = _now()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def format_classes_for_prompt(registry):
    classes = registry.get("classes", [])
    if not classes:
        return "EXISTING SUB-CLASSES: (none yet - you are starting the taxonomy)"
    lines = ["EXISTING SUB-CLASSES (reuse these EXACT names whenever one fits):"]
    for c in classes:
        desc = c.get("description", "") or ""
        lines.append(f"- {c['name']}: {desc}")
    return "\n".join(lines)


def _article_text(a, i):
    title = a.get("title_en") or a.get("title") or ""
    summary = a.get("summary_en") or a.get("summary") or ""
    return f"--- NEWS {i} ---\nTitle: {title}\nSummary: {summary}\n"


class DynamicSubclassifier:
    def __init__(self, api_key, models, batch_size, store_path, base_instruction):
        if not _GENAI_OK:
            raise RuntimeError("google-genai is not available")
        self.client = genai.Client(api_key=api_key)
        self.models = list(models) if isinstance(models, (list, tuple)) else [models]
        self.model_idx = 0
        self.batch_size = int(batch_size)
        self.store_path = store_path
        self.base_instruction = base_instruction or ""
        self.registry = load_registry(store_path)

    # registry helpers -----------------------------------------------------
    def _names_lower(self):
        return {c["name"].strip().lower(): c["name"]
                for c in self.registry["classes"] if c.get("name")}

    def _register(self, name, description):
        """Add a new sub-class if unseen; return the canonical stored name."""
        low = name.strip().lower()
        existing = self._names_lower()
        if low in existing:
            return existing[low]
        canonical = name.strip()
        self.registry["classes"].append({
            "name": canonical,
            "description": (description or "").strip(),
            "created_at": _now(),
            "count": 0,
        })
        return canonical

    # gemini call ----------------------------------------------------------
    def _generate(self, system_instruction, user_text, max_retries=4):
        cfg = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_SCHEMA,
            system_instruction=system_instruction,
        )
        last_err = None
        for attempt in range(max_retries):
            model = self.models[self.model_idx]
            try:
                resp = self.client.models.generate_content(
                    model=model, contents=user_text, config=cfg,
                )
                if resp.text:
                    stripped = resp.text.strip()
                    if not stripped.startswith("{"):
                        raise ValueError("non-JSON response")
                    obj, _ = json.JSONDecoder().raw_decode(stripped)
                    return obj
                raise ValueError("empty response (possible block)")
            except Exception as e:
                last_err = e
                es = str(e)
                if ("503" in es or "429" in es) and self.model_idx < len(self.models) - 1:
                    old = self.models[self.model_idx]
                    self.model_idx += 1
                    print(f"  -> model {old} failed (503/429), switching to {self.models[self.model_idx]}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
        print(f"  -> batch failed after {max_retries} attempts: {last_err}")
        return {"items": []}

    # batch processing -----------------------------------------------------
    def _process_batch(self, batch):
        """batch: list of article dicts (references). Tags them in place."""
        system_instruction = (
            self.base_instruction
            + "\n\n" + format_classes_for_prompt(self.registry)
        )
        user_text = "Assign each of the following news items to a sub-topic.\n\n"
        user_text += "\n".join(_article_text(a, i) for i, a in enumerate(batch))

        obj = self._generate(system_instruction, user_text)
        results = obj.get("items", []) if isinstance(obj, dict) else []

        tagged = 0
        for res in results:
            bi = res.get("NewsIndex")
            if bi is None or not (0 <= bi < len(batch)):
                continue
            name = (res.get("Subclass") or "").strip()
            if not name or name.lower() == "other":
                continue
            canonical = self._register(name, res.get("NewClassDescription"))
            art = batch[bi]
            art["OtherSubclass"] = canonical
            art["OtherSubclassScore"] = res.get("RelationScore", -1)
            tagged += 1
        return tagged

    def subclassify(self, other_items, progress_callback=None):
        """Tag each 'Other' article in other_items with a dynamic sub-class."""
        total = len(other_items)
        if not total:
            return
        start = time.time()
        done = 0
        for bstart in range(0, total, self.batch_size):
            batch = other_items[bstart:bstart + self.batch_size]
            self._process_batch(batch)
            done += len(batch)
            elapsed = time.time() - start
            eta = (elapsed / done) * (total - done) / 60 if done else 0
            msg = (f"[{done}/{total}] sub-classified "
                   f"({len(self.registry['classes'])} classes so far, ~{eta:.1f} min left)")
            print(f"  -> {msg}")
            if progress_callback:
                progress_callback("success", msg)
            if done < total:
                time.sleep(2)

    def recount(self, all_articles):
        counts = Counter(a.get("OtherSubclass") for a in all_articles
                         if a.get("OtherSubclass"))
        for c in self.registry["classes"]:
            c["count"] = counts.get(c["name"], 0)

    def save(self):
        save_registry(self.store_path, self.registry)


# --- API key (env or .env, mirrors scraper_w_filter) ----------------------

def load_api_key():
    key = os.getenv("GEMINI_API")
    if not key and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("GEMINI_API="):
                    key = line.strip().split("=", 1)[1]
                    break
    return key


# --- standalone reclassification of an existing dataset -------------------

def main():
    ap = argparse.ArgumentParser(description="Dynamic 'Other' subclassification.")
    ap.add_argument("--file", default=config.CLASSIFIED_FILENAME,
                    help="classified news JSON to (re)process")
    ap.add_argument("--dry-run", action="store_true",
                    help="no API calls; report what would happen")
    ap.add_argument("--no-backup", action="store_true",
                    help="do not write a .bak copy before saving")
    ap.add_argument("--only-untagged", action="store_true",
                    help="only subclassify 'Other' items that lack OtherSubclass "
                         "(incremental: leaves already-tagged items untouched)")
    args = ap.parse_args()

    cfg = getattr(config, "DYNAMIC_SUBCLASS", {}) or {}
    store_path = cfg.get("store_file", "dynamic_classes.json")

    with open(args.file, "r", encoding="utf-8") as f:
        articles = json.load(f)
    print(f"Loaded {len(articles)} articles from {args.file}")

    # 1) Normalize primary labels (repairs Other/other + IoT drift).
    changed = 0
    for a in articles:
        old = a.get("Classification")
        if old is not None:
            new = normalize_classification(old)
            if new != old:
                a["Classification"] = new
                changed += 1
    print(f"Normalized {changed} primary labels.")

    # 2) Collect the 'Other' items - the input to the dynamic layer.
    other_items = [a for a in articles if a.get("Classification") == "Other"]
    if args.only_untagged:
        other_items = [a for a in other_items if not a.get("OtherSubclass")]
        print(f"Found {len(other_items)} UNTAGGED 'Other' articles to subclassify "
              f"(incremental).")
    else:
        print(f"Found {len(other_items)} 'Other' articles to subclassify.")

    registry = load_registry(store_path)
    if args.dry_run:
        print("\n[dry-run] no API calls made.")
        print(f"[dry-run] registry currently has {len(registry['classes'])} sub-classes:")
        for c in registry["classes"]:
            print(f"    - {c['name']} ({c.get('count', 0)})")
        print(f"[dry-run] would send {len(other_items)} items in batches of "
              f"{cfg.get('batch_size', 25)}.")
        return

    api_key = load_api_key()
    if not api_key:
        print("GEMINI_API key not found (env or .env). Aborting.")
        return

    sub = DynamicSubclassifier(
        api_key=api_key,
        models=config.GEMINI_MODELS,
        batch_size=cfg.get("batch_size", 25),
        store_path=store_path,
        base_instruction=cfg.get("base_instruction", ""),
    )

    print(f"\n=== Dynamic subclassification ({len(other_items)} items) ===")
    sub.subclassify(other_items)
    sub.recount(articles)

    # 3) Persist registry + dataset (back up the dataset first).
    sub.save()
    if not args.no_backup:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{args.file}.{ts}.predynamic.bak"
        with open(backup, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=4, ensure_ascii=False)
        print(f"Backed up original to {backup}")

    with open(args.file, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=4, ensure_ascii=False)
    print(f"Saved {args.file} and {store_path}")

    # 4) Report the discovered taxonomy.
    print("\n=== Dynamic 'Other' sub-taxonomy ===")
    for c in sorted(sub.registry["classes"], key=lambda x: -x.get("count", 0)):
        print(f"  {c.get('count', 0):4d}  {c['name']}")
    tagged = sum(1 for a in other_items if a.get("OtherSubclass"))
    print(f"\nTagged {tagged}/{len(other_items)} 'Other' items with a sub-class.")


if __name__ == "__main__":
    main()
