"""gate_audit.aggregate_accounting — P7(b) 판정 도구의 합산·비율·반증력 검증.

스크립트는 research/devloop/scripts/에 살지만 판정 도구이므로 회귀 감시 대상이다.
"""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "research" / "devloop" / "scripts" / "gate_audit.py"
spec = importlib.util.spec_from_file_location("gate_audit", SCRIPT)
gate_audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate_audit)


def _event(event_id: str, accounting: dict | None) -> dict:
    metadata = {"accounting": accounting} if accounting is not None else {}
    return {"id": event_id, "event_type": "ADD", "metadata": metadata}


CLEAN = {
    # 보존식 성립: raw 6 = extracted 5 + batch_dedup 1; out 4 = 5 - filtered 1;
    # 4 - scope 1 - sanitize 1 = kept 2; pairs 3 = created 2 + dup 1
    "messages_in": 4, "empty_messages": 1, "ack_messages_dropped": 1,
    "sentences_seen": 8, "fragments_dropped": 2, "gate_dropped": 2,
    "facts_raw": 6, "facts_extracted": 5, "batch_deduped": 1,
    "instruction_filtered": 1, "facts_out": 4,
    "scope_deduped": 1, "sanitize_dropped": 1, "records_kept": 2,
    "fact_scope_pairs": 3, "duplicate_skipped": 1, "memories_created": 2,
}

BROKEN = {
    # storage 보존식 위반: pairs 5 != created 2 + dup 1
    "facts_out": 3, "records_kept": 3,
    "fact_scope_pairs": 5, "duplicate_skipped": 1, "memories_created": 2,
    "provider_extractions": 1,  # 문장 단계 검사는 건너뛰고 저장식만
}


def test_totals_coverage_and_ratios():
    report = gate_audit.aggregate_accounting(
        [_event("a", CLEAN), _event("b", CLEAN), _event("c", None)]
    )
    assert report["add_events"] == 3
    assert report["events_with_accounting"] == 2
    assert report["coverage"] == round(2 / 3, 4)
    assert report["totals"]["memories_created"] == 4
    assert report["totals"]["gate_dropped"] == 4
    assert report["counted_refusals"] == 2 * (2 + 1 + 1)
    ratios = report["stage_ratios"]
    assert ratios["gate_refusal"] == round(4 / 16, 4)
    assert ratios["message_drop"] == round(4 / 8, 4)
    assert ratios["retention"] == round(4 / 6, 4)
    assert report["identity_violations_recomputed"] == []


def test_violation_is_recomputed_not_trusted_from_stamp():
    # 이벤트에 identity_violations 스탬프가 없어도 재계산으로 잡는다 — 반증력.
    report = gate_audit.aggregate_accounting([_event("bad", BROKEN)])
    recomputed = report["identity_violations_recomputed"]
    assert len(recomputed) == 1 and recomputed[0]["event"] == "bad"
    assert any("storage" in v for v in recomputed[0]["violations"])
    assert report["identity_violations_stamped_events"] == []


def test_empty_window_yields_null_ratios():
    report = gate_audit.aggregate_accounting([])
    assert report["coverage"] is None
    assert all(v is None for v in report["stage_ratios"].values())
