"""Gate log — forgetting with an audit trail.

The observation gate is an editor, and editors are power: what was
dropped and why must be reviewable by the store's owner ("잊은 것의
목록조차 네 것이어야 한다"). The log itself forgets — default 30-day
retention — because an immortal log of drops would just be a second,
shadow memory.
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

_DB_COUNTER = 0
USER = f"gatelog-user-{uuid.uuid4().hex[:8]}"
MCP_PATH = f"/mcp/gatelog-app/http/{USER}"


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-gatelog-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
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


def test_extractor_reports_drops_with_reasons() -> None:
    gate_log: list[dict] = []
    facts = extract_memories(
        [
            {"role": "assistant", "content": "Consider offering a buy-it-now option for the live painting."},
            {"role": "user", "content": "Thanks so much!"},
        ],
        infer=True,
        gate_log=gate_log,
    )
    assert facts == []
    reasons = {entry["reason"] for entry in gate_log}
    assert "assistant_advice_or_knowledge" in reasons
    assert "user_smalltalk" in reasons


def test_drops_persist_and_are_listable_via_mcp() -> None:
    client = _client()
    _call(client, "add_memory", {
        "messages": [
            {"role": "user", "content": "우리 결제는 Paddle로 확정했어."},
            {"role": "assistant", "content": "Consider adding a checklist before deploying."},
        ],
        "infer": True,
    })
    listed = _call(client, "list_gate_log", {"limit": 10}, request_id=2)
    dropped = [entry["text"] for entry in listed["results"]]
    assert any("checklist" in text for text in dropped), listed
    assert all(entry["reason"] for entry in listed["results"])


def test_gate_log_retention_sweeps_old_rows() -> None:
    client = _client()
    _call(client, "add_memory", {
        "messages": [{"role": "assistant", "content": "Consider using a swap file for memory pressure."}],
        "infer": True,
    })
    with get_db() as conn:
        conn.execute("UPDATE gate_log SET created_at = '2020-01-01T00:00:00Z'")
    # 다음 쓰기가 청소를 트리거
    _call(client, "add_memory", {
        "messages": [{"role": "assistant", "content": "Consider enabling verbose logs for debugging."}],
        "infer": True,
    }, request_id=3)
    listed = _call(client, "list_gate_log", {"limit": 50}, request_id=4)
    assert all(entry["created_at"] > "2020-01-02" for entry in listed["results"]), listed
