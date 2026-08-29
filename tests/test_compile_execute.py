"""집행 모드 v0 계약 (memory-intelligence-design.md §4.12).

계약: ①컴파일 형태(rule/fact/stale-state)만 집행, 최신 행이 정본
②강등 = metadata.superseded_by→정본 + sank_by=compiler:배치 (삭제·텍스트
변형 없음) ③이미 침강한 행은 건너뜀(멱등 — 재실행 무해) ④revert가 원장
역재생으로 전량 복원, 타 경로가 손댄 행은 불가침 ⑤journal/other 무접촉.
"""
from __future__ import annotations

import json
import sqlite3

from forget.compiler import execute_compile, revert_compile


def _db(tmp_path, rows):
    path = str(tmp_path / "c.sqlite3")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE memories (id TEXT PRIMARY KEY, created_at TEXT,"
                 " metadata TEXT, deleted INTEGER DEFAULT 0)")
    conn.executemany("INSERT INTO memories VALUES (?, ?, ?, 0)", rows)
    conn.commit(); conn.close()
    return path


def _meta(path):
    conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    out = {r["id"]: json.loads(r["metadata"] or "{}")
           for r in conn.execute("SELECT id, metadata FROM memories")}
    conn.close()
    return out


REPORT = [
    {"form": "stale-state", "member_ids": ["a1", "a2", "a3"]},
    {"form": "journal", "member_ids": ["j1", "j2"]},
]


def test_execute_demotes_all_but_latest_and_is_reversible(tmp_path):
    db = _db(tmp_path, [
        ("a1", "2026-08-26T00:00:00Z", "{}"),
        ("a2", "2026-08-27T00:00:00Z", '{"sank_by": "old-path"}'),
        ("a3", "2026-08-28T00:00:00Z", "{}"),
        ("j1", "2026-08-26T00:00:00Z", "{}"),
        ("j2", "2026-08-27T00:00:00Z", "{}"),
    ])
    ledger = str(tmp_path / "ledger.jsonl")
    out = execute_compile(db, REPORT, ledger, "b1")
    assert out["demoted"] == 2                                  # a1, a2
    meta = _meta(db)
    assert meta["a1"]["superseded_by"] == "a3"                  # ① 최신 정본
    assert meta["a1"]["sank_by"] == "compiler:b1"               # ② 귀속
    assert meta["a2"]["superseded_by"] == "a3"
    assert meta["a3"] == {} and meta["j1"] == {}                # ①⑤ 정본·저널 무접촉
    # ③ 멱등
    again = execute_compile(db, REPORT, ledger, "b2")
    assert again["demoted"] == 0 and again["skipped"] == 2
    # ④ 가역
    back = revert_compile(db, ledger, "b1")
    assert back["restored"] == 2
    meta = _meta(db)
    assert "superseded_by" not in meta["a1"] and "compiled_form" not in meta["a1"]
    assert meta["a2"]["sank_by"] == "old-path"                  # 이전 값 복원


def test_revert_leaves_foreign_touches_alone(tmp_path):
    db = _db(tmp_path, [
        ("a1", "2026-08-26T00:00:00Z", "{}"),
        ("a2", "2026-08-27T00:00:00Z", "{}"),
        ("a3", "2026-08-28T00:00:00Z", "{}"),
    ])
    ledger = str(tmp_path / "ledger.jsonl")
    execute_compile(db, REPORT[:1], ledger, "b1")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE memories SET metadata = ? WHERE id = ?",
                 (json.dumps({"sank_by": "someone-else"}), "a1"))
    conn.commit(); conn.close()
    out = revert_compile(db, ledger, "b1")
    assert out["restored"] == 1                                 # a2만 — a1은 불가침
    assert _meta(db)["a1"]["sank_by"] == "someone-else"
