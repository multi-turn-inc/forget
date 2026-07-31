"""Recall relevance: active task states must not outrank the turn's topic.

Regression guard for friction F2 (field note #2, 2026-07-31): during devloop
cycle 0 the unrelated Quant task surfaced four times in turn recall. The
mechanism was a flat +0.08 activeness boost in _task_state_search_results —
stacked on score_memory's recency bonus (≤0.08) it handed every fresh active
state ~0.16 of topic-free score, enough to ride over recall gates on prompts
it had nothing to do with.

The contract after the fix:
- read side: search ranks task states by topic like any memory; being
  in_progress earns only the recency bonus. An off-topic active state stays
  below the default threshold and out of the results.
- the capsule remains the one place active states appear topic-free —
  activeness is session-start context, not per-turn relevance.
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

_DB_COUNTER = 0
USER = f"recall-user-{uuid.uuid4().hex[:8]}"
APP = "recall-app"
MCP_PATH = f"/mcp/{APP}/http/{USER}"


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-recall-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def _call(client: TestClient, name: str, arguments: dict, request_id: int = 1) -> dict:
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


def _task_state_results(results: list[dict]) -> list[dict]:
    return [
        r for r in results
        if (r.get("metadata") or {}).get("assertion_kind") == "task_state"
    ]


def test_off_topic_active_task_state_stays_out_of_recall() -> None:
    # The F2 shape: a fresh in_progress task about a foreign topic must not
    # appear on a query it shares no ground with. Recency alone (~0.08) sits
    # below the default threshold (0.1); only a topic-free boost put it back.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "quant-weekly",
        "status": "in_progress",
        "summary": "Quant 16주 검증 주간 데이터 워크플로 하드닝",
        "next_actions": ["월요일 주간 리포트 갱신"],
    })
    results = _call(
        client, "search_memories",
        {"query": "캡슐 신선도 경고 배치 설계", "top_k": 5},
        request_id=2,
    )["results"]
    assert not _task_state_results(results), results


def test_on_topic_active_task_state_still_surfaces() -> None:
    # Relevance and activeness are orthogonal — dropping the boost must not
    # cost topical recall of the state itself.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "embedding-switch",
        "status": "in_progress",
        "summary": "임베딩 스위치는 outcome 측정 게이트 뒤로 미룸",
        "next_actions": ["주말 메아리 라벨 품질 비교"],
    })
    results = _call(
        client, "search_memories",
        {"query": "임베딩 스위치 결정", "top_k": 5},
        request_id=2,
    )["results"]
    hits = _task_state_results(results)
    assert hits, results
    assert any("임베딩 스위치" in str(r.get("memory") or "") for r in hits), hits
