import json
import os
import urllib.parse
import urllib.request
from flask import Flask, jsonify, render_template
import pytz

app = Flask(__name__)

# ---------------------------------------------------------
# Temporary diagnostic version
# ---------------------------------------------------------

CRICSCORE_URL = "https://api.cricapi.com/v1/cricScore"
CURRENT_MATCHES_URL = "https://api.cricapi.com/v1/currentMatches"

IST = pytz.timezone("Asia/Kolkata")


def get_api_key():
    return os.getenv("CRICKET_API_KEY", "").strip()


def safe_response_body(raw_body):
    """
    Return a safe diagnostic preview.
    Never expose an API key in the browser.
    """
    text = raw_body.decode("utf-8", errors="replace") if isinstance(raw_body, bytes) else str(raw_body)

    # Redact common API-key patterns if they appear in an error message.
    text = re.sub(
        r"(apikey|api_key|key)\s*[=:]\s*['\"]?[^&\s,'\"}]+",
        r"\1=[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )

    return text[:1000]


def test_endpoint(base_url, extra_params=None):
    """
    Make a direct request from Render and report only safe diagnostics.
    """
    api_key = get_api_key()

    if not api_key:
        return {
            "configured": False,
            "http_status": None,
            "api_status": None,
            "error": "CRICKET_API_KEY is missing",
        }

    params = {
        "apikey": api_key,
    }

    if extra_params:
        params.update(extra_params)

    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CrixData/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            text = body.decode("utf-8", errors="replace")

            try:
                payload = json.loads(text)
                api_status = payload.get("status")
                data_count = (
                    len(payload.get("data", []))
                    if isinstance(payload.get("data"), list)
                    else None
                )
            except json.JSONDecodeError:
                api_status = None
                data_count = None

            return {
                "configured": True,
                "http_status": response.status,
                "api_status": api_status,
                "data_count": data_count,
                "error": None,
            }

    except urllib.error.HTTPError as exc:
        body = exc.read()

        return {
            "configured": True,
            "http_status": exc.code,
            "api_status": None,
            "data_count": None,
            "error": safe_response_body(body),
        }

    except Exception as exc:
        return {
            "configured": True,
            "http_status": None,
            "api_status": None,
            "data_count": None,
            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
        }


@app.route("/")
def home():
    # Temporary page so the app stays usable.
    return jsonify({
        "service": "CrixData",
        "message": "Diagnostic build is running. Open /debug to test CricketData.",
    })


@app.route("/debug")
def debug():
    """
    TEMPORARY route.
    It checks both CricketData endpoints from the Render server.
    API key value is never returned.
    """
    key_exists = bool(get_api_key())

    return jsonify({
        "service": "CrixData",
        "environment": {
            "CRICKET_API_KEY_present": key_exists,
        },
        "tests": {
            "cricScore": test_endpoint(CRICSCORE_URL),
            "currentMatches": test_endpoint(
                CURRENT_MATCHES_URL,
                {"offset": 0},
            ),
        },
    })


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
