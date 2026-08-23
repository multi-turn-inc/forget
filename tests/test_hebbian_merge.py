"""Hebbian merge: a restated fact reinforces its original instead of appending.

The dangerous half of this feature is what it must NOT merge. Each blocking
case below is a real incident from 2026-08-23 dogfooding: the naive trigram
merge swallowed a staging→production contradiction (supersede territory) and
a plan→completion pair (the trust system's core distinction). Merge only what
is unmistakably the same statement said again.
"""
import os
import uuid

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-hebbian.sqlite3")

from forget import store  # noqa: E402
from forget.db import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "hebbian.sqlite3"
    monkeypatch.setenv("MEM1_DB_PATH", str(db))
    init_db()
    yield


def _add(text: str, user: str) -> dict:
    return store.add_memories(
        {"messages": [{"role": "user", "content": text}], "user_id": user, "infer": False}
    )


def _counts(result: dict) -> tuple[int, int]:
    acc = result["accounting"]
    return acc["memories_created"], acc.get("hebbian_merged", 0)


def test_pure_restatement_merges_and_reinforces():
    user = f"heb-{uuid.uuid4().hex[:8]}"
    first = _add("정훈은 매일 아침 드립 커피를 내려 마신다.", user)
    assert _counts(first) == (1, 0)
    second = _add("정훈은 매일 아침 드립커피를 내려 마신다", user)
    assert _counts(second) == (0, 1)
    merged = second["merged"][0]
    assert merged["evidence_count"] == 2


def test_content_word_replacement_never_merges():
    # staging → production is a contradiction pair: supersede's job, not merge's.
    user = f"heb-{uuid.uuid4().hex[:8]}"
    _add("the deployment target is staging", user)
    result = _add("the deployment target is production", user)
    assert _counts(result) == (1, 0)


def test_differing_numbers_never_merge():
    user = f"heb-{uuid.uuid4().hex[:8]}"
    _add("user's laptop is a 2019 intel macbook pro", user)
    result = _add("user's laptop is an m4 macbook pro now", user)
    assert _counts(result) == (1, 0)


def test_plan_and_completion_never_merge():
    # Bidirectional containment: the differing word ("todo") sits in the longer
    # text, which the one-directional guard missed.
    user = f"heb-{uuid.uuid4().hex[:8]}"
    _add("todo: publish the verified memory blog post", user)
    result = _add("the verified memory blog post is published", user)
    assert _counts(result) == (1, 0)


def test_negation_flip_never_merges():
    user = f"heb-{uuid.uuid4().hex[:8]}"
    _add("정훈은 아침에 커피를 마신다", user)
    result = _add("정훈은 아침에 커피를 마시지 않는다", user)
    assert _counts(result) == (1, 0)


def test_merge_is_auditable():
    # Forgetting a duplicate is still forgetting: history row + gate log entry.
    user = f"heb-{uuid.uuid4().hex[:8]}"
    _add("하나의 몸은 언제든 갈아끼울 수 있다", user)
    second = _add("하나의 몸은 언제든 갈아 끼울 수 있다", user)
    assert _counts(second) == (0, 1)
    memory_id = second["merged"][0]["id"]
    history = store.memory_history(memory_id)
    assert any(row.get("event") == "UPDATE" for row in history)


def test_opt_out_flag_appends():
    user = f"heb-{uuid.uuid4().hex[:8]}"
    _add("정훈은 매일 아침 드립 커피를 내려 마신다.", user)
    result = store.add_memories(
        {
            "messages": [{"role": "user", "content": "정훈은 매일 아침 드립커피를 내려 마신다"}],
            "user_id": user,
            "infer": False,
            "hebbian": False,
        }
    )
    assert _counts(result) == (1, 0)
