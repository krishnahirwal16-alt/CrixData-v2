import logging

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
)

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
    Ensure PostgreSQL schema exists and the competition
    catalog is seeded.
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
# SECURE SYNC UI
# =========================================================

@app.get("/admin/sync-ui")
def sync_ui():

    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >
    <title>CrixData Admin Sync</title>

    <style>
        body {
            font-family:
                Arial,
                sans-serif;

            max-width: 700px;

            margin: 60px auto;

            padding: 24px;

            background: #f5f7fb;

            color: #172033;
        }

        .card {
            background: white;

            padding: 28px;

            border-radius: 16px;

            box-shadow:
                0 10px 30px
                rgba(0, 0, 0, 0.08);
        }

        input {
            width: 100%;

            box-sizing: border-box;

            padding: 14px;

            margin: 12px 0;

            border:
                1px solid #dbe2ea;

            border-radius: 10px;

            font-size: 15px;
        }

        button {
            padding:
                12px 18px;

            border: 0;

            border-radius: 10px;

            cursor: pointer;

            font-weight: 700;
        }

        #run {
            background: #1476c6;

            color: white;
        }

        #output {
            margin-top: 20px;

            padding: 16px;

            background: #f8fafc;

            border-radius: 10px;

            white-space: pre-wrap;

            overflow-wrap: anywhere;
        }

        .warning {
            color: #a15c00;

            font-size: 14px;
        }
    </style>
</head>

<body>

<div class="card">

    <h1>CrixData Provider Sync</h1>

    <p>
        This page is for administrator use only.
    </p>

    <p class="warning">
        Never share your sync token.
    </p>

    <input
        id="token"
        type="password"
        placeholder="Enter SYNC_ADMIN_TOKEN"
        autocomplete="off"
    >

    <button id="run">
        Run Competition Sync
    </button>

    <div id="output">
        Ready.
    </div>

</div>

<script>

const button =
    document.getElementById(
        "run"
    );

const tokenInput =
    document.getElementById(
        "token"
    );

const output =
    document.getElementById(
        "output"
    );


button.addEventListener(
    "click",
    async () => {

        const token =
            tokenInput.value.trim();

        if (!token) {

            output.textContent =
                "Please enter the sync token.";

            return;
        }

        button.disabled = true;

        output.textContent =
            "Running sync... Please wait.";

        try {

            const response =
                await fetch(
                    "/admin/sync",
                    {
                        method: "POST",

                        headers: {
                            "X-Sync-Token":
                                token,
                            "Accept":
                                "application/json",
                        },
                    }
                );

            const data =
                await response.json();

            output.textContent =
                JSON.stringify(
                    data,
                    null,
                    2
                );

        } catch (error) {

            output.textContent =
                "Request failed: "
                + error;

        } finally {

            button.disabled = false;

            tokenInput.value = "";
        }
    }
);

</script>

</body>
</html>
"""


# =========================================================
# SECURE PROVIDER SYNC
# =========================================================

@app.post("/admin/sync")
def admin_sync():

    provided_token = (
        request.headers.get(
            "X-Sync-Token",
            "",
        ).strip()
    )

    expected_token = (
        config.sync_admin_token
    )

    if (
        not expected_token
        or provided_token != expected_token
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
