"""Inhibition edges: supersession is retrieval-time competition, not a stored label.

The brain does not delete or tombstone a superseded memory — the replacement
wins *when both are retrieved*, the old one resurfaces when its replacement is
absent (renewal), and time-travel recall restores the old state. Before this
mechanism (measured 2026-08-23 on 18 real supersede pairs): the unconditional
×0.45 demotion sank old rows below the global 0.1 score floor — effectively
deletion — and the supersede-time updated_at bump made as-of queries exclude
them entirely (renewal 0/14).

Contract pinned here, one behavior per test:
  1. successor retrieved too      → successor ranks above the old row
  2. successor missed by the query → the edge fetches it in, above the old row
  3. successor dead               → old row NOT demoted (sole carrier survives)
  4. as_of before the supersede   → old row retrievable at full score
  5. superseded_at without a link → legacy ×0.45 demotion still applies
"""
import json
import os
import uuid

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-inhibition.sqlite3")

from forget import store  # noqa: E402
from forget.db import get_db, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "inh.sqlite3"))
    monkeypatch.setenv("MEM1_RECALL_TEMPORAL", "0")
    init_db()
    yield


def _add(text: str, user: str) -> str:
    result = store.add_memories({"messages": [{"role": "user", "content": text}],
                                 "user_id": user, "infer": False, "hebbian": False})
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM memories WHERE user_id = ? ORDER BY rowid DESC LIMIT 1", (user,)
        ).fetchone()
    assert result["event_id"] and row
    return str(row[0])


def _search(query: str, user: str, **kw):
    return (store.search_memories({"query": query, "filters": {"user_id": user},
                                   "top_k": 20, "score_breakdown": True, **kw})
            .get("results") or [])


def _ranks(results) -> dict:
    return {str(m.get("id")): i for i, m in enumerate(results)}


def test_successor_outranks_old_when_both_retrieved():
    user = f"in-{uuid.uuid4().hex[:8]}"
    old = _add("배포 대상은 스테이징 서버다", user)
    new = _add("배포 대상은 프로덕션 서버다", user)
    store.supersede_memory(old, {"reason": "정정", "superseded_by": new})
    ranks = _ranks(_search("배포 대상 서버", user))
    assert old in ranks and new in ranks
    assert ranks[new] < ranks[old], "대체본이 구본을 이겨야 한다 — 억압은 경쟁이다"


def test_edge_fetches_a_successor_the_query_missed():
    # 구본으로 표현된 질의 — 대체본은 다른 어휘라 검색이 놓친다. 간선이 데려와야 한다.
    user = f"in-{uuid.uuid4().hex[:8]}"
    old = _add("하나의 몸은 Motif 2.6B 로컬 모델이다", user)
    new = _add("현재 대화 모델은 Qwen 27B 쿼트다", user)
    store.supersede_memory(old, {"reason": "몸 교체", "superseded_by": new})
    results = _search("하나의 몸 Motif 로컬", user)
    ranks = _ranks(results)
    assert old in ranks, "구본은 여전히 인출 가능해야 한다"
    assert new in ranks, "간선 승급: 원장이 아는 후계자를 데려와야 한다"
    assert ranks[new] < ranks[old]
    succ = next(m for m in results if str(m.get("id")) == new)
    assert (succ.get("score_breakdown") or {}).get("inherited_from") == old


def test_dead_successor_leaves_the_old_row_undemoted():
    # 주제의 유일한 담지자를 누르면 주제가 통째로 사라진다 (renewal).
    user = f"in-{uuid.uuid4().hex[:8]}"
    old = _add("결제 프로바이더는 Paddle로 확정했다", user)
    new = _add("결제 프로바이더를 Stripe로 바꿨다", user)
    store.supersede_memory(old, {"reason": "번복", "superseded_by": new})
    store.delete_memory(new)
    results = _search("결제 프로바이더 확정", user)
    hit = next((m for m in results if str(m.get("id")) == old), None)
    assert hit is not None, "후계자가 죽었으면 구본이 살아 있어야 한다"
    breakdown = hit.get("score_breakdown") or {}
    assert breakdown.get("renewal") is True
    assert "inhibited_by" not in breakdown


def test_as_of_before_the_supersede_restores_the_old_state():
    # supersede가 updated_at을 올려도 시점 질의는 당시 현행이던 사실을 봐야 한다.
    user = f"in-{uuid.uuid4().hex[:8]}"
    old = _add("YC 지원서는 초안 상태다", user)
    new = _add("YC 지원서 제출이 완료됐다", user)
    store.supersede_memory(old, {"reason": "제출", "superseded_by": new})
    # 생성과 supersede가 같은 초에 일어나므로, 구본을 어제 태어난 것으로 백데이트해
    # "생성 이후·supersede 이전"이라는 실존 가능한 시점을 만든다.
    with get_db() as conn:
        conn.execute("UPDATE memories SET created_at='2026-08-20T00:00:00Z' WHERE id=?", (old,))
        meta = json.loads(conn.execute("SELECT metadata FROM memories WHERE id=?", (old,)).fetchone()[0])
    assert meta.get("superseded_at")
    asof = "2026-08-21T00:00:00Z"     # 생성 후 · supersede 전
    results = _search("YC 지원서 상태", user, memory_as_of=asof)
    hit = next((m for m in results if str(m.get("id")) == old), None)
    assert hit is not None, "재부상: as_of 시점엔 구본이 현행이었다"
    assert "inhibited_by" not in (hit.get("score_breakdown") or {}), "그 시점엔 경쟁이 없었다"


def test_unlinked_supersede_keeps_the_legacy_demotion():
    user = f"in-{uuid.uuid4().hex[:8]}"
    old = _add("점심 회의는 화요일마다 한다", user)
    store.supersede_memory(old, {"reason": "구식 주석"})   # superseded_by 없음
    results = _search("점심 회의 요일", user)
    hit = next((m for m in results if str(m.get("id")) == old), None)
    if hit is not None:      # 강등으로 문턱 아래 침몰도 정당한 결과다
        assert (hit.get("score_breakdown") or {}).get("superseded") is True
        assert "renewal" not in (hit.get("score_breakdown") or {})
