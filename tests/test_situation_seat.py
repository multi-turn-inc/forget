"""상황 좌석 계약 (P-M-8, §19).

계약: ①외래어 다리(벤치마크↔bench)가 결정론으로 발화 문턱을 완화
②문턱 미달 전원이면 판독기 호출 없이 None ③판독기 none이면 None
④판독기 픽은 shortlist 안에서만 유효 ⑤짧은 질의 None.
"""
from __future__ import annotations

import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-sit.sqlite3")

import pytest

from forget import situation


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    from forget.db import init_db
    init_db()


def _fake_tasks(monkeypatch, tasks):
    monkeypatch.setattr("forget.store.get_task_state",
                        lambda payload=None, project_id=None: {"results": tasks})


def test_loanword_bridge_lowers_gate(monkeypatch):
    _fake_tasks(monkeypatch, [
        {"task_id": "bench-loop", "current_goal": "LME-V2 캠페인 제출 대기"},
        {"task_id": "quant-x", "current_goal": "무관한 퀀트 트랙"},
    ])
    # 임베딩 결정론(테스트 폴백)에선 코사인이 낮다 — 다리 없으면 발화 실패,
    # 다리(벤치마크→bench)가 있으면 완화 문턱이 적용돼 판독기까지 간다.
    called = {}
    monkeypatch.setattr(situation, "_llm_pick",
                        lambda q, s: called.setdefault("short", [t["task_id"] for t in s]) and "bench-loop")
    monkeypatch.setattr(situation, "COS_GATE_BRIDGED", -1.0)   # 다리 경로만 통과
    monkeypatch.setattr(situation, "COS_GATE", 2.0)            # 코사인 단독 봉쇄
    out = situation.situation_recall("벤치마크 돌려서 증명해볼 수 있으려나?", "proj_local")
    assert out and out["task_id"] == "bench-loop" and out["via"] == "bridge+reader"   # ①
    assert called["short"][0] == "bench-loop"                  # 다리 적중이 서열 우선


def test_no_candidate_fires_no_reader(monkeypatch):
    _fake_tasks(monkeypatch, [{"task_id": "quant-x", "current_goal": "퀀트 트랙"}])
    monkeypatch.setattr(situation, "COS_GATE", 2.0)
    monkeypatch.setattr(situation, "COS_GATE_BRIDGED", 2.0)
    boom = lambda q, s: (_ for _ in ()).throw(AssertionError("판독기 호출 금지"))
    monkeypatch.setattr(situation, "_llm_pick", boom)
    assert situation.situation_recall("완전히 무관한 질문이려나?", "proj_local") is None  # ②


def test_reader_none_is_silence(monkeypatch):
    _fake_tasks(monkeypatch, [{"task_id": "bench-loop", "current_goal": "LME-V2 제출"}])
    monkeypatch.setattr(situation, "COS_GATE_BRIDGED", -1.0)
    monkeypatch.setattr(situation, "_llm_pick", lambda q, s: None)
    assert situation.situation_recall("벤치마크 얘기인데 판독기가 기권?", "proj_local") is None  # ③


def test_reader_pick_must_be_in_shortlist(monkeypatch):
    _fake_tasks(monkeypatch, [{"task_id": "bench-loop", "current_goal": "LME-V2 제출"}])
    monkeypatch.setattr(situation, "COS_GATE_BRIDGED", -1.0)
    monkeypatch.setattr(situation, "_llm_pick", lambda q, s: "hallucinated-track")
    assert situation.situation_recall("벤치마크 증명 되려나?", "proj_local") is None  # ④


def test_short_query_silent():
    assert situation.situation_recall("뭐?", "proj_local") is None                    # ⑤
