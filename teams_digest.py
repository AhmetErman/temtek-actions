"""
Weekly Microsoft Teams trend digest (one-way).

Posts newly-classified, RELEVANT tech-news articles to a Teams channel via a
Power Automate "Workflows" webhook (the supported replacement for the retired
Office 365 Incoming Webhook connector). "Relevant" = a real home-appliance
class (not "Other") with RelationScore >= threshold.

This module only READS tech_news_classified.json - it never modifies the
dataset. It tracks which articles have already been sent in a small state file
(teams_digest_state.json) so each weekly run only shows what is genuinely new.

Setup (done once, by a human):
  Teams -> Workflows -> "Post to a channel when a webhook request is received".
  Copy the generated URL into a GitHub Actions secret named TEAMS_WEBHOOK_URL.

Usage:
  python teams_digest.py                 # incremental: post articles new since last run
  python teams_digest.py --force         # post top current articles, ignore state (testing)
  python teams_digest.py --dry-run       # build the card and print it; never POST
  python teams_digest.py --force --dry-run --limit 5
"""
import os
import json
import argparse
import datetime
import urllib.request
import urllib.error

import config
from taxonomy import normalize_classification


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- state (teams_digest_state.json) -------------------------------------

def load_state(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                s = json.load(f)
            if isinstance(s, dict):
                s.setdefault("sent_urls", [])
                return s
        except Exception:
            pass
    return None  # None => first run / bootstrap


def save_state(path, sent_urls, last_run):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"last_run": last_run, "sent_urls": sorted(sent_urls)},
                  f, indent=2, ensure_ascii=False)


# --- selection -----------------------------------------------------------

def candidate_articles(articles, min_score, exclude_categories):
    """Relevant articles: a real (non-excluded) class with a high enough score.

    Returns them newest-first (the dataset appends new items at the end).
    """
    excl = {c.lower() for c in exclude_categories}
    out = []
    for idx, a in enumerate(articles):
        cls = normalize_classification(a.get("Classification"))
        if not isinstance(cls, str) or cls.lower() in excl:
            continue
        score = a.get("RelationScore")
        if not isinstance(score, int) or score < min_score:
            continue
        if not (a.get("url") and (a.get("title_en") or a.get("title"))):
            continue
        out.append((idx, a))
    # most relevant first, then newest first
    out.sort(key=lambda p: (-p[1]["RelationScore"], -p[0]))
    return [a for _, a in out]


# --- Adaptive Card -------------------------------------------------------

def _truncate(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def build_card(items, title, period_label):
    body = [
        {"type": "TextBlock", "size": "Large", "weight": "Bolder", "text": title, "wrap": True},
        {"type": "TextBlock", "spacing": "None", "isSubtle": True, "wrap": True,
         "text": f"{period_label} · {len(items)} new article{'s' if len(items) != 1 else ''}"},
    ]
    for a in items:
        headline = _truncate(a.get("title_en") or a.get("title"), 140)
        url = a.get("url")
        cls = normalize_classification(a.get("Classification"))
        meta = f"**{cls}** · {a.get('source', '')} · relevance {a.get('RelationScore')}/5"
        summary = _truncate(a.get("Gemini_Summary") or a.get("summary_en") or "", 160)
        block = {
            "type": "Container", "separator": True, "spacing": "Medium", "items": [
                {"type": "TextBlock", "weight": "Bolder", "wrap": True,
                 "text": f"[{headline}]({url})"},
                {"type": "TextBlock", "spacing": "None", "isSubtle": True, "wrap": True,
                 "text": meta},
            ],
        }
        if summary:
            block["items"].append(
                {"type": "TextBlock", "spacing": "None", "wrap": True, "text": summary})
        body.append(block)

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    # Teams message envelope expected by the Workflows webhook.
    return {
        "type": "message",
        "attachments": [
            {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
        ],
    }


# --- delivery ------------------------------------------------------------

def post_to_teams(webhook_url, payload, timeout=20):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url, data=data,
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, resp.status, resp.read().decode("utf-8", "replace")[:300]
    except urllib.error.HTTPError as e:
        return False, e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:
        return False, None, str(e)


# --- main ----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Weekly Teams trend digest.")
    ap.add_argument("--file", default=config.CLASSIFIED_FILENAME)
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print the card; never POST or write state")
    ap.add_argument("--force", action="store_true",
                    help="post top current articles ignoring state (for testing); "
                         "does not update state")
    ap.add_argument("--limit", type=int, default=None,
                    help="override max number of articles in the digest")
    args = ap.parse_args()

    cfg = getattr(config, "TEAMS_DIGEST", {}) or {}
    if not cfg.get("enabled", True) and not args.force:
        print("TEAMS_DIGEST disabled in config; nothing to do.")
        return

    state_path = cfg.get("state_file", "teams_digest_state.json")
    min_score = cfg.get("min_relation_score", 3)
    max_items = args.limit or cfg.get("max_items", 12)
    exclude = cfg.get("exclude_categories", ["Other"])
    title = cfg.get("title", "Weekly Appliance Tech Digest")

    with open(args.file, "r", encoding="utf-8") as f:
        articles = json.load(f)
    candidates = candidate_articles(articles, min_score, exclude)
    print(f"{len(candidates)} relevant candidate articles (score >= {min_score}, "
          f"excluding {exclude}).")

    state = load_state(state_path)
    bootstrap = state is None
    sent = set(state["sent_urls"]) if state else set()

    if args.force:
        selected = candidates[:max_items]
        mode = "force"
    elif bootstrap:
        selected = candidates[:max_items]
        mode = "bootstrap"
    else:
        new = [a for a in candidates if a.get("url") not in sent]
        selected = new[:max_items]
        mode = "incremental"
    print(f"Mode: {mode}; selected {len(selected)} article(s).")

    if not selected and not args.force:
        print("Nothing new to post.")
        if not args.dry_run and not bootstrap:
            save_state(state_path, sent, _now())  # refresh last_run
        return

    period = datetime.datetime.now(datetime.timezone.utc).strftime("Week of %d %b %Y")
    payload = build_card(selected, title, period)

    if args.dry_run:
        print("\n[dry-run] payload that WOULD be posted:\n")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    webhook = os.getenv(cfg.get("webhook_env", "TEAMS_WEBHOOK_URL"))
    if not webhook:
        print(f"ERROR: webhook URL not set (env {cfg.get('webhook_env', 'TEAMS_WEBHOOK_URL')}).")
        raise SystemExit(1)

    ok, status, info = post_to_teams(webhook, payload, cfg.get("request_timeout", 20))
    print(f"POST -> ok={ok} status={status} {info}")
    if not ok:
        raise SystemExit(1)

    # Persist what we sent (force mode is non-committal: leave state untouched).
    if not args.force:
        if bootstrap:
            sent = {a.get("url") for a in candidates if a.get("url")}  # suppress backlog
        else:
            sent |= {a.get("url") for a in selected if a.get("url")}
        save_state(state_path, sent, _now())
        print(f"State saved: {len(sent)} URLs marked sent.")


if __name__ == "__main__":
    main()
