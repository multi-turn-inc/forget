#!/usr/bin/env python3
"""Adversarial live smoke for the authenticated team-ledger contract.

Reads per-agent keys from ~/.forget/keys without printing them. Run ``create``
once, restart the server, then run ``verify`` to prove persistence and replay.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PRINCIPALS = ("claude-exec", "gpt-live", "selfharness")
QUESTION_KEY = "live-ledger-auth-question-v3"
ANSWER_KEY = "live-ledger-auth-answer-v3"


def _key(keys_dir: Path, principal: str) -> str:
    value = (keys_dir / f"{principal}.key").read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"empty key for {principal}")
    return value


def _request(
    url: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def _rpc(
    base_url: str,
    keys_dir: Path,
    principal: str | None,
    method: str,
    params: dict[str, Any],
    *,
    query: str = "",
) -> tuple[int, dict[str, Any]]:
    token = _key(keys_dir, principal) if principal else None
    return _request(
        f"{base_url}/mcp/forget/http/junghunkim{query}",
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        token=token,
    )


def _tool(
    base_url: str,
    keys_dir: Path,
    principal: str | None,
    name: str,
    arguments: dict[str, Any],
) -> tuple[int, dict[str, Any], dict[str, Any] | None]:
    status, rpc = _rpc(
        base_url,
        keys_dir,
        principal,
        "tools/call",
        {"name": name, "arguments": arguments},
    )
    content = (rpc.get("result") or {}).get("content") or []
    text = next((part.get("text") for part in content if part.get("type") == "text"), None)
    decoded = json.loads(text) if isinstance(text, str) else None
    return status, rpc, decoded


def _assert_schema(base_url: str, keys_dir: Path) -> None:
    for principal in PRINCIPALS:
        status, rpc = _rpc(base_url, keys_dir, principal, "tools/list", {})
        assert status == 200 and "error" not in rpc
        tools = rpc["result"]["tools"]
        schema = next(tool for tool in tools if tool["name"] == "team_note")["inputSchema"]
        assert "author" not in schema.get("properties", {})
        _, read_rpc, read = _tool(base_url, keys_dir, principal, "team_read", {"limit": 1})
        assert "error" not in read_rpc and read and read["viewer"] == principal


def _question(base_url: str, keys_dir: Path) -> dict[str, Any]:
    _, rpc, result = _tool(
        base_url,
        keys_dir,
        "claude-exec",
        "team_note",
        {
            "kind": "question",
            "text": "live credential-bound cross-agent receipt",
            "addressed_to": "gpt-live",
            "idempotency_key": QUESTION_KEY,
        },
    )
    assert "error" not in rpc and result
    return result["item"]


def _answer(base_url: str, keys_dir: Path, question_id: str) -> dict[str, Any]:
    _, rpc, result = _tool(
        base_url,
        keys_dir,
        "gpt-live",
        "team_note",
        {
            "kind": "decision",
            "text": "authenticated cross-agent receipt accepted",
            "reply_to": question_id,
            "addressed_to": "claude-exec",
            "idempotency_key": ANSWER_KEY,
        },
    )
    assert "error" not in rpc and result
    return result["item"]


def create(base_url: str, keys_dir: Path) -> dict[str, Any]:
    _assert_schema(base_url, keys_dir)
    question = _question(base_url, keys_dir)

    _, _, open_items = _tool(
        base_url,
        keys_dir,
        "gpt-live",
        "team_read",
        {"open_only": True, "addressed_to": "gpt-live"},
    )
    assert any(item["id"] == question["id"] for item in open_items["items"])

    _, wrong_rpc, _ = _tool(
        base_url,
        keys_dir,
        "selfharness",
        "team_note",
        {"kind": "decision", "text": "wrong closer", "reply_to": question["id"]},
    )
    assert "error" in wrong_rpc and "addressed principal" in wrong_rpc["error"]["message"]

    answer = _answer(base_url, keys_dir, question["id"])
    _, _, ledger = _tool(base_url, keys_dir, "claude-exec", "team_read", {"limit": 100})
    closed = next(item for item in ledger["items"] if item["id"] == question["id"])
    assert closed["status"] == "answered" and closed["closed_by"] == answer["id"]

    _, replay_rpc, replay = _tool(
        base_url,
        keys_dir,
        "gpt-live",
        "team_note",
        {
            "kind": "decision",
            "text": "authenticated cross-agent receipt accepted",
            "reply_to": question["id"],
            "addressed_to": "claude-exec",
            "idempotency_key": ANSWER_KEY,
        },
    )
    assert "error" not in replay_rpc and replay["idempotent_replay"] is True

    _, conflict_rpc, _ = _tool(
        base_url,
        keys_dir,
        "gpt-live",
        "team_note",
        {"kind": "decision", "text": "changed", "idempotency_key": ANSWER_KEY},
    )
    assert "error" in conflict_rpc and "different payload" in conflict_rpc["error"]["message"]

    _, anonymous_rpc, _ = _tool(base_url, keys_dir, None, "team_read", {})
    assert "error" in anonymous_rpc
    spoof_status, _ = _rpc(
        base_url,
        keys_dir,
        "gpt-live",
        "tools/list",
        {},
        query="?principal=claude-exec",
    )
    assert spoof_status == 403
    query_secret_status, _ = _rpc(
        base_url,
        keys_dir,
        "gpt-live",
        "tools/list",
        {},
        query="?ptoken=forbidden",
    )
    assert query_secret_status == 400

    raw_status, _ = _request(
        f"{base_url}/v1/memories/",
        {"text": "raw bypass", "app_id": "forget-dev", "agent_id": "gpt-live"},
        token=_key(keys_dir, "gpt-live"),
    )
    assert raw_status == 403
    return {
        "phase": "create",
        "principals": list(PRINCIPALS),
        "question_id": question["id"],
        "answer_id": answer["id"],
        "status": closed["status"],
        "spoof_query_http": spoof_status,
        "query_secret_http": query_secret_status,
        "raw_bypass_http": raw_status,
        "secrets_printed": False,
    }


def verify(base_url: str, keys_dir: Path) -> dict[str, Any]:
    _assert_schema(base_url, keys_dir)
    question = _question(base_url, keys_dir)
    answer = _answer(base_url, keys_dir, question["id"])
    _, _, ledger = _tool(base_url, keys_dir, "selfharness", "team_read", {"limit": 100})
    closed = next(item for item in ledger["items"] if item["id"] == question["id"])
    assert closed["status"] == "answered" and closed["closed_by"] == answer["id"]
    return {
        "phase": "verify-after-restart",
        "question_id": question["id"],
        "answer_id": answer["id"],
        "status": closed["status"],
        "question_replayed": True,
        "answer_replayed": True,
        "secrets_printed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("create", "verify"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--keys-dir", type=Path, default=Path.home() / ".forget" / "keys")
    args = parser.parse_args()
    result = create(args.base_url.rstrip("/"), args.keys_dir) if args.phase == "create" else verify(
        args.base_url.rstrip("/"), args.keys_dir
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
