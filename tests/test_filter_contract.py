"""Search-filter contract: unknown keys fail loud instead of matching nothing.

Before 2026-07-05 an unrecognized filter key (e.g. {"scope": "user"}) fell
through to a memory-field lookup no row satisfies: the primary scope silently
matched zero memories and, with scope_fallback enabled, every result degraded
to discounted fallback hits. Observed over MCP dogfooding on 2026-07-04.

The repaired contract rejects at the boundary with a 400 that names the bad
key, lists the valid vocabulary, and suggests the nearest valid spelling.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import init_db
from forget.server import app
from forget.mcp import TOOLS, call_tool

_DB_COUNTER = 0


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-filter-contract-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def _add_v3(c: TestClient, text: str, user_id: str, **extra) -> None:
    response = c.post(
        "/v3/memories/add/",
        json={
            "messages": [{"role": "user", "content": text}],
            "user_id": user_id,
            "infer": False,
            **extra,
        },
    )
    assert response.status_code == 200, response.text


def _search_v3(c: TestClient, filters: dict, **extra):
    return c.post("/v3/memories/search/", json={"query": "tea", "filters": filters, **extra})


def test_unknown_filter_key_rejected_with_vocabulary() -> None:
    c = _client()
    response = _search_v3(c, {"scope": "user"})
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "'scope'" in detail
    assert "user_id" in detail  # the vocabulary is listed
    assert "scope by entity id" in detail  # the targeted hint


def test_unknown_filter_key_rejected_on_list_endpoint() -> None:
    c = _client()
    response = c.post("/v3/memories/", json={"filters": {"scoped_to": "alice"}})
    assert response.status_code == 400
    assert "'scoped_to'" in response.json()["detail"]


def test_camelcase_filter_key_suggests_snake_case() -> None:
    c = _client()
    response = _search_v3(c, {"userId": "alice"})
    assert response.status_code == 400
    assert "Did you mean 'user_id'?" in response.json()["detail"]


def test_unknown_key_nested_in_logical_operator_rejected() -> None:
    c = _client()
    response = _search_v3(c, {"AND": [{"user_id": "alice"}, {"scopes": "x"}]})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "'scopes'" in detail
    assert "filters.AND[1]" in detail


def test_logical_operator_requires_nonempty_list() -> None:
    c = _client()
    response = _search_v3(c, {"user_id": "alice", "AND": []})
    assert response.status_code == 400
    assert "non-empty list" in response.json()["detail"]


def test_unknown_comparison_operator_rejected() -> None:
    c = _client()
    response = _search_v3(c, {"user_id": {"equals": "alice"}})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "'equals'" in detail
    assert "icontains" in detail  # valid operators are listed


def test_metadata_dict_filter_suggests_dotted_path() -> None:
    c = _client()
    response = _search_v3(c, {"user_id": "alice", "metadata": {"topic": "tea"}})
    assert response.status_code == 400
    assert "metadata.topic" in response.json()["detail"]


def test_bare_list_value_suggests_in_operator() -> None:
    c = _client()
    response = _search_v3(c, {"user_id": ["alice", "bob"]})
    assert response.status_code == 400
    assert '{"in": [...]}' in response.json()["detail"]


def test_valid_filter_vocabulary_still_matches() -> None:
    c = _client()
    _add_v3(c, "I drink green tea every morning.", "alice", metadata={"topic": "tea"}, categories=["habits"])
    _add_v3(c, "I prefer coffee.", "bob")

    scalar = _search_v3(c, {"user_id": "alice"})
    assert scalar.status_code == 200, scalar.text
    assert scalar.json()["results"], scalar.text

    combined = _search_v3(
        c,
        {
            "AND": [
                {"user_id": "alice"},
                {"metadata.topic": "tea"},
                {"categories": {"contains": "habits"}},
                {"created_at": "*"},
            ],
            "NOT": {"user_id": "bob"},
        },
    )
    assert combined.status_code == 200, combined.text
    assert combined.json()["results"], combined.text

    operator = _search_v3(c, {"user_id": {"in": ["alice", "carol"]}})
    assert operator.status_code == 200, operator.text
    assert operator.json()["results"], operator.text


def test_not_with_scalar_rejected_instead_of_crashing() -> None:
    # matches_filters would raise AttributeError on {"NOT": "x"}; the
    # contract turns that latent 500 into a 400.
    c = _client()
    response = _search_v3(c, {"user_id": "alice", "NOT": "bob"})
    assert response.status_code == 400
    assert "must be an object" in response.json()["detail"]


def test_task_state_keys_are_valid_filter_vocabulary() -> None:
    c = _client()
    _add_v3(c, "I drink green tea every morning.", "alice")
    for task_filter in ({"task_id": "t-1"}, {"goal_id": "g-1"}, {"task_phase": "build"}, {"phase": "build"}):
        response = _search_v3(c, {"user_id": "alice", **task_filter})
        assert response.status_code == 200, response.text


def test_metadata_dotted_path_with_operator_accepted() -> None:
    c = _client()
    _add_v3(c, "I drink green tea every morning.", "alice", metadata={"topic": "tea"})
    response = _search_v3(c, {"user_id": "alice", "metadata.topic": {"icontains": "TEA"}})
    assert response.status_code == 200, response.text
    assert response.json()["results"], response.text


def test_created_at_range_operators_match_end_to_end() -> None:
    c = _client()
    _add_v3(c, "I drink green tea every morning.", "alice")

    within = _search_v3(c, {"user_id": "alice", "created_at": {"gte": "2000-01-01"}})
    assert within.status_code == 200, within.text
    assert within.json()["results"], within.text

    before = _search_v3(c, {"user_id": "alice", "created_at": {"lte": "2000-01-01"}})
    assert before.status_code == 200, before.text
    assert not before.json()["results"], before.text


def test_delete_all_rejects_unknown_filter_key() -> None:
    c = _client()
    _add_v3(c, "I drink green tea every morning.", "alice")
    request = c.request(
        "DELETE",
        "/v1/memories/",
        json={"filters": {"user_id": "alice", "scope": "user"}},
    )
    assert request.status_code == 400
    # Nothing was deleted by the rejected request.
    remaining = _search_v3(c, {"user_id": "alice"})
    assert remaining.json()["results"]


def test_v2_list_rejects_unknown_key_but_accepts_show_expired() -> None:
    c = _client()
    _add_v3(c, "I drink green tea every morning.", "alice")

    junk = c.post("/v2/memories/", json={"user_id": "alice", "sc0pe": "user"})
    assert junk.status_code == 400
    assert "'sc0pe'" in junk.json()["detail"]

    # show_expired is a request option, not a filter key.
    listed = c.post("/v2/memories/", json={"user_id": "alice", "show_expired": True})
    assert listed.status_code == 200, listed.text
    assert listed.json()["count"] == 1


def test_mcp_search_surfaces_filter_contract_error() -> None:
    _client()
    with pytest.raises(HTTPException) as excinfo:
        call_tool(
            "search_memories",
            {"query": "tea", "filters": {"scope": "user"}},
            {"user_id": "codex", "client_name": "codex"},
        )
    assert excinfo.value.status_code == 400
    assert "scope by entity id" in str(excinfo.value.detail)


def test_mcp_boundary_validates_tools_that_ignore_unknown_keys() -> None:
    # get_task_state drops unrecognized filter keys instead of matching
    # nothing, so without boundary validation a typo would silently widen
    # the scope rather than narrow it.
    _client()
    with pytest.raises(HTTPException) as excinfo:
        call_tool(
            "get_task_state",
            {"filters": {"task_ids": "enacta-ui-reference-dogfood"}},
            {"user_id": "codex", "client_name": "codex"},
        )
    assert excinfo.value.status_code == 400
    assert "Did you mean 'task_id'?" in str(excinfo.value.detail)


def test_mcp_filters_schema_documents_vocabulary() -> None:
    documented = [
        tool for tool in TOOLS if "filters" in (tool.get("inputSchema", {}).get("properties") or {})
    ]
    assert documented, "no MCP tools expose a filters property"
    for tool in documented:
        description = tool["inputSchema"]["properties"]["filters"].get("description") or ""
        assert "user_id" in description, f"{tool['name']} filters schema lacks vocabulary"
        assert "Unknown keys are rejected" in description, f"{tool['name']} filters schema lacks rejection note"
