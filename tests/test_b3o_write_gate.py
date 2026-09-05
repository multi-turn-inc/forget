"""B3O 제품 레인 쓰기 게이트 계약 (승격 계약 §④, 경계 해제 2026-08-29).

계약: ①b3o.* 스코프 쓰기는 human_approved=true 없이는 403 ②있으면 통과
③타 스코프는 무영향 ④human_approved의 참-유사값(1, "true")은 불허 — 명시 true만.
"""
from __future__ import annotations

import os

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-b3o.sqlite3")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from forget.db import init_db  # noqa: E402
from forget.server import app  # noqa: E402
from forget.store import create_api_key  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "a.sqlite3"))
    init_db()


def _client_headers():
    key = create_api_key({"name": "b3o", "agent_principal": "b3o-desktop"})
    return TestClient(app), {"Authorization": f"Bearer {key['api_key']}"}


def test_b3o_write_requires_human_approval():
    client, headers = _client_headers()
    body = {"text": "사용자 결정: 다크 모드 선호", "app_id": "b3o.ws-main"}
    out = client.post("/v1/memories/", json=body, headers=headers)
    assert out.status_code == 403 and "human_approved" in out.json()["detail"]   # ①
    ok = client.post("/v1/memories/", json={**body, "human_approved": True}, headers=headers)
    assert ok.status_code == 200                                                 # ②


@pytest.mark.parametrize("value", [1, "true", "yes"])
def test_truthy_lookalikes_rejected(value):
    client, headers = _client_headers()
    out = client.post("/v1/memories/", json={
        "text": "x", "app_id": "b3o.ws", "human_approved": value}, headers=headers)
    assert out.status_code == 403                                                # ④


def test_other_scopes_unaffected():
    client, headers = _client_headers()
    out = client.post("/v1/memories/", json={
        "text": "데모 씨딩", "app_id": "demo-mentoring"}, headers=headers)
    assert out.status_code == 200                                                # ③
