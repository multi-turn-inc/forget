"""Codex gets a small, cwd-bound memory surface instead of generic autopilot."""

import json

import pytest


@pytest.fixture()
def codex_store(tmp_path, monkeypatch):
    from forget import db as app_db
    from forget.db import init_db

    path = tmp_path / "codex.sqlite3"
    monkeypatch.setenv("MEM1_DB_PATH", str(path))
    monkeypatch.setattr(app_db, "DB_PATH", path)
    init_db()

    from forget.store import add_memories

    def add(text: str, metadata: dict) -> None:
        add_memories({
            "messages": [{"role": "user", "content": text}],
            "user_id": "junghunkim",
            "app_id": "forget",
            "metadata": metadata,
            "infer": False,
        })

    add("BotBotBot keeps the reconstructed app UI", {"project": "botbotbot", "scope_layer": "project"})
    add("Quant live order policy", {"project": "quant", "scope_layer": "project"})
    add("The user prefers evidence before claims", {"scope_layer": "global"})
    add("Legacy untagged decision", {})
    return path


def test_codex_profile_is_small_and_excludes_generic_autopilot():
    from forget.mcp import tools_for_profile

    names = {tool["name"] for tool in tools_for_profile("codex")}
    assert names == {
        "prepare_codex_context",
        "search_memories",
        "add_memory",
        "supersede_memory",
        "confirm_memory",
        "get_event_status",
        "record_context_outcome",
        "team_read",
        "team_note",
        "catalog_search",
        "product_quote",
        "grant_create",
        "agent_consult",
        "receipt_verify",
        "grant_revoke",
    }
    assert "prepare_context_autopilot" not in names
    assert "get_task_state" not in names


def test_codex_context_keeps_project_global_and_legacy_but_excludes_other_project(codex_store, monkeypatch):
    from forget import mcp

    monkeypatch.setattr(mcp, "_codex_project_key_for_path", lambda _path: "botbotbot")
    response = mcp.handle_mcp_rpc({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "prepare_codex_context", "arguments": {
            "query": "project decision and user preference",
            "client_workdir": "/workspace/botbotbot",
            "top_k": 12,
            "threshold": 0,
            "recall": "low",
        }},
    }, context={"user_id": "junghunkim", "client_name": "forget"})
    body = json.loads(response["result"]["content"][0]["text"])
    assert body["status"] == "ready"
    assert body["project"] == "botbotbot"
    joined = " ".join(item["memory"] for item in body["results"])
    assert "BotBotBot" in joined
    assert "evidence before claims" in joined
    assert "Legacy untagged" in joined
    assert "Quant live order" not in joined
    assert "action_hints" not in body
    assert "task" not in body


def test_codex_context_fails_closed_when_workdir_cannot_be_bound(codex_store, monkeypatch):
    from forget import mcp

    monkeypatch.setattr(mcp, "_codex_project_key_for_path", lambda _path: "")
    response = mcp.handle_mcp_rpc({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "prepare_codex_context", "arguments": {
            "query": "current work",
            "client_workdir": "/missing/workspace",
        }},
    }, context={"user_id": "junghunkim", "client_name": "forget"})
    body = json.loads(response["result"]["content"][0]["text"])
    assert body == {
        "schema_version": "forget-codex-context-v1",
        "status": "project_unresolved",
        "project": "",
        "results": [],
        "capsule_text": "",
        "context_trace_id": "",
    }


def test_scoped_route_echoes_codex_profile():
    from fastapi.testclient import TestClient
    from forget.server import app

    response = TestClient(app).get("/mcp/forget/http/junghunkim?profile=codex")
    assert response.status_code == 200
    assert response.json()["tool_profile"] == "codex"
