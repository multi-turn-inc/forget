"""MCP filter scoping: explicit entities must not attract default app_id.

Regression guard for the 2026-07-04 dogfooding finding: calling
assemble_context over MCP with an explicit user_id silently injected the
default app_id ("codex") into the search filters, excluding every memory
stored without an app_id and returning an empty context capsule.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from forget import db as app_db
from forget.db import init_db
from forget.mcp import _mcp_scoped_filters, call_tool
from forget.store import add_memories

_DB_COUNTER = 0


def _fresh_db() -> None:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-mcp-scope-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()


def test_explicit_user_id_does_not_attract_default_app_id() -> None:
    assert _mcp_scoped_filters({"user_id": "u1"}, None) == {"user_id": "u1"}


def test_no_entity_falls_back_to_default_scope() -> None:
    scoped = _mcp_scoped_filters({}, None)
    assert scoped == {"user_id": "codex", "app_id": "codex"}


def test_client_context_is_treated_as_explicit_scope() -> None:
    scoped = _mcp_scoped_filters({"user_id": "u1"}, {"client_name": "cursor"})
    assert scoped == {"user_id": "u1", "app_id": "cursor"}


def test_explicit_filters_pass_through_untouched() -> None:
    scoped = _mcp_scoped_filters({"filters": {"user_id": "u2"}}, None)
    assert scoped == {"user_id": "u2"}


def test_assemble_context_over_mcp_uses_stored_memories(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    add_memories(
        {
            "messages": [
                {"role": "user", "content": "결제는 Paddle을 씁니다. Stripe가 아닙니다."},
                {"role": "user", "content": "저는 배포를 main 브랜치에서만 합니다."},
            ],
            "user_id": "ctx-tester",
        }
    )
    result = call_tool("assemble_context", {"query": "결제 정책", "user_id": "ctx-tester"}, None)
    inner = json.loads(result["content"][0]["text"])
    assert inner.get("budgeted_count", 0) >= 1, inner.get("budgeted_count")
    assert "Paddle" in (inner.get("context") or "")


def test_assemble_context_compact_shape(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    add_memories(
        {"messages": [{"role": "user", "content": "결제는 Paddle을 씁니다."}], "user_id": "compact-user"}
    )
    result = call_tool(
        "assemble_context",
        {"query": "결제", "user_id": "compact-user", "compact": True},
        None,
    )
    inner = json.loads(result["content"][0]["text"])
    assert set(inner.keys()) == {
        "context",
        "capsule_text",
        "memories",
        "budgeted_count",
        "omitted_count",
        "context_status",
        "next_actions",
        "context_trace_id",
        "hint",
    }
    assert inner["context_trace_id"], "trace id must survive compaction for outcome recording"
    assert inner["memories"] and set(inner["memories"][0].keys()) == {"id", "memory", "score"}
    # compact env default applies when args are silent
    monkeypatch.setenv("MEM1_MCP_COMPACT_CONTEXT", "true")
    silent = json.loads(
        call_tool("assemble_context", {"query": "결제", "user_id": "compact-user"}, None)["content"][0]["text"]
    )
    assert "working_memory" not in silent and silent.get("context_trace_id")
    # explicit debug overrides the env default back to the full capsule
    full = json.loads(
        call_tool("assemble_context", {"query": "결제", "user_id": "compact-user", "debug": True}, None)["content"][0]["text"]
    )
    assert "working_memory" in full
