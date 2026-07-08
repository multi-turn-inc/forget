"""SQL entity prefilter must not change search behavior — it only narrows
the candidate rows loaded from SQLite (superset of primary-match plus
scope-fallback-eligible shared rows)."""

from fastapi.testclient import TestClient

from forget.server import app
from forget.store import _simple_entity_prefilter


client = TestClient(app)


def _add(text: str, **scope) -> None:
    response = client.post("/v1/memories/", json={"messages": [{"role": "user", "content": text}], "infer": False, **scope})
    assert response.status_code in (200, 201), response.text


def _search(filters: dict) -> list[str]:
    response = client.post("/v3/memories/search/", json={"query": "favorite database engine", "filters": filters, "top_k": 20})
    assert response.status_code == 200, response.text
    return [r["memory"] for r in response.json().get("results") or []]


def test_prefilter_shape_detection() -> None:
    assert _simple_entity_prefilter({"user_id": "u1"}) == {"user_id": "u1"}
    assert _simple_entity_prefilter({"user_id": "u1", "agent_id": "a1"}) == {"user_id": "u1", "agent_id": "a1"}
    assert _simple_entity_prefilter({"user_id": "u1", "categories": "x"}) is None
    assert _simple_entity_prefilter({"AND": [{"user_id": "u1"}]}) is None
    assert _simple_entity_prefilter({}) is None
    assert _simple_entity_prefilter({"user_id": ""}) is None


def test_search_isolation_and_fallback_preserved() -> None:
    _add("prefilter-user-a prefers the sqlite database engine", user_id="prefilter-a")
    _add("prefilter-user-b prefers the postgres database engine", user_id="prefilter-b")
    _add("the shared deployment uses the mysql database engine", agent_id="prefilter-agent")

    hits_a = _search({"user_id": "prefilter-a"})
    joined = " ".join(hits_a)
    assert "sqlite" in joined, hits_a
    assert "postgres" not in joined, "another user's row must never appear"

    # shared (no user_id) row stays reachable for fallback-enabled searches
    response = client.post(
        "/v3/memories/search/",
        json={"query": "mysql database engine", "filters": {"user_id": "prefilter-a"}, "top_k": 20, "scope_fallback": True},
    )
    assert response.status_code == 200
    fallback_join = " ".join(r["memory"] for r in response.json().get("results") or [])
    assert "mysql" in fallback_join, "shared agent-scoped row must survive the SQL prefilter"


def test_complex_filters_keep_full_scan_path() -> None:
    hits = client.post(
        "/v3/memories/search/",
        json={"query": "database engine", "filters": {"AND": [{"user_id": "prefilter-a"}]}, "top_k": 20},
    )
    assert hits.status_code == 200
    joined = " ".join(r["memory"] for r in hits.json().get("results") or [])
    assert "sqlite" in joined
