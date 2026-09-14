import json
import urllib.request
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, jsonify

app = Flask(__name__)

# ---------------------------------------------------------
# CrixData configuration
# ---------------------------------------------------------

IST = pytz.timezone("Asia/Kolkata")

# ESPN personalized cricket header gives the currently active
# cricket series/competitions and their events.
DISCOVERY_URL = (
    "https://site.api.espn.com/apis/personalized/v2/scoreboard/header"
    "?sport=cricket&region=in&tz=Asia/Calcutta"
)

# Keep only recent finished matches on the main page.
# This prevents very old archived matches (for example, 2008)
# from appearing in the FINISHED tab.
FINISHED_LOOKBACK_DAYS = 14

# Refreshing the page from the browser is handled in index.html.
# No background worker is required.


# ---------------------------------------------------------
# HTTP / JSON helpers
# ---------------------------------------------------------

def fetch_json(url, timeout=15):
    """Fetch JSON from a public endpoint with a browser-like User-Agent."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_event_datetime(raw_date):
    """
    Convert ESPN event date into a timezone-aware datetime.
    Supports ISO timestamps with Z or an explicit offset.
    """
    if not raw_date:
        return None

    try:
        value = raw_date.strip()

        if value.endswith("Z"):
            value = value[:-1] + "+00:00"

        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)

        return dt.astimezone(pytz.utc)

    except (ValueError, TypeError):
        return None


def format_event_time(raw_date):
    """Return date/day and IST time for frontend display."""
    dt_utc = parse_event_datetime(raw_date)

    if not dt_utc:
        return {
            "day": "Date TBD",
            "ist_time": "Time TBD",
            "timestamp": None,
        }

    dt_ist = dt_utc.astimezone(IST)

    return {
        "day": dt_ist.strftime("%A, %b %d, %Y"),
        "ist_time": dt_ist.strftime("%I:%M %p IST"),
        "timestamp": dt_utc.timestamp(),
    }


# ---------------------------------------------------------
# Match status engine
# ---------------------------------------------------------

def normalize_status(event, competition):
    """
    Convert ESPN's raw status into exactly one CrixData status.

    Desired behavior:
        post/completed/result -> FINISHED
        in/live              -> LIVE
        pre/scheduled         -> UPCOMING

    Important:
    A toss by itself does NOT make the match LIVE.
    The match must actually be in progress.
    """

    status = competition.get("status", {}) or {}
    status_type = status.get("type", {}) or {}

    state = str(status_type.get("state", "")).lower().strip()
    completed = bool(status_type.get("completed", status.get("completed", False)))

    # 1) Result/completed always wins.
    if state == "post" or completed:
        return "finished"

    # 2) Match is actually in progress.
    if state == "in":
        return "live"

    # 3) Everything else is treated as not started yet.
    return "upcoming"


def get_status_detail(competition):
    """Get the human-readable ESPN status text."""
    status = competition.get("status", {}) or {}
    status_type = status.get("type", {}) or {}

    return (
        status_type.get("detail")
        or status_type.get("shortDetail")
        or status_type.get("description")
        or "Scheduled"
    )


# ---------------------------------------------------------
# Match normalization
# ---------------------------------------------------------

def build_match_info(event, competition, series_name):
    competitors = competition.get("competitors", []) or []

    t1 = "Team A"
    t2 = "Team B"
    t1_score = ""
    t2_score = ""

    if len(competitors) > 0:
        team = competitors[0].get("team", {}) or {}
        t1 = (
            team.get("displayName")
            or team.get("shortDisplayName")
            or team.get("name")
            or "Team A"
        )
        t1_score = competitors[0].get("score", "") or ""

    if len(competitors) > 1:
        team = competitors[1].get("team", {}) or {}
        t2 = (
            team.get("displayName")
            or team.get("shortDisplayName")
            or team.get("name")
            or "Team B"
        )
        t2_score = competitors[1].get("score", "") or ""

    raw_date = event.get("date", "")
    time_info = format_event_time(raw_date)

    venue_obj = competition.get("venue", {}) or {}
    venue = venue_obj.get("fullName") or venue_obj.get("name") or "Venue TBD"

    status_bucket = normalize_status(event, competition)

    return {
        "id": str(event.get("id", "")),
        "title": event.get("name", f"{t1} vs {t2}"),
        "series": series_name or "Cricket",
        "t1": t1,
        "t1_score": t1_score if t1_score else "Yet to bat",
        "t2": t2,
        "t2_score": t2_score if t2_score else "Yet to bat",
        "status": get_status_detail(competition),
        "bucket": status_bucket,
        "venue": venue,
        "day": time_info["day"],
        "ist_time": time_info["ist_time"],
        "timestamp": time_info["timestamp"],
    }


# ---------------------------------------------------------
# Global cricket discovery
# ---------------------------------------------------------

def fetch_global_cricket():
    """
    Discover active cricket series globally and combine their events.

    The old CrixData version queried one hard-coded numeric endpoint:
        /cricket/13840/scoreboard

    That is the main reason CrixData can show an old 2008 match while
    current LIVE/UPCOMING tabs are empty. The new version first discovers
    currently active cricket series and then reads their events.
    """

    matches = {
        "live": [],
        "upcoming": [],
        "finished": [],
    }

    try:
        discovery = fetch_json(DISCOVERY_URL)

        sports = discovery.get("sports", []) or []
        if not sports:
            return matches

        # The first sports entry is Cricket because sport=cricket was requested.
        cricket = sports[0] or {}
        leagues = cricket.get("leagues", []) or []

        now_utc = datetime.now(pytz.utc)
        finished_cutoff = now_utc - timedelta(days=FINISHED_LOOKBACK_DAYS)

        seen_ids = set()

        for league in leagues:
            series_name = (
                league.get("name")
                or league.get("shortName")
                or league.get("abbreviation")
                or "Cricket"
            )

            events = league.get("events", []) or []

            for event in events:
                event_id = str(event.get("id", "")).strip()

                if not event_id or event_id in seen_ids:
                    continue

                competitions = event.get("competitions", []) or []
                competition = competitions[0] if competitions else {}

                match = build_match_info(event, competition, series_name)

                event_dt = parse_event_datetime(event.get("date", ""))
                bucket = match["bucket"]

                # Never let old archived matches pollute the current FINISHED tab.
                if bucket == "finished":
                    if event_dt is None or event_dt < finished_cutoff:
                        continue

                seen_ids.add(event_id)
                matches[bucket].append(match)

        # Sort for a scorecard-style experience.
        matches["live"].sort(key=lambda m: m["timestamp"] or 0)
        matches["upcoming"].sort(
            key=lambda m: m["timestamp"] if m["timestamp"] is not None else float("inf")
        )
        matches["finished"].sort(
            key=lambda m: m["timestamp"] if m["timestamp"] is not None else 0,
            reverse=True,
        )

    except Exception as exc:
        # Keep the website alive even if the external feed has a temporary issue.
        print(f"CrixData feed error: {exc}")

    return matches


# ---------------------------------------------------------
# Routes
# ---------------------------------------------------------

@app.route("/")
def home():
    matches = fetch_global_cricket()
    return render_template("index.html", matches=matches)


@app.route("/api/matches")
def api_matches():
    """
    JSON endpoint for future AJAX/live-refresh features.
    """
    return jsonify(fetch_global_cricket())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
