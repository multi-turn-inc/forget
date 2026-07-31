"""ADD 파이프라인 회계 — F5 침묵 잊음의 항등식 (사이클 16, P7a).

사이클 7 기준선: 30일 ADD 34,530건 → 기억 517개, 게이트 로그 1건 —
잊음의 사실상 전부가 감사 추적 밖에서 일어났다. 결함은 거름의 양이
아니라 거름의 관측 불가능성. 이 테스트는 그 수용 기준을 검사한다:
파이프라인에 들어간 모든 단위는 저장·로그된 거부·계수된 탈락 중
하나로 나가야 하며(스테이지별 보존식), 분모의 권위는 카운터에 있다
(게이트 로그는 이벤트당 50건 샘플).
"""

import json
import os
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import get_db, init_db
from forget.memory_engine import extract_memories
from forget.server import app
from forget.store import add_accounting_violations

_DB_COUNTER = 0
USER = f"accounting-user-{uuid.uuid4().hex[:8]}"
MCP_PATH = f"/mcp/accounting-app/http/{USER}"


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-accounting-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def _call(client: TestClient, name: str, arguments: dict, request_id: int = 1) -> dict:
    response = client.post(
        MCP_PATH,
        json={"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
              "params": {"name": name, "arguments": arguments}},
    )
    assert response.status_code == 200, response.text
    return json.loads(response.json()["result"]["content"][0]["text"])


def _last_add_accounting() -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT metadata FROM events WHERE event_type = 'ADD' "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    return json.loads(row["metadata"]).get("accounting") or {}


MIXED_MESSAGES = [
    {"role": "user", "content": "우리 결제는 Paddle로 확정했어."},   # 저장될 사실
    {"role": "user", "content": "Thanks so much!"},                    # smalltalk → 게이트
    {"role": "assistant", "content": "Consider offering a buy-it-now option for the painting."},  # 조언 → 게이트
    {"role": "assistant", "content": "Got it, I'll set that up."},     # ack → 게이트
    {"role": "assistant", "content": "Deploy now."},                   # <3 단어 → 단편 탈락(구 침묵 경로)
    {"role": "user", "content": ""},                                   # 빈 메시지
]


def test_extraction_counters_conserve() -> None:
    accounting: dict = {}
    gate_log: list[dict] = []
    facts = extract_memories(MIXED_MESSAGES, infer=True, gate_log=gate_log, accounting=accounting)
    assert accounting["messages_in"] == len(MIXED_MESSAGES)
    assert accounting["empty_messages"] == 1
    assert accounting["ack_messages_dropped"] == 1
    assert accounting["fragments_dropped"] >= 1
    assert accounting["gate_dropped"] == len(gate_log) - 1  # ack은 메시지 단위로 별도 계수
    assert accounting["facts_extracted"] == len(facts)
    assert accounting["facts_raw"] == accounting["facts_extracted"] + accounting.get("batch_deduped", 0)


def test_batch_dedup_is_counted_not_silent() -> None:
    accounting: dict = {}
    facts = extract_memories(
        [
            {"role": "user", "content": "우리 결제는 Paddle로 확정했어."},
            {"role": "user", "content": "우리 결제는 Paddle로 확정했어."},
        ],
        infer=True,
        accounting=accounting,
    )
    assert accounting["batch_deduped"] >= 1
    assert accounting["facts_raw"] == len(facts) + accounting["batch_deduped"]


def test_add_event_persists_accounting_and_identity_holds() -> None:
    client = _client()
    _call(client, "add_memory", {"messages": MIXED_MESSAGES, "infer": True})
    accounting = _last_add_accounting()
    assert add_accounting_violations(accounting) == [], accounting
    assert "identity_violations" not in accounting
    assert accounting["memories_created"] >= 1
    # 외부 대조: 카운터 = 실제 DB 관측치 (P7a의 반증 지점)
    with get_db() as conn:
        memory_rows = conn.execute("SELECT COUNT(*) AS c FROM memories WHERE deleted = 0").fetchone()["c"]
        gate_rows = conn.execute("SELECT COUNT(*) AS c FROM gate_log").fetchone()["c"]
    assert accounting["memories_created"] == memory_rows
    # 게이트 로그 행 = gate_dropped(문장) + ack(메시지) — 50캡 미만 구간이므로 전량 일치
    assert gate_rows == accounting["gate_dropped"] + accounting["ack_messages_dropped"]


def test_duplicate_skip_is_counted_under_sanitize() -> None:
    client = _client()
    message = {"messages": [{"role": "user", "content": "우리 결제는 Paddle로 확정했어."}],
               "infer": True, "sanitize": True}
    _call(client, "add_memory", message)
    first = _last_add_accounting()
    assert first["memories_created"] >= 1
    _call(client, "add_memory", message, request_id=2)
    second = _last_add_accounting()
    assert second["duplicate_skipped"] >= 1
    assert second["memories_created"] == 0
    assert add_accounting_violations(second) == [], second


def test_violation_checker_flags_missing_denominator() -> None:
    # 저장 단계에서 1건이 증발한 회계 — 검사기가 잡아야 한다
    broken = {"facts_raw": 3, "facts_extracted": 3, "facts_out": 3,
              "records_kept": 3, "fact_scope_pairs": 3,
              "memories_created": 2, "duplicate_skipped": 0}
    assert any("storage" in v for v in add_accounting_violations(broken))
    # 원격 프로바이더 이벤트는 문장 단위 불투명 — 저장식만 검사
    provider = {"provider_extractions": 1, "facts_out": 5, "records_kept": 5,
                "fact_scope_pairs": 5, "memories_created": 5}
    assert add_accounting_violations(provider) == []
