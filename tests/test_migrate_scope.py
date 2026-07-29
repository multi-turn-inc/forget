"""Scope migration: legacy alias merge with provenance and receipts (#22)."""

import json
import sqlite3

import pytest

from forget.migrate import migrate_scope


@pytest.fixture()
def legacy_db(tmp_path):
    path = tmp_path / "m.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE memories (
            id TEXT PRIMARY KEY, project_id TEXT DEFAULT 'proj_local',
            memory TEXT NOT NULL, user_id TEXT, agent_id TEXT, app_id TEXT,
            run_id TEXT, metadata TEXT DEFAULT '{}'
        );
        CREATE TABLE claims (
            id TEXT PRIMARY KEY, claim_text TEXT NOT NULL, scope TEXT DEFAULT '{}'
        );
        CREATE TABLE gate_log (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL DEFAULT 'proj_local',
            user_id TEXT, agent_id TEXT, app_id TEXT, run_id TEXT,
            dropped_text TEXT NOT NULL DEFAULT '', role TEXT,
            reason TEXT NOT NULL DEFAULT 'x', source_event_id TEXT,
            created_at TEXT NOT NULL DEFAULT '2026-01-01'
        );
        """
    )
    conn.executemany(
        "INSERT INTO memories (id, memory, user_id, app_id) VALUES (?, ?, ?, ?)",
        [
            ("m1", "legacy fact", "junghunkim", "Mem1"),
            ("m2", "legacy fact 2", "junghunkim", "Mem1"),
            ("m3", "other user, same legacy app", "someone", "Mem1"),
            ("m4", "already canonical", "junghunkim", "forget"),
            ("m5", "ownerless orphan", None, "Mem1"),
        ],
    )
    conn.executemany(
        "INSERT INTO claims (id, claim_text, scope) VALUES (?, ?, ?)",
        [
            ("c1", "task state", json.dumps({"user_id": "junghunkim", "app_id": "Mem1"})),
            ("c2", "other-user task", json.dumps({"user_id": "someone", "app_id": "Mem1"})),
            ("c3", "ownerless claim", json.dumps({"user_id": None, "app_id": "Mem1"})),
        ],
    )
    conn.execute(
        "INSERT INTO gate_log (id, user_id, app_id) VALUES ('g1', 'junghunkim', 'Mem1')"
    )
    conn.commit()
    conn.close()
    return path


def _rows(path, sql):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def test_dry_run_counts_without_writing(legacy_db):
    receipt = migrate_scope(from_app="Mem1", to_app="forget", user="junghunkim", db_path=str(legacy_db))
    assert receipt["applied"] is False
    assert receipt["counts"] == {
        "memories": 2, "claims": 1, "gate_log": 1,
        "null_user_claimed": 0, "null_user_claims_claimed": 0,
    }
    assert {r["app_id"] for r in _rows(legacy_db, "SELECT app_id FROM memories")} == {"Mem1", "forget"}


def test_apply_migrates_with_provenance_and_receipt(legacy_db):
    receipt = migrate_scope(
        from_app="Mem1", to_app="forget", user="junghunkim", db_path=str(legacy_db), apply=True
    )
    assert receipt["applied"] is True
    rows = {r["id"]: r for r in _rows(legacy_db, "SELECT id, user_id, app_id, metadata FROM memories")}
    assert rows["m1"]["app_id"] == "forget"
    prov = json.loads(rows["m1"]["metadata"])["scope_migration"]
    assert prov["original_app_id"] == "Mem1"
    assert prov["reason"] == "verified_legacy_alias"
    # scoping respected: other user and ownerless rows untouched
    assert rows["m3"]["app_id"] == "Mem1"
    assert rows["m5"]["app_id"] == "Mem1" and rows["m5"]["user_id"] is None
    claims = {r["id"]: json.loads(r["scope"]) for r in _rows(legacy_db, "SELECT id, scope FROM claims")}
    assert claims["c1"]["app_id"] == "forget"
    assert claims["c2"]["app_id"] == "Mem1"
    assert _rows(legacy_db, "SELECT app_id FROM gate_log")[0]["app_id"] == "forget"
    # receipt persisted next to the db
    receipt_path = receipt["receipt_path"]
    saved = json.loads(open(receipt_path).read())
    assert saved["ids"]["memories"] == ["m1", "m2"]


def test_null_user_claim_requires_explicit_flag(legacy_db):
    migrate_scope(from_app="Mem1", to_app="forget", db_path=str(legacy_db), apply=True)
    ownerless = _rows(legacy_db, "SELECT user_id, app_id FROM memories WHERE id='m5'")[0]
    assert ownerless["user_id"] is None, "no implicit ownership claim"
    assert ownerless["app_id"] == "forget", "app migrates even for ownerless rows when user filter absent"

    receipt = migrate_scope(
        from_app="Mem1", to_app="forget", claim_null_user="junghunkim",
        db_path=str(legacy_db), apply=True,
    )
    claimed = _rows(legacy_db, "SELECT user_id, metadata FROM memories WHERE id='m5'")[0]
    assert claimed["user_id"] == "junghunkim"
    assert json.loads(claimed["metadata"])["owner_claim"]["reason"] == "explicit_null_user_claim"
    assert receipt["counts"]["null_user_claims_claimed"] == 1
    c3 = _rows(legacy_db, "SELECT scope FROM claims WHERE id='c3'")[0]
    assert json.loads(c3["scope"])["user_id"] == "junghunkim", "ownerless claims are claimed too"


def test_same_app_rejected(legacy_db):
    with pytest.raises(ValueError):
        migrate_scope(from_app="forget", to_app="forget", db_path=str(legacy_db))
