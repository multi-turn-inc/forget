"""Relay contract tests — signature, token lifecycle, cap, metering.

Run: FORGET_RELAY_DB=/tmp/test-relay.sqlite3 python -m pytest test_relay.py -q
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time

os.environ.setdefault("FORGET_RELAY_DB", "/tmp/test-relay.sqlite3")
os.environ["PADDLE_WEBHOOK_SECRET"] = "test-secret"
os.environ["FORGET_RELAY_MONTHLY_CAP"] = "3"

import relay
from fastapi.testclient import TestClient

relay.MONTHLY_CALL_CAP = 3
client = TestClient(relay.app)


def _signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    ts = str(int(time.time()))
    h1 = hmac.new(b"test-secret", f"{ts}:".encode() + raw, hashlib.sha256).hexdigest()
    return raw, f"ts={ts};h1={h1}"


def setup_module(_m) -> None:
    if os.path.exists(os.environ["FORGET_RELAY_DB"]):
        os.remove(os.environ["FORGET_RELAY_DB"])


def test_webhook_rejects_bad_signature() -> None:
    response = client.post(
        "/webhooks/paddle", content=b"{}", headers={"paddle-signature": "ts=1;h1=deadbeef"}
    )
    assert response.status_code == 400


def test_webhook_cancel_deactivates_token() -> None:
    token = relay._issue_token("sub_test1", "txn_test1")
    raw, signature = _signed(
        {"event_type": "subscription.canceled", "data": {"id": "sub_test1"}}
    )
    response = client.post("/webhooks/paddle", content=raw, headers={"paddle-signature": signature})
    assert response.status_code == 200 and response.json()["applied"] == "canceled"
    with relay._db() as conn:
        row = conn.execute(
            "SELECT status FROM tokens WHERE token_hash = ?", (relay._hash(token),)
        ).fetchone()
    assert row["status"] == "canceled"


def test_reissue_rotates_previous_token() -> None:
    first = relay._issue_token("sub_test2", "txn_a")
    second = relay._issue_token("sub_test2", "txn_a")
    with relay._db() as conn:
        first_status = conn.execute(
            "SELECT status FROM tokens WHERE token_hash = ?", (relay._hash(first),)
        ).fetchone()["status"]
        second_status = conn.execute(
            "SELECT status FROM tokens WHERE token_hash = ?", (relay._hash(second),)
        ).fetchone()["status"]
    assert first_status == "rotated" and second_status == "active"


def test_auth_unknown_token_401() -> None:
    response = client.post(
        "/v1/chat/completions",
        json={"messages": []},
        headers={"Authorization": "Bearer fgc_nope"},
    )
    assert response.status_code == 401


def test_monthly_cap_429_and_metering(monkeypatch) -> None:
    token = relay._issue_token("sub_test3", "txn_b")

    class FakeResponse:
        def read(self) -> bytes:
            return json.dumps(
                {"choices": [{"message": {"content": "[1]"}}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(relay.urllib.request, "urlopen", lambda *a, **k: FakeResponse())
    monkeypatch.setenv("FORGET_RELAY_UPSTREAM_KEY", "fake")

    for _ in range(3):
        ok = client.post(
            "/v1/chat/completions", json={"messages": []}, headers={"Authorization": f"Bearer {token}"}
        )
        assert ok.status_code == 200
    over = client.post(
        "/v1/chat/completions", json={"messages": []}, headers={"Authorization": f"Bearer {token}"}
    )
    assert over.status_code == 429
    with relay._db() as conn:
        calls, prompt_sum = conn.execute(
            "SELECT COUNT(*), SUM(prompt_tokens) FROM usage WHERE token_hash = ?", (relay._hash(token),)
        ).fetchone()
    assert calls == 3 and prompt_sum == 30
