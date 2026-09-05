"""`reason_recorded` — 파트 X의 «사유 기재» 판정 (c171 신설, 관측 103 처치 (i)).

왜 이 파일이 있는가. 파트 X는 12사이클 동안 프로브 위반 4건을 **옳게** 인쇄했다.
규약은 *"당 사이클 산출이면 처치하고, 과거분이면 사유를 원장에 적을 것"*이었고,
c167·c169는 처치도 사유도 없이 이월했다(원장 직독, audit-170 표).

P45는 c163에 이미 판정됐다 — *"계기는 5사이클 내내 옳게 인쇄했고 깨진 것은 인쇄를
읽는 손이었다"*. 그래서 이것은 반증이 아니라 **판정 후 재발**이며, c163이 명명한
그 병이 판정 6사이클 뒤에 두 번 다시 났다. 인쇄는 상태를 알리지만 **행동을 요구하지
않는다**. 이 처치가 요구를 문면에서 계기로 옮긴다.

기울기의 방향을 **선언한다.** 어휘 밖 표현으로 사유를 적으면 이 눈은 «미기재»라고
과하게 고발한다. 관측 76·93·104가 잡은 병이 하나같이 «루프에 유리한 거짓 음성»이었으므로,
자[尺]를 만들 때 기울기를 루프에 **불리한** 쪽으로 골랐다. 그 선택을 테스트가 고정한다.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_reason", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


def test_a_row_that_mentions_part_x_counts_as_recorded():
    row = {"cycle": 168, "work": "…파트 X 위반 4건은 전부 과거분이므로 이월한다(사유: …)"}
    assert c48.reason_recorded(row) == ["파트 X"]


def test_a_row_that_names_the_pattern_kind_counts_as_recorded():
    """처치 어휘가 아니라 **위반 종류**로 적어도 기재로 본다 — c166이 그렇게 적었다."""
    row = {"cycle": 166, "tests": "getattr-기본값 1건은 c149 산출이라 …"}
    assert c48.reason_recorded(row) == ["getattr-기본값"]


def test_a_silent_row_is_detected_as_missing():
    """c167·c169의 모양 — 위반을 인쇄받고 아무 말도 하지 않은 행."""
    row = {"cycle": 167, "work": "오늘은 서수 계열을 고쳤다", "tests": "521 passed"}
    assert c48.reason_recorded(row) == []


def test_non_string_fields_do_not_break_the_scan():
    """원장 행에는 int·dict·null이 섞인다 — 스캔이 거기서 죽으면 눈이 멀고 침묵한다."""
    row = {"cycle": 170, "recall_hits": 2, "evidence": {"n": 1}, "work": "probe_guard 채택"}
    assert c48.reason_recorded(row) == ["probe_guard"]


def test_multiple_terms_are_reported_without_duplicates():
    row = {"cycle": 165, "work": "파트 X · probe_guard", "tests": "파트 X 재확인"}
    assert c48.reason_recorded(row) == ["파트 X", "probe_guard"]


def test_vocabulary_is_a_declared_hand_maintained_constant():
    """어휘가 상수로 살아야 인쇄할 수 있고, 인쇄해야 거짓 음성이 보인다(파트 P의 VOCAB 규율)."""
    assert isinstance(c48.VIOLATION_REASON_TERMS, tuple)
    assert len(c48.VIOLATION_REASON_TERMS) >= 5
    assert "파트 X" in c48.VIOLATION_REASON_TERMS


def test_the_false_negative_direction_is_over_accusation():
    """기울기 계약 — 어휘 밖 표현은 «미기재»로 고발된다. 관대한 쪽으로 기울면 처치가 죽는다."""
    row = {"cycle": 999, "work": "일회용 탐침의 폴백 4건은 오늘 손대지 않았다"}
    assert c48.reason_recorded(row) == [], (
        "어휘 밖 표현이 기재로 통과했다 — 루프에 유리한 거짓 음성 방향이다")


def test_real_ledger_reproduces_the_audit_finding_for_c167_and_c169():
    """실 원장 회귀 — audit-170이 손으로 만든 표(c167 없음 · c169 없음)를 계기가 재현한다.

    이 절의 값은 **독립 재현**이다: 감사는 별 계기(`tmp/c170_remaining_checks.py`)로
    같은 결론에 닿았고, 여기서 다른 코드가 같은 원장에서 같은 답을 낸다.
    """
    rows = {int(r["cycle"]): r for r in c48._ledger_rows()}
    for cyc in (166, 168, 170):
        assert cyc in rows and c48.reason_recorded(rows[cyc]), (
            f"c{cyc}는 감사 표에서 «언급 있음»이었다")
    for cyc in (167, 169):
        assert cyc in rows and c48.reason_recorded(rows[cyc]) == [], (
            f"c{cyc}는 감사 표에서 «없음»이었다 — 재현이 갈렸다")
