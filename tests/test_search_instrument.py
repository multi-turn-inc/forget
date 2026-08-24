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
