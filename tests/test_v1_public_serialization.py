"""#7 회귀: v1 REST 표면은 내부 저장 필드를 노출하지 않는다."""
import os
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import init_db
from forget.server import app

_INTERNAL = {"_embedding", "hash", "project_id"}


def _client() -> TestClient:
    path = Path(f"/tmp/mem1-v1-public-{os.getpid()}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def test_v1_list_strips_internal_fields() -> None:
    c = _client()
    created = c.post("/v1/memories/", json={
        "text": "Harbor prefers single-binary deploys", "infer": False,
        "user_id": "u1", "app_id": "a1",
    })
    assert created.status_code == 200

    listed = c.get("/v1/memories/", params={"user_id": "u1", "app_id": "a1"})
    assert listed.status_code == 200
    items = listed.json()
    assert items, "expected at least one memory"
    for item in items:
        leaked = _INTERNAL & set(item)
        assert not leaked, f"internal fields leaked from v1 list: {leaked}"
        assert not any(k.startswith("_") for k in item)
    # 단건 조회와 필드 집합 동형 (allowlist 일관성)
    single = c.get(f"/v1/memories/{items[0]['id']}/").json()
    assert set(items[0]) <= set(single) | {"score"}
