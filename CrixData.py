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
# CrixData — Multi-provider v1
# Providers:
#   1) Highlightly Cricket API
#   2) CricketData.org eCricScore
#
# IMPORTANT:
# Both API keys are read from Render Environment Variables.
# Never paste either key into this source file or GitHub.
# ============================================================

IST = pytz.timezone("Asia/Kolkata")

HIGHLIGHTLY_URL = "https://cricket.highlightly.net/matches"
CRICKETDATA_URL = "https://api.cricapi.com/v1/cricScore"

# With the free 100-requests/day tier, 20 minutes gives a safety margin:
# 72 potential calls/day/provider when the service is continuously active.
CACHE_SECONDS = 20 * 60


# ============================================================
# Target competitions
# ============================================================

# We keep aliases because providers do not always use exactly the
# same competition name.
TARGET_ALIASES = {
    "IPL": [
        "indian premier league",
        "ipl",
    ],
    "WPL": [
        "women's premier league",
        "wpl",
        "women premier league",
    ],
    "BBL": [
        "big bash league",
        "bbl",
    ],
    "WBBL": [
        "women's big bash league",
        "wbbl",
        "women big bash league",
    ],
    "CPL": [
        "caribbean premier league",
        "cpl",
    ],
    "WCPL": [
        "women's caribbean premier league",
        "wcpl",
        "women caribbean premier league",
    ],
    "PSL": [
        "pakistan super league",
        "psl",
    ],
    "SA20": [
        "sa20",
        "south africa20",
    ],
    "LPL": [
        "lanka premier league",
        "lpl",
    ],
    "The Hundred Men": [
        "the hundred",
    ],
    "The Hundred Women": [
        "the hundred women",
        "the hundred women’s",
        "the hundred women",
    ],
    "MLC": [
        "major league cricket",
        "mlc",
    ],
    "ILT20": [
        "international league t20",
        "ilt20",
    ],
    "Abu Dhabi T10": [
        "abu dhabi t10",
        "abu dhabi t10 league",
    ],
    "ETPL": [
        "european t10 premier league",
        "etpl",
    ],
}

# International matches are handled separately because bilateral
# competitions have many different provider league names.
INTERNATIONAL_MARKERS = (
    "international",
    "icc",
    "world test",
    "world cup",
    "champions trophy",
    "t20 world cup",
    "test championship",
    "test series",
    "odi series",
    "t20i",
    "t20 international",
)

# Major Indian domestic competitions. This is deliberately conservative.
INDIA_DOMESTIC_MARKERS = (
    "ranji trophy",
    "syed mushtaq ali trophy",
    "vijay hazare trophy",
    "duleep trophy",
    "irani cup",
    "india a",
)

_cache = {
    "timestamp": 0.0,
    "data": None,
}


# ============================================================
# Generic helpers
# ============================================================

def safe_text(value):
    return str(value or "").strip()


def parse_dt(raw):
    if not raw:
        return None

    value = safe_text(raw)

    try:
        value = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def parse_cricketdata_dt(match):
    return parse_dt(match.get("dateTimeGMT") or match.get("dateTime"))


def parse_highlightly_dt(match):
    return parse_dt(
        match.get("startTime")
        or match.get("startDate")
        or match.get("dateTime")
    )


def format_time(dt_utc):
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


def get_highlightly_key():
    key = safe_text(os.getenv("HIGHLIGHTLY_API_KEY"))
    if not key:
        raise RuntimeError("HIGHLIGHTLY_API_KEY is not configured.")
    return key


def get_cricketdata_key():
    key = safe_text(os.getenv("CRICKET_API_KEY"))
    if not key:
        raise RuntimeError("CRICKET_API_KEY is not configured.")
    return key


def request_json(url, headers, timeout=15):
    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
        payload = json.loads(text)

        return payload, dict(response.headers)


def contains_any(text, markers):
    value = safe_text(text).lower()
    return any(marker in value for marker in markers)


# ============================================================
# Highlightly provider
# ============================================================

def fetch_highlightly():
    """
    Fetch today's Highlightly cricket matches.

    Highlightly direct-platform requests use x-rapidapi-key.
    The RapidAPI host header is NOT required for direct Highlightly access.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    params = urllib.parse.urlencode({
        "date": today,
        "timezone": "Asia/Kolkata",
        "limit": 100,
        "offset": 0,
    })

    url = f"{HIGHLIGHTLY_URL}?{params}"

    payload, headers = request_json(
        url,
        {
            "x-rapidapi-key": get_highlightly_key(),
            "Accept": "application/json",
            "User-Agent": "CrixData/1.0",
        },
    )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError("Highlightly returned invalid data.")

    return data, headers


# ============================================================
# CricketData provider
# ============================================================

def fetch_cricketdata():
    params = urllib.parse.urlencode({
        "apikey": get_cricketdata_key(),
    })

    url = f"{CRICKETDATA_URL}?{params}"

    payload, headers = request_json(
        url,
        {
            "Accept": "application/json",
            "User-Agent": "CrixData/1.0",
        },
    )

    if payload.get("status") != "success":
        raise RuntimeError(
            f"CricketData API returned {payload.get('status')}"
        )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError("CricketData returned invalid data.")

    return data, headers


# ============================================================
# Competition matching
# ============================================================

def canonical_competition(provider_name):
    name = safe_text(provider_name).lower()

    for canonical, aliases in TARGET_ALIASES.items():
        if any(alias in name for alias in aliases):
            return canonical

    if contains_any(name, INDIA_DOMESTIC_MARKERS):
        return "India Domestic"

    if contains_any(name, INTERNATIONAL_MARKERS):
        return "International"

    return None


def is_the_hundred_women(home, away, league_name):
    combined = f"{league_name} {home} {away}".lower()

    return (
        "women" in combined
        or "women's" in combined
        or "women’s" in combined
        or "w " in combined
    )


# ============================================================
# Highlightly normalization
# ============================================================

def highlightly_score(match, team_name):
    state = match.get("state") or {}
    score = state.get("score") or {}

    current = score.get("current")

    if isinstance(current, str) and current.strip():
        return current.strip()

    # Some responses expose scores as a list/object.
    if isinstance(score, dict):
        for key in ("home", "away", "value"):
            value = score.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return "Yet to bat"


def normalize_highlightly(match):
    home = safe_text(
        (match.get("homeTeam") or {}).get("name")
        or match.get("homeTeamName")
    )
    away = safe_text(
        (match.get("awayTeam") or {}).get("name")
        or match.get("awayTeamName")
    )

    league_obj = match.get("league") or {}
    league_name = safe_text(
        league_obj.get("name")
        or match.get("leagueName")
        or ""
    )

    canonical = canonical_competition(league_name)

    if canonical == "The Hundred Men" and is_the_hundred_women(
        home, away, league_name
    ):
        canonical = "The Hundred Women"

    state = match.get("state") or {}
    description = safe_text(
        state.get("description")
        or state.get("shortDescription")
        or ""
    )

    start_dt = parse_highlightly_dt(match)

    return {
        "provider": "Highlightly",
        "provider_id": safe_text(match.get("id")),
        "canonical": canonical,
        "title": f"{home} vs {away}",
        "series": league_name or "Cricket",
        "match_type": safe_text(match.get("format")).upper(),
        "t1": home or "Team A",
        "t2": away or "Team B",
        "t1_score": highlightly_score(match, home),
        "t2_score": highlightly_score(match, away),
        "status_raw": description or safe_text(state.get("type")),
        "venue": safe_text(
            (match.get("venue") or {}).get("name")
            or (match.get("venue") or {}).get("fullName")
            or "Venue TBD"
        ),
        "start_dt": start_dt,
        "timestamp": format_time(start_dt)["timestamp"],
        "raw": match,
    }


# ============================================================
# CricketData normalization
# ============================================================

def cricketdata_score(match, key):
    value = safe_text(match.get(key))

    if value:
        return value

    score = match.get("score")

    if isinstance(score, list):
        output = []

        for item in score[:4]:
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

            output.append(text)

        index = 0 if key == "t1s" else 1

        if index < len(output):
            return output[index]

    return "Yet to bat"


def normalize_cricketdata(match):
    t1 = safe_text(match.get("t1"))
    t2 = safe_text(match.get("t2"))
    series = safe_text(match.get("series"))

    canonical = canonical_competition(series)

    dt = parse_cricketdata_dt(match)
    status = safe_text(match.get("status"))

    return {
        "provider": "CricketData",
        "provider_id": safe_text(match.get("id")),
        "canonical": canonical,
        "title": safe_text(match.get("name")) or f"{t1} vs {t2}",
        "series": series or "Cricket",
        "match_type": safe_text(match.get("matchType")).upper(),
        "t1": t1 or "Team A",
        "t2": t2 or "Team B",
        "t1_score": cricketdata_score(match, "t1s"),
        "t2_score": cricketdata_score(match, "t2s"),
        "status_raw": status,
        "venue": safe_text(match.get("venue")) or "Venue TBD",
        "start_dt": dt,
        "timestamp": format_time(dt)["timestamp"],
        "raw": match,
    }


# ============================================================
# Status engine
# ============================================================

def is_finished(match):
    raw = (
        f"{safe_text(match.get('status_raw'))} "
        f"{safe_text((match.get('raw') or {}).get('ms'))}"
    ).lower()

    if "finished" in raw or "result" in raw or "completed" in raw:
        return True

    if contains_any(
        raw,
        (
            "won by",
            " draw",
            "tied",
            "no result",
            "abandoned",
            "cancelled",
        ),
    ):
        return True

    return False


def is_live(match):
    raw = safe_text(match.get("status_raw")).lower()

    if contains_any(
        raw,
        (
            "in play",
            "live",
            "in progress",
            "in-progress",
            "playing",
        ),
    ):
        return True

    raw_match = match.get("raw") or {}

    ms = safe_text(raw_match.get("ms")).lower()

    if ms in {"live", "in", "inprogress", "in_progress", "ongoing", "playing"}:
        return True

    # If a provider gives actual score innings for a match whose start time
    # has passed, treat it as live unless it is a result.
    if (
        isinstance(raw_match.get("score"), list)
        and raw_match.get("score")
        and match.get("start_dt")
        and match["start_dt"] <= datetime.now(timezone.utc)
        and not is_finished(match)
    ):
        return True

    return False


def get_bucket(match):
    if is_finished(match):
        return "finished"

    if is_live(match):
        return "live"

    return "upcoming"


# ============================================================
# Deduplication
# ============================================================

def normalize_for_key(value):
    return " ".join(
        safe_text(value).lower().replace("-", " ").split()
    )


def dedupe_key(match):
    # Provider IDs are strongest when available.
    if match.get("provider") == "Highlightly" and match.get("provider_id"):
        return f"h:{match['provider_id']}"

    if match.get("provider") == "CricketData" and match.get("provider_id"):
        return f"c:{match['provider_id']}"

    # Cross-provider fallback identity:
    # same teams + close start time + same canonical competition.
    timestamp = match.get("timestamp")

    if timestamp is not None:
        bucket = int(timestamp // (30 * 60))
    else:
        bucket = "none"

    return "|".join(
        (
            normalize_for_key(match.get("canonical")),
            normalize_for_key(match.get("t1")),
            normalize_for_key(match.get("t2")),
            str(bucket),
        )
    )


def merge_matches(highlightly_matches, cricketdata_matches):
    """
    Prefer Highlightly for the shared match when both providers have
    a record, because its current match state includes an explicit
    in-play description.

    If the same match is found only in CricketData, retain it.
    """
    combined = []
    seen_cross_provider = {}

    for item in highlightly_matches:
        if not item.get("canonical"):
            continue

        key = dedupe_key(item)

        # provider-specific IDs are unique only within the provider;
        # keep the broad fallback too.
        cross_key = (
            normalize_for_key(item.get("canonical")),
            normalize_for_key(item.get("t1")),
            normalize_for_key(item.get("t2")),
            int(item["timestamp"] // (30 * 60))
            if item.get("timestamp") is not None
            else None,
        )

        seen_cross_provider[cross_key] = item
        combined.append(item)

    for item in cricketdata_matches:
        if not item.get("canonical"):
            continue

        cross_key = (
            normalize_for_key(item.get("canonical")),
            normalize_for_key(item.get("t1")),
            normalize_for_key(item.get("t2")),
            int(item["timestamp"] // (30 * 60))
            if item.get("timestamp") is not None
            else None,
        )

        if cross_key in seen_cross_provider:
            # Highlightly already supplies this match.
            continue

        seen_cross_provider[cross_key] = item
        combined.append(item)

    return combined


# ============================================================
# Display conversion
# ============================================================

def display_match(match):
    times = format_time(match.get("start_dt"))

    bucket = get_bucket(match)

    return {
        "id": dedupe_key(match),
        "provider": match.get("provider"),
        "competition": match.get("canonical") or "Cricket",
        "title": match.get("title"),
        "series": match.get("series"),
        "match_type": match.get("match_type"),
        "t1": match.get("t1"),
        "t2": match.get("t2"),
        "t1_score": match.get("t1_score"),
        "t2_score": match.get("t2_score"),
        "status": match.get("status_raw") or (
            "LIVE" if bucket == "live" else "Scheduled"
        ),
        "venue": match.get("venue"),
        "day": times["day"],
        "ist_time": times["ist_time"],
        "timestamp": times["timestamp"],
        "bucket": bucket,
    }


# ============================================================
# Main feed
# ============================================================

def fetch_global_cricket(force=False):
    now = time.time()

    if (
        not force
        and _cache["data"] is not None
        and now - _cache["timestamp"] < CACHE_SECONDS
    ):
        return _cache["data"]

    highlightly_raw = []
    cricketdata_raw = []

    errors = []

    try:
        highlightly_raw, _ = fetch_highlightly()
    except Exception as exc:
        errors.append(f"Highlightly: {type(exc).__name__}: {exc}")

    try:
        cricketdata_raw, _ = fetch_cricketdata()
    except Exception as exc:
        errors.append(f"CricketData: {type(exc).__name__}: {exc}")

    highlightly_matches = [
        normalize_highlightly(item)
        for item in highlightly_raw
        if isinstance(item, dict)
    ]

    cricketdata_matches = [
        normalize_cricketdata(item)
        for item in cricketdata_raw
        if isinstance(item, dict)
    ]

    merged = merge_matches(
        highlightly_matches,
        cricketdata_matches,
    )

    result = {
        "live": [],
        "upcoming": [],
        "finished": [],
        "errors": errors,
        "meta": {
            "highlightly_count": len(highlightly_raw),
            "cricketdata_count": len(cricketdata_raw),
            "cache_seconds": CACHE_SECONDS,
        },
    }

    for item in merged:
        display = display_match(item)
        result[display["bucket"]].append(display)

    result["live"].sort(
        key=lambda x: (
            x["timestamp"]
            if x["timestamp"] is not None
            else 0
        )
    )

    result["upcoming"].sort(
        key=lambda x: (
            x["timestamp"]
            if x["timestamp"] is not None
            else float("inf")
        )
    )

    result["finished"].sort(
        key=lambda x: (
            x["timestamp"]
            if x["timestamp"] is not None
            else 0
        ),
        reverse=True,
    )

    # Cache even if one provider failed, as long as we got something
    # from at least one provider.
    if merged or not _cache["data"]:
        _cache["data"] = result
        _cache["timestamp"] = now

    print(
        "CrixData update:",
        f"Highlightly={len(highlightly_raw)},",
        f"CricketData={len(cricketdata_raw)},",
        f"live={len(result['live'])},",
        f"upcoming={len(result['upcoming'])},",
        f"finished={len(result['finished'])},",
        f"errors={len(errors)}",
    )

    return result


# ============================================================
# Routes
# ============================================================

@app.route("/")
def home():
    return render_template(
        "index.html",
        matches=fetch_global_cricket(),
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
