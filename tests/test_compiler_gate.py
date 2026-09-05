"""P-C-1b(①) 게이트 재설계 계약 (memory-intelligence-design.md §4.6).

계약: ①stale-state 응답 변주(stale-state/stale_state/stale)가 한 형태로
정규화 ②stale-state는 compilable + 강등 대상 = 군집−1 ③대표 표본이 군집
중심성 순으로 게이트에 전달(변두리 표본이 아니라) ④게이트 불가 시 other 보수.
"""
from __future__ import annotations

import io
import json

import numpy as np
import pytest

from forget import compiler


def _fake_urlopen(reply_text):
    def fake(req, timeout=None):
        body = {"choices": [{"message": {"content": reply_text}}]}
        return io.BytesIO(json.dumps(body).encode())
    return fake


@pytest.mark.parametrize("reply,expected", [
    ("stale-state", "stale-state"),
    ("Stale_State", "stale-state"),
    ("stale", "stale-state"),          # ① 변주 정규화
    ("rule", "rule"),
    ("완전히 딴소리", "other"),          # ④ 보수 폴백
])
def test_gate_reply_normalization(monkeypatch, reply, expected):
    monkeypatch.setattr(compiler.urllib.request, "urlopen", _fake_urlopen(reply))
    assert compiler._llm_gate(["표본"], 5, 4) == expected


def test_stale_state_is_compilable_with_full_demote(monkeypatch):
    monkeypatch.setattr(compiler, "_llm_gate", lambda *a, **k: "stale-state")
    items = [{"text": f"현재 큐 잔고 {n}건", "day": f"2026-08-2{n}", "id": f"m{n}",
              "app_id": None, "agent_id": None} for n in range(5)]
    out = compiler.classify_cluster(items, [0, 1, 2, 3, 4])
    assert out["form"] == "stale-state"
    assert out["compilable"] is True                    # ②
    assert out["demote_count"] == 4                     # 정본 1행 제외 전부
    assert out["canonical"] == 4                        # 최신 정본


def test_representatives_ordered_by_centrality(monkeypatch):
    captured = {}

    def spy(samples, n, days):
        captured["samples"] = samples
        return "other"

    monkeypatch.setattr(compiler, "_llm_gate", spy)
    # 0·1·2는 서로 같고(중심), 3은 변두리 — 배열 순서상으론 3이 head가 아님을 강제
    center = np.array([1.0, 0.0, 0.0])
    edge = np.array([0.8, 0.6, 0.0])
    X = np.stack([edge, center, center, center]).astype(np.float32)
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    items = [{"text": t, "day": f"2026-08-2{i}", "id": f"m{i}",
              "app_id": None, "agent_id": None}
             for i, t in enumerate(["변두리 표본", "중심 표본 A", "중심 표본 B", "중심 표본 C"])]
    compiler.classify_cluster(items, [0, 1, 2, 3], X)
    assert captured["samples"][0].startswith("중심 표본")   # ③ 중심이 첫 표본
    assert captured["samples"][-1] == "변두리 표본"


def test_track_routing_bypasses_llm(monkeypatch):
    # P-C-1c: 과반이 app_id 보유(타 트랙) → 게이트 호출 없이 journal 불가침
    called = {"n": 0}
    monkeypatch.setattr(compiler, "_llm_gate",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "rule")
    items = [{"text": f"사이클 산문 {n}", "day": f"2026-08-2{n}", "id": f"m{n}",
              "app_id": "forget" if n < 4 else None, "agent_id": None}
             for n in range(5)]
    out = compiler.classify_cluster(items, [0, 1, 2, 3, 4])
    assert out["form"] == "journal" and out["via"] == "deterministic-track"
    assert out["demote_count"] == 0 and called["n"] == 0


def test_personal_majority_still_gated(monkeypatch):
    monkeypatch.setattr(compiler, "_llm_gate", lambda *a, **k: "fact")
    items = [{"text": f"개인 사실 {n}", "day": f"2026-08-2{n}", "id": f"m{n}",
              "app_id": None, "agent_id": None} for n in range(5)]
    out = compiler.classify_cluster(items, [0, 1, 2, 3, 4])
    assert out["form"] == "fact" and out["via"] == "llm-gate"


def test_correction_clusters_use_low_threshold():
    """P-C-3: 교정-마커 과반 군집은 2회·2일로도 성립, 일반 군집은 4회 유지."""
    import numpy as np
    v = np.eye(4, dtype=np.float32)
    v[1] = v[0]; v[3] = v[2]          # (0,1) 쌍·(2,3) 쌍이 각각 동일 벡터
    items = [
        {"text": "정정: 낡은 수치를 인용한 사고", "day": "2026-08-29", "id": "c1", "app_id": None, "agent_id": None},
        {"text": "자기 교정: 같은 사고의 재기록", "day": "2026-08-30", "id": "c2", "app_id": None, "agent_id": None},
        {"text": "평범한 반복 진술", "day": "2026-08-29", "id": "p1", "app_id": None, "agent_id": None},
        {"text": "평범한 반복 진술 둘", "day": "2026-08-30", "id": "p2", "app_id": None, "agent_id": None},
    ]
    out = compiler.detect_clusters(items, v)
    flat = [set(c) for c in out]
    assert {0, 1} in flat              # 교정 쌍 — 저문턱 성립
    assert {2, 3} not in flat          # 일반 쌍 — 4회 미달로 미성립
