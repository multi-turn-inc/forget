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
from fastapi.responses import HTMLResponse

UPSTREAM = os.getenv("FORGET_RELAY_UPSTREAM", "https://api.deepinfra.com/v1/openai").rstrip("/")
UPSTREAM_MODEL = os.getenv("FORGET_RELAY_UPSTREAM_MODEL", "Qwen/Qwen3.5-9B")
DB_PATH = Path(os.getenv("FORGET_RELAY_DB", "~/.forget/cloud-relay.sqlite3")).expanduser()
MONTHLY_CALL_CAP = int(os.getenv("FORGET_RELAY_MONTHLY_CAP", "2000"))
# forget cloud Pro (2026-08-04 생성, 정훈 반환 ②) — 결제 ID는 공개값이라 기본값으로 박음
PRO_PRICE_ID = os.getenv("FORGET_RELAY_PRICE_ID", "pri_01kz5r9rj5fa8ahsjz6hwq5z3b")
PRO_PRODUCT_ID = os.getenv("FORGET_RELAY_PRODUCT_ID", "pro_01kz5r87rh4qq9zggk2xah4jk5")

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


def _transaction_buys_pro(transaction: dict[str, Any]) -> bool:
    """/activate는 '완료된 아무 결제'가 아니라 '우리 Pro를 산 결제'만 믿는다."""
    for item in transaction.get("items") or []:
        price = item.get("price") or {}
        if str(price.get("id") or "") == PRO_PRICE_ID:
            return True
        if str(price.get("product_id") or "") == PRO_PRODUCT_ID:
            return True
    for line in (transaction.get("details") or {}).get("line_items") or []:
        if str(line.get("price_id") or "") == PRO_PRICE_ID:
            return True
    return False


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


ACTIVATE_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>forget cloud — welcome</title>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  body { background:#faf9f7; color:#1a1c20; font:16px/1.7 "Inter",-apple-system,sans-serif; -webkit-font-smoothing:antialiased; }
  ::selection { background:#d31126; color:#fff; }
  .wrap { max-width:640px; margin:0 auto; padding:64px 32px; }
  h1 { font-family:"Instrument Serif",Georgia,serif; font-weight:400; font-size:40px; }
  h1 s { text-decoration-color:#d31126; text-decoration-thickness:2px; }
  p.sub { font-family:"Instrument Serif",serif; font-style:italic; color:#4e5359; font-size:20px; margin-top:10px; }
  .token { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:14px; background:#fff;
           border:1px solid #e5e2dc; border-radius:8px; padding:16px; margin:32px 0 8px; word-break:break-all;
           cursor:pointer; }
  .hint { font-size:13px; color:#71767d; }
  .steps { margin-top:32px; color:#4e5359; font-size:15px; }
  .steps code { font-family:ui-monospace,Menlo,monospace; font-size:13.5px; background:#f8e9e7; border-radius:4px; padding:2px 6px; }
  .warn { margin-top:24px; font-size:13.5px; color:#71767d; border-left:2px solid #e5e2dc; padding-left:14px; }
</style></head><body><div class="wrap">
<h1>Welcome to <s>forget</s> cloud.</h1>
<p class="sub">Depth when you need it. Speed when you don&rsquo;t.</p>
<div class="token" onclick="navigator.clipboard.writeText(this.textContent.trim());this.style.borderColor='#d31126'">__TOKEN__</div>
<p class="hint">click to copy</p>
<div class="steps">One line in your terminal:<br>
<code>forget recall cloud-token __TOKEN__</code><br><br>
That&rsquo;s it &mdash; your dial&rsquo;s high and extra gears now answer from the cloud.</div>
<p class="warn">This token is shown once. If you lose it, revisit this page from your receipt link &mdash;
a fresh token is issued and the old one goes quiet.</p>
</div></body></html>"""


@app.get("/activate")
def activate(request: Request, txn: str) -> Any:
    """Checkout success lands here: verify the transaction with Paddle
    directly (never trust the query string), then hand out the token."""
    if not txn.startswith("txn_"):
        raise HTTPException(status_code=400, detail="invalid transaction id")
    transaction = paddle_query_transaction(txn)
    if str(transaction.get("status") or "") not in {"completed", "paid"}:
        raise HTTPException(status_code=402, detail=f"transaction not completed ({transaction.get('status')})")
    if not _transaction_buys_pro(transaction):
        raise HTTPException(status_code=403, detail="transaction is not a forget cloud Pro purchase")
    subscription_id = str(transaction.get("subscription_id") or txn)
    token = _issue_token(subscription_id, txn)
    if "text/html" in str(request.headers.get("accept") or ""):
        return HTMLResponse(ACTIVATE_HTML.replace("__TOKEN__", token))
    return {
        "token": token,
        "next": "forget recall cloud-token <token>",
        "note": "shown once — revisiting reissues and quiets the old token",
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
