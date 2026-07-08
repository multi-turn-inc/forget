"""Consolidation worker — the verification loop as a background behavior.

The adjudicator is faked (no network): tests pin the worker's mechanics —
gating, pair flow, supersession, caps, fail-safe refusal.
"""

import uuid

from fastapi.testclient import TestClient

import forget.consolidation as consolidation
from forget.consolidation import consolidation_cycle
from forget.server import app
from forget.providers import update_project_settings


client = TestClient(app)


def _add(text: str, created_at: str, user: str) -> str:
    response = client.post(
        "/v1/memories/",
        json={
            "messages": [{"role": "user", "content": text}],
            "infer": False,
            "user_id": user,
            "created_at": created_at,
        },
    )
    assert response.status_code in (200, 201), response.text
    body = response.json()
    items = body if isinstance(body, list) else body.get("results") or [body]
    return str(items[0]["id"])


def _memory(memory_id: str) -> dict:
    response = client.get(f"/v1/memories/{memory_id}/")
    assert response.status_code == 200, response.text
    return response.json()


def _enable(monkeypatch, **env) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MEM1_CONSOLIDATION_MIN_SIMILARITY", "0.60")
    # test rows are backdated; widen the activity window so they count,
    # and raise the entity cap so shared-DB growth can't push them out
    monkeypatch.setenv("MEM1_CONSOLIDATION_WINDOW_HOURS", "100000")
    monkeypatch.setenv("MEM1_CONSOLIDATION_MAX_ENTITIES", "500")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    update_project_settings("proj_local", {"consolidation_enabled": True})


def _fake_adjudicator(decide):
    def fake(pairs, params):
        return [decide(pair) for pair in pairs]

    return fake


def test_cycle_supersedes_replaced_state_and_completed_todo(monkeypatch) -> None:
    _enable(monkeypatch)
    user = f"consol-{uuid.uuid4().hex[:8]}"
    try:
        old_state = _add("user's laptop is a 2019 intel macbook pro", "2026-01-05T09:00:00", user)
        new_state = _add("user's laptop is an m4 macbook pro now", "2026-07-01T09:00:00", user)
        todo = _add("todo: publish the verified memory blog post", "2026-06-01T09:00:00", user)
        done = _add("the verified memory blog post is published", "2026-07-02T09:00:00", user)
        bystander = _add("user drinks pour-over coffee every morning", "2026-01-06T09:00:00", user)

        def decide(pair):
            older_text = (pair.get("older") or {}).get("memory") or ""
            return "laptop" in older_text or "todo" in older_text

        monkeypatch.setattr(consolidation, "_adjudicate_batch", _fake_adjudicator(decide))
        report = consolidation_cycle()

        assert report["superseded"] >= 2, report
        assert _memory(old_state)["metadata"].get("superseded_by") == new_state
        assert _memory(todo)["metadata"].get("superseded_by") == done
        assert not _memory(bystander)["metadata"].get("superseded_at"), "unrelated memory untouched"
        assert not _memory(new_state)["metadata"].get("superseded_at")
    finally:
        update_project_settings("proj_local", {"consolidation_enabled": False})


def test_project_gate_and_fail_safe(monkeypatch) -> None:
    user = f"consol-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("MEM1_CONSOLIDATION_MIN_SIMILARITY", "0.60")
    monkeypatch.setenv("MEM1_CONSOLIDATION_WINDOW_HOURS", "100000")
    monkeypatch.setenv("MEM1_CONSOLIDATION_MAX_ENTITIES", "500")
    update_project_settings("proj_local", {"consolidation_enabled": False})
    old_id = _add("user lives in seattle by the bay", "2026-01-05T09:00:00", user)
    _add("user lives in austin these days", "2026-07-01T09:00:00", user)

    # project gate off → nothing happens even with an eager adjudicator
    monkeypatch.setattr(consolidation, "_adjudicate_batch", _fake_adjudicator(lambda pair: True))
    report = consolidation_cycle()
    assert report["superseded"] == 0 and report["skipped_projects"] >= 1
    assert not _memory(old_id)["metadata"].get("superseded_at")

    # gate on but adjudicator refuses (fail-safe default) → still nothing
    update_project_settings("proj_local", {"consolidation_enabled": True})
    try:
        monkeypatch.setattr(consolidation, "_adjudicate_batch", _fake_adjudicator(lambda pair: False))
        report = consolidation_cycle()
        assert report["superseded"] == 0
        assert report["pairs"] >= 1, "pair inbox surfaced but judgment declined"
        assert not _memory(old_id)["metadata"].get("superseded_at")

        # declined verdicts are cached — the next cycle skips re-adjudication
        second = consolidation_cycle()
        assert second["superseded"] == 0
        assert second["pairs"] < report["pairs"], "verdict cache should shrink the inbox"
    finally:
        update_project_settings("proj_local", {"consolidation_enabled": False})


def test_missing_api_key_disables_cycle(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MEM1_CONSOLIDATION_API_KEY", raising=False)
    report = consolidation_cycle()
    assert report.get("disabled") == "no_api_key"


def test_env_kill_switch(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_CONSOLIDATION", "0")
    report = consolidation_cycle()
    assert report.get("disabled") == "env"
