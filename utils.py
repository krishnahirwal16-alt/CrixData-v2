from datetime import datetime
from typing import Any, Dict, Optional

import requests


def text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lower(value: Any) -> str:
    return text(value).lower()


def parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None

    raw = text(value)

    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass

    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    return None


def http_get_json(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    response = requests.get(
        url,
        headers=headers or {},
        params=params or {},
        timeout=timeout,
    )

    response.raise_for_status()
    return response.json()
