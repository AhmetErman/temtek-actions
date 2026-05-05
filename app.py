import os
import json
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# The data file is in the same directory
DATA_FILE = "tech_news_classified.json"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/news')
def get_news():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                news_data = json.load(f)
            # Reverse order so newest parsed is first
            news_data.reverse() 
            return jsonify(news_data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify([])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
