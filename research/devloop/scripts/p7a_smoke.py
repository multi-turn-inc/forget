"""P7(a) 격리 스모크 — 무작위 ADD 트래픽 40이벤트에서 회계 항등식 + 외부 대조.

임시 DB(/tmp) 인프로세스 실행 — 실DB(:8000, ~/.forget) 무접촉.
재현: .venv/bin/python research/devloop/scripts/p7a_smoke.py (저장소 루트에서)
사이클 16 실측: 위반 0, 회계 누락 0, created 63=DB 63, drops 23=gate_log 23.
"""
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

path = Path("/tmp/mem1-p7a-smoke-c16.sqlite3")
for s in ("", "-wal", "-shm"):
    path.with_name(path.name + s).unlink(missing_ok=True)
os.environ["MEM1_DB_PATH"] = str(path)

from forget import db as app_db  # noqa: E402
app_db.DB_PATH = path
from forget.db import init_db, get_db  # noqa: E402
init_db()
from fastapi.testclient import TestClient  # noqa: E402
from forget.server import app  # noqa: E402
from forget.store import add_accounting_violations  # noqa: E402

client = TestClient(app, base_url="http://testserver")

random.seed(16)
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

with get_db() as conn:
    rows = conn.execute("SELECT metadata FROM events WHERE event_type='ADD'").fetchall()
    mem_count = conn.execute("SELECT COUNT(*) c FROM memories WHERE deleted=0").fetchone()["c"]
    gate_count = conn.execute("SELECT COUNT(*) c FROM gate_log").fetchone()["c"]

accs = [json.loads(r["metadata"]).get("accounting") for r in rows]
missing = [i for i, a in enumerate(accs) if not a]
viols = []
for a in accs:
    if a:
        viols.extend(add_accounting_violations(a))
sum_created = sum((a or {}).get("memories_created", 0) for a in accs)
sum_drops = sum((a or {}).get("gate_dropped", 0) + (a or {}).get("ack_messages_dropped", 0)
                + (a or {}).get("sanitize_dropped", 0) for a in accs)
print(json.dumps({
    "add_events": len(accs), "events_missing_accounting": len(missing),
    "identity_violations": viols,
    "sum_memories_created": sum_created, "db_memory_rows": mem_count,
    "created_matches_db": sum_created == mem_count,
    "sum_counted_drops": sum_drops, "db_gate_log_rows": gate_count,
    "drops_match_log": sum_drops == gate_count,
}, ensure_ascii=False, indent=1))
