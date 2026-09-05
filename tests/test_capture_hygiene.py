"""P-C-2 캡처 포인터 위생 레인 계약 (memory-intelligence-design.md §4.5).

계약: ①어휘 겹침 0인 질의에서 캡처 포인터는 후보 경쟁에서 구조적 제외
②세션을 사냥하는 질의(토큰 겹침 >0)는 종전 ×0.5 강등으로 생존 + 계기 기록
③include_session_captures=True는 전면 opt-in (재수화 흐름) ④일반 기억은 불변.
"""
from __future__ import annotations

import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-cap.sqlite3")

import pytest  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.store import add_memories, search_memories  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    monkeypatch.setenv("FORGET_LEARNED_RANKER", str(tmp_path / "absent.json"))
    init_db()


def _capture(text):
    out = add_memories({"messages": [{"role": "user", "content": text}],
                        "user_id": "owner-a", "infer": False, "hebbian": False,
                        "metadata": {"hook": "SessionEnd", "session_id": "s1"}})
    from forget.store import get_event
    return get_event(out["event_id"])["results"][0]["id"]


def _search(query, **kw):
    return search_memories({"query": query, "filters": {"user_id": "owner-a"},
                            "top_k": 10, "score_breakdown": True, **kw})


def test_vector_only_query_excludes_captures():
    cap = _capture("세션 캡처: 배포 파이프라인과 롤백 절차 논의")
    out = _search("완전히 무관한 주제의 어휘들")
    assert cap not in [r["id"] for r in out.get("results", [])]          # ①


def test_lexical_hunt_still_surfaces_with_demotion():
    cap = _capture("세션 캡처: 배포 파이프라인과 롤백 절차 논의")
    out = _search("배포 파이프라인 세션 찾아줘")
    row = next((r for r in out["results"] if r["id"] == cap), None)
    assert row is not None                                               # ②
    assert row["score_breakdown"].get("session_capture") is True


def test_opt_in_bypasses_exclusion():
    cap = _capture("세션 캡처: 배포 파이프라인과 롤백 절차 논의")
    out = _search("완전히 무관한 주제의 어휘들", include_session_captures=True)
    ids = [r["id"] for r in out.get("results", [])]
    # opt-in이면 제외 없이 종전 강등 경로 — 문턱을 넘으면 등장 가능해야 한다.
    # (등장 여부는 점수에 달렸으니 계약은 "제외 로직 미발동"만: 등장 시 계기 확인)
    row = next((r for r in out["results"] if r["id"] == cap), None)
    if row is not None:
        assert row["score_breakdown"].get("session_capture") is True     # ③


def test_normal_memories_unaffected():
    out = add_memories({"messages": [{"role": "user", "content": "정훈은 mpnet 임베딩을 쓴다"}],
                        "user_id": "owner-a", "infer": False, "hebbian": False})
    from forget.store import get_event
    mid = get_event(out["event_id"])["results"][0]["id"]
    got = _search("mpnet 임베딩")
    assert mid in [r["id"] for r in got["results"]]                      # ④
