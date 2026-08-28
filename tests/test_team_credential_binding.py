"""HTTP-level contract for credential-derived team-ledger attribution."""
from __future__ import annotations

import json
import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-team-credential.sqlite3")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.server import app  # noqa: E402
from forget.store import create_api_key, list_memory_dicts  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "t.sqlite3"))
    init_db()


def _agent_key(principal: str) -> str:
    created = create_api_key({
        "name": f"team:{principal}",
        "agent_principal": principal,
        "scopes": ["team:read", "team:write"],
    })
    return str(created["api_key"])


def _call(client: TestClient, tool: str, arguments: dict, *, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(
        "/mcp/forget/http/junghunkim",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    )


def test_bearer_credential_is_the_only_authority_for_team_note():
    client = TestClient(app)
    token = _agent_key("gpt-live")

    response = _call(
        client,
        "team_note",
        {"kind": "decision", "text": "credential-bound"},
        token=token,
    )

    assert response.status_code == 200
    assert "error" not in response.json()
    row = next(m for m in list_memory_dicts() if "credential-bound" in str(m.get("memory")))
    assert row.get("agent_id") == "gpt-live"
    assert row.get("user_id") in (None, "")


def test_unbound_connection_and_spoofed_query_fail_closed():
    client = TestClient(app)
    token = _agent_key("gpt-live")

    unbound = _call(client, "team_note", {"kind": "decision", "text": "anonymous"})
    assert "error" in unbound.json()

    spoofed = client.post(
        "/mcp/forget/http/junghunkim?principal=claude-exec",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "team_note", "arguments": {"kind": "decision", "text": "spoof"}},
        },
    )
    assert spoofed.status_code == 403


def test_public_tool_schema_has_no_caller_selected_author():
    client = TestClient(app)
    token = _agent_key("claude-exec")
    response = client.post(
        "/mcp/forget/http/junghunkim",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
    )
    tools = response.json()["result"]["tools"]
    schema = next(tool for tool in tools if tool["name"] == "team_note")["inputSchema"]
    assert "author" not in schema.get("properties", {})


def test_api_key_payload_exposes_binding_but_not_secret_on_list():
    from forget.store import list_api_keys

    secret = _agent_key("selfharness")
    payload = list_api_keys()
    encoded = json.dumps(payload)
    assert payload["results"][0]["agent_principal"] == "selfharness"
    assert secret not in encoded


def test_generic_mcp_tools_cannot_bypass_team_contract():
    client = TestClient(app)
    token = _agent_key("gpt-live")
    write = _call(
        client,
        "team_note",
        {"kind": "decision", "text": "protected item"},
        token=token,
    )
    item = json.loads(write.json()["result"]["content"][0]["text"])["item"]

    forged = _call(
        client,
        "add_memory",
        {"text": "forged", "app_id": "forget-dev", "agent_id": "claude-exec"},
        token=token,
    )
    assert "error" in forged.json()

    generic_read = _call(client, "get_memory", {"memory_id": item["id"]}, token=token)
    assert "error" in generic_read.json()


def test_rest_team_reads_require_rostered_bearer():
    client = TestClient(app)
    token = _agent_key("claude-exec")
    write = _call(
        client,
        "team_note",
        {"kind": "decision", "text": "rest protected"},
        token=token,
    )
    item = json.loads(write.json()["result"]["content"][0]["text"])["item"]

    assert client.get("/v1/memories/?app_id=forget-dev").status_code == 403
    assert client.get(f"/v1/memories/{item['id']}/").status_code == 403

    headers = {"Authorization": f"Bearer {token}"}
    listed = client.get("/v1/memories/?app_id=forget-dev", headers=headers)
    assert listed.status_code == 200
    assert any(row["id"] == item["id"] for row in listed.json())
    assert client.get(f"/v1/memories/{item['id']}/", headers=headers).status_code == 200


def test_nested_filter_operators_cannot_bypass_team_scope_guard():
    client = TestClient(app)
    token = _agent_key("gpt-live")
    filters = {"app_id": {"in": ["forget-dev"]}}

    generic_mcp = _call(
        client,
        "search_memories",
        {"query": "ledger", "filters": filters},
        token=token,
    )
    assert "error" in generic_mcp.json()

    raw_rest = client.post(
        "/v1/memories/search/",
        json={"query": "ledger", "filters": filters},
    )
    assert raw_rest.status_code == 403


def test_generic_event_surfaces_do_not_leak_team_payloads():
    client = TestClient(app)
    token = _agent_key("gpt-live")
    write = _call(
        client,
        "team_note",
        {"kind": "decision", "text": "event protected"},
        token=token,
    )
    result = json.loads(write.json()["result"]["content"][0]["text"])
    event_id = result["event_id"]

    event = _call(client, "get_event_status", {"event_id": event_id}, token=token)
    assert "error" in event.json()

    listed = _call(client, "list_events", {"page_size": 100}, token=token)
    listed_payload = json.loads(listed.json()["result"]["content"][0]["text"])
    assert event_id not in {row["id"] for row in listed_payload["results"]}

    rest = client.get("/v1/memories/events/?page_size=100")
    assert rest.status_code == 200
    assert event_id not in {row["id"] for row in rest.json()["results"]}
