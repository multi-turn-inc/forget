"""_claim_eval_matched 채점 규칙 고정.

2026-08-13 자기개선 세션 발견: 개수 기대값(expected_supported_count /
expected_unsupported_count)이 전부 일치해도 마지막 줄이 verification.valid를
요구해서, 음성 케이스(기각을 기대하는 항목)가 구조적으로 통과 불가능했다.
개수 기대값을 명시한 항목은 그 일치가 곧 판정이어야 한다.
"""
from forget.store import _claim_eval_matched


def _verification(valid: bool, supported: int, unsupported: int, status: str) -> dict:
    return {
        "valid": valid,
        "status": status,
        "supported_count": supported,
        "unsupported_count": unsupported,
    }


def test_negative_case_with_counts_matches():
    # 회귀 고정: 기각을 기대하는 항목이 개수 일치만으로 통과해야 한다.
    item = {"expected_supported_count": 0, "expected_unsupported_count": 1}
    verification = _verification(valid=False, supported=0, unsupported=1, status="UNSUPPORTED")
    assert _claim_eval_matched(item, verification) is True


def test_count_mismatch_fails():
    item = {"expected_supported_count": 1, "expected_unsupported_count": 0}
    verification = _verification(valid=False, supported=0, unsupported=1, status="UNSUPPORTED")
    assert _claim_eval_matched(item, verification) is False


def test_positive_case_with_counts_matches():
    item = {"expected_supported_count": 1, "expected_unsupported_count": 0}
    verification = _verification(valid=True, supported=1, unsupported=0, status="VERIFIED")
    assert _claim_eval_matched(item, verification) is True


def test_no_expectations_falls_back_to_valid():
    assert _claim_eval_matched({}, _verification(True, 1, 0, "VERIFIED")) is True
    assert _claim_eval_matched({}, _verification(False, 0, 1, "UNSUPPORTED")) is False


def test_expected_status_still_short_circuits():
    item = {"expected_status": "UNSUPPORTED"}
    verification = _verification(valid=False, supported=0, unsupported=1, status="UNSUPPORTED")
    assert _claim_eval_matched(item, verification) is True


def test_expected_valid_still_short_circuits():
    item = {"expected_valid": False}
    verification = _verification(valid=False, supported=0, unsupported=1, status="UNSUPPORTED")
    assert _claim_eval_matched(item, verification) is True
