"""score_breakdown must reassemble score — hidden corrections carry markers.

Regression guard for observation 33 (frictions.md, cycle 69): reassembling
score from score_breakdown silently failed on 4.22% of live rows because
feedback_adjusted_score never appeared in the breakdown, and task_state
claims bypass the rule×w + vector×w composition while presenting as
rule=vector=0. Acceptance criteria from the field note:

  ① rows with a nonzero feedback adjustment carry the applied delta in the
     breakdown; rows without feedback gain no key (false-positive control).
  ② composition-bypass rows carry an explicit marker, so rule=vector=0 is
     distinguishable from "zero lexical/semantic similarity".
  ③ reassembly reaches 100% on every surfaced row (live F1 was 99.81%).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import init_db
from forget.server import app
from forget.store import _search_score_weights

_DB_COUNTER = 0
USER = f"breakdown-user-{uuid.uuid4().hex[:8]}"
APP = "breakdown-app"
MCP_PATH = f"/mcp/{APP}/http/{USER}"


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-breakdown-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def _add(client: TestClient, text: str) -> str:
    response = client.post(
        "/v1/memories/",
        json={
            "messages": [{"role": "user", "content": text}],
            "infer": False,
            "user_id": USER,
        },
    )
    assert response.status_code in (200, 201), response.text
    body = response.json()
    items = body if isinstance(body, list) else body.get("results") or [body]
    return str(items[0]["id"])


def _feedback(client: TestClient, memory_id: str, value: str) -> None:
    response = client.post("/v1/feedback/", json={"memory_id": memory_id, "feedback": value})
    assert response.status_code == 200, response.text


def _search(client: TestClient, query: str, **overrides) -> list[dict]:
    payload = {
        "query": query,
        "filters": {"user_id": USER},
        "top_k": 10,
        "score_breakdown": True,
        **overrides,
    }
    response = client.post("/v3/memories/search/", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["results"]


def _mcp(client: TestClient, name: str, arguments: dict, request_id: int = 1) -> dict:
    response = client.post(
        MCP_PATH,
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    assert response.status_code == 200, response.text
    return json.loads(response.json()["result"]["content"][0]["text"])


def _reassemble(item: dict) -> float:
    """Recompute score from the breakdown alone, mirroring the search chain."""
    b = item["score_breakdown"]
    if b.get("task_state"):
        score = float(b["rule"])
    else:
        rule_w, vector_w = _search_score_weights()
        score = round(float(b["rule"]) * rule_w + float(b["vector"]) * vector_w, 4)
        if "entity_boost" in b:
            score = min(1.0, round(score + b["entity_boost"], 4))
        if "keyword" in b:
            score = min(1.0, round(score + 0.3 * b["keyword"], 4))
    if "feedback" in b:
        score = max(0.0, min(1.0, round(score + b["feedback"], 4)))
    if b.get("superseded"):
        score = round(score * 0.45, 4)
    if b.get("session_capture"):
        score = round(score * 0.5, 4)
    if item.get("scope") == "fallback":
        score = round(score * 0.88, 4)
    return round(score, 4)


def _assert_all_reassemble(results: list[dict]) -> None:
    assert results, "query surfaced nothing — the fixture lost its ground truth"
    for item in results:
        assert abs(_reassemble(item) - item["score"]) < 1e-9, item


def test_feedback_delta_is_visible_and_control_rows_gain_no_key() -> None:
    client = _client()
    liked = _add(client, "user prefers postgres over mysql for analytics workloads")
    plain = _add(client, "user prefers sqlite for tiny local tools")
    _feedback(client, liked, "POSITIVE")

    results = _search(client, "which database does the user prefer", threshold=0.05)
    by_id = {item["id"]: item for item in results}
    assert abs(by_id[liked]["score_breakdown"]["feedback"] - 0.05) < 1e-9, by_id[liked]
    assert "feedback" not in by_id[plain]["score_breakdown"], by_id[plain]
    _assert_all_reassemble(results)


def test_negative_feedback_delta_reassembles() -> None:
    client = _client()
    disliked = _add(client, "user prefers postgres over mysql for analytics workloads")
    _feedback(client, disliked, "NEGATIVE")

    results = _search(client, "user prefers postgres over mysql for analytics workloads")
    by_id = {item["id"]: item for item in results}
    assert disliked in by_id, results
    assert abs(by_id[disliked]["score_breakdown"]["feedback"] + 0.15) < 1e-9, by_id[disliked]
    _assert_all_reassemble(results)


def test_task_state_bypass_is_marked_and_reassembles() -> None:
    client = _client()
    _mcp(client, "record_task_state", {
        "task_id": "embedding-switch",
        "status": "in_progress",
        "summary": "임베딩 스위치는 outcome 측정 게이트 뒤로 미룸",
        "next_actions": ["주말 메아리 라벨 품질 비교"],
    })
    results = _mcp(
        client, "search_memories",
        {"query": "임베딩 스위치 결정", "top_k": 5, "score_breakdown": True},
        request_id=2,
    )["results"]
    claims = [r for r in results if (r.get("metadata") or {}).get("assertion_kind") == "task_state"]
    assert claims, results
    for claim in claims:
        b = claim["score_breakdown"]
        assert b.get("task_state") is True, claim
        assert "vector" not in b, "bypass rows must not fake a vector component"
        assert claim["score"] == _reassemble(claim), claim


def test_breakdown_stays_opt_in() -> None:
    # The markers ride the existing exposure contract — a search that never
    # asked for components must not start receiving them.
    client = _client()
    _add(client, "user prefers postgres over mysql for analytics workloads")
    _mcp(client, "record_task_state", {
        "task_id": "quiet",
        "status": "in_progress",
        "summary": "postgres analytics migration in progress",
    })
    response = client.post(
        "/v3/memories/search/",
        json={"query": "postgres analytics", "filters": {"user_id": USER}, "top_k": 10},
    )
    assert response.status_code == 200, response.text
    for item in response.json()["results"]:
        assert item.get("score_breakdown") in (None, {}), item


def test_reassembly_is_total_across_mixed_rows() -> None:
    # ③ as a sweep: plain rows, positive/negative/very-negative feedback and a
    # composition-bypass claim, all surfaced by one query, all reassemble.
    client = _client()
    ids = {
        "plain": _add(client, "the analytics pipeline exports parquet files nightly"),
        "pos": _add(client, "the analytics pipeline prefers duckdb for parquet scans"),
        "neg": _add(client, "the analytics pipeline once used csv exports nightly"),
        "very": _add(client, "the analytics pipeline nightly exports go to parquet"),
    }
    _feedback(client, ids["pos"], "POSITIVE")
    _feedback(client, ids["neg"], "NEGATIVE")
    _feedback(client, ids["very"], "VERY_NEGATIVE")
    _mcp(client, "record_task_state", {
        "task_id": "pipeline-hardening",
        "status": "in_progress",
        "summary": "analytics pipeline parquet export hardening",
    })

    results = _search(client, "analytics pipeline parquet nightly exports", threshold=0.05)
    _assert_all_reassemble(results)
    kinds = {
        "feedback": any("feedback" in r["score_breakdown"] for r in results),
        "task_state": any(r["score_breakdown"].get("task_state") for r in results),
        "plain": any(
            "feedback" not in r["score_breakdown"] and not r["score_breakdown"].get("task_state")
            for r in results
        ),
    }
    assert all(kinds.values()), (kinds, results)
