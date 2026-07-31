"""Default MCP scope: the unscoped endpoint must not invent a ghost owner.

Regression guard for the 2026-07-29 cold-install audit, defect 1: add_memory
over the scope-less /mcp endpoint stored everything under a hardcoded
user_id='codex' × app_id='codex' scope regardless of which client connected,
silently voiding user × app isolation on the golden path. The fallback owner
is now the OS account name, no app_id is invented, and the response says
out loud when the fallback was used.
"""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException

from forget import db as app_db
from forget import mcp as mcp_module
from forget.db import init_db
from forget.mcp import _default_scope_user_id, call_tool
from forget.store import get_event, get_memory

_DB_COUNTER = 0


def _fresh_db() -> None:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-mcp-default-scope-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()


def _add_memory(args: dict, context: dict | None) -> tuple[dict, list[str]]:
    """Run add_memory and return (first stored memory, warning texts)."""
    result = call_tool("add_memory", args, context)
    contents = result["content"]
    payload = json.loads(contents[0]["text"])
    event = get_event(payload["event_id"])
    created = event.get("results", [])
    assert created, f"add_memory stored nothing: {event}"
    memory = get_memory(created[0]["id"])
    warnings = [item["text"] for item in contents[1:] if item.get("type") == "text"]
    return memory, warnings


def test_default_user_id_is_the_os_user(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_MCP_DEFAULT_USER_ID", raising=False)
    assert _default_scope_user_id() == (getpass.getuser().strip() or "local")


def test_default_user_id_env_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_MCP_DEFAULT_USER_ID", "  team-shared ")
    assert _default_scope_user_id() == "team-shared"


def test_hardcoded_codex_default_is_gone() -> None:
    assert mcp_module.MCP_DEFAULT_USER_ID != "codex" or getpass.getuser() == "codex"
    assert mcp_module.MCP_DEFAULT_APP_ID != "codex"


def test_unscoped_add_memory_lands_in_os_user_scope_with_warning(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    memory, warnings = _add_memory(
        {"text": "결제는 Paddle을 씁니다. Stripe가 아닙니다.", "infer": False}, None
    )
    assert memory["user_id"] == mcp_module.MCP_DEFAULT_USER_ID
    assert memory["user_id"] not in ("", "codex")
    assert not memory.get("app_id"), "no client was named; an app pool must not be invented"
    scope_notes = [text for text in warnings if "default scope" in text]
    assert scope_notes, f"fallback-scoped write must warn in-band: {warnings}"
    assert mcp_module.MCP_DEFAULT_USER_ID in scope_notes[0]
    assert "/mcp/{app_id}/http/{user_id}" in scope_notes[0]


def test_explicit_user_id_write_does_not_warn(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    memory, warnings = _add_memory(
        {"text": "배포는 main 브랜치에서만 합니다.", "infer": False, "user_id": "explicit-user"}, None
    )
    assert memory["user_id"] == "explicit-user"
    assert not any("default scope" in text for text in warnings), warnings


def test_scoped_endpoint_context_write_does_not_warn(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    memory, warnings = _add_memory(
        {"text": "테스트 러너는 pytest입니다.", "infer": False},
        {"user_id": "route-user", "client_name": "route-app"},
    )
    assert memory["user_id"] == "route-user"
    assert memory["app_id"] == "route-app"
    assert not any("default scope" in text for text in warnings), warnings


def test_openmemory_add_memories_requires_client_identity(monkeypatch) -> None:
    # The OpenMemory-compat tools require an app identity; with the codex
    # fallback gone, an unidentified client gets an explicit 400 instead of
    # a silent write into a ghost app pool.
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    monkeypatch.setattr(mcp_module, "MCP_DEFAULT_APP_ID", "")
    _fresh_db()
    with pytest.raises(HTTPException) as excinfo:
        call_tool("add_memories", {"text": "unscoped write"}, None)
    assert excinfo.value.status_code == 400
    assert "client_name or app_id" in str(excinfo.value.detail)
