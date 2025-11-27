import json
from typing import Any, Dict
from urllib.parse import parse_qs
from pathlib import Path

import requests

from .models import Message, SearchResponse

# ---- Config ----
BASE_URL = "https://november7-730026606190.europe-west1.run.app/messages"
LIMIT = 2000

# ---- Initial load from messages.json (fallback) ----
DATA_PATH = Path(__file__).resolve().parent / "messages.json"
try:
    with DATA_PATH.open("r", encoding="utf-8") as f:
        RAW_DATA = json.load(f)
except FileNotFoundError:
    RAW_DATA = []

# In-memory dataset used by search
DATA = []
for m in RAW_DATA:
    DATA.append(Message(**m))


# --------- Refresh from source API (used by cron) ---------
def refresh_from_source() -> int:
    """
    Fetch a single large page from the slow source API and refresh in-memory DATA.
    Called only by EventBridge cron (not by user search requests).
    """
    global DATA

    resp = requests.get(
        BASE_URL,
        params={"skip": 0, "limit": LIMIT},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Unexpected API response: 'items' is not a list")

    # Replace in-memory dataset
    DATA = [Message(**m) for m in items]
    return len(DATA)


# ---------------- Main Lambda handler ----------------
def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """
    Two modes:
    - EventBridge cron refresh: event["source"] == "cron.refresh"
    - API Gateway HTTP API search: event has rawQueryString
    """

    # 1) Cron refresh path
    if event.get("source") == "cron.refresh":
        try:
            count = refresh_from_source()
            body = {"status": "refreshed", "count": count}
            return _response(200, body)
        except Exception as exc:
            body = {"status": "error", "message": str(exc)}
            return _response(500, body)

    # 2) Normal search path via API Gateway
    raw_query = event.get("rawQueryString", "")
    params = parse_qs(raw_query)

    query = params.get("query", [""])[0]
    page = int(params.get("page", ["1"])[0])
    page_size = int(params.get("page_size", ["10"])[0])

    if not query:
        return _response(400, {"error": "query is required"})

    q = query.lower()

    # Case-insensitive search in message or user_name
    matches = []
    for msg in DATA:
        text = msg.message.lower()
        name = msg.user_name.lower()
        if q in text or q in name:
            matches.append(msg)

    total = len(matches)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = matches[start:end]

    resp = SearchResponse(
        query=query,
        page=page,
        page_size=page_size,
        total=total,
        items=paginated,
    )

    return _response(200, resp.dict())


def _response(status: int, body: dict) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
