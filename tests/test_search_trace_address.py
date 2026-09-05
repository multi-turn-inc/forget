"""A traced search must hand back the address it just wrote.

Measured failure (2026-08-23): `trace: "turn_recall"` wrote the row — the
counter moved — but the response carried no trace_id, because the layered
recall gears call the v1 search internally and rebuild their response as
{"results", "recall_layer"}. The hook therefore never learned where to send
feedback: 784 turn_recall traces, zero with used_memory_ids, and the usage
that *was* measured landed on the session capsule's trace instead, pairing
real gold with the query "session startup — active tasks, open loops".

The reflex gear compounded it: one search per angle, so a single user-facing
recall minted several rows and none of them was reachable.
"""
import os
import uuid

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-trace-address.sqlite3")

from forget import store  # noqa: E402
from forget.db import get_db, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "trace.sqlite3"))
    monkeypatch.delenv("MEM1_RECALL_V2", raising=False)
    monkeypatch.setenv("MEM1_RECALL_TEMPORAL", "0")   # 이웃 동반은 이 시험의 관심사가 아니다
    init_db()
    yield


def _seed(user: str, n: int = 12) -> None:
    for i in range(n):
        store.add_memories({
            "messages": [{"role": "user", "content": f"조립기 실측 기록 {i}: 캐시 배치로 토큰 {i}% 절감"}],
            "user_id": user, "infer": False, "hebbian": False,
        })


def _trace_rows() -> list[tuple]:
    with get_db() as conn:
        return list(conn.execute("SELECT trace_id, query, selected_ids, payload FROM context_traces"))


def test_untraced_search_writes_nothing():
    user = f"tr-{uuid.uuid4().hex[:8]}"
    _seed(user)
    result = store.search_memories({"query": "캐시 배치 절감", "filters": {"user_id": user}, "top_k": 3})
    assert "trace_id" not in result
    assert _trace_rows() == []


def test_plain_traced_search_returns_its_address():
    user = f"tr-{uuid.uuid4().hex[:8]}"
    _seed(user)
    result = store.search_memories({
        "query": "캐시 배치 절감", "filters": {"user_id": user}, "top_k": 3, "trace": "turn_recall",
    })
    trace_id = result.get("trace_id")
    assert trace_id, "주소 없이 트레이스만 남으면 피드백이 붙을 곳이 없다"
    rows = _trace_rows()
    assert len(rows) == 1 and rows[0][0] == trace_id


@pytest.mark.parametrize("gear", ["reflex", "gate", "reader"])
def test_every_gear_returns_exactly_one_reachable_address(gear):
    # gate/reader는 LLM 미설정 시 v1으로 강등된다 — 주소 계약은 강등 경로에서도 같다.
    user = f"tr-{uuid.uuid4().hex[:8]}"
    _seed(user)
    result = store.search_memories({
        "query": "캐시 배치 절감", "filters": {"user_id": user}, "top_k": 3,
        "trace": "turn_recall", "recall": gear,
    })
    trace_id = result.get("trace_id")
    assert trace_id, f"{gear} 기어가 주소를 버렸다"
    rows = _trace_rows()
    assert len(rows) == 1, f"{gear} 기어가 트레이스 {len(rows)}개를 만들었다 — 사용자 회상 1회당 1개여야 한다"
    assert rows[0][0] == trace_id


def test_the_address_describes_what_was_returned():
    # 광폭 후보의 주소를 최종 선택의 주소로 착각하면 라벨이 엉뚱한 기억에 붙는다.
    user = f"tr-{uuid.uuid4().hex[:8]}"
    _seed(user, n=20)
    result = store.search_memories({
        "query": "캐시 배치 절감", "filters": {"user_id": user}, "top_k": 3,
        "trace": "turn_recall", "recall": "gate",
    })
    returned = [str(item["id"]) for item in result["results"] if item.get("id")]
    rows = _trace_rows()
    import json
    selected = [str(x) for x in json.loads(rows[0][2] or "[]")]
    assert selected == returned


def test_the_source_label_is_preserved_through_a_gear():
    import json
    user = f"tr-{uuid.uuid4().hex[:8]}"
    _seed(user)
    store.search_memories({
        "query": "캐시 배치 절감", "filters": {"user_id": user}, "top_k": 3,
        "trace": "turn_recall", "recall": "reflex",
    })
    payload = json.loads(_trace_rows()[0][3] or "{}")
    assert payload.get("source") == "turn_recall"
