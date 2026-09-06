"""Retention — records must not outweigh memories (2026-09-07).

Measured on the dogfood DB: memories 48MB vs context_traces 717MB + SEARCH event results 361MB, no policy.
Contracts:
  ① new traces are compact by default (heavy keys dropped, capsule kept); FORGET_TRACE_VERBOSE=1 restores full payload
  ② SEARCH events store id/score/160 chars, not full memory bodies
  ③ retention.run() is a dry-run unless apply=True, never touches memories, keeps labeled traces for labeled_days
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-retention.sqlite3")


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "r.sqlite3"))
    monkeypatch.delenv("FORGET_TRACE_VERBOSE", raising=False)
    from forget import db
    db.init_db() if hasattr(db, "init_db") else None
    yield


def _ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _insert_trace(conn, trace_id: str, created_at: str, heavy: bool = True):
    payload = {"schema_version": "v1", "trace_id": trace_id, "trace_query": "q", "context_capsule": {"x": 1},
               "context_capsule_text": "capsule"}
    if heavy:
        payload.update({"materialization": {"big": "m" * 20000}, "candidate_snapshots": [{"id": f"m{i}", "memory": "x" * 500} for i in range(20)],
                        "debug": {"d": "z" * 5000}, "use_now": {"u": "y" * 5000}})
    conn.execute(
        "INSERT INTO context_traces (trace_id, project_id, task_id, task_phase, policy_version, query, filters, candidate_ids, "
        "selected_ids, rejected_ids, scores, roles, decision_reasons, token_cost, payload, created_at) "
        "VALUES (?, 'proj_local', '', '', 'v', 'q', '{}', '[]', '[]', '[]', '{}', '{}', '{}', 0, ?, ?)",
        (trace_id, json.dumps(payload), created_at),
    )


def test_compact_trace_payload_keeps_capsule_drops_heavy():
    from forget.retention import compact_trace_payload, TRACE_HEAVY_KEYS
    p = {"schema_version": "v1", "trace_id": "t", "context_capsule": {"a": 1}, "context_capsule_text": "c",
         "materialization": {"x": "m" * 1000}, "debug": {"d": 1}, "candidate_snapshots": [{"id": "m1"}, {"id": "m2"}]}
    c = compact_trace_payload(p)
    assert c["context_capsule"] == {"a": 1} and c["context_capsule_text"] == "c"
    assert all(k not in c for k in TRACE_HEAVY_KEYS)
    assert c["candidate_ids"] == ["m1", "m2"] and "materialization" in c["dropped_keys"]
    assert len(json.dumps(c)) < len(json.dumps(p)) / 5


def test_compact_search_results_id_score_only():
    from forget.retention import compact_search_results
    r = compact_search_results([{"id": "a", "score": 0.9, "memory": "x" * 1000, "metadata": {"k": 1}}], text_chars=160)
    assert r == [{"id": "a", "score": 0.9, "memory": "x" * 160}]
    assert compact_search_results("garbage") == []


def test_run_is_dry_by_default_and_respects_age_and_labels():
    from forget.db import get_db
    from forget import retention
    with get_db() as conn:
        _insert_trace(conn, "old", _ago(30))
        _insert_trace(conn, "new", _ago(2))
        _insert_trace(conn, "old-labeled", _ago(30))
        conn.execute(
            "INSERT INTO context_outcomes (outcome_id, project_id, trace_id, created_at) VALUES ('o1', 'proj_local', 'old-labeled', ?)",
            (_ago(30),),
        )
        conn.execute(
            "INSERT INTO events (id, project_id, event_type, status, payload, metadata, results, created_at, updated_at) "
            "VALUES ('e-old', 'proj_local', 'SEARCH', 'SUCCEEDED', '{}', '{}', ?, ?, ?)",
            (json.dumps([{"id": "m1", "score": 0.5, "memory": "y" * 3000, "metadata": {}}]), _ago(30), _ago(30)),
        )
        conn.commit()
    dry = retention.run(older_than_days=14, labeled_days=90, apply=False)
    assert dry["traces"]["candidates"] == 1 and dry["traces"]["compacted"] == 0
    assert dry["traces"]["skipped_labeled"] == 1
    assert dry["search_events"]["candidates"] == 1 and dry["reclaim_mb_total"] >= 0
    with get_db() as conn:  # dry-run wrote nothing
        assert len(conn.execute("SELECT payload FROM context_traces WHERE trace_id='old'").fetchone()[0]) > 20000
    applied = retention.run(older_than_days=14, labeled_days=90, apply=True)
    assert applied["traces"]["compacted"] == 1 and applied["search_events"]["compacted"] == 1
    with get_db() as conn:
        old = json.loads(conn.execute("SELECT payload FROM context_traces WHERE trace_id='old'").fetchone()[0])
        assert old.get("compacted_at") and "materialization" not in old and old["context_capsule_text"] == "capsule"
        new = json.loads(conn.execute("SELECT payload FROM context_traces WHERE trace_id='new'").fetchone()[0])
        assert "materialization" in new  # too young — untouched
        lab = json.loads(conn.execute("SELECT payload FROM context_traces WHERE trace_id='old-labeled'").fetchone()[0])
        assert "materialization" in lab  # labeled — kept
        res = json.loads(conn.execute("SELECT results FROM events WHERE id='e-old'").fetchone()[0])
        assert res == [{"id": "m1", "score": 0.5}]
    # idempotent
    again = retention.run(older_than_days=14, labeled_days=90, apply=True)
    assert again["traces"]["candidates"] == 0 and again["search_events"]["candidates"] == 0


def test_report_has_growth_and_sizes():
    from forget import retention
    rep = retention.report()
    assert "db_mb" in rep and "growth_7d_mb" in rep and "context_traces" in rep


def test_new_search_events_are_compact_by_default():
    """Contract ②: a real search writes id/score/160-char results, not bodies."""
    from forget import store
    from forget.db import get_db
    store.add_memories({"messages": [{"role": "user", "content": "retention contract memory " + "z" * 800}], "user_id": "u"})
    store.search_memories({"query": "retention contract", "filters": {"user_id": "u"}})
    with get_db() as conn:
        row = conn.execute("SELECT results FROM events WHERE event_type='SEARCH' ORDER BY created_at DESC LIMIT 1").fetchone()
    res = json.loads(row[0])
    assert res and set(res[0].keys()) <= {"id", "score", "memory"} and len(res[0].get("memory", "")) <= 160
