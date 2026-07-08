"""Korean (CJK) tokenization, embedding, and end-to-end search ranking.

Regression guard for the 2026-07-04 dogfooding finding: the ASCII-only
tokenizer produced zero tokens for Korean text, collapsing every Korean
query into a zero vector and flat, meaningless search scores.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from forget import db as app_db
from forget.db import init_db
from forget.server import app
from forget.memory_engine import cosine_similarity, deterministic_embedding
from forget.utils import tokenize

_DB_COUNTER = 0


def _client() -> TestClient:
    global _DB_COUNTER
    _DB_COUNTER += 1
    path = Path(f"/tmp/mem1-korean-test-{os.getpid()}-{_DB_COUNTER}.sqlite3")
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    return TestClient(app, base_url="http://testserver")


def test_tokenize_korean_produces_bigrams_and_keeps_english_unchanged() -> None:
    assert tokenize("I deploy only from the main branch") == ["deploy", "only", "main", "branch"]
    korean = tokenize("결제는 무엇으로 처리하나요")
    assert "결제" in korean and len(korean) >= 4
    mixed = tokenize("배포는 main 브랜치에서만 합니다")
    assert "main" in mixed and "배포" in mixed


def test_korean_embeddings_are_nonzero_and_discriminative() -> None:
    query = deterministic_embedding("결제 수단이 뭐야")
    assert any(value != 0 for value in query)
    payment = deterministic_embedding("결제는 Paddle을 씁니다. Stripe가 아닙니다.")
    database = deterministic_embedding("프로덕션 DB는 4090 호스트의 Postgres 16입니다.")
    assert cosine_similarity(query, payment) > cosine_similarity(query, database)


def test_korean_extraction_normalizes_first_person_and_merges_fragments() -> None:
    from forget.memory_engine import extract_memories

    merged = extract_memories([{"role": "user", "content": "결제는 Paddle을 씁니다. Stripe가 아닙니다."}])
    assert merged == ["결제는 Paddle을 씁니다. Stripe가 아닙니다."], merged

    normalized = extract_memories(
        [{"role": "user", "content": "저는 배포를 main 브랜치에서만 합니다. 핫픽스는 릴리스 브랜치를 씁니다."}]
    )
    assert normalized[0].startswith("사용자는 배포를"), normalized
    assert all(not fact.startswith("User said:") for fact in normalized), normalized

    possessive = extract_memories([{"role": "user", "content": "제 이름은 정훈입니다."}])
    assert possessive == ["사용자의 이름은 정훈입니다."], possessive

    # English behavior is byte-for-byte unchanged.
    english = extract_memories([{"role": "user", "content": "my name is Junghun and I prefer TypeScript"}])
    assert english == ["User's name is Junghun", "User prefers TypeScript"], english


def test_korean_search_ranks_relevant_memory_first(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    c = _client()
    facts = [
        "결제는 Paddle을 사용합니다. Stripe가 아닙니다.",
        "프로덕션 데이터베이스는 4090 호스트의 Postgres 16입니다.",
        "배포는 main 브랜치에서만 합니다. 핫픽스는 릴리스 브랜치를 씁니다.",
    ]
    for fact in facts:
        response = c.post(
            "/v1/memories/",
            json={"messages": [{"role": "user", "content": fact}], "user_id": "ko-tester"},
        )
        assert response.status_code == 200

    search = c.post(
        "/v3/memories/search/",
        json={"query": "결제 수단이 뭐야", "filters": {"user_id": "ko-tester"}, "top_k": 3},
    )
    assert search.status_code == 200
    body = search.json()
    items = body if isinstance(body, list) else (body.get("results") or body.get("memories") or [])
    assert items, "korean search returned no results"
    top = items[0]
    assert "결제" in str(top.get("memory") or ""), f"expected payment memory first, got: {top.get('memory')}"
    scores = [round(float(item.get("score") or 0.0), 4) for item in items]
    assert len(set(scores)) > 1, f"scores are flat: {scores}"


def test_add_memories_sanitize_rejects_junk_and_dedupes(monkeypatch) -> None:
    monkeypatch.delenv("MEM1_REQUIRE_AUTH", raising=False)
    from forget.store import add_memories, get_memories

    c = _client()
    # sanitize off (default): junk is stored — contract preserved.
    add_memories({"messages": [{"role": "user", "content": 'x with "payload": {}'}], "user_id": "s-off"})
    assert len(get_memories({"user_id": "s-off"}).get("results", [])) == 1

    # sanitize on: junk rejected, clean fact kept.
    result = add_memories(
        {
            "messages": [
                {"role": "user", "content": 'User said: {"type":"event_msg","payload":{}}'},
                {"role": "user", "content": "저는 결제에 Paddle을 씁니다."},
            ],
            "user_id": "s-on",
            "sanitize": True,
        }
    )
    assert result["skipped"]["junk_total"] >= 1
    kept = get_memories({"user_id": "s-on"}).get("results", [])
    assert len(kept) == 1 and "Paddle" in kept[0]["memory"]

    # dedup: identical fact twice with sanitize stores once.
    add_memories({"messages": [{"role": "user", "content": "저는 배포를 main에서만 합니다."}], "user_id": "s-dup", "sanitize": True})
    second = add_memories({"messages": [{"role": "user", "content": "저는 배포를 main에서만 합니다."}], "user_id": "s-dup", "sanitize": True})
    assert second["skipped"]["duplicate"] == 1
    assert len(get_memories({"user_id": "s-dup"}).get("results", [])) == 1
