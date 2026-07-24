"""supersede_memory — the verification loop's deterministic staleness operation.

Contract: non-destructive (row stays retrievable, annotated), hard search
demotion (MEM1_SUPERSEDED_SCORE_MULT), reciprocal link on the successor,
immutable memories refuse, and explicit human feedback rows are untouched.
"""

import time

from fastapi.testclient import TestClient

from forget.server import app


client = TestClient(app)


def _add(text: str, user_id: str) -> str:
    response = client.post(
        "/v1/memories/",
        json={"messages": [{"role": "user", "content": text}], "infer": False, "user_id": user_id},
    )
    assert response.status_code in (200, 201), response.text
    body = response.json()
    items = body if isinstance(body, list) else body.get("results") or [body]
    return str(items[0]["id"])


def _search(query: str, user_id: str) -> list[dict]:
    response = client.post(
        "/v3/memories/search/",
        json={"query": query, "filters": {"user_id": user_id}, "top_k": 10},
    )
    assert response.status_code == 200, response.text
    return response.json().get("results") or []


def test_supersede_demotes_but_keeps_retrievable() -> None:
    user = "supersede-user-1"
    old_id = _add("the deploy pipeline still uses the legacy runner", user)
    new_id = _add("the deploy pipeline moved to the new runner in july", user)

    before = _search("deploy pipeline runner", user)
    assert {old_id, new_id} <= {r["id"] for r in before}, "both facts retrievable before"

    response = client.post(
        f"/v1/memories/{old_id}/supersede/",
        json={"superseded_by": new_id, "reason": "runner migrated"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["superseded_by"] == new_id and body["still_retrievable"] is True

    after = _search("deploy pipeline runner", user)
    ids = [r["id"] for r in after]
    assert old_id in ids, "supersede must be non-destructive"
    assert ids.index(new_id) < ids.index(old_id), "successor must outrank the superseded fact"
    old_hit = next(r for r in after if r["id"] == old_id)
    assert old_hit["metadata"].get("superseded_at"), "annotation must surface in search results"
    assert old_hit["metadata"].get("superseded_by") == new_id
    breakdown = old_hit.get("score_breakdown") or {}
    if breakdown:  # breakdown is only attached on debug-style searches (existing contract)
        assert breakdown.get("superseded") is True

    new_hit = next(r for r in after if r["id"] == new_id)
    assert old_id in (new_hit["metadata"].get("supersedes") or []), "reciprocal link on the successor"


def test_supersede_guards() -> None:
    user = "supersede-user-2"
    memory_id = _add("temporary fact for guard tests", user)
    assert client.post(f"/v1/memories/{memory_id}/supersede/", json={"superseded_by": memory_id}).status_code == 400

    immutable = client.post(
        "/v1/memories/",
        json={
            "messages": [{"role": "user", "content": "immutable policy fact"}],
            "infer": False,
            "user_id": user,
            "metadata": {"immutable": True},
        },
    )
    body = immutable.json()
    items = body if isinstance(body, list) else body.get("results") or [body]
    immutable_id = str(items[0]["id"])
    assert client.post(f"/v1/memories/{immutable_id}/supersede/", json={}).status_code == 409


def test_supersede_leaves_human_feedback_untouched() -> None:
    user = "supersede-user-3"
    memory_id = _add("the team prefers the blue dashboard theme", user)
    fb = client.post("/v1/feedback/", json={"memory_id": memory_id, "feedback": "POSITIVE", "feedback_reason": "human"})
    assert fb.status_code in (200, 201), fb.text

    assert client.post(f"/v1/memories/{memory_id}/supersede/", json={"reason": "theme changed"}).status_code == 200

    from forget.store import current_project_id, memory_feedback_map

    feedback = memory_feedback_map(current_project_id()).get(memory_id) or {}
    assert feedback.get("feedback") == "POSITIVE", "explicit human feedback must survive supersession"


def test_assemble_context_excludes_superseded_memories() -> None:
    # Issue #3 (dogfood repro on 0.2.0): supersede demoted the old fact in
    # search, but assemble_context still selected BOTH versions into action
    # context — a struck-through fact re-entering the acting prompt defeats
    # the whole supersede contract. Search keeps it (history/audit); the
    # action capsule must not.
    from uuid import uuid4

    from forget.store import assemble_context

    user = f"supersede-context-user-{uuid4().hex[:8]}"
    old_id = _add("the deployment target is staging", user)
    new_id = _add("the deployment target is production", user)

    response = client.post(
        f"/v1/memories/{old_id}/supersede/",
        json={"superseded_by": new_id, "reason": "production rollout completed"},
    )
    assert response.status_code == 200, response.text

    capsule = assemble_context(
        {
            "query": "where should I deploy?",
            "filters": {"user_id": user},
            "threshold": 0,
        }
    )
    selected_ids = {str(memory["id"]) for memory in capsule["memories"]}
    assert new_id in selected_ids
    assert old_id not in selected_ids
    assert "staging" not in capsule.get("context", "")
