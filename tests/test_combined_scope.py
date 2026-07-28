"""#6 회귀: 결합 스코프(add)는 결합 스코프(search/list)로 되찾을 수 있다."""
import os
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import init_db
from forget.server import app


def _client() -> TestClient:
    path = Path(f"/tmp/mem1-combined-scope-{os.getpid()}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def test_combined_add_is_one_record_with_both_ids() -> None:
    c = _client()
    created = c.post("/v1/memories/", json={
        "text": "Use Paddle for payments.", "infer": False,
        "user_id": "user-1", "agent_id": "agent-1", "app_id": "app-1",
    }).json()
    assert created["user_id"] == "user-1"
    assert created["agent_id"] == "agent-1"

    everything = c.get("/v1/memories/", params={"app_id": "app-1"}).json()
    assert len(everything) == 1, f"expected one combined record, got {len(everything)}"


def test_combined_filters_return_the_record() -> None:
    c = _client()
    c.post("/v1/memories/", json={
        "text": "Use Paddle for payments.", "infer": False,
        "user_id": "user-1", "agent_id": "agent-1", "app_id": "app-1",
    })
    for params in (
        {"user_id": "user-1", "app_id": "app-1"},
        {"agent_id": "agent-1", "app_id": "app-1"},
        {"user_id": "user-1", "agent_id": "agent-1", "app_id": "app-1"},
    ):
        listed = c.get("/v1/memories/", params=params).json()
        assert len(listed) == 1, f"filters {params} returned {len(listed)}"
    hits = c.post("/v1/memories/search/", json={
        "query": "payments", "user_id": "user-1", "agent_id": "agent-1", "app_id": "app-1",
    }).json()
    assert hits.get("results"), "combined-scope search returned zero results"


def test_single_entity_adds_unchanged() -> None:
    c = _client()
    c.post("/v1/memories/", json={"text": "solo", "infer": False, "user_id": "only-user", "app_id": "a"})
    listed = c.get("/v1/memories/", params={"user_id": "only-user"}).json()
    assert len(listed) == 1 and listed[0]["agent_id"] is None
