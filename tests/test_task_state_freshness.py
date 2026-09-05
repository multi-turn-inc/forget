"""The fast layer has to say how old it is.

LOOP.md's persona model gives task state an hourly TTL and requires a stale
marker once it is exceeded. The rule was written on 2026-07-31; the wiring for
get_task_state was never built. Cycle 93 (observation 49) paid the bill: two
record_task_state calls left no generation behind, and the sessions that
followed were handed a two-cycle-old state as "current" with nothing in the
payload saying so. A write that does not land raises nothing, and a read of an
older generation is byte-shaped like a read of the newest one.

These tests pin the four things the response now says about itself: it is
fresh, it is old, there is nothing there at all, or it is a deliberate replay
and freshness does not apply.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import get_db, init_db
from forget.mcp import call_tool
from forget.server import app
from forget.store import get_task_state, record_task_state, task_state_freshness
from forget.utils import utc_now

_DB_COUNTER = 0
_CTX = {"user_id": "codex", "client_name": "codex"}


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-task-freshness-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def _age_every_generation(hours: float) -> None:
    """Backdate the stored state, reproducing the cycle 93 control group.

    The session that inherited a cycle-91 generation was roughly two cycles and
    thirty hours behind its own ledger, and read it as current.
    """
    old = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(microsecond=0)
    stamp = old.isoformat().replace("+00:00", "Z")
    with get_db() as conn:
        conn.execute("UPDATE workspace_epochs SET valid_from = ?", (stamp,))
        conn.execute(
            "UPDATE claims SET created_at = ?, updated_at = ? WHERE assertion_kind = 'task_state'",
            (stamp, stamp),
        )


def test_fresh_generation_is_certified_fresh() -> None:
    _client()
    record_task_state({"task_id": "devloop", "summary": "cycle 94 in flight"})

    freshness = get_task_state({"task_id": "devloop"})["freshness"]

    assert freshness["state"] == "fresh"
    assert freshness["stale"] is False
    assert freshness["age_hours"] is not None and freshness["age_hours"] < 1
    assert freshness["ttl_hours"] == 24.0
    assert freshness["recorded_at"], "a fresh marker must name the write it measured"
    assert freshness["advice"] == "", "healthy responses stay quiet"


def test_two_cycle_old_generation_is_marked_stale() -> None:
    # The control group: cycle 93 received exactly this and had no way to see it.
    _client()
    record_task_state({"task_id": "devloop", "summary": "cycle 91 state"})
    _age_every_generation(30)

    response = get_task_state({"task_id": "devloop"})
    freshness = response["freshness"]

    assert response["count"] == 1, "the state is old, not missing"
    assert freshness["state"] == "stale"
    assert freshness["stale"] is True
    assert 29 < freshness["age_hours"] < 31
    assert "re-verify" in freshness["advice"].lower()


def test_absent_generation_carries_a_marker_not_just_a_zero_count() -> None:
    # count: 0 is not the same sentence as "nothing is in progress". The last
    # write may simply have failed -- the case cycle 93 could not tell apart.
    _client()
    record_task_state({"task_id": "heartbeat", "summary": "other task"})

    response = get_task_state({"task_id": "devloop"})

    assert response["count"] == 0
    assert response["current"] is None
    assert response["freshness"]["state"] == "absent"
    assert response["freshness"]["stale"] is True
    assert "may have failed" in response["freshness"]["advice"]


def test_replay_is_never_flagged_stale() -> None:
    # Asking for a past view is deliberate; alarming on it would train callers
    # to ignore the marker.
    _client()
    record_task_state({"task_id": "devloop", "summary": "cycle 94"})
    _age_every_generation(72)

    freshness = get_task_state({"task_id": "devloop", "as_of": utc_now()})["freshness"]

    assert freshness["state"] == "replay"
    assert freshness["stale"] is False
    assert freshness["replay_as_of"]


def test_unreadable_timestamp_is_not_certified_fresh() -> None:
    # Absence of a measurement is not evidence of freshness.
    assert task_state_freshness({"task_id": "devloop", "valid_from": "not-a-date"})["state"] == "unknown"
    assert task_state_freshness({"task_id": "devloop", "valid_from": "not-a-date"})["stale"] is True
    assert task_state_freshness({"task_id": "devloop"})["state"] == "unknown"


def test_ttl_dial_prefers_task_state_env_then_capsule() -> None:
    written = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    row = {"valid_from": written}
    previous = {name: os.environ.get(name) for name in ("MEM1_TASK_STATE_STALE_HOURS", "MEM1_CAPSULE_STALE_HOURS")}
    try:
        os.environ.pop("MEM1_TASK_STATE_STALE_HOURS", None)
        os.environ.pop("MEM1_CAPSULE_STALE_HOURS", None)
        assert task_state_freshness(row)["ttl_hours"] == 24.0

        os.environ["MEM1_CAPSULE_STALE_HOURS"] = "4"
        assert task_state_freshness(row)["state"] == "stale", "the capsule dial is the fallback"

        os.environ["MEM1_TASK_STATE_STALE_HOURS"] = "48"
        assert task_state_freshness(row)["state"] == "fresh", "the task-state dial wins"

        os.environ["MEM1_TASK_STATE_STALE_HOURS"] = "garbage"
        assert task_state_freshness(row)["ttl_hours"] == 4.0, "a bad dial falls through, it does not crash"
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_mcp_get_task_state_surfaces_freshness() -> None:
    # The devloop step 0 reads this tool over MCP, not over HTTP.
    _client()
    call_tool("record_task_state", {"task_id": "devloop", "summary": "cycle 94"}, _CTX)

    payload = json.loads(call_tool("get_task_state", {"task_id": "devloop"}, _CTX)["content"][0]["text"])

    assert payload["freshness"]["schema_version"] == "mem1-task-state-freshness-v1"
    assert payload["freshness"]["state"] == "fresh"
