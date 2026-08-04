#!/usr/bin/env python3
"""forget cloud relay — deep recall without heating your laptop.

The certification (2026-08-04) said it plainly: hosted BF16 wins on both
quality (0.950 vs local q4 0.908) and speed (2.5s vs 20s). This relay is
that advantage productized. Billing rides the Paddle account inherited
from Mem1 — forget.sh's predecessor — whose KYB and live transactions
already cleared; the webhook signature scheme is ported from its
battle-tested billing.py.

The privacy contract, in code:
  * memory candidates PASS THROUGH — request and response bodies are never
    written to disk, never logged, never retained
  * what we keep per call: token hash, timestamp, token counts — the bill,
    not the memory
  * tokens are stored as SHA-256 hashes; a lost token is rotated, not
    recovered

Flow:
  Paddle checkout ──▶ success redirect /activate?txn=... ──▶ token issued
  client `forget recall engine cloud` + token ──▶ /v1/chat/completions
  over monthly cap ──▶ 429 — the client's ladder quietly degrades to local

Run (dev):
  FORGET_RELAY_ENV_FILE=~/Documents/Mem1/.secrets/paddle-payments.sandbox.env \
  uvicorn relay:app --port 9100
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets as pysecrets
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

UPSTREAM = os.getenv("FORGET_RELAY_UPSTREAM", "https://api.deepinfra.com/v1/openai").rstrip("/")
UPSTREAM_MODEL = os.getenv("FORGET_RELAY_UPSTREAM_MODEL", "Qwen/Qwen3.5-9B")
DB_PATH = Path(os.getenv("FORGET_RELAY_DB", "~/.forget/cloud-relay.sqlite3")).expanduser()
MONTHLY_CALL_CAP = int(os.getenv("FORGET_RELAY_MONTHLY_CAP", "2000"))

app = FastAPI(title="forget-cloud-relay", docs_url=None, redoc_url=None)


def _load_env_file() -> None:
    env_file = os.getenv("FORGET_RELAY_ENV_FILE", "")
    if env_file and os.path.exists(os.path.expanduser(env_file)):
        for line in open(os.path.expanduser(env_file)):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env_file()

PADDLE_API = "https://sandbox-api.paddle.com" if os.getenv("PADDLE_SANDBOX") else "https://api.paddle.com"


def _db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """CREATE TABLE IF NOT EXISTS tokens (
             token_hash TEXT PRIMARY KEY,
             paddle_subscription_id TEXT,
             paddle_transaction_id TEXT,
             plan TEXT DEFAULT 'pro',
             status TEXT DEFAULT 'active',
             created_at REAL);
           CREATE TABLE IF NOT EXISTS usage (
             token_hash TEXT, at REAL, prompt_tokens INTEGER, completion_tokens INTEGER);
           CREATE INDEX IF NOT EXISTS usage_token_at ON usage (token_hash, at);"""
    )
    return conn


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _upstream_key() -> str:
    key = os.getenv("FORGET_RELAY_UPSTREAM_KEY", "")
    if key:
        return key
    key_file = os.getenv("FORGET_RELAY_UPSTREAM_KEY_FILE", "")
    if key_file and os.path.exists(os.path.expanduser(key_file)):
        return open(os.path.expanduser(key_file)).read().strip()
    raise HTTPException(status_code=503, detail="relay upstream key not configured")


# --- Paddle (scheme ported from Mem1 billing.py — the predecessor's tested code) ---


def verify_paddle_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    try:
        parts = dict(item.split("=", 1) for item in str(signature_header or "").split(";") if "=" in item)
        ts, h1 = parts.get("ts", ""), parts.get("h1", "")
        if not ts or not h1 or not secret:
            return False
        signed = f"{ts}:".encode("utf-8") + raw_body
        digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, h1)
    except Exception:
        return False


def paddle_query_transaction(transaction_id: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{PADDLE_API}/transactions/{transaction_id}",
        headers={"Authorization": f"Bearer {os.getenv('PADDLE_API_KEY', '')}"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read()).get("data") or {}


def _issue_token(subscription_id: str, transaction_id: str) -> str:
    """One live token per subscription — re-activation rotates rather than
    recovers (we only store hashes; there is nothing to recover)."""
    token = f"fgc_{pysecrets.token_urlsafe(32)}"
    with _db() as conn:
        conn.execute(
            "UPDATE tokens SET status='rotated' WHERE paddle_subscription_id = ? AND status='active'",
            (subscription_id,),
        )
        conn.execute(
            "INSERT INTO tokens VALUES (?, ?, ?, 'pro', 'active', ?)",
            (_hash(token), subscription_id, transaction_id, time.time()),
        )
    return token


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {"service": "forget-cloud-relay", "upstream_model": UPSTREAM_MODEL, "cap": MONTHLY_CALL_CAP}


@app.post("/webhooks/paddle")
async def paddle_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    secret = os.getenv("PADDLE_WEBHOOK_SECRET", "")
    if not verify_paddle_signature(raw, request.headers.get("paddle-signature", ""), secret):
        raise HTTPException(status_code=400, detail="signature verification failed")
    payload = json.loads(raw.decode("utf-8"))
    event_type = str(payload.get("event_type") or "")
    data = payload.get("data") or {}
    subscription_id = str(data.get("subscription_id") or data.get("id") or "")
    if event_type.startswith("subscription.") and event_type.endswith(("canceled", "cancelled", "past_due")):
        with _db() as conn:
            conn.execute(
                "UPDATE tokens SET status='canceled' WHERE paddle_subscription_id = ?", (subscription_id,)
            )
        return {"ok": True, "applied": "canceled"}
    return {"ok": True, "applied": "noted"}


@app.get("/activate")
def activate(txn: str) -> dict[str, Any]:
    """Checkout success lands here: verify the transaction with Paddle
    directly (never trust the query string), then hand out the token."""
    if not txn.startswith("txn_"):
        raise HTTPException(status_code=400, detail="invalid transaction id")
    transaction = paddle_query_transaction(txn)
    if str(transaction.get("status") or "") not in {"completed", "paid"}:
        raise HTTPException(status_code=402, detail=f"transaction not completed ({transaction.get('status')})")
    subscription_id = str(transaction.get("subscription_id") or txn)
    token = _issue_token(subscription_id, txn)
    return {
        "token": token,
        "next": "forget recall engine cloud 를 실행하고, 설정에 이 토큰을 저장하세요: "
                "forget recall cloud-token <token>",
        "note": "토큰은 다시 볼 수 없습니다 — 잃어버리면 이 페이지에서 재발급(기존 토큰은 무효화).",
    }


def _authorize(token: str) -> str:
    token_hash = _hash(token)
    with _db() as conn:
        row = conn.execute("SELECT status FROM tokens WHERE token_hash = ?", (token_hash,)).fetchone()
        if row is None or row["status"] != "active":
            raise HTTPException(status_code=401, detail="unknown or inactive forget cloud token — forget.sh/cloud")
        month_start = time.time() - 30 * 86400
        calls = conn.execute(
            "SELECT COUNT(*) FROM usage WHERE token_hash = ? AND at > ?", (token_hash, month_start)
        ).fetchone()[0]
    if calls >= MONTHLY_CALL_CAP:
        raise HTTPException(
            status_code=429,
            detail=f"monthly deep-recall cap reached ({MONTHLY_CALL_CAP}) — recall falls back to local until renewal",
        )
    return token_hash


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    auth = request.headers.get("authorization", "")
    token_hash = _authorize(auth.removeprefix("Bearer ").strip())

    body = json.loads(await request.body())
    body["model"] = UPSTREAM_MODEL  # the client names a gear alias; we pin the certified model

    upstream_request = urllib.request.Request(
        f"{UPSTREAM}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_upstream_key()}"},
    )
    try:
        with urllib.request.urlopen(upstream_request, timeout=90) as upstream_response:
            payload = json.loads(upstream_response.read())
    except urllib.error.HTTPError as exc:  # pragma: no cover - passthrough
        raise HTTPException(status_code=exc.code, detail="upstream error") from exc

    usage = payload.get("usage") or {}
    with _db() as conn:
        conn.execute(
            "INSERT INTO usage VALUES (?, ?, ?, ?)",
            (token_hash, time.time(), int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)),
        )
    return payload
