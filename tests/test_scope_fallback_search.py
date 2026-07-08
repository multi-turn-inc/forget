"""Scope-fallback search: shared knowledge is findable, privacy is not.

2026-07-04 dogfood finding: deployment knowledge stored under
agent_id=enacta-eng was invisible to a user_id-scoped search in the same
project — scope fragmentation made stored knowledge unfindable. The
fallback blends shared (non-user) rows in at a discount, and must never
cross the user_id privacy boundary.
"""

from __future__ import annotations

import os
from pathlib import Path

from forget import db as app_db
from forget.db import init_db
from forget.store import add_memories, assemble_context, search_memories

_DB_COUNTER = 0


def _fresh_db() -> None:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-scope-fb-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()


def _seed() -> None:
    add_memories({"messages": [{"role": "user", "content": "배포는 main 브랜치에서만 합니다."}], "agent_id": "eng-agent"})
    add_memories({"messages": [{"role": "user", "content": "고양이 알레르기가 있습니다."}], "user_id": "someone-else"})
    add_memories({"messages": [{"role": "user", "content": "저는 어두운 테마를 선호합니다."}], "user_id": "me"})


def test_fallback_surfaces_shared_agent_knowledge_with_discount_and_tags(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("MEM1_SCOPE_FALLBACK_DEFAULT", raising=False)
    _fresh_db()
    _seed()

    off = search_memories({"query": "배포 브랜치", "filters": {"user_id": "me"}, "top_k": 5})["results"]
    assert all("배포" not in str(m.get("memory")) for m in off), "default off must stay strictly scoped"

    on = search_memories({"query": "배포 브랜치", "filters": {"user_id": "me"}, "top_k": 5, "scope_fallback": True})["results"]
    hit = next((m for m in on if "배포" in str(m.get("memory"))), None)
    assert hit, "shared agent knowledge must surface via fallback"
    assert hit["scope"] == "fallback" and hit["scope_source"] == "agent_id:eng-agent"


def test_fallback_never_leaks_another_users_memories(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    _fresh_db()
    _seed()
    on = search_memories({"query": "고양이 알레르기", "filters": {"user_id": "me"}, "top_k": 8, "scope_fallback": True})["results"]
    assert all("알레르기" not in str(m.get("memory")) for m in on), "another user's personal rows must never appear"


def test_env_default_enables_fallback_and_primary_outranks_equal_fallback(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    monkeypatch.setenv("MEM1_SCOPE_FALLBACK_DEFAULT", "true")
    _fresh_db()
    add_memories({"messages": [{"role": "user", "content": "결제는 Paddle을 씁니다."}], "user_id": "me"})
    add_memories({"messages": [{"role": "user", "content": "결제는 Paddle을 씁니다."}], "agent_id": "eng-agent"})
    results = search_memories({"query": "결제 수단", "filters": {"user_id": "me"}, "top_k": 4})["results"]
    assert results[0].get("scope") is None, "identical content: primary scope must rank first"
    fallback = next((m for m in results if m.get("scope") == "fallback"), None)
    assert fallback and fallback["score"] < results[0]["score"]


def test_assemble_context_passes_scope_fallback_through(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("MEM1_SCOPE_FALLBACK_DEFAULT", raising=False)
    _fresh_db()
    _seed()
    capsule = assemble_context({"query": "배포 브랜치", "filters": {"user_id": "me"}, "scope_fallback": True})
    assert any("배포" in str(m.get("memory")) for m in capsule.get("memories", [])), (
        "agent-scope knowledge must reach a user-scoped capsule when fallback is on"
    )
