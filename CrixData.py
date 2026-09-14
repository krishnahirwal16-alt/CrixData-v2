import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pytz
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# ============================================================
# CrixData Multi-Provider v2
#
# Providers:
#   1) Highlightly Cricket API
#   2) CricketData.org eCricScore
#
# Design goals:
#   - Do NOT discard valid matches just because a league name
#     wasn't in a small hard-coded list.
#   - Recognize major target competitions.
#   - Recognize international + Indian domestic matches.
#   - Correctly read Highlightly's cricket state + score structure.
#   - Merge duplicate matches from both providers.
#   - Keep API keys server-side in Render Environment Variables.
# ============================================================

IST = pytz.timezone("Asia/Kolkata")

HIGHLIGHTLY_MATCHES_URL = "https://cricket.highlightly.net/matches"
CRICKETDATA_SCORE_URL = "https://api.cricapi.com/v1/cricScore"

# Two Highlightly requests (today + tomorrow) and one CricketData
# request per cache refresh.
#
# 30 minutes => at most 48 refresh cycles/day.
# Highlightly: <= 96 requests/day
# CricketData: <= 48 requests/day
#
# This leaves a small safety margin under each provider's 100/day
# free tier when the service is continuously accessed.
CACHE_SECONDS = 30 * 60

_cache = {
    "timestamp": 0.0,
    "data": None,
}


# ============================================================
# Target competitions
# ============================================================

TARGET_ALIASES = {
    "IPL": (
        "ipl",
        "indian premier league",
    ),
    "WPL": (
        "wpl",
        "women's premier league",
        "women’s premier league",
        "women premier league",
    ),
    "BBL": (
        "big bash league",
        "bbl",
    ),
    "WBBL": (
        "women's big bash league",
        "women’s big bash league",
        "women big bash league",
        "wbbl",
    ),
    "CPL": (
        "caribbean premier league",
        "cpl",
    ),
    "WCPL": (
        "women's caribbean premier league",
        "women’s caribbean premier league",
        "women caribbean premier league",
        "wcpl",
    ),
    "PSL": (
        "pakistan super league",
        "psl",
    ),
    "SA20": (
        "sa20",
        "south africa20",
    ),
    "LPL": (
        "lanka premier league",
        "lpl",
    ),
    "The Hundred": (
        "the hundred",
        "hundred men",
        "hundred women",
    ),
    "MLC": (
        "major league cricket",
        "mlc",
    ),
    "ILT20": (
        "international league t20",
        "ilt20",
    ),
    "Abu Dhabi T10": (
        "abu dhabi t10",
        "abu dhabi t10 league",
    ),
    "ETPL": (
        "european t10 premier league",
        "europe t10 premier league",
        "etpl",
    ),
}

# Major Indian domestic competitions requested for CrixData.
INDIA_DOMESTIC_MARKERS = (
    "ranji trophy",
    "syed mushtaq ali trophy",
    "vijay hazare trophy",
    "duleep trophy",
    "duleep trophy",
    "irani cup",
    "india a",
    "india under",
    "state t20",
    "maharaja trophy",
    "maharashtra premier league",
    "tamil nadu premier league",
    "tamil nadu t20",
    "karnataka premier league",
    "kerala premier league",
    "uttar pradesh t20",
    "delhi premier league",
    "saurashtra premier league",
    "bengal pro t20",
    "bengal t20",
)

# National-team markers used to recognize international cricket even
# when the provider's series/competition name is not standardized.
NATIONAL_TEAM_MARKERS = (
    "afghanistan",
    "australia",
    "bangladesh",
    "england",
    "india",
    "ireland",
    "new zealand",
    "pakistan",
    "south africa",
    "sri lanka",
    "west indies",
    "zimbabwe",
    "namibia",
    "scotland",
    "nepal",
    "united arab emirates",
    "oman",
    "usa",
    "united states",
    "netherlands",
    "canada",
    "uganda",
    "papua new guinea",
    "hong kong",
    "italy",
    "jersey",
    "guernsey",
    "bermuda",
    "germany",
    "france",
    "italy",
    "vanuatu",
    "new zealand a",
    "india a",
    "australia a",
    "england lions",
    "pakistan a",
    "south africa a",
    "new zealand under",
    "india under",
    "pakistan under",
    "england under",
    "australia under",
    "bangladesh under",
    "south africa under",
    "sri lanka under",
    "west indies under",
)

INTERNATIONAL_SERIES_MARKERS = (
    "international",
    "icc",
    "world cup",
    "champions trophy",
    "test championship",
    "world test championship",
    "odi series",
    "t20i",
    "t20 international",
    "test series",
    "bilateral",
)

# Highlightly cricket-state values from its documented cricket API.
LIVE_STATES = {
    "in play",
    "live",
    "stumps",
    "lunch",
    "innings break",
    "drinks",
    "tea",
    "timeout",
}

FINISHED_STATES = {
    "finished",
    "abandoned",
    "no result",
    "cancelled",
    "canceled",
}

UPCOMING_STATES = {
    "not started",
    "scheduled",
    "to be announced",
}

DELAYED_STATES = {
    "match delayed",
    "delayed",
}

# ============================================================
# Basic helpers
# ============================================================

def text(value):
    return str(value or "").strip()


def lower(value):
    return text(value).lower()


def contains_any(value, markers):
    value = lower(value)
    return any(marker in value for marker in markers)


def parse_datetime(value):
    raw = text(value)
    if not raw:
        return None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except ValueError:
        return None


def format_time(dt_utc):
    if not dt_utc:
        return {
            "day": "Date TBD",
            "ist_time": "Time TBD",
            "timestamp": None,
        }

    ist_dt = dt_utc.astimezone(IST)

    return {
        "day": ist_dt.strftime("%A, %b %d, %Y"),
        "ist_time": ist_dt.strftime("%I:%M %p IST"),
        "timestamp": dt_utc.timestamp(),
    }


# ============================================================
# Environment / HTTP
# ============================================================

def get_env(name):
    value = text(os.getenv(name))

    if not value:
        raise RuntimeError(f"{name} is not configured on Render.")

    return value


def request_json(url, headers):
    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body)
            return payload, dict(response.headers)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"HTTP {exc.code} from provider: {body[:300]}"
        ) from exc

    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Provider network error: {exc.reason}"
        ) from exc


# ============================================================
# Highlightly
# ============================================================

def fetch_highlightly_for_date(date_string):
    params = urllib.parse.urlencode({
        "date": date_string,
        "timezone": "Asia/Kolkata",
        "limit": 100,
        "offset": 0,
    })

    url = f"{HIGHLIGHTLY_MATCHES_URL}?{params}"

    payload, headers = request_json(
        url,
        {
            "x-rapidapi-key": get_env("HIGHLIGHTLY_API_KEY"),
            "Accept": "application/json",
            "User-Agent": "CrixData/2.0",
        },
    )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError("Highlightly returned invalid match data.")

    return data, headers


def fetch_highlightly():
    now = datetime.now(timezone.utc)

    today = now.strftime("%Y-%m-%d")
    tomorrow = (
        now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    )

    # Add one UTC day without another dependency.
    from datetime import timedelta
    tomorrow = tomorrow + timedelta(days=1)
    tomorrow_string = tomorrow.strftime("%Y-%m-%d")

    today_data, today_headers = fetch_highlightly_for_date(today)
    tomorrow_data, tomorrow_headers = fetch_highlightly_for_date(
        tomorrow_string
    )

    # Deduplicate same provider IDs.
    output = []
    seen = set()

    for item in today_data + tomorrow_data:
        if not isinstance(item, dict):
            continue

        item_id = text(item.get("id"))

        key = item_id or json.dumps(
            item,
            sort_keys=True,
            default=str,
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(item)

    return output, today_headers or tomorrow_headers


# ============================================================
# CricketData
# ============================================================

def fetch_cricketdata():
    params = urllib.parse.urlencode({
        "apikey": get_env("CRICKET_API_KEY"),
    })

    url = f"{CRICKETDATA_SCORE_URL}?{params}"

    payload, headers = request_json(
        url,
        {
            "Accept": "application/json",
            "User-Agent": "CrixData/2.0",
        },
    )

    if payload.get("status") != "success":
        raise RuntimeError(
            f"CricketData returned status={payload.get('status')}"
        )

    data = payload.get("data")

    if not isinstance(data, list):
        raise RuntimeError("CricketData returned invalid match data.")

    return data, headers


# ============================================================
# Competition classification
# ============================================================

def canonical_competition(league_name, home="", away=""):
    combined = f"{league_name} {home} {away}".strip().lower()

    # The Hundred gets one canonical family. We distinguish the
    # women's competition using the provider name/team name.
    if "the hundred" in combined:
        if contains_any(
            combined,
            ("women", "women's", "women’s"),
        ):
            return "The Hundred Women"

        return "The Hundred Men"

    for canonical, aliases in TARGET_ALIASES.items():
        if any(alias in combined for alias in aliases):
            if canonical == "The Hundred":
                return "The Hundred Men"
            return canonical

    if contains_any(combined, INDIA_DOMESTIC_MARKERS):
        return "India Domestic"

    # International competition name.
    if contains_any(combined, INTERNATIONAL_SERIES_MARKERS):
        return "International"

    # Two national-team-like sides are enough to identify a likely
    # international fixture when the series name is generic.
    national_hits = sum(
        1
        for marker in NATIONAL_TEAM_MARKERS
        if marker in combined
    )

    if national_hits >= 2:
        return "International"

    return None


def is_relevant_cricket_match(competition):
    """
    We deliberately keep an explicit allow-list at the final stage:
      - requested major competitions
      - International
      - India Domestic

    Unknown local/low-tier leagues are not displayed.
    """
    return competition in (
        "IPL",
        "WPL",
        "BBL",
        "WBBL",
        "CPL",
        "WCPL",
        "PSL",
        "SA20",
        "LPL",
        "The Hundred Men",
        "The Hundred Women",
        "MLC",
        "ILT20",
        "Abu Dhabi T10",
        "ETPL",
        "International",
        "India Domestic",
    )


# ============================================================
# Highlightly normalization
# ============================================================

def highlightly_state(match):
    state = match.get("state") or {}

    return (
        text(state.get("description"))
        or text(state.get("shortDescription"))
        or ""
    )


def highlightly_team_data(match, side):
    state = match.get("state") or {}
    teams = state.get("teams") or {}
    value = teams.get(side) or {}

    return {
        "score": text(value.get("score")),
        "info": text(value.get("info")),
    }


def normalize_highlightly(match):
    home_obj = match.get("homeTeam") or {}
    away_obj = match.get("awayTeam") or {}
    league_obj = match.get("league") or {}

    home = text(home_obj.get("name"))
    away = text(away_obj.get("name"))
    league_name = text(
        league_obj.get("name")
        or match.get("leagueName")
    )

    competition = canonical_competition(
        league_name,
        home,
        away,
    )

    start_dt = parse_datetime(
        match.get("startTime")
        or match.get("startDate")
    )

    state_desc = highlightly_state(match)

    home_state = highlightly_team_data(match, "home")
    away_state = highlightly_team_data(match, "away")

    return {
        "provider": "Highlightly",
        "provider_id": text(match.get("id")),
        "competition": competition,
        "title": f"{home} vs {away}",
        "series": league_name or "Cricket",
        "match_type": text(match.get("format")).upper(),
        "t1": home or "Team A",
        "t2": away or "Team B",
        "t1_abbrev": text(home_obj.get("abbreviation")),
        "t2_abbrev": text(away_obj.get("abbreviation")),
        "t1_score": home_state["score"],
        "t2_score": away_state["score"],
        "t1_info": home_state["info"],
        "t2_info": away_state["info"],
        "state": state_desc,
        "report": text(
            (match.get("state") or {}).get("report")
        ),
        "venue": text(
            (match.get("venue") or {}).get("name")
            or (match.get("venue") or {}).get("fullName")
        ) or "Venue TBD",
        "start_dt": start_dt,
        "raw": match,
    }


# ============================================================
# CricketData normalization
# ============================================================

def cricketdata_score(match, key):
    direct = text(match.get(key))

    if direct:
        return direct

    scores = match.get("score")

    if not isinstance(scores, list):
        return ""

    formatted = []

    for item in scores[:4]:
        if not isinstance(item, dict):
            continue

        runs = item.get("r")
        wickets = item.get("w")
        overs = item.get("o")

        if runs is None:
            continue

        value = str(runs)

        if wickets is not None:
            value = f"{runs}/{wickets}"

        if overs:
            value += f" ({overs})"

        formatted.append(value)

    index = 0 if key == "t1s" else 1

    if index < len(formatted):
        return formatted[index]

    return ""


def normalize_cricketdata(match):
    t1 = text(match.get("t1"))
    t2 = text(match.get("t2"))
    series = text(match.get("series"))

    competition = canonical_competition(
        series,
        t1,
        t2,
    )

    start_dt = parse_datetime(
        match.get("dateTimeGMT")
        or match.get("dateTime")
    )

    return {
        "provider": "CricketData",
        "provider_id": text(match.get("id")),
        "competition": competition,
        "title": text(match.get("name"))
        or f"{t1} vs {t2}",
        "series": series or "Cricket",
        "match_type": text(
            match.get("matchType")
        ).upper(),
        "t1": t1 or "Team A",
        "t2": t2 or "Team B",
        "t1_abbrev": "",
        "t2_abbrev": "",
        "t1_score": cricketdata_score(match, "t1s"),
        "t2_score": cricketdata_score(match, "t2s"),
        "t1_info": "",
        "t2_info": "",
        "state": text(
            match.get("status")
        ),
        "report": text(
            match.get("status")
        ),
        "venue": text(match.get("venue")) or "Venue TBD",
        "start_dt": start_dt,
        "raw": match,
    }


# ============================================================
# Status classification
# ============================================================

def classify_status(match):
    provider = match.get("provider")
    state = lower(match.get("state"))

    # Highlightly has the cleanest cricket state model.
    if provider == "Highlightly":
        if state in LIVE_STATES:
            return "live"

        if state in FINISHED_STATES:
            return "finished"

        if state in UPCOMING_STATES:
            return "upcoming"

        if state in DELAYED_STATES:
            # If the provider says delayed and the event start time
            # is still in the future, keep it upcoming. Otherwise
            # consider it active.
            start_dt = match.get("start_dt")
            if (
                start_dt is not None
                and start_dt > datetime.now(timezone.utc)
            ):
                return "upcoming"
            return "live"

    # CricketData uses "ms" and human-readable status.
    raw = match.get("raw") or {}
    ms = lower(raw.get("ms"))
    status = lower(raw.get("status"))

    if ms in {
        "result",
        "completed",
        "complete",
        "finished",
        "post",
    }:
        return "finished"

    if contains_any(
        status,
        (
            "won by",
            "draw",
            "tied",
            "no result",
            "abandoned",
            "cancelled",
            "canceled",
        ),
    ):
        return "finished"

    if ms in {
        "live",
        "in",
        "inprogress",
        "in_progress",
        "ongoing",
        "started",
        "playing",
    }:
        return "live"

    score = raw.get("score")
    start_dt = match.get("start_dt")

    if (
        isinstance(score, list)
        and score
        and start_dt is not None
        and start_dt <= datetime.now(timezone.utc)
    ):
        return "live"

    return "upcoming"


# ============================================================
# Cross-provider deduplication
# ============================================================

def normalized_name(value):
    return " ".join(
        lower(value)
        .replace("-", " ")
        .replace("_", " ")
        .split()
    )


def cross_provider_key(match):
    competition = normalized_name(
        match.get("competition")
    )
    t1 = normalized_name(match.get("t1"))
    t2 = normalized_name(match.get("t2"))

    # 30-minute time bucket avoids duplicate records when provider
    # timestamps differ slightly.
    start_dt = match.get("start_dt")

    if start_dt:
        bucket = int(
            start_dt.timestamp() // (30 * 60)
        )
    else:
        bucket = "none"

    unordered_teams = tuple(
        sorted((t1, t2))
    )

    return (
        competition,
        unordered_teams,
        bucket,
    )


def merge_provider_matches(highlightly, cricketdata):
    """
    Highlightly wins when both providers have the same match.
    CricketData fills gaps that Highlightly does not have.
    """
    merged = {}
    order = []

    for item in highlightly:
        if not is_relevant_cricket_match(
            item.get("competition")
        ):
            continue

        key = cross_provider_key(item)

        if key not in merged:
            merged[key] = item
            order.append(key)

    for item in cricketdata:
        if not is_relevant_cricket_match(
            item.get("competition")
        ):
            continue

        key = cross_provider_key(item)

        if key not in merged:
            merged[key] = item
            order.append(key)

    return [merged[key] for key in order]


# ============================================================
# Display conversion
# ============================================================

def display_match(match):
    bucket = classify_status(match)
    time_info = format_time(match.get("start_dt"))

    status = match.get("state") or ""

    # Prefer a result report for finished matches.
    if bucket == "finished" and match.get("report"):
        status = match.get("report")

    if not status:
        status = {
            "live": "Live",
            "upcoming": "Scheduled",
            "finished": "Finished",
        }[bucket]

    return {
        "id": (
            f"{match.get('provider')}::"
            f"{match.get('provider_id') or cross_provider_key(match)}"
        ),
        "provider": match.get("provider"),
        "competition": (
            match.get("competition")
            or "Cricket"
        ),
        "title": match.get("title"),
        "series": match.get("series"),
        "match_type": match.get("match_type"),
        "t1": match.get("t1"),
        "t2": match.get("t2"),
        "t1_abbrev": match.get("t1_abbrev"),
        "t2_abbrev": match.get("t2_abbrev"),
        "t1_score": (
            match.get("t1_score")
            or "Yet to bat"
        ),
        "t2_score": (
            match.get("t2_score")
            or "Yet to bat"
        ),
        "t1_info": match.get("t1_info"),
        "t2_info": match.get("t2_info"),
        "status": status,
        "bucket": bucket,
        "venue": match.get("venue"),
        "day": time_info["day"],
        "ist_time": time_info["ist_time"],
        "timestamp": time_info["timestamp"],
    }


# ============================================================
# Main feed + caching
# ============================================================

def fetch_global_cricket(force=False):
    now = time.time()

    if (
        not force
        and _cache["data"] is not None
        and now - _cache["timestamp"] < CACHE_SECONDS
    ):
        return _cache["data"]

    errors = []

    highlightly_raw = []
    cricketdata_raw = []

    # Provider 1
    try:
        highlightly_raw, _ = fetch_highlightly()
    except Exception as exc:
        errors.append(
            f"Highlightly: {type(exc).__name__}: {exc}"
        )

    # Provider 2
    try:
        cricketdata_raw, _ = fetch_cricketdata()
    except Exception as exc:
        errors.append(
            f"CricketData: {type(exc).__name__}: {exc}"
        )

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

    merged = merge_provider_matches(
        highlightly_matches,
        cricketdata_matches,
    )

    result = {
        "live": [],
        "upcoming": [],
        "finished": [],
        "errors": errors,
        "meta": {
            "highlightly_raw": len(highlightly_raw),
            "cricketdata_raw": len(cricketdata_raw),
            "merged_relevant": len(merged),
            "cache_seconds": CACHE_SECONDS,
        },
    }

    for item in merged:
        display = display_match(item)
        result[display["bucket"]].append(display)

    # Live first.
    result["live"].sort(
        key=lambda m: (
            m["timestamp"]
            if m["timestamp"] is not None
            else 0
        )
    )

    # Upcoming nearest first.
    result["upcoming"].sort(
        key=lambda m: (
            m["timestamp"]
            if m["timestamp"] is not None
            else float("inf")
        )
    )

    # Finished latest first.
    result["finished"].sort(
        key=lambda m: (
            m["timestamp"]
            if m["timestamp"] is not None
            else 0
        ),
        reverse=True,
    )

    # Only cache a response if at least one provider returned
    # usable data. On a total provider outage, keep the last good
    # response when available.
    if merged or _cache["data"] is None:
        _cache["data"] = result
        _cache["timestamp"] = now

    print(
        "CrixData update:",
        f"Highlightly={len(highlightly_raw)},",
        f"CricketData={len(cricketdata_raw)},",
        f"merged_relevant={len(merged)},",
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
