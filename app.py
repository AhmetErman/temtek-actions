import os
import json
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# Data files in the same directory
DATA_FILE = "tech_news_classified.json"
COMPANY_NEWS_FILE = "company_news.json"
COMPANY_ANALYSIS_FILE = "company_analysis.json"
PRODUCTS_FILE = "products.json"
EPREL_FILE = "eprel_products.json"


def _load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}
    return default


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/news')
def get_news():
    data = _load_json(DATA_FILE, [])
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    data.reverse()  # newest parsed first
    return jsonify(data)


@app.route('/companies')
def companies():
    return render_template('companies.html')

@app.route('/api/company-news')
def get_company_news():
    data = _load_json(COMPANY_NEWS_FILE, [])
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
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

@app.route('/api/eprel')
def get_eprel():
    # Absent until eprel_scraper.py has run once; the page degrades gracefully.
    data = _load_json(EPREL_FILE, {"categories": {}})
    if isinstance(data, dict) and "error" in data:
        return jsonify(data), 500
    return jsonify(data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
