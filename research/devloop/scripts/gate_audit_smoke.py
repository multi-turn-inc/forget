"""gate_audit 격리 스모크 — p7a와 동일한 무작위 ADD 트래픽 위에서
aggregate_accounting이 전수 분모 비율을 내는지, 외부 관측치와 맞는지 대조.

임시 DB(/tmp) 인프로세스 실행 — 실DB(:8000, ~/.forget) 무접촉.
재현: .venv/bin/python research/devloop/scripts/gate_audit_smoke.py (저장소 루트에서)
"""
import importlib.util
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

path = Path("/tmp/mem1-gate-audit-smoke-c17.sqlite3")
for s in ("", "-wal", "-shm"):
    path.with_name(path.name + s).unlink(missing_ok=True)
os.environ["MEM1_DB_PATH"] = str(path)

from forget import db as app_db  # noqa: E402
app_db.DB_PATH = path
from forget.db import init_db, get_db  # noqa: E402
init_db()
from fastapi.testclient import TestClient  # noqa: E402
from forget.server import app  # noqa: E402
from forget.store import list_events  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "gate_audit", ROOT / "research" / "devloop" / "scripts" / "gate_audit.py")
gate_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate_audit)

client = TestClient(app, base_url="http://testserver")

random.seed(17)
subjects = ["결제", "배포", "요금제", "온보딩", "로그인", "데이터베이스", "알림", "백업"]
verbs = ["Paddle로 확정했어", "매주 금요일로 옮기기로 했어", "연 99달러로 정했어",
         "이메일 없이 진행하기로 했어", "패스키만 쓰기로 했어"]
fillers = ["Thanks so much!", "Got it, I'll handle it.", "Deploy now.", "Sure thing!",
           "Consider adding a checklist before deploying.", ""]

for i in range(40):
    msgs = []
    for _ in range(random.randint(1, 5)):
        if random.random() < 0.5:
            msgs.append({"role": "user",
                         "content": f"우리 {random.choice(subjects)}는 {random.choice(verbs)}."})
        else:
            msgs.append({"role": random.choice(["user", "assistant"]),
                         "content": random.choice(fillers)})
    body = {"jsonrpc": "2.0", "id": i, "method": "tools/call",
            "params": {"name": "add_memory",
                       "arguments": {"messages": msgs, "infer": True,
                                     "sanitize": bool(random.random() < 0.5)}}}
    r = client.post("/mcp/smoke-app/http/smoke-user", json=body)
    assert r.status_code == 200, r.text

# gate_audit이 MCP list_events로 받는 것과 동일한 행 형태.
add_events = [e for e in list_events(page=1, page_size=200)["results"]
              if e["event_type"] == "ADD"]
report = gate_audit.aggregate_accounting(add_events)

with get_db() as conn:
    mem_count = conn.execute("SELECT COUNT(*) c FROM memories WHERE deleted=0").fetchone()["c"]
    gate_count = conn.execute("SELECT COUNT(*) c FROM gate_log").fetchone()["c"]

print(json.dumps({
    "report": report,
    "external_check": {
        "sum_memories_created": report["totals"].get("memories_created", 0),
        "db_memory_rows": mem_count,
        "created_matches_db": report["totals"].get("memories_created", 0) == mem_count,
        "counted_refusals": report["counted_refusals"],
        "db_gate_log_rows": gate_count,
        "refusals_match_log": report["counted_refusals"] == gate_count,
    },
}, ensure_ascii=False, indent=1))
