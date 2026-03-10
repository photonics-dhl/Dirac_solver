"""
Dirac Solver — web application entry point.

Run with:
    python src/app.py

Then open http://localhost:5000 in your browser.
"""

import os

from flask import Flask

app = Flask(__name__)


@app.route("/")
def index():
    return "<h1>Dirac Solver</h1><p>Web interface coming soon.</p>"


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug)
