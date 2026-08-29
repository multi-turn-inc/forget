"""시계열 자동 승계 계약 (2026-08-30 구조 수리 — LAFS 낡은 인용 사고).

계약: ①같은 series의 신규 저장이 이전 현행 행을 supersede(링크·sank_by)
②다른 series·무 series 행은 무접촉 ③사슬: 세 번째 저장은 두 번째만 침강
(이미 침강한 행은 재승계 안 함 — 링크 사슬 보존) ④회상에서 구본은 억제
간선 경로로 강등(superseded 표기).
"""
from __future__ import annotations

import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-series.sqlite3")

import pytest  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.store import add_memories, get_memory, search_memories  # noqa: E402


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


def test_series_succession_chain():
    a = _add("LAFS +2.211 v5 패키지", series="lmev2.package")
    b = _add("LAFS +2.577 v6 패키지", series="lmev2.package")
    other = _add("무관 시리즈", series="other.track")
    plain = _add("시리즈 없는 기억")
    c = _add("LAFS +3.732 v6.2 SOTA", series="lmev2.package")
    ma, mb = get_memory(a), get_memory(b)
    assert ma["metadata"]["superseded_by"] == b          # ①③ 사슬 보존: a→b
    assert ma["metadata"]["sank_by"] == "series:lmev2.package"
    assert mb["metadata"]["superseded_by"] == c          # b→c
    assert "superseded_by" not in (get_memory(c)["metadata"] or {})   # 정본
    assert "superseded_by" not in (get_memory(other)["metadata"] or {})  # ②
    assert "superseded_by" not in (get_memory(plain)["metadata"] or {})


def test_recall_marks_stale_snapshots():
    _add("리더보드 점수 +2.577", series="bench.score")
    new = _add("리더보드 점수 +3.732", series="bench.score")
    out = search_memories({"query": "리더보드 점수", "filters": {"user_id": "owner-a"},
                           "top_k": 5, "score_breakdown": True})
    by_id = {r["id"]: r for r in out["results"]}
    assert new in by_id and "superseded" not in by_id[new]["score_breakdown"]
    stale = [r for r in out["results"] if (r.get("score_breakdown") or {}).get("superseded")]
    assert all(r["id"] != new for r in stale)            # ④ 구본만 표기
