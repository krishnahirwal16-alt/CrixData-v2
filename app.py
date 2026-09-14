from flask import Flask, jsonify, render_template, request

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
    return jsonify(
        aggregator.get_feed()
    )


@app.get("/api/search")
def search_api():
    query = request.args.get(
        "q",
        "",
        type=str,
    ).strip().lower()

    feed = aggregator.get_feed()

    upcoming = feed.get(
        "upcoming",
        [],
    )

    finished = feed.get(
        "finished",
        [],
    )

    # Search is intentionally limited to
    # upcoming + finished matches.
    searchable_matches = (
        upcoming + finished
    )

    # -------------------------------------------------
    # AUTOCOMPLETE / SUGGESTIONS
    # -------------------------------------------------

    suggestions = set()

    for match in searchable_matches:
        for field in (
            "competition",
            "match_type",
            "team1",
            "team2",
        ):
            value = str(
                match.get(field) or ""
            ).strip()

            if value:
                suggestions.add(value)

    sorted_suggestions = sorted(
        suggestions,
        key=lambda value: value.lower(),
    )

    if query:
        suggestions = [
            value
            for value in sorted_suggestions
            if value.lower().startswith(query)
        ][:12]
    else:
        suggestions = sorted_suggestions[:12]

    # -------------------------------------------------
    # MATCH SEARCH
    # -------------------------------------------------

    results = []

    if query:
        for match in searchable_matches:

            searchable_text = " ".join(
                [
                    str(
                        match.get("competition")
                        or ""
                    ),
                    str(
                        match.get("match_type")
                        or ""
                    ),
                    str(
                        match.get("team1")
                        or ""
                    ),
                    str(
                        match.get("team2")
                        or ""
                    ),
                    str(
                        match.get("status_text")
                        or ""
                    ),
                ]
            ).lower()

            if query in searchable_text:
                results.append(match)

    return jsonify(
        {
            "ok": True,
            "query": query,
            "suggestions": suggestions,
            "counts": {
                "upcoming": sum(
                    1
                    for match in results
                    if match.get("status")
                    == "upcoming"
                ),
                "finished": sum(
                    1
                    for match in results
                    if match.get("status")
                    == "finished"
                ),
                "total": len(results),
            },
            "upcoming": [
                match
                for match in results
                if match.get("status")
                == "upcoming"
            ],
            "finished": [
                match
                for match in results
                if match.get("status")
                == "finished"
            ],
        }
    )


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


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "CrixData",
        }
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(config.port),
        debug=False,
    )
