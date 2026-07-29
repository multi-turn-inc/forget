"""MCP argument contract: aliases work, unknown arguments warn instead of vanishing.

Regression guard for the 2026-07-29 dogfooding finding: search_memories
declared only top_k, and a client passing limit=3 (the OpenMemory-style name)
got it silently dropped — the call "succeeded" with the default 10 results.
Worse, mcp._validate_search_params already validated limit as if it were
top_k, so the value was type-checked and then thrown away.

Contract now: limit is a real alias of top_k for search_memories (top_k wins
when both are given), and any argument neither declared in a tool's
inputSchema nor in the known-alias allowlist earns an explicit warning block
in the result instead of silence.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from forget import db as app_db
from forget.db import init_db
from forget.mcp import TOOLS, _EXTRA_ACCEPTED_ARGS, _unknown_args_warning, call_tool
from forget.store import add_memories

_DB_COUNTER = 0


def _fresh_db() -> None:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-mcp-arg-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()


def _seed(user_id: str, count: int = 4) -> None:
    for index in range(count):
        add_memories(
            {
                "messages": [{"role": "user", "content": f"결제 정책 메모 {index}: Paddle을 씁니다"}],
                "user_id": user_id,
                "infer": False,
            }
        )


def _search_results(arguments: dict) -> list[dict]:
    result = call_tool("search_memories", arguments, None)
    return json.loads(result["content"][0]["text"])["results"]


def test_search_memories_accepts_limit_as_top_k_alias(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    _seed("alias-user")
    results = _search_results({"query": "결제 Paddle", "user_id": "alias-user", "limit": 1})
    assert len(results) == 1, "limit must cap results exactly like top_k"


def test_search_memories_top_k_wins_over_limit(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    _seed("precedence-user")
    results = _search_results({"query": "결제 Paddle", "user_id": "precedence-user", "top_k": 2, "limit": 1})
    assert len(results) == 2, "explicit top_k must take precedence over the limit alias"


def test_search_memories_declares_limit_in_schema() -> None:
    schema = next(tool for tool in TOOLS if tool["name"] == "search_memories")["inputSchema"]
    assert "limit" in schema["properties"], "the accepted alias must be advertised, not folklore"


def test_unknown_argument_appends_warning_block(monkeypatch) -> None:
    """Non-search tools keep the warning path; search tools now reject (#29).

    Superseded for search: field report showed callers never see appended
    warnings, so search_memories raises 400 instead (see
    test_search_rejects_unknown_top_level_argument).
    """
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    result = call_tool(
        "add_memory",
        {"text": "warning path probe", "user_id": "warn-user", "max_results": 2},
        None,
    )
    warnings = [block["text"] for block in result["content"][1:] if block.get("type") == "text"]
    assert any("max_results" in text and "unknown argument" in text for text in warnings), (
        f"an ignored argument must be named in a warning block, got: {result['content']}"
    )


def test_known_arguments_do_not_warn(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    _seed("clean-user")
    result = call_tool(
        "search_memories",
        {"query": "결제 Paddle", "user_id": "clean-user", "limit": 2, "threshold": 0, "rerank": False},
        None,
    )
    assert len(result["content"]) == 1, f"no warning expected for supported args: {result['content']}"


def test_unknown_args_warning_suggests_close_match() -> None:
    warning = _unknown_args_warning("search_memories", {"query": "q", "topk": 3})
    assert warning is not None and "topk" in warning and "top_k" in warning


def test_supported_undeclared_aliases_do_not_warn() -> None:
    # Handlers accept these without declaring them; the allowlist must keep
    # the warning honest (a warning on a working argument trains people to
    # ignore warnings).
    assert _unknown_args_warning("assemble_context", {"query": "q", "limit": 5, "budget": 400}) is None
    assert _unknown_args_warning("search_memory", {"query": "q", "top_k": 5}) is None
    assert _unknown_args_warning("get_task_state", {"as_of": "2026-07-01T00:00:00Z"}) is None


def test_extra_accepted_args_only_name_real_tools() -> None:
    tool_names = {str(tool["name"]) for tool in TOOLS}
    unknown_tools = set(_EXTRA_ACCEPTED_ARGS) - tool_names
    assert not unknown_tools, f"allowlist entries for nonexistent tools: {sorted(unknown_tools)}"


def test_search_rejects_unknown_top_level_argument():
    """Issue #29: unknown top-level args must fail loudly, not warn quietly."""
    import pytest
    from fastapi import HTTPException
    from forget import mcp

    with pytest.raises(HTTPException) as exc:
        mcp.call_tool("search_memories", {"query": "x", "definitely_unknown_parameter": 1})
    assert exc.value.status_code == 400
    assert "definitely_unknown_parameter" in str(exc.value.detail)


def test_search_memory_rejects_unknown_top_level_argument():
    import pytest
    from fastapi import HTTPException
    from forget import mcp

    with pytest.raises(HTTPException) as exc:
        mcp.call_tool(
            "search_memory",
            {"query": "x", "user_id": "u", "app_id": "a", "bogus_key": True},
        )
    assert exc.value.status_code == 400
    assert "bogus_key" in str(exc.value.detail)


def test_search_still_accepts_limit_alias_strictly():
    from forget import mcp

    result = mcp.call_tool("search_memories", {"query": "x", "limit": 1})
    assert isinstance(result.get("content"), list)
