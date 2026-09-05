"""The vector score is max(0, cos), not the affine (cos+1)/2 (c72 / P23).

The affine rescale paid every pair a topic-free constant — 0.275 of the
final score after the 0.55 weight — so zero-signal rows cleared the 0.45
recall gate on the constant alone (c68 FPR=1.00). These tests pin the new
scale in both copies of the arithmetic: any reintroduction of an additive
constant, and any scalar/batch divergence, fails here.
"""
from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")

from forget.memory_engine import cosine_similarity, deterministic_embedding
from forget.store import _batch_cosine_scores


def _raw_cos(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    ln = math.sqrt(sum(v * v for v in left)) or 1.0
    rn = math.sqrt(sum(v * v for v in right)) or 1.0
    return dot / (ln * rn)


def test_orthogonal_pair_scores_zero_not_half():
    # On the affine scale this was exactly 0.5 — above the 0.45 recall gate.
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_negative_cosine_clamps_to_zero():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == 0.0


def test_identity_still_scores_one():
    vec = deterministic_embedding("payment failure logs", dimensions=128)
    assert cosine_similarity(vec, vec) == 1.0


def test_scalar_matches_raw_cosine_rounding():
    left = deterministic_embedding("payment failed with an error", dimensions=128)
    right = deterministic_embedding("payment failure logs", dimensions=128)
    expected = max(0.0, min(1.0, round(_raw_cos(left, right), 4)))
    assert cosine_similarity(left, right) == expected


def test_batch_path_is_bit_for_bit_scalar():
    # _batch_cosine_scores only engages at >= 64 candidates; build 80 so the
    # numpy path (not the scalar fallback) is what gets compared.
    query = deterministic_embedding("결제 실패 로그를 다시 보여줘", dimensions=128)
    candidates = []
    for i in range(80):
        emb = deterministic_embedding(f"memory row number {i}", dimensions=128)
        candidates.append({"id": f"m{i}", "_embedding": emb})
    batch = _batch_cosine_scores(query, candidates)
    assert len(batch) == 80
    for cand in candidates:
        assert batch[cand["id"]] == cosine_similarity(query, cand["_embedding"])
