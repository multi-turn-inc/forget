#!/usr/bin/env python3
"""forget cloud relay — deep recall without heating your laptop.

The certification (2026-08-04) said it plainly: hosted BF16 wins on both
quality (0.950 vs local q4 0.908) and speed (2.5s vs 20s). This relay is
that advantage productized: the client's recall gears speak to us with an
account token; we forward to the upstream serving the certified model and
meter usage. Nothing else.

The privacy contract, in code:
  * memory candidates PASS THROUGH — request and response bodies are never
    written to disk, never logged, never retained
  * what we keep per call: token id, timestamp, token counts — the bill,
    not the memory

Run (dev):
  FORGET_RELAY_UPSTREAM=https://api.deepinfra.com/v1/openai \
  FORGET_RELAY_UPSTREAM_KEY_FILE=~/.config/openai/deepinfra.key \
  FORGET_RELAY_TOKENS=dev-token-1 \
  uvicorn relay:app --port 9100
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

UPSTREAM = os.getenv("FORGET_RELAY_UPSTREAM", "https://api.deepinfra.com/v1/openai").rstrip("/")
UPSTREAM_MODEL = os.getenv("FORGET_RELAY_UPSTREAM_MODEL", "Qwen/Qwen3.5-9B")
USAGE_DB = Path(os.getenv("FORGET_RELAY_USAGE_DB", "~/.forget/cloud-relay-usage.sqlite3")).expanduser()

app = FastAPI(title="forget-cloud-relay", docs_url=None, redoc_url=None)


def _upstream_key() -> str:
    key = os.getenv("FORGET_RELAY_UPSTREAM_KEY", "")
    if key:
        return key
    key_file = os.getenv("FORGET_RELAY_UPSTREAM_KEY_FILE", "")
    if key_file and os.path.exists(os.path.expanduser(key_file)):
        return open(os.path.expanduser(key_file)).read().strip()
    raise HTTPException(status_code=503, detail="relay upstream key not configured")


def _valid_tokens() -> set[str]:
    """Dev: a comma-separated env list. Production swaps this for the
    account store the payment page writes into — same contract."""
    return {t.strip() for t in os.getenv("FORGET_RELAY_TOKENS", "").split(",") if t.strip()}


def _meter(token: str, prompt_tokens: int, completion_tokens: int) -> None:
    USAGE_DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(USAGE_DB) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS usage (
                token TEXT, at REAL, prompt_tokens INTEGER, completion_tokens INTEGER)"""
        )
        conn.execute(
            "INSERT INTO usage VALUES (?, ?, ?, ?)",
            (token, time.time(), prompt_tokens, completion_tokens),
        )


@app.get("/ready")
def ready() -> dict[str, Any]:
    return {"service": "forget-cloud-relay", "upstream_model": UPSTREAM_MODEL}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Any:
    auth = request.headers.get("authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    if not token or token not in _valid_tokens():
        raise HTTPException(status_code=401, detail="unknown forget cloud token — see forget.sh/cloud")

    body = json.loads(await request.body())
    # The client names a gear-model alias; the relay pins the certified model.
    body["model"] = UPSTREAM_MODEL

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
    _meter(token, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0))
    return payload
