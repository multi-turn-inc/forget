"""자기 하네스 H-0 골격 계약 (헌장: docs/self-harness-design.md).

계약: ①기상은 이력을 소유한다 — 강제 종료된 run을 재수화하면 턴이 그대로
돌아온다 (P-H-0의 측정 지점) ②유언장이 기상 블록에 실리고 만료는 재심사
표시가 붙는다 ③비용 가드는 상한에서 끊는다 ④wake_report가 남는다 —
연속성 충실도 계기의 원자료.
"""
import json
import sqlite3

import pytest

from forget import selfharness as sh
from forget import worldmodel


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(sh, "HARNESS_DB", str(tmp_path / "harness.sqlite3"))
    monkeypatch.setattr(sh, "FORGET_URL", "http://127.0.0.1:1")  # 캡슐 fail-open 검증
    monkeypatch.setattr(worldmodel, "DEFAULT_WORLD_DB", str(tmp_path / "world.sqlite3"))
    yield


def test_wake_owns_history_across_kill(tmp_path):
    first = sh.wake("파생 v1 정찰")
    assert first["messages"][0]["content"] == "파생 v1 정찰"
    sh.record_turn(first["run_id"], 0, "user", "파생 v1 정찰")
    sh.record_turn(first["run_id"], 1, "assistant",
                   [{"type": "text", "text": "timeline을 훑는 중"}])
    # 강제 종료 시나리오: finish_run 없이 프로세스 사망 → 다음 기상이 찾아낸다
    assert sh.last_unfinished_run() == first["run_id"]
    second = sh.wake("파생 v1 정찰", resume_run=first["run_id"])
    assert len(second["messages"]) == 2
    assert second["messages"][1]["content"][0]["text"] == "timeline을 훑는 중"
    assert "WAKING into an interrupted run" in second["system"]


def test_wake_block_carries_hands_and_expiry(tmp_path):
    world = worldmodel.DEFAULT_WORLD_DB
    worldmodel.arm_hand(world, "g1", "watch", "llama-server 재기동 억제",
                        "훈련이 VRAM 점유", "run_w2b", expires_at="2020-01-01T00:00:00Z")
    out = sh.wake("아무 작업")
    assert "llama-server 재기동 억제" in out["system"]
    assert "EXPIRED" in out["system"]          # 만료 손은 재심사 표시
    assert out["hands"][0]["expired"] is True
    conn = sqlite3.connect(sh.HARNESS_DB)
    n_hands, capsule_chars = conn.execute(
        "SELECT hands_inherited, capsule_chars FROM wake_reports").fetchone()
    conn.close()
    assert n_hands == 1
    assert capsule_chars == 0                  # forget 죽어도 기상은 된다 (fail-open)


def test_cost_guard_caps():
    guard = sh.CostGuard(cap_usd=0.01)
    cost = guard.add_usage({"input_tokens": 2000, "output_tokens": 500,
                            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
    assert cost == pytest.approx(2000 * 2.0 / 1e6 + 500 * 10.0 / 1e6)
    assert not guard.exceeded
    guard.add_usage({"input_tokens": 1_000_000, "output_tokens": 0})
    assert guard.exceeded


def test_distill_preserves_handles_even_when_llm_dead(monkeypatch):
    # 대장 #20 계약: LLM이 죽어도(빈 응답) 핸들은 결정론으로 산다.
    turns = [{"role": "assistant", "content":
              "커밋 4ba6a6f로 배선. 검증은 http://localhost:8000/v1/memories/search/ "
              "에서 2026-08-25에 수행. 파일 forget/store.py 수정."}]
    out = sh.distill_turns(turns, llm=lambda p: "")
    kinds = {h["kind"] for h in out["handles"]}
    values = " ".join(h["value"] for h in out["handles"])
    assert {"url", "commit", "date", "path"} <= kinds
    assert "4ba6a6f" in values and "/v1/memories/search/" in values
    assert out["facts"] == [] and out["distilled_by"] == "none"


def test_distill_parses_llm_json_and_caps(monkeypatch):
    fake = lambda p: 'noise {"facts": ["A했다 — 영수증 x"], "lessons": ["규칙 L"],' \
                     ' "intents": ["다음 기상은 Y"]} tail'
    out = sh.distill_turns([{"role": "user", "content": "작업"}], llm=fake)
    assert out["facts"] == ["A했다 — 영수증 x"]
    assert out["intents"] == ["다음 기상은 Y"]
    assert out["distilled_by"] == "llm"


def test_finish_run_records_reason(tmp_path):
    run = sh.wake("한 건")
    sh.finish_run(run["run_id"], "done", 0.1234)
    conn = sqlite3.connect(sh.HARNESS_DB)
    reason, cost = conn.execute(
        "SELECT end_reason, cost_usd FROM runs WHERE id=?", (run["run_id"],)).fetchone()
    conn.close()
    assert reason == "done" and cost == pytest.approx(0.1234)
    assert sh.last_unfinished_run() is None
