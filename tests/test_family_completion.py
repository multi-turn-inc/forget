"""P-R-5 추이 승계 계약 (recallbench 사이클 5) — 억제 간선의 상속을 사슬 머리까지.

계약: ①top-k에 같은 사슬 구본 ≥2 → 사슬 머리가 합류(최고 구본 바로 위)
②구본 1개뿐이면 무동작 ③as_of 질의엔 무동작 ④검색당 1석·계기 기록.
"""
from __future__ import annotations

import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-fam.sqlite3")

import pytest  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.store import add_memories, search_memories  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    monkeypatch.setenv("FORGET_LEARNED_RANKER", str(tmp_path / "absent.json"))
    init_db()


def _add(text, series=None):
    meta = {"series": series} if series else {}
    out = add_memories({"messages": [{"role": "user", "content": text}],
                        "user_id": "owner-a", "infer": False, "hebbian": False,
                        "metadata": meta})
    from forget.store import get_event
    return get_event(out["event_id"])["results"][0]["id"]


def test_transitive_inheritance_reaches_chain_head(monkeypatch):
    a = _add("리더보드 벤치마크 점수 패키지 확정 버전 다섯", series="s.lafs")
    b = _add("리더보드 벤치마크 점수 패키지 확정 버전 여섯", series="s.lafs")
    head = _add("행정 문면 재제출 완료 접수", series="s.lafs")   # 어휘 빈곤 정본
    # temporal_rerank(형제 승격) 끔 — 이 계약은 그래프-링크 기관 단독을 잰다
    out = search_memories({"query": "리더보드 벤치마크 점수 패키지",
                           "filters": {"user_id": "owner-a"}, "top_k": 5,
                           "temporal_rerank": False, "score_breakdown": True})
    rows = out["results"]
    ids = [r["id"] for r in rows]
    assert head in ids                                            # ① 머리 도달 (1홉이면 중간본)
    hrow = next(r for r in rows if r["id"] == head)
    # ④ 계기 기록 — 도달 경로 둘 다 정당 (P-R-6 앵커 유산 이후 머리가 자력
    # 도달 가능해짐): 간선 소환이면 머리에 inherited_from, 함께-인출이면
    # 구본에 inhibited_by(머리 지목). 어느 쪽이든 판정 근거가 원장에 남는다.
    if not hrow["score_breakdown"].get("inherited_from"):
        stale_rows = [r for r in rows if r["id"] in (a, b)]
        assert all(r["score_breakdown"].get("inhibited_by") == head for r in stale_rows)
    stale_ranks = [ids.index(x) for x in (a, b) if x in ids]
    if stale_ranks:
        assert ids.index(head) < min(stale_ranks)                 # 구본 위


def test_single_stale_member_no_completion():
    _add("옛 진술 하나", series="s.x")
    _add("새 진술 정본입니다 완전히 다른 어휘", series="s.x")
    out = search_memories({"query": "옛 진술 하나", "filters": {"user_id": "owner-a"},
                           "top_k": 3, "score_breakdown": True})
    ids = [r["id"] for r in out["results"]]
    assert len(ids) == len(set(ids))                              # ② 중복 좌석 없음


def test_as_of_before_supersede_keeps_old_current():
    # 행들은 2020년에 생성, 승계는 «지금»(2026) 발생 — 2020년 중반 시점 질의에선
    # 구본이 그때의 현행이므로 상속 좌석이 서면 안 된다. (2099 같은 미래 시점엔
    # 승계가 이미 유효하니 발동이 정답 — 첫 판의 전제 오류를 정정한 테스트.)
    def _old(text, series):
        out = add_memories({"messages": [{"role": "user", "content": text}],
                            "user_id": "owner-a", "infer": False, "hebbian": False,
                            "created_at": "2020-01-01T00:00:00Z",
                            "metadata": {"series": series}})
        from forget.store import get_event
        return get_event(out["event_id"])["results"][0]["id"]
    _old("리더보드 점수 하나", "s.y")
    _old("리더보드 점수 둘", "s.y")
    _old("행정 정본", "s.y")
    # 시리즈 승계는 superseded_at을 행 시각(2020 오버라이드)으로 찍는다 — 가드를
    # 겨누려면 승계 시각만 2026으로 올린다 (supersede가 as_of 이후인 세계).
    import json as _json
    from forget.db import get_db
    with get_db() as conn:
        for row in conn.execute("SELECT id, metadata FROM memories").fetchall():
            meta = _json.loads(row["metadata"] or "{}")
            if meta.get("superseded_at"):
                meta["superseded_at"] = "2026-01-01T00:00:00Z"
                conn.execute("UPDATE memories SET metadata = ? WHERE id = ?",
                             (_json.dumps(meta, ensure_ascii=False), row["id"]))
    out = search_memories({"query": "리더보드 점수", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "memory_as_of": "2020-06-01T00:00:00Z",
                           "score_breakdown": True})
    assert out["results"], "2020 시점에 행들이 보여야 함"
    assert all((r.get("score_breakdown") or {}).get("inherited_from") is None
               for r in out["results"])
