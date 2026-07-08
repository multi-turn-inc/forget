"""Temporal rerank — query-time stale-sibling demotion.

A stale fact usually survives as several near-duplicate rows, and a query
phrased around the old state embeds closer to those rows than to the
replacement fact. With temporal_rerank on, an older memory yields to a
sufficiently similar, meaningfully newer one; the newest similar row keeps
its full score. Similarity floors here are calibrated for the deterministic
test embedding (same convention as test_stale_candidates.py).
"""

import uuid

from fastapi.testclient import TestClient

from forget.server import app


client = TestClient(app)
# unique per run: the test DB persists across pytest invocations, and ranking
# assertions are not tolerant of duplicate rows from earlier runs
USER = f"temporal-rerank-user-{uuid.uuid4().hex[:8]}"


def _add(text: str, created_at: str, user: str = USER) -> str:
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


def _search(query: str, user: str = USER, **overrides) -> list[dict]:
    payload = {"query": query, "filters": {"user_id": user}, "top_k": 10, **overrides}
    response = client.post("/v3/memories/search/", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["results"]


def test_stale_siblings_yield_to_newer_similar_memory(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_STALE_SIBLING_MIN_SIMILARITY", "0.60")
    user = f"{USER}-demote"
    old_a = _add("user lives in seattle near the waterfront", "2026-01-05T09:00:00", user)
    old_b = _add("user lives in seattle and loves the coffee scene", "2026-02-10T09:00:00", user)
    new_id = _add("user lives in austin after moving from seattle", "2026-06-20T09:00:00", user)

    baseline = _search("does the user still live in seattle", user)
    by_id = {item["id"]: item for item in baseline}
    assert not by_id[old_a]["score_breakdown"].get("stale_sibling"), "flag off: no demotion"

    results = _search("does the user still live in seattle", user, temporal_rerank=True)
    by_id = {item["id"]: item for item in results}
    for stale_id in (old_a, old_b):
        marker = by_id[stale_id]["score_breakdown"].get("stale_sibling")
        assert marker, results
        assert marker["newer_id"] in (new_id, old_b), marker
    assert not by_id[new_id]["score_breakdown"].get("stale_sibling"), "newest similar row keeps full score"
    assert by_id[new_id]["score"] > by_id[old_a]["score"]
    assert by_id[new_id]["score"] > by_id[old_b]["score"]


def test_buried_replacement_is_promoted_next_to_its_anchor(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_TEMPORAL_PROMOTE_MIN_SIMILARITY", "0.55")
    monkeypatch.setenv("MEM1_STALE_SIBLING_MIN_SIMILARITY", "0.55")
    user = f"{USER}-promote"
    # noise predates the anchor, so it can never qualify as its newer sibling
    _add("user lives near a lively city market and loves it", "2025-12-01T09:00:00", user)
    _add("the user lives for seattle sports and city events", "2025-12-02T09:00:00", user)
    old_id = _add("user lives in seattle waterfront pier apartment", "2026-01-05T09:00:00", user)
    # the replacement shares topic words with the anchor, not with the query
    new_id = _add("user apartment waterfront pier relocated to austin now", "2026-06-20T09:00:00", user)

    query = "does the user still live in seattle"
    baseline_order = [item["id"] for item in _search(query, user)]
    assert baseline_order.index(old_id) < baseline_order.index(new_id), (
        "query wording must favor the stale row for this test to mean anything"
    )

    results = _search(query, user, temporal_rerank=True)
    by_id = {item["id"]: item for item in results}
    order = [item["id"] for item in results]
    marker = by_id[new_id]["score_breakdown"].get("temporal_sibling_of")
    assert marker and marker["anchor_id"] == old_id, results
    assert order.index(new_id) < order.index(old_id), "newest state outranks the stale anchor"


def test_recent_siblings_are_not_demoted(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_STALE_SIBLING_MIN_SIMILARITY", "0.60")
    user = f"{USER}-fresh"
    _add("standup happens on mondays at 9am", "2026-07-01T09:00:00", user)
    _add("standup happens on mondays at 9am in room b", "2026-07-03T09:00:00", user)

    results = _search("when is standup", user, temporal_rerank=True)
    assert all(not item["score_breakdown"].get("stale_sibling") for item in results), (
        "siblings closer than MEM1_STALE_SIBLING_MIN_DAYS stay untouched"
    )


def test_project_setting_enables_rerank_without_payload(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_STALE_SIBLING_MIN_SIMILARITY", "0.60")
    from forget.providers import update_project_settings

    user = f"{USER}-projset"
    old_id = _add("user lives in seattle near the waterfront docks", "2026-01-05T09:00:00", user)
    new_id = _add("user lives in austin after moving from seattle", "2026-06-20T09:00:00", user)

    update_project_settings("proj_local", {"temporal_rerank": True})
    try:
        results = _search("does the user still live in seattle", user)  # no payload flag
        by_id = {item["id"]: item for item in results}
        assert by_id[old_id]["score_breakdown"].get("stale_sibling"), "project setting turns rerank on"
        # payload override still wins for benchmark arms
        off = _search("does the user still live in seattle", user, temporal_rerank=False)
        assert not {i["id"]: i for i in off}[old_id]["score_breakdown"].get("stale_sibling")
    finally:
        update_project_settings("proj_local", {"temporal_rerank": False})


def test_superseded_rows_keep_the_harder_penalty_only(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_STALE_SIBLING_MIN_SIMILARITY", "0.60")
    user = f"{USER}-superseded"
    old_id = _add("user's laptop is a 2019 intel macbook pro", "2026-01-05T09:00:00", user)
    new_id = _add("user's laptop is an m4 macbook pro", "2026-06-20T09:00:00", user)
    response = client.post(f"/v1/memories/{old_id}/supersede/", json={"superseded_by": new_id})
    assert response.status_code == 200, response.text

    results = _search("which laptop does the user have", user, temporal_rerank=True)
    by_id = {item["id"]: item for item in results}
    # (the plain "superseded" breakdown flag only surfaces under keyword/
    # criteria search — pre-existing contract; the demotion itself applies)
    assert not by_id[old_id]["score_breakdown"].get("stale_sibling"), (
        "superseded rows already carry the deterministic penalty"
    )
    assert by_id[new_id]["score"] > by_id[old_id]["score"]
