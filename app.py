from flask import Flask, jsonify, render_template

from config import AppConfig
from services.aggregator import CricketAggregator

app = Flask(__name__)

config = AppConfig.from_env()
aggregator = CricketAggregator(config)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/matches")
def matches_api():
    return jsonify(aggregator.get_feed())


@app.get("/api/matches/<path:match_id>/details")
def match_details_api(match_id: str):
    return jsonify(aggregator.get_match_details(match_id))


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "CrixData"})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(config.port),
        debug=False,
    )
