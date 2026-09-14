import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pytz
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# ============================================================
# CrixData — CricketData.org production version
# ============================================================

API_URL = "https://api.cricapi.com/v1/cricScore"
IST = pytz.timezone("Asia/Kolkata")

# Free plan protection:
# 15-minute cache = at most 96 API calls/day if the site is
# continuously requested.
CACHE_SECONDS = 15 * 60

_cache = {
    "timestamp": 0.0,
    "data": None,
}


# ============================================================
# CricketData API
# ============================================================

def get_api_key():
    """Read the secret from Render Environment Variables."""
    api_key = os.getenv("CRICKET_API_KEY", "").strip()

    if not api_key:
        raise RuntimeError(
            "CRICKET_API_KEY is missing in Render Environment Variables."
        )

    return api_key


def fetch_cricscore():
    """
    Fetch the CricketData eCricScore feed.

    API key is NEVER hard-coded in this file.
    Render supplies it through CRICKET_API_KEY.
    """
    params = urllib.parse.urlencode({
        "apikey": get_api_key()
    })

    url = f"{API_URL}?{params}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CrixData/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(
            response.read().decode("utf-8", errors="replace")
        )

    if payload.get("status") != "success":
        raise RuntimeError(
            f"CricketData returned status={payload.get('status')}"
        )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError("CricketData returned invalid data.")

    return data


# ============================================================
# Date / time
# ============================================================

def parse_match_datetime(match):
    """
    CricketData's dateTimeGMT is treated as UTC.

    Example:
        2026-09-20T10:00:00
    """
    raw = match.get("dateTimeGMT")

    if not raw:
        return None

    raw = str(raw).strip()

    try:
        dt = datetime.fromisoformat(
            raw.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except ValueError:
        return None


def format_match_datetime(match):
    dt_utc = parse_match_datetime(match)

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


# ============================================================
# Status normalization
# ============================================================

RESULT_MS = {
    "result",
    "completed",
    "complete",
    "finished",
    "post",
}

LIVE_MS = {
    "live",
    "in",
    "inprogress",
    "in_progress",
    "ongoing",
    "started",
    "playing",
}

RESULT_PHRASES = (
    "won by",
    "won",
    "draw",
    "tied",
    "tie",
    "no result",
    "abandoned",
    "cancelled",
    "canceled",
)


def get_bucket(match):
    """
    Convert CricketData fields to one CrixData section:

        live
        upcoming
        finished

    Priority:
      1. result/completed
      2. explicit live
      3. live score evidence
      4. upcoming
    """

    ms = str(match.get("ms") or "").strip().lower()
    status = str(match.get("status") or "").strip().lower()

    # A result must never appear in LIVE.
    if ms in RESULT_MS:
        return "finished"

    if any(phrase in status for phrase in RESULT_PHRASES):
        return "finished"

    # Explicit live state.
    if ms in LIVE_MS:
        return "live"

    # If score innings data exists and the scheduled start time has passed,
    # treat it as live unless a result was already detected above.
    score = match.get("score")
    start_time = parse_match_datetime(match)

    if (
        isinstance(score, list)
        and score
        and start_time is not None
        and start_time <= datetime.now(timezone.utc)
    ):
        return "live"

    # Fixture / not started.
    return "upcoming"


# ============================================================
# Scores
# ============================================================

def get_score(match, team_number):
    """
    Prefer CricketData's t1s/t2s fields.
    Fall back to the score[] array when needed.
    """
    direct_key = "t1s" if team_number == 1 else "t2s"
    direct = str(match.get(direct_key) or "").strip()

    if direct:
        return direct

    scores = match.get("score")

    if not isinstance(scores, list):
        return "Yet to bat"

    formatted = []

    for item in scores[:4]:
        if not isinstance(item, dict):
            continue

        runs = item.get("r")
        wickets = item.get("w")
        overs = item.get("o")

        if runs is None or wickets is None:
            continue

        text = f"{runs}/{wickets}"

        if overs:
            text += f" ({overs})"

        formatted.append(text)

    if team_number <= len(formatted):
        return formatted[team_number - 1]

    return "Yet to bat"


# ============================================================
# Match formatting
# ============================================================

def normalize_match(match):
    t1 = str(match.get("t1") or "Team A").strip()
    t2 = str(match.get("t2") or "Team B").strip()

    bucket = get_bucket(match)
    time_info = format_match_datetime(match)

    return {
        "id": str(
            match.get("id")
            or f"{t1}|{t2}|{match.get('date', '')}"
        ),
        "title": str(
            match.get("name")
            or f"{t1} vs {t2}"
        ).strip(),
        "series": str(
            match.get("series")
            or "Cricket"
        ).strip(),
        "match_type": str(
            match.get("matchType")
            or ""
        ).strip().upper(),
        "t1": t1,
        "t2": t2,
        "t1_score": get_score(match, 1),
        "t2_score": get_score(match, 2),
        "status": str(
            match.get("status")
            or (
                "LIVE"
                if bucket == "live"
                else "Scheduled"
            )
        ).strip(),
        "venue": str(
            match.get("venue")
            or "Venue TBD"
        ).strip(),
        "day": time_info["day"],
        "ist_time": time_info["ist_time"],
        "timestamp": time_info["timestamp"],
        "bucket": bucket,
    }


# ============================================================
# Build sections
# ============================================================

def build_sections(raw_matches):
    result = {
        "live": [],
        "upcoming": [],
        "finished": [],
    }

    seen_ids = set()

    for raw in raw_matches:
        if not isinstance(raw, dict):
            continue

        match = normalize_match(raw)

        if match["id"] in seen_ids:
            continue

        seen_ids.add(match["id"])
        result[match["bucket"]].append(match)

    # LIVE: oldest start first.
    result["live"].sort(
        key=lambda m: (
            m["timestamp"]
            if m["timestamp"] is not None
            else 0
        )
    )

    # UPCOMING: nearest match first.
    result["upcoming"].sort(
        key=lambda m: (
            m["timestamp"]
            if m["timestamp"] is not None
            else float("inf")
        )
    )

    # FINISHED: latest result first.
    result["finished"].sort(
        key=lambda m: (
            m["timestamp"]
            if m["timestamp"] is not None
            else 0
        ),
        reverse=True,
    )

    return result


# ============================================================
# Cached feed
# ============================================================

def fetch_global_cricket():
    now = time.time()

    if (
        _cache["data"] is not None
        and now - _cache["timestamp"] < CACHE_SECONDS
    ):
        return _cache["data"]

    try:
        raw_matches = fetch_cricscore()
        sections = build_sections(raw_matches)

        _cache["data"] = sections
        _cache["timestamp"] = now

        print(
            "CrixData feed updated:",
            f"live={len(sections['live'])},",
            f"upcoming={len(sections['upcoming'])},",
            f"finished={len(sections['finished'])}"
        )

        return sections

    except Exception as exc:
        print(f"CrixData feed error: {exc}")

        # Keep the last successful response alive during a temporary
        # provider/network failure.
        if _cache["data"] is not None:
            return _cache["data"]

        return {
            "live": [],
            "upcoming": [],
            "finished": [],
        }


# ============================================================
# Routes
# ============================================================

@app.route("/")
def home():
    return render_template(
        "index.html",
        matches=fetch_global_cricket()
    )


@app.route("/api/matches")
def api_matches():
    return jsonify(fetch_global_cricket())


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "CrixData",
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
