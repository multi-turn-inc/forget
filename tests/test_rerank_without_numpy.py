"""Temporal rerank must work on a minimal install (no numpy).

The engine's README promise is FastAPI + httpx only. numpy is a speedup,
not a requirement: without it these paths must fall back to pure Python,
not silently no-op (the regression this file pins down).
"""

import sys
import uuid

import pytest
from fastapi.testclient import TestClient

from forget.server import app
from forget.store import _pairwise_cosine_matrix

client = TestClient(app)
USER = f"no-numpy-user-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def no_numpy(monkeypatch):
    """Make `import numpy` raise ImportError for the duration of a test."""
    for name in [key for key in sys.modules if key == "numpy" or key.startswith("numpy.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "numpy", None)


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


def test_pairwise_matrix_matches_between_backends(no_numpy):
    embeddings = [
        [1.0, 0.0, 0.0],
        [0.6, 0.8, 0.0],
        [0.0, 0.0, 1.0],
    ]
    fallback = _pairwise_cosine_matrix(embeddings)
    assert fallback is not None
    assert fallback[0][0] == pytest.approx(1.0)
    assert fallback[0][1] == pytest.approx((0.6 + 1.0) / 2.0)
    assert fallback[0][2] == pytest.approx(0.5)
    assert fallback[1][2] == pytest.approx(fallback[2][1])


def test_stale_sibling_demotion_fires_without_numpy(no_numpy, monkeypatch):
    monkeypatch.setenv("MEM1_STALE_SIBLING_MIN_SIMILARITY", "0.60")
    user = f"{USER}-demote"
    old_id = _add("user lives in seattle near the waterfront", "2026-01-05T09:00:00", user)
    new_id = _add("user lives in austin after moving from seattle", "2026-06-20T09:00:00", user)

    response = client.post(
        "/v3/memories/search/",
        json={
            "query": "does the user still live in seattle",
            "filters": {"user_id": user},
            "top_k": 10,
            "temporal_rerank": True,
        },
    )
    assert response.status_code == 200, response.text
    by_id = {item["id"]: item for item in response.json()["results"]}
    assert by_id[old_id]["score_breakdown"].get("stale_sibling"), (
        "temporal rerank must not silently no-op without numpy"
    )
    assert not by_id[new_id]["score_breakdown"].get("stale_sibling")
