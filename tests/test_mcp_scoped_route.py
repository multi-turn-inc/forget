"""Scoped MCP endpoint: /mcp/<app_id>/http/<user_id> pins the scope.

Regression guard for the 2026-07-13 dogfooding finding: the OSS engine only
served unscoped /mcp, so a client connected with an explicit scope hit 404,
and an unscoped connection searched the default scope — a fresh session
recalled none of the user's memories.
"""

import json
import uuid

from fastapi.testclient import TestClient

from forget.server import app

client = TestClient(app)
USER = f"scoped-route-user-{uuid.uuid4().hex[:8]}"
APP = "scoped-route-app"


def _rpc(path: str, method: str, params: dict, request_id: int = 1) -> dict:
    response = client.post(path, json={
        "jsonrpc": "2.0", "id": request_id, "method": method, "params": params,
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_scope_identity_echo():
    response = client.get(f"/mcp/{APP}/http/{USER}")
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == USER
    assert body["client_name"] == APP


def test_scoped_route_initializes():
    body = _rpc(f"/mcp/{APP}/http/{USER}", "initialize", {"protocolVersion": "2025-06-18"})
    assert body["result"]["serverInfo"]["name"] == "forget-mcp"


def test_scoped_route_search_inherits_scope():
    added = client.post("/v1/memories/", json={
        "text": "we settled on paddle for payments",
        "infer": False, "user_id": USER, "app_id": APP,
    })
    assert added.status_code in (200, 201), added.text

    body = _rpc(
        f"/mcp/{APP}/http/{USER}",
        "tools/call",
        {"name": "search_memories", "arguments": {"query": "what did we pick for payments"}},
        request_id=2,
    )
    text = body["result"]["content"][0]["text"]
    results = json.loads(text).get("results", json.loads(text) if text.startswith("[") else [])
    flat = json.dumps(results)
    assert "paddle" in flat.lower(), f"scoped search must recall the user's memory: {text[:200]}"
