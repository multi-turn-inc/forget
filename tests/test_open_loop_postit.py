"""Open-loop post-its: aged unverified action claims surface at session start.

Regression guard for incident #0 (2026-07-22): "문의 발송" was recorded on
7/15 and sat unchallenged for a week — an open loop nobody chased — until the
agent built a false "reply pending → send a reminder" chain on top of it.
The post-it makes staleness itself visible: an agent-reported completion
claim (modality "reported") that stays open past MEM1_OPEN_LOOP_DAYS shows
up in the session-start capsule until the loop is closed by correction.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import get_db, init_db
from forget.server import app

_DB_COUNTER = 0
USER = f"postit-user-{uuid.uuid4().hex[:8]}"
APP = "postit-app"
MCP_PATH = f"/mcp/{APP}/http/{USER}"

STALE_CLAIM = "오버엣지 지분/IP 조건 문의 발송했음."
FRESH_CLAIM = "YC 원서 초안 제출했음."


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-postit-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
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


def _capsule_text(client: TestClient) -> str:
    result = _call(
        client,
        "prepare_context_autopilot",
        {"query": "session startup — active tasks, open loops", "include_debug": False},
        request_id=9,
    )
    return str(result.get("capsule_text") or "")


def _backdate_reported_claim(claim_text: str, days: int) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_db() as conn:
        conn.execute(
            "UPDATE claims SET created_at = ? WHERE modality = 'reported' AND claim_text = ?",
            (stale, claim_text),
        )


def test_aged_reported_claim_surfaces_and_correction_clears_it() -> None:
    client = _client()
    _call(client, "add_memory", {"text": STALE_CLAIM, "infer": False})
    _call(client, "add_memory", {"text": FRESH_CLAIM, "infer": False}, request_id=2)
    _backdate_reported_claim(STALE_CLAIM, days=5)

    capsule = _capsule_text(client)
    assert "열린 루프" in capsule, capsule
    assert STALE_CLAIM[:20] in capsule, capsule
    # fresh claims are not nagging material — only aged ones surface
    assert FRESH_CLAIM[:10] not in capsule, capsule

    # closing the loop by correction (supersede) removes the post-it
    results = _call(client, "search_memories", {"query": "오버엣지 문의 발송", "top_k": 1}, request_id=3)["results"]
    assert results
    _call(client, "supersede_memory", {"memory_id": results[0]["id"], "reason": "발송된 적 없음 — 사용자 정정"}, request_id=4)
    capsule_after = _capsule_text(client)
    assert STALE_CLAIM[:20] not in capsule_after, capsule_after


def test_confirm_clears_postit_and_promotes_to_green() -> None:
    # A TRUE unverified claim must not require supersede (="it was wrong") to
    # silence its post-it — confirm attaches the receipt and promotes it.
    client = _client()
    _call(client, "add_memory", {"text": STALE_CLAIM, "infer": False})
    _backdate_reported_claim(STALE_CLAIM, days=5)
    assert "열린 루프" in _capsule_text(client)

    results = _call(client, "search_memories", {"query": "오버엣지 문의 발송", "top_k": 1}, request_id=3)["results"]
    memory_id = results[0]["id"]

    # no receipt, no confirmation
    response = client.post(
        MCP_PATH,
        json={"jsonrpc": "2.0", "id": 4, "method": "tools/call",
              "params": {"name": "confirm_memory", "arguments": {"memory_id": memory_id}}},
    )
    assert "evidence" in response.text

    _call(client, "confirm_memory", {"memory_id": memory_id, "evidence": "발송 메일이 보낸편지함에서 확인됨"}, request_id=5)
    assert STALE_CLAIM[:20] not in _capsule_text(client)
    confirmed = _call(client, "search_memories", {"query": "오버엣지 문의 발송", "top_k": 1}, request_id=6)["results"][0]
    assert confirmed["trust"]["light"] == "green"
    assert "verified" in confirmed["trust"]["note"]
    with get_db() as conn:
        row = conn.execute("SELECT modality FROM claims WHERE memory_id = ?", (memory_id,)).fetchone()
    assert row["modality"] == "asserted"


def test_korean_negation_sets_negative_polarity() -> None:
    client = _client()
    _call(client, "add_memory", {"text": "오버엣지 문의는 발송된 적 없음.", "infer": False})
    with get_db() as conn:
        row = conn.execute("SELECT polarity FROM claims ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row["polarity"] == "negative"


def test_parallel_tracks_keep_shadowed_task_visible() -> None:
    # Taste-test finding 2026-07-23: the newest task epoch hijacked the
    # morning capsule; other in-flight tasks (the actual deadline) vanished.
    client = _client()
    _call(client, "record_task_state", {
        "task_id": "deadline-task",
        "status": "in_progress",
        "summary": "마감 태스크",
        "next_actions": ["수요일 아침: 계정 생성"],
    })
    _call(client, "record_task_state", {
        "task_id": "late-night-task",
        "status": "in_progress",
        "summary": "밤샘 기술 태스크",
        "next_actions": ["다음 조각 구현"],
    }, request_id=2)
    capsule = _capsule_text(client)
    # 불변식: 어느 쪽이 "현재 목표"로 뽑히든, 다른 활성 스레드가 병행 트랙으로 보인다
    assert "병행 트랙" in capsule, capsule
    assert "마감 태스크" in capsule or "deadline-task" in capsule, capsule
    assert "밤샘 기술 태스크" in capsule or "late-night-task" in capsule, capsule


def test_no_reported_claims_means_no_postit_line() -> None:
    client = _client()
    _call(client, "add_memory", {"text": "사용자는 로컬-퍼스트 아키텍처를 선호함.", "infer": False})
    capsule = _capsule_text(client)
    assert "열린 루프" not in capsule, capsule
