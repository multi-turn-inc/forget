"""P-M-4 증류 결합기 계약 테스트 (neural-memory-gate-study.md §13~14).

계약: ①가중치 파일이 있으면 관성 집합 내 서열을 학습 결합기가 정하고
breakdown에 actr_learned 표시 ②없으면 종전 손-공식(0.12*actr) 그대로 —
키·캡 불변 ③피처 배선이 훈련 정의와 일치(in_current 피처가 실제로
직전 트레이스 멤버십을 읽는다) ④깨진 가중치 파일은 조용히 폴백.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-lr.sqlite3")

import pytest  # noqa: E402

from forget.db import get_db, init_db  # noqa: E402
from forget.store import (  # noqa: E402
    _actr_replay,
    _learned_inertia_boosts,
    add_memories,
    current_project_id,
    search_memories,
)
from forget.utils import new_id, utc_now  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    # 도그푸드 머신엔 실가중치(~/.forget/learned_ranker_v1.json)가 있다 —
    # 기본은 부재 경로로 격리하고, 필요한 테스트만 명시 주입한다.
    monkeypatch.setenv("FORGET_LEARNED_RANKER", str(tmp_path / "absent.json"))
    init_db()


def _weights(tmp_path, w1, b1, w2, b2, mask=(1, 1, 1, 0, 0, 1)):
    path = tmp_path / "ranker.json"
    path.write_text(json.dumps({
        "w1": w1, "b1": b1, "w2": w2, "b2": b2, "feature_mask": list(mask),
    }))
    return str(path)


def _identity_on(feature_idx):
    """은닉 1유닛이 피처 하나만 통과시키는 최소 가중치."""
    w1 = [[1.0 if i == feature_idx else 0.0 for i in range(6)]]
    return w1, [0.0], [[1.0]], [0.0]


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


def test_fallback_without_weights_keeps_hand_formula():
    target = _mem("배포 반사 문서")
    for _ in range(6):
        _trace([target])
    out = search_memories({"query": "무관한 질의", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "score_breakdown": True})
    row = next(r for r in out["results"] if r["id"] == target)
    bd = row["score_breakdown"]
    assert bd["actr_boost"] == pytest.approx(0.12, abs=1e-3)  # actr 정규 1.0
    assert "actr_learned" not in bd                            # ② 폴백엔 표시 없음


def test_learned_reorders_by_in_current_feature(tmp_path, monkeypatch):
    # 은닉 유닛이 in_current(f5)만 통과 → 직전 트레이스 멤버가 1.0, 나머지 0.0
    old = _mem("옛 관성 기억")
    now = _mem("직전 트레이스 기억")
    for _ in range(8):
        _trace([old])          # old가 actr 최고
    _trace([now])              # 마지막 트레이스는 now만
    w1, b1, w2, b2 = _identity_on(5)
    monkeypatch.setenv("FORGET_LEARNED_RANKER", _weights(tmp_path, w1, b1, w2, b2))
    state = _actr_replay(current_project_id())
    boosts = _learned_inertia_boosts(state)
    assert boosts[now] == pytest.approx(1.0)   # ③ 피처 배선 실증
    assert boosts[old] == pytest.approx(0.0)   # actr 최고여도 서열은 학습기가
    out = search_memories({"query": "무관한 질의", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "score_breakdown": True})
    by_id = {r["id"]: r["score_breakdown"] for r in out["results"]}
    assert by_id[now].get("actr_learned") is True              # ① 표시
    assert by_id[now]["actr_boost"] == pytest.approx(0.12, abs=1e-3)
    # old는 부스트 0.0 → 무관 질의에선 전역 문턱 아래로 가라앉는 게 정상
    # (학습 서열이 실제로 랭킹을 갈랐다는 증거). 있으면 부스트 0이어야 한다.
    if old in by_id:
        assert by_id[old]["actr_boost"] == pytest.approx(0.0, abs=1e-3)


def test_broken_weights_fall_back(tmp_path, monkeypatch):
    target = _mem("아무 기억")
    for _ in range(6):
        _trace([target])
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    monkeypatch.setenv("FORGET_LEARNED_RANKER", str(bad))
    out = search_memories({"query": "무관", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "score_breakdown": True})
    row = next(r for r in out["results"] if r["id"] == target)
    assert "actr_learned" not in row["score_breakdown"]        # ④ 조용한 폴백
    assert row["score_breakdown"]["actr_boost"] > 0


def test_decay_bank_closed_form_matches_recurrence(tmp_path, monkeypatch):
    """감쇠 은행 골든: 닫힌꼴 Σ a1^p·a2^q가 재귀(×0.9+1 / ×0.97)와 일치."""
    from forget.store import _decay_bank_boosts
    # 이력: 선택(0)·부재(1)·선택(2)·부재(3) → 재귀 s = ((1)·0.97·0.9+1)·0.97
    s_rec = ((1.0 * 0.97) * 0.9 + 1.0) * 0.97
    state = {"scores": {"m1": s_rec, "m2": 1.0}, "events": {"m1": [0, 2], "m2": [3]},
             "co": {}, "current": {"m2"}, "steps": 4, "last_used": {"m1": 2, "m2": 3}}
    weights = {"version": "pm6-decay-bank-v2", "a1": [0.9], "a2": [0.97],
               "hist_window": 20, "w1": [[1.0, 0.0, 0.0]], "b1": [0.0],
               "w2": [[1.0]], "b2": [0.0]}
    out = _decay_bank_boosts(weights, state)
    # raw(m1) = s_rec/ch_max, raw(m2) = 1.0/ch_max → min-max 후 m2=1, m1=0
    # (m2가 정규화 분모 최대: 1.0 < s_rec → m1이 최대) — 수치로 직접 검증:
    assert s_rec > 1.0
    assert out["m1"] == pytest.approx(1.0)     # 은행 상태 최대 → 1
    assert out["m2"] == pytest.approx(0.0)


def test_decay_bank_via_search_and_rollback_ladder(tmp_path, monkeypatch):
    import shutil
    target = _mem("감쇠 은행 라이브 대상")
    for _ in range(6):
        _trace([target])
    bank = tmp_path / "v2.json"
    shutil.copy("/tmp/pm6_bank_weights.json", bank) if __import__("os").path.exists(
        "/tmp/pm6_bank_weights.json") else bank.write_text(json.dumps({
            "version": "pm6-decay-bank-v2", "a1": [0.9], "a2": [0.97],
            "hist_window": 20, "w1": [[1.0, 0.0, 0.0]], "b1": [0.0],
            "w2": [[1.0]], "b2": [0.0]}))
    monkeypatch.setenv("FORGET_LEARNED_RANKER", str(bank))
    out = search_memories({"query": "무관 질의", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "score_breakdown": True})
    row = next(r for r in out["results"] if r["id"] == target)
    assert row["score_breakdown"].get("actr_learned") is True
    # 롤백: 파일 제거 → 손-공식 (마커 없음)
    bank.unlink()
    out = search_memories({"query": "무관 질의", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "score_breakdown": True})
    row = next(r for r in out["results"] if r["id"] == target)
    assert "actr_learned" not in row["score_breakdown"]
    assert row["score_breakdown"]["actr_boost"] > 0
