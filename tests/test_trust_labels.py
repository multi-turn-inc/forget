"""Trust labels (traffic light): provenance-stamped writes, permission-labeled reads.

Regression guard for the 2026-07-22 dogfooding incident: a 7/15 session
summary recorded a *planned* action ("오버엣지 지분/IP 조건 문의 발송") as a
completed action. MCP text saves were wrapped as role "user", laundering the
agent's self-summary into top-authority user speech; a week later the agent
built a "reply pending → send a reminder" chain on top of the false memory
and nearly sent a follow-up for an email that never existed.

The fix has two ends that must stay wired together:
- write side: text saves default to source_role "assistant"; agent-side
  completion claims get modality "reported" and a yellow trust stamp.
- read side: search results surface `trust` as a permission label, without
  demoting relevance (find it, but say what it is).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import get_db, init_db
from forget.server import app

_DB_COUNTER = 0
USER = f"trust-user-{uuid.uuid4().hex[:8]}"
APP = "trust-app"
MCP_PATH = f"/mcp/{APP}/http/{USER}"

CONTAMINATED = "오늘 사용자 액션: YC 계정 생성과 문항 덤프, 오버엣지 지분/IP 조건 문의 발송."


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-trust-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
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


def _search(client: TestClient, query: str) -> list[dict]:
    return _call(client, "search_memories", {"query": query}, request_id=9)["results"]


def test_agent_text_save_is_yellow_action_report() -> None:
    client = _client()
    _call(client, "add_memory", {"text": CONTAMINATED, "infer": False})
    results = _search(client, "오버엣지 문의 발송")
    assert results, "relevance and authority are orthogonal — the memory must still be findable"
    trust = results[0].get("trust")
    assert trust, "search results must carry the trust label"
    assert trust["light"] == "yellow"
    assert trust["source"] == "assistant"
    assert trust["kind"] == "action_report"
    assert "confirm" in trust.get("note", "")


def test_user_voiced_messages_stay_green() -> None:
    client = _client()
    _call(
        client,
        "add_memory",
        {"messages": [{"role": "user", "content": "저는 메모리 엔진으로 forget을 씁니다."}], "infer": False},
    )
    results = _search(client, "메모리 엔진 뭐 써")
    assert results
    trust = results[0].get("trust")
    assert trust and trust["light"] == "green" and trust["source"] == "user"


def test_explicit_source_role_user_overrides_text_default() -> None:
    client = _client()
    _call(
        client,
        "add_memory",
        {"text": "오버엣지 문의는 발송된 적 없다고 사용자가 직접 확인함.", "source_role": "user", "infer": False},
    )
    results = _search(client, "오버엣지 문의 확인")
    assert results and results[0]["trust"]["light"] == "green"


def test_agent_action_claim_modality_is_reported() -> None:
    client = _client()
    _call(client, "add_memory", {"text": CONTAMINATED, "infer": False})
    with get_db() as conn:
        row = conn.execute(
            "SELECT modality, source_role FROM claims ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    assert row["modality"] == "reported"
    assert row["source_role"] == "assistant"


def test_session_capture_pointers_rank_below_real_facts() -> None:
    # Dogfooding finding 2026-07-22: capture entries quote user utterances
    # verbatim, so they outranked the real facts those utterances asked about.
    client = _client()
    _call(client, "add_memory", {"text": "오버엣지 문의는 보류하기로 결정함.", "infer": False})
    _call(
        client,
        "add_memory",
        {
            "text": "세션 캡처 (SessionEnd/exit): 세션 xyz — 최근 사용자 발화: 오버엣지 문의 보냈었나? 보류 결정 확인. 전문: /tmp/x.jsonl",
            "infer": False,
            "source_role": "tool",
            "metadata": {"hook": "SessionEnd", "session_id": "xyz"},
        },
        request_id=2,
    )
    results = _search(client, "오버엣지 문의 보류")
    assert results
    assert not (results[0].get("metadata") or {}).get("hook"), results[0]["memory"]


def test_plain_agent_fact_is_yellow_without_action_note() -> None:
    client = _client()
    _call(client, "add_memory", {"text": "사용자는 로컬-퍼스트 아키텍처를 선호함.", "infer": False})
    results = _search(client, "아키텍처 선호")
    assert results
    trust = results[0]["trust"]
    assert trust["light"] == "yellow" and trust["kind"] == "fact"
    assert "note" not in trust
