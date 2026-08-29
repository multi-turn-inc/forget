"""작업 관성 채널 계약 테스트 (P-M-2 — neural-memory-gate-study.md §9).

계약: ①관성 이력이 있으면 유사도 풀 밖 기억도 후보로 올라 결과에 등장 가능
②actr_boost가 score_breakdown에 기록 ③트레이스 없으면 완전 무동작
④스코프 규칙은 공용 채점 루프가 그대로 집행(타 소유 기억 누수 없음).
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-actr.sqlite3")

import pytest  # noqa: E402

from forget.db import get_db, init_db  # noqa: E402
from forget.store import add_memories, current_project_id, search_memories  # noqa: E402
from forget.utils import new_id, utc_now  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    init_db()


def _mem(text, user="owner-a"):
    out = add_memories({"messages": [{"role": "user", "content": text}],
                        "user_id": user, "infer": False, "hebbian": False})
    from forget.store import get_event
    return get_event(out["event_id"])["results"][0]["id"]


def _trace(selected, task="t1"):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO context_traces (trace_id, project_id, task_id, query,"
            " candidate_ids, selected_ids, created_at)"
            " VALUES (?, ?, ?, ?, '[]', ?, ?)",
            (new_id("trace"), current_project_id(), task, "q",
             json.dumps(selected), utc_now()),
        )


def test_inertia_surfaces_memory_similarity_would_miss():
    target = _mem("배포 반사: 서버 재기동이 곧 배포다")
    _mem("오늘 점심은 김치찌개")
    for _ in range(6):
        _trace([target])
    out = search_memories({"query": "완전히 무관한 주제의 질의문",
                           "filters": {"user_id": "owner-a"}, "top_k": 5,
                           "score_breakdown": True})
    ids = [r["id"] for r in out.get("results", [])]
    boosts = [r.get("score_breakdown", {}).get("actr_boost") for r in out.get("results", [])]
    assert target in ids                      # ① 관성으로 부상
    assert any(b for b in boosts)             # ② 계기 기록


def test_no_traces_no_effect():
    _mem("그냥 기억 하나")
    out = search_memories({"query": "그냥 기억", "filters": {"user_id": "owner-a"}})
    for r in out.get("results", []):
        assert "actr_boost" not in (r.get("score_breakdown") or {})  # ③


def test_inertia_respects_scope():
    secret = _mem("타인의 비밀 기억", user="owner-b")
    for _ in range(6):
        _trace([secret])
    out = search_memories({"query": "아무 질의",
                           "filters": {"user_id": "owner-a"}, "top_k": 10})
    assert secret not in [r["id"] for r in out.get("results", [])]   # ④ 누수 없음
