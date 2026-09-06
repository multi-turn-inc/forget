"""activation — 존재 빈도가 아니라 사용 빈도가 순위를 정한다 (2026-09-07)."""
from __future__ import annotations

import math

from forget import activation as A


def test_machine_record_detection():
    assert A.is_machine_record("[devloop] 사이클 37 결정+발견 (2026-08-03)")
    assert A.is_machine_record("loop(cycle 292): 일반 — ㉼ 291/291 일치")
    assert not A.is_machine_record("효돌·케어콜과 경쟁하지 않는다, 시장이 작고 글로벌이 안 된다.")


def test_base_activation_prefers_recent_use():
    recent = A.base_activation({"used_days": [1.0, 3.0]})
    old = A.base_activation({"used_days": [60.0, 90.0]})
    none = A.base_activation(None)
    assert recent > old > none


def test_hub_penalty_hits_shown_but_unused():
    hub = A.hub_penalty({"shown": 1000, "used": 0})
    useful = A.hub_penalty({"shown": 1000, "used": 400})
    rare = A.hub_penalty({"shown": 20, "used": 0})
    assert hub > 0.5 and useful < 0.05 and rare == 0.0


def test_rerank_demotes_hub_and_machine_without_touching_search_score():
    stats = {"computed_at": 0, "stats": {"hub": {"shown": 900, "used": 0, "noise": 0, "used_days": []},
                                          "good": {"shown": 20, "used": 12, "noise": 0, "used_days": [2.0, 5.0]}}, "co": {}}
    res = [{"id": "hub", "score": 0.80, "memory": "[devloop] 사이클 37 결정", "created_at": "2026-08-02T00:00:00Z"},
           {"id": "good", "score": 0.62, "memory": "정훈 결정: 경계 코드는 오픈소스", "created_at": "2026-08-27T00:00:00Z"}]
    out = A.rerank(res, stats)
    assert [x["id"] for x in out] == ["good", "hub"]
    assert out[1]["score"] == 0.80  # 검색 점수는 그대로 남긴다
    assert math.isclose(out[0]["activation_breakdown"]["search"], 0.62)


def test_spread_lifts_co_selected_neighbor():
    stats = {"computed_at": 0, "stats": {}, "co": {"a": {"b": 3}}}
    res = [{"id": "a", "score": 0.9, "memory": "x"}, {"id": "b", "score": 0.1, "memory": "y"}, {"id": "c", "score": 0.1, "memory": "z"}]
    out = A.rerank(res, stats)
    ranks = {x["id"]: i for i, x in enumerate(out)}
    assert ranks["b"] < ranks["c"]
