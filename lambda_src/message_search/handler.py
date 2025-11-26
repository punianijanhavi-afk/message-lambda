import json
from typing import Any, Dict
from urllib.parse import parse_qs
from pathlib import Path

import requests  # NEW
from .models import Message, SearchResponse

# ---- Config ----
BASE_URL = "https://november7-730026606190.europe-west1.run.app/messages"
LIMIT = 100  # page size for source API

# ---- Initial load from baked messages.json (fallback / initial snapshot) ----
DATA_PATH = Path(__file__).resolve().parent / "messages.json"
with DATA_PATH.open("r", encoding="utf-8") as f:
    RAW_DATA = json.load(f)

DATA = [Message(**m) for m in RAW_DATA]


# ---- Source API fetch helpers (used ONLY for cron refresh) ----
def _fetch_page(skip: int, limit: int) -> Dict[str, Any]:
    resp = requests.get(
        BASE_URL,
        params={"skip": skip, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def refresh_from_source() -> int:
    """
    Fetch all messages from the slow source API and refresh in-memory DATA.
    Called only by EventBridge cron (not by user search requests).
    """
    global DATA

    first = _fetch_page(skip=0, limit=LIMIT)
    total = first["total"]
    items = first["items"]

    pages = (total + LIMIT - 1) // LIMIT  # ceil(total / LIMIT)

    for page_idx in range(1, pages):
        skip = page_idx * LIMIT
        page = _fetch_page(skip=skip, limit=LIMIT)
        items.extend(page["items"])

    # Replace in-memory dataset
    DATA = [Message(**m) for m in items]
    return len(DATA)


# ---- Main Lambda handler ----
def lambda_handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """
    Two modes:
    - API Gateway HTTP API (search): event has rawQueryString
    - EventBridge cron (refresh): event has source == "cron.refresh"
    """

    # 1) Cron refresh path (EventBridge)
    if event.get("source") == "cron.refresh":
        count = refresh_from_source()
        body = {"status": "refreshed", "count": count}
        return _response(200, body)

    # 2) Normal search path (API Gateway HTTP API)
    raw_query = event.get("rawQueryString", "")
    params = parse_qs(raw_query)

    query = params.get("query", [""])[0]
    page = int(params.get("page", ["1"])[0])
    page_size = int(params.get("page_size", ["10"])[0])

    if not query:
        return _response(400, {"error": "query is required"})

    q = query.lower()

    # Case-insensitive search in message or user_name
    matches = [
        msg for msg in DATA
        if q in msg.message.lower() or q in msg.user_name.lower()
    ]

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

    # Pydantic v1 -> use .dict()
    return _response(200, resp.dict())


def _response(status: int, body: dict) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
