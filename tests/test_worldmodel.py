"""텍스트 세계모델 v0 — 상태 코어 계약 테스트.

핵심 계약: 분리 원칙 A(관측 ↔ 상태) — tick()은 관측 없이 시간만으로 전이하고,
문턱은 반열림이 아니라 '이상(≥)' — 정확히 STALE_AFTER_S 초에 낡음이 된다
(시각 경계 규율: 경계 포함 여부를 테스트가 문서화한다).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from forget.worldmodel import STALE_AFTER_S, expectations, rebuild, tick

NOW = datetime(2026, 8, 24, 12, 0, 0, tzinfo=timezone.utc)


def _ledger(tmp_path, rows):
    path = str(tmp_path / "ledger.sqlite3")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE memories (id TEXT, memory TEXT, metadata TEXT,"
        " created_at TEXT, updated_at TEXT, deleted INTEGER DEFAULT 0)"
    )
    for r in rows:
        conn.execute("INSERT INTO memories VALUES (?,?,?,?,?,?)", r)
    conn.commit()
    conn.close()
    return path


def _mem(mid, text, light, created, superseded=False, kind="action_report", deleted=0):
    meta = {"trust": {"kind": kind, "light": light}}
    if superseded:
        meta["superseded_by"] = "x"
    return (mid, text, json.dumps(meta), created, created, deleted)


def test_rebuild_opens_yellow_and_closes_green_red(tmp_path):
    ledger = _ledger(tmp_path, [
        _mem("m1", "배포했다고 보고", "yellow", "2026-08-20T00:00:00Z"),
        _mem("m2", "확정된 완료", "green", "2026-08-20T00:00:00Z"),
        _mem("m3", "철회된 주장", "yellow", "2026-08-20T00:00:00Z", superseded=True),
        _mem("m4", "지워진 행", "yellow", "2026-08-20T00:00:00Z", deleted=1),
        _mem("m5", "고리 아님(fact)", "yellow", "2026-08-20T00:00:00Z", kind="fact"),
    ])
    world = str(tmp_path / "world.sqlite3")
    stats = rebuild(world, ledger, now=NOW)
    assert stats["seen"] == 3  # m4 deleted, m5 kind 불일치 제외
    conn = sqlite3.connect(world)
    status = dict(conn.execute("SELECT id, status FROM loops"))
    assert status == {"loop-m1": "open", "loop-m2": "closed_confirmed",
                      "loop-m3": "closed_retracted"}


def test_tick_time_transition_boundary_is_inclusive(tmp_path):
    just_stale = NOW - timedelta(seconds=STALE_AFTER_S)          # 정확히 문턱
    not_yet = NOW - timedelta(seconds=STALE_AFTER_S - 1)          # 1초 모자람
    ledger = _ledger(tmp_path, [
        _mem("old", "14일 된 주장", "yellow", just_stale.strftime("%Y-%m-%dT%H:%M:%SZ")),
        _mem("new", "13일23시간 주장", "yellow", not_yet.strftime("%Y-%m-%dT%H:%M:%SZ")),
    ])
    world = str(tmp_path / "world.sqlite3")
    # 재구축 시점을 과거로 두어 둘 다 open으로 태어나게 한다
    rebuild(world, ledger, now=not_yet + timedelta(seconds=1))
    moved = tick(world, now=NOW)
    assert moved == 1
    conn = sqlite3.connect(world)
    status = dict(conn.execute("SELECT id, status FROM loops"))
    assert status["loop-old"] == "stale"
    assert status["loop-new"] == "open"
    causes = list(conn.execute(
        "SELECT cause FROM transitions WHERE loop_id='loop-old' AND to_status='stale'"))
    assert causes == [("time",)]  # 관측 없는 전이 — 원인이 명시 기록된다


def test_rebuild_is_idempotent_and_preserves_opened_at(tmp_path):
    ledger = _ledger(tmp_path, [_mem("m1", "주장", "yellow", "2026-08-01T00:00:00Z")])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)
    rebuild(world, ledger, now=NOW + timedelta(hours=1))
    conn = sqlite3.connect(world)
    rows = list(conn.execute("SELECT opened_at FROM loops"))
    assert rows == [("2026-08-01T00:00:00Z",)]
    # 상태 불변 재구축은 전이를 다시 쌓지 않는다 (최초 rebuild 1건뿐)
    n_tr = conn.execute("SELECT count(*) FROM transitions").fetchone()[0]
    assert n_tr == 1


def test_observation_closes_after_time_staled(tmp_path):
    """시간으로 낡은 고리가 관측(green 확정)으로 종결되는 전체 생애주기."""
    ledger = _ledger(tmp_path, [_mem("m1", "주장", "yellow", "2026-07-01T00:00:00Z")])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)  # 54일 경과 → 곧바로 stale로 태어남
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT status FROM loops").fetchone()[0] == "stale"
    conn.close()
    ledger2 = _ledger(tmp_path.joinpath("2").mkdir() or tmp_path / "2",
                      [_mem("m1", "주장", "green", "2026-07-01T00:00:00Z")])
    rebuild(world, ledger2, now=NOW + timedelta(hours=1))
    conn = sqlite3.connect(world)
    assert conn.execute("SELECT status FROM loops").fetchone()[0] == "closed_confirmed"
    tr = list(conn.execute("SELECT from_status, to_status, cause FROM transitions ORDER BY at"))
    assert tr[-1] == ("stale", "closed_confirmed", "observation")


def test_expectations_rank_oldest_first_and_skip_closed(tmp_path):
    ledger = _ledger(tmp_path, [
        _mem("a", "오래된 주장", "yellow", "2026-07-01T00:00:00Z"),
        _mem("b", "새 주장", "yellow", "2026-08-23T00:00:00Z"),
        _mem("c", "끝난 주장", "green", "2026-07-01T00:00:00Z"),
    ])
    world = str(tmp_path / "world.sqlite3")
    rebuild(world, ledger, now=NOW)
    exps = expectations(world, now=NOW)
    assert [e["loop_id"] for e in exps] == ["loop-a", "loop-b"]
    assert exps[0]["days_open"] == 54
    assert "증거 확인 또는 정정" in exps[0]["expectation"]
