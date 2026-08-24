"""B-② G-신호 계기 — 검색 응답의 instrument 계약.

계약: ①강도 밴드 경계(≥0.45 strong / ≥0.33 moderate / 미만 weak — 신공간
실측 유도) ②증거 스팬 = 고유 날짜 수 ③풀 소진 신호 ④빈 결과에도 안전.
소비자는 에이전트 더듬기 — 신호는 물어본 확신이 아니라 잰 확신이다.
"""
import os

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-instrument.sqlite3")

from forget import store  # noqa: E402
from forget.db import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "inst.sqlite3"))
    monkeypatch.setenv("MEM1_RECALL_TEMPORAL", "0")
    init_db()
    yield


def _add(user, text, created=None):
    payload = {"messages": [{"role": "user", "content": text}], "user_id": user,
               "infer": False, "hebbian": False}
    if created:
        payload["created_at"] = created
    store.add_memories(payload)


def test_instrument_fields_and_span(tmp_path):
    _add("u1", "정훈은 커피를 좋아한다", "2026-08-01T10:00:00Z")
    _add("u1", "정훈은 커피를 아침에 마신다", "2026-08-03T10:00:00Z")
    res = store.search_memories({"query": "커피", "filters": {"user_id": "u1"}, "top_k": 10})
    inst = res["instrument"]
    assert set(inst) == {"top_score", "strength", "evidence_span_days",
                         "result_count", "pool_exhausted"}
    assert inst["result_count"] == len(res["results"]) >= 1
    assert inst["evidence_span_days"] >= 1
    assert inst["pool_exhausted"] is True  # 후보 2 < top_k 10


def test_strength_bands_follow_top_score(tmp_path):
    _add("u2", "완전히 무관한 잡담 한 줄", "2026-08-01T10:00:00Z")
    res = store.search_memories({"query": "양자 중력 세미나", "filters": {"user_id": "u2"},
                                 "top_k": 5, "threshold": 0.0})
    inst = res["instrument"]
    expected = ("strong" if inst["top_score"] >= 0.45
                else "moderate" if inst["top_score"] >= 0.33 else "weak")
    assert inst["strength"] == expected


def test_empty_results_safe(tmp_path):
    res = store.search_memories({"query": "아무것도", "filters": {"user_id": "없는유저"},
                                 "top_k": 5})
    inst = res["instrument"]
    assert inst["result_count"] == 0
    assert inst["top_score"] == 0.0
    assert inst["strength"] == "weak"
    assert inst["pool_exhausted"] is True


def test_gate_gear_carries_instrument(tmp_path, monkeypatch):
    # 마찰 #3 회귀 계약 (2026-08-25): 라이브 기본 기어(recall high → gate-v2)는
    # search_memories 초입에서 조기 반환한다 — 첫 배선(v1 반환 전용)이 통째로
    # 우회됐다. 기어의 모든 반환 경로에 계기가 실려야 한다.
    for i in range(6):
        _add("u3", f"세계모델 상태 유형 메모 {chr(0xAC00 + i)}",
             f"2026-08-{10 + i:02d}T10:00:00Z")
    # ① passthrough: 광폭 후보(≤6) ≤ top_k 10
    res = store.search_memories({"query": "세계모델", "filters": {"user_id": "u3"},
                                 "top_k": 10, "recall": "high", "threshold": 0.0})
    assert str(res["recall_layer"]).startswith("gate-v2")
    inst = res["instrument"]
    assert inst["result_count"] == len(res["results"]) >= 1
    assert inst["pool_exhausted"] is True  # 광폭 16을 못 채움 — 풀 바닥이 광폭 신호로 전달
    # ② unconfigured→v1: 후보 > top_k, 선별 LLM 미구성
    monkeypatch.setattr(store, "_resolve_recall_llm", lambda: None)
    res2 = store.search_memories({"query": "세계모델", "filters": {"user_id": "u3"},
                                  "top_k": 2, "recall": "high", "threshold": 0.0})
    assert "unconfigured" in str(res2["recall_layer"])
    inst2 = res2["instrument"]
    assert inst2["result_count"] == len(res2["results"]) == 2
    assert inst2["pool_exhausted"] is True  # 소진은 선별이 아니라 광폭 풀의 사실


def test_layered_funnel_attaches_when_missing():
    # 안전망 계약: 미래의 어떤 기어가 와도 깔때기가 계기를 보증한다.
    out = store._layered_recall_result({"results": []}, payload={}, project_id="p")
    assert out["instrument"]["result_count"] == 0
    assert out["instrument"]["pool_exhausted"] is None  # 풀 미상은 미상으로 정직하게
