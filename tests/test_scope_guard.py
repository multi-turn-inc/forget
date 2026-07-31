"""F4 재발 방지: 쓰기 시점 스코프 가드 — warn 기본, enforce 옵트인, allowlist."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from forget import db as app_db, scope_guard
from forget.cli import foreign_pools
from forget.db import init_db
from forget.server import app


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    path = Path(f"/tmp/mem1-scope-guard-{os.getpid()}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    monkeypatch.setenv("MEM1_DB_PATH", str(path))
    monkeypatch.setattr(app_db, "DB_PATH", path)
    monkeypatch.setenv("MEM1_MCP_DEFAULT_USER_ID", "owner")
    monkeypatch.delenv("MEM1_SCOPE_GUARD", raising=False)
    monkeypatch.delenv("MEM1_ALLOWED_SCOPES", raising=False)
    init_db()
    return TestClient(app, base_url="http://testserver")


def _add(client: TestClient, **scope) -> dict:
    return client.post(
        "/v1/memories/",
        json={"text": "Use Paddle for payments.", "infer": False, **scope},
    )


def test_canonical_write_is_untouched(client) -> None:
    created = _add(client, user_id="owner", app_id="forget").json()
    assert "scope_guard" not in (created.get("metadata") or {})


def test_warn_default_stamps_foreign_write(client) -> None:
    created = _add(client, user_id="demo", app_id="demo-redis").json()
    assert (created.get("metadata") or {}).get("scope_guard") == "foreign"


def test_enforce_rejects_foreign_write_with_remedy(client, monkeypatch) -> None:
    monkeypatch.setenv("MEM1_SCOPE_GUARD", "enforce")
    response = _add(client, user_id="demo", app_id="demo-redis")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "demo×demo-redis" in detail
    assert "MEM1_ALLOWED_SCOPES" in detail
    assert "FORGET_HOME" in detail


def test_enforce_admits_canonical_write(client, monkeypatch) -> None:
    monkeypatch.setenv("MEM1_SCOPE_GUARD", "enforce")
    response = _add(client, user_id="owner", app_id="forget")
    assert response.status_code == 200


def test_allowlist_admits_named_pool(client, monkeypatch) -> None:
    monkeypatch.setenv("MEM1_SCOPE_GUARD", "enforce")
    monkeypatch.setenv("MEM1_ALLOWED_SCOPES", "acme-corp:work, other:*")
    assert _add(client, user_id="acme-corp", app_id="work").status_code == 200
    assert _add(client, user_id="other", app_id="anything").status_code == 200
    assert _add(client, user_id="acme-corp", app_id="play").status_code == 400


def test_off_mode_is_silent(client, monkeypatch) -> None:
    monkeypatch.setenv("MEM1_SCOPE_GUARD", "off")
    created = _add(client, user_id="demo", app_id="demo-redis").json()
    assert "scope_guard" not in (created.get("metadata") or {})


def test_doctor_foreign_pools_share_the_allowlist(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_ALLOWED_SCOPES", "acme-corp:work")
    pools = [("u", "forget", 10), ("acme-corp", "work", 5), ("demo", "demo-redis", 200)]
    assert foreign_pools(pools, user="u") == [("demo", "demo-redis", 200)]


def test_guard_mode_defaults_to_warn(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_SCOPE_GUARD", raising=False)
    assert scope_guard.guard_mode() == "warn"
    monkeypatch.setenv("MEM1_SCOPE_GUARD", "bogus")
    assert scope_guard.guard_mode() == "warn"
