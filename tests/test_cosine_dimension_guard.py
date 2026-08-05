"""Cross-dimension vectors must be rejected, not silently truncated.

Cycle 43 measured the live store scoring 384d queries against legacy 128d
rows via min(len) truncation: 600/600 pairs cleared the 0.45 recall gate
(min 0.4658) because truncation noise lands near 0.5 on the (cos+1)/2
scale. P11 treatment 3: a dimension mismatch carries no comparable signal
and scores 0.0 — in both copies of the function (memory_engine and the
vector_adapters in-memory scan fallback).
"""
from __future__ import annotations

from forget.memory_engine import cosine_similarity, deterministic_embedding
from forget.vector_adapters import _cosine_similarity

RECALL_GATE = 0.45


def test_dimension_mismatch_is_rejected_below_gate():
    # The exact shape c43 caught live: 384d query vs 128d legacy row.
    query = deterministic_embedding("결제 실패 로그를 다시 보여줘", dimensions=384)
    legacy = deterministic_embedding("payment failure logs", dimensions=128)
    score = cosine_similarity(query, legacy)
    assert score == 0.0
    assert score < RECALL_GATE


def test_same_dimension_scoring_is_unchanged():
    left = deterministic_embedding("payment failed with an error", dimensions=128)
    right = deterministic_embedding("payment failure logs", dimensions=128)
    assert cosine_similarity(left, left) == 1.0
    assert cosine_similarity(left, right) > cosine_similarity(
        left, deterministic_embedding("완전히 무관한 정원 가꾸기 이야기", dimensions=128)
    )


def test_empty_vectors_still_score_zero():
    vector = deterministic_embedding("anything", dimensions=128)
    assert cosine_similarity([], vector) == 0.0
    assert cosine_similarity(vector, []) == 0.0


def test_adapter_copy_rejects_mismatch_and_keeps_same_dim():
    # vector_adapters._cosine_similarity had the same defect via zip()
    # truncation; it returns raw cosine, so identity == 1.0 stays intact.
    assert _cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0]) == 0.0
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
