"""Devin REST API v3 client (service-user auth)."""

import json
import os
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai")
API_KEY = os.environ["DEVIN_SERVICE_API_KEY"]
ORG_ID = os.environ["DEVIN_ORG_ID"]


def _request(method, path, body=None):
    url = f"{API_BASE}/v3/organizations/{ORG_ID}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Devin API error {e.code}: {e.read().decode()}")
        raise


def create_session(prompt, title, tags=None, max_acu_limit=30):
    """POST /v3/organizations/{org_id}/sessions -> (session_id, url)."""
    body = {
        "prompt": prompt,
        "title": title,
        "tags": tags or [],
        "max_acu_limit": max_acu_limit,
    }
    data = _request("POST", "/sessions", body)
    session_id = data["session_id"]
    url = data.get("url", f"https://app.devin.ai/sessions/{session_id.split('-', 1)[-1]}")
    print(f"Created session {session_id}: {url}")
    return session_id, url


def get_session(session_id):
    """GET /v3/organizations/{org_id}/sessions/{id}."""
    return _request("GET", f"/sessions/{session_id}")


def list_sessions(limit=100):
    """GET /v3/organizations/{org_id}/sessions (cursor-paginated)."""
    items = []
    cursor = None
    while True:
        path = f"/sessions?limit={min(limit, 100)}"
        if cursor:
            path += f"&cursor={cursor}"
        data = _request("GET", path)
        items.extend(data.get("items", []))
        cursor = data.get("end_cursor")
        if not data.get("has_next_page") or not cursor or len(items) >= limit:
            return items


def wait_for_session(session_id, polls=6, interval=10):
    """Poll until the session is confirmed working or settled."""
    status = detail = None
    for i in range(1, polls + 1):
        time.sleep(interval)
        data = get_session(session_id)
        status = data.get("status")
        detail = data.get("status_detail")
        print(f"Poll {i}/{polls}: status={status} detail={detail}")
        if status in ("working", "running", "blocked", "finished", "expired", "error"):
            return status, detail
    return status, detail
