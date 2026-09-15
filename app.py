import logging

from flask import Flask, jsonify, render_template, request

from config import AppConfig
from database import Database
from seed_data import seed_competitions
from services.aggregator import CricketAggregator


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
)

logger = logging.getLogger(
    __name__
)


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

config = AppConfig.from_env()

aggregator = CricketAggregator(
    config
)


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def initialize_database():
    """
    Ensure the PostgreSQL schema exists and the centralized
    competition catalog is seeded.
    """

    try:
        database = Database()

        database.initialize_schema(
            "schema.sql"
        )

        logger.info(
            "PostgreSQL schema initialized."
        )

        seeded = seed_competitions()

        logger.info(
            "Competition catalog initialized: %s competitions.",
            seeded,
        )

    except Exception as exc:

        logger.exception(
            "Database initialization failed: %s",
            exc,
        )


initialize_database()
# =========================================================
# PROTECTED PROVIDER SYNC
# =========================================================

@app.get("/admin/sync")
def admin_sync():

    sync_token = request.args.get(
        "token",
        "",
        type=str,
    )

    expected_token = config.sync_admin_token

    if (
        not expected_token
        or sync_token != expected_token
    ):
        return jsonify(
            {
                "ok": False,
                "error": "Unauthorized",
            }
        ), 401

    try:
        from services.sync import run_sync

        result = run_sync()

        return jsonify(
            result
        )

    except Exception as exc:

        logger.exception(
            "Manual provider sync failed: %s",
            exc,
        )

        return jsonify(
            {
                "ok": False,
                "error": "Sync failed",
            }
        ), 500

# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():
    return render_template(
        "index.html"
    )


# =========================================================
# MATCH FEED
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
        aggregator.search(
            query
        )
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

    required_tables = [
        "competitions",
        "competition_aliases",
        "seasons",
        "teams",
        "team_aliases",
        "venues",
        "matches",
        "match_scores",
        "competition_sources",
        "season_sources",
        "team_sources",
    ]

    found_tables = []

    competition_count = None
    alias_count = None

    database_status = "error"

    try:

        database = Database()

        # ---------------------------------------------
        # Check all required tables
        # ---------------------------------------------

        table_result = database.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = ANY(%s)
            ORDER BY table_name;
            """,
            (
                required_tables,
            ),
            fetch=True,
        )

        found_tables = [
            row[0]
            for row in table_result
        ]

        # ---------------------------------------------
        # Competition count
        # ---------------------------------------------

        competition_result = database.execute(
            """
            SELECT COUNT(*)
            FROM competitions;
            """,
            fetch=True,
        )

        if competition_result:
            competition_count = (
                competition_result[0][0]
            )

        # ---------------------------------------------
        # Alias count
        # ---------------------------------------------

        alias_result = database.execute(
            """
            SELECT COUNT(*)
            FROM competition_aliases;
            """,
            fetch=True,
        )

        if alias_result:
            alias_count = (
                alias_result[0][0]
            )

        # ---------------------------------------------
        # Database status
        # ---------------------------------------------

        database_status = (
            "ok"
            if len(found_tables)
            == len(required_tables)
            else "incomplete"
        )

    except Exception as exc:

        logger.exception(
            "Database health check failed: %s",
            exc,
        )

    return jsonify(
        {
            "ok": True,

            "service":
                "CrixData",

            "database":
                database_status,

            "required_tables":
                required_tables,

            "found_tables":
                found_tables,

            "table_count":
                len(found_tables),

            "competition_count":
                competition_count,

            "competition_alias_count":
                alias_count,
        }
    )


# =========================================================
# LOCAL DEVELOPMENT
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            config.port
        ),
        debug=False,
    )
