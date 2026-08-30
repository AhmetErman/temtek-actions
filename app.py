import os
import json
from flask import Flask, render_template, jsonify, request

app = Flask(__name__)

# Data files in the same directory
DATA_FILE = "tech_news_classified.json"
COMPANY_NEWS_FILE = "company_news.json"
COMPANY_ANALYSIS_FILE = "company_analysis.json"
PRODUCTS_FILE = "products.json"
EPREL_FILE = "eprel_products.json"
TECH_EVIDENCE_FILE = "tech_evidence.json"

# Turkish sidecars written by translate_data.py: {url: {field: translation}}.
# They hold only the language-dependent fields, so classification and scores
# have exactly one home and cannot drift between the two languages.
NEWS_TR_FILE = "tech_news_tr.json"
COMPANY_TR_FILE = "company_news_tr.json"
CLASSES_TR_FILE = "dynamic_classes_tr.json"

SUPPORTED_LANGS = ("en", "tr")


def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}
    return default


def _lang():
    """Requested language, defaulting to English for anything unrecognised."""
    value = (request.args.get('lang') or 'en').lower()
    return value if value in SUPPORTED_LANGS else 'en'


def _merge_tr(records, sidecar, fields):
    """Overlay Turkish text onto the records the dashboard already expects.

    ``fields`` maps a sidecar key to the record key it replaces, so the
    frontend reads the same field names in both languages and needs no
    per-language branches. A record with no translation yet keeps its English
    text rather than rendering blank — a partial backfill degrades to mixed
    language, never to an empty feed.
    """
    if not isinstance(sidecar, dict) or not sidecar:
        return records
    for rec in records:
        tr = sidecar.get(rec.get('url'))
        if not tr:
            continue
        for src, dest in fields.items():
            if tr.get(src):
                rec[dest] = tr[src]
    return records


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/news')
def get_news():
    data = _load_json(DATA_FILE, [])
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    data.reverse()  # newest parsed first
    if _lang() == 'tr':
        # title_en/summary_en are what the page renders, so the Turkish text
        # goes into those same keys.
        _merge_tr(data, _load_json(NEWS_TR_FILE, {}), {
            'title': 'title_en',
            'summary': 'summary_en',
            'gemini': 'Gemini_Summary',
        })
        classes = _load_json(CLASSES_TR_FILE, {})
        if isinstance(classes, dict) and classes:
            for rec in data:
                sub = rec.get('OtherSubclass')
                if sub and classes.get(sub):
                    rec['OtherSubclass'] = classes[sub]
    return jsonify(data)


@app.route('/companies')
def companies():
    return render_template('companies.html')

@app.route('/api/company-news')
def get_company_news():
    data = _load_json(COMPANY_NEWS_FILE, [])
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    if _lang() == 'tr':
        _merge_tr(data, _load_json(COMPANY_TR_FILE, {}), {
            'title': 'title',
            'summary': 'summary',
        })
    return jsonify(data)

@app.route('/api/company-analysis')
def get_company_analysis():
    data = _load_json(COMPANY_ANALYSIS_FILE, {})
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    return jsonify(data)


@app.route('/beyond')
def beyond():
    return render_template('beyond.html')


@app.route('/products')
def products():
    return render_template('products.html')

@app.route('/api/products')
def get_products():
    data = _load_json(PRODUCTS_FILE, {})
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    return jsonify(data)

@app.route('/eprel')
def eprel():
    return render_template('eprel.html')

@app.route('/api/tech-evidence')
def get_tech_evidence():
    # Written by tech_matrix.py; absent until that job has run once.
    data = _load_json(TECH_EVIDENCE_FILE, {})
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    return jsonify(data)

@app.route('/api/eprel')
def get_eprel():
    # Absent until eprel_scraper.py has run once; the page degrades gracefully.
    data = _load_json(EPREL_FILE, {"categories": {}})
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    return jsonify(data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
