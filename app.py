import logging

from flask import Flask, jsonify, render_template, request

from config import AppConfig
from database import Database
from services.aggregator import CricketAggregator


logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


app = Flask(__name__)

config = AppConfig.from_env()
aggregator = CricketAggregator(config)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def initialize_database():
    try:
        database = Database()
        database.initialize_schema("schema.sql")

        logger.info(
            "PostgreSQL schema initialized successfully."
        )

    except Exception as exc:
        # Do not crash the whole web service if the database
        # is temporarily unavailable.
        logger.exception(
            "Database initialization failed: %s",
            exc,
        )


initialize_database()


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return render_template(
        "index.html"
    )


# =========================================================
# NORMAL MATCH FEED
# =========================================================

@app.get("/api/matches")
def matches_api():
    return jsonify(
        aggregator.get_feed()
    )


# =========================================================
# SEARCH
# =========================================================

@app.get("/api/search")
def search_api():
    query = request.args.get(
        "q",
        "",
        type=str,
    ).strip()

    return jsonify(
        aggregator.search(query)
    )


# =========================================================
# MATCH DETAILS
# =========================================================

@app.get(
    "/api/matches/<path:match_id>/details"
)
def match_details_api(
    match_id: str,
):
    return jsonify(
        aggregator.get_match_details(
            match_id
        )
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/health")
def health():
    database_status = "not_checked"

    try:
        database = Database()

        result = database.execute(
            "SELECT 1;",
            fetch=True,
        )

        if result:
            database_status = "ok"
        else:
            database_status = "error"

    except Exception as exc:
        logger.exception(
            "Database health check failed: %s",
            exc,
        )

        database_status = "error"

    return jsonify(
        {
            "ok": True,
            "service": "CrixData",
            "database": database_status,
        }
    )


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(config.port),
        debug=False,
    )
