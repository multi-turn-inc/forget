"""㉼ — c48 첫 줄 N의 crash-orphan 3자 대조 눈 (c264 실측 · c265 상신 · c267 집행).

왜 이 파일이 있는가. `N = max(cycle)+1`은 직전 세션이 수확 중 죽으며 남긴 미커밋
orphan 원장 행을 구별 없이 센다 — c264에서 죽은 세션의 c264 행이 착지·커밋 실패했고,
c48 첫 줄은 N=265 회고를 인쇄했다(손 재판정 = c264 일반). 같은 스크립트의 파트 S(P53)가
사망을 탐지하는데 첫 줄 N 계산이 그 증거를 소비하지 않았다. ㉼의 처치는 3자 대조
(ledger max · git HEAD `loop(cycle N)` · task_state 세대)로 갈림을 **경고로만** 바꾼다 —
자동 차감은 금물이다(오판 시 원장 이중 기재 위험 — 판정은 손 몫).

전 표본이 합성 픽스처다 — 실원장 값을 상수로 박으면 다음 수확이 테스트를 붉힌다
(관측 100)거나 결함을 기대 상태로 잠근다(관측 106).

계약:
① 3자 일치 → 의심 없음, «3자 일치» 인쇄.
② c264 지문(ledger가 HEAD·task_state보다 앞섬) → 의심 + «crash-orphan 의심 — N 재판정
   필요» 경고 + 갈린 축의 이름·값 병기.
③ None 축은 판정 불가다 — 일치로도 갈림으로도 계상하지 않는다(«판정 불가는 일치가
   아니다» 문면 의무).
④ 자동 차감 금물 — 경고문 자신이 그 사실을 말하고, 번호 산술(cycle_number_and_mode)은
   orphan 행이 있어도 max+1 그대로다(눈은 산술을 만지지 않는다).
⑤ HEAD 파서: `loop(cycle N)` 제목만 N을 내고, 비-loop 제목은 None(관측 126 사각 명시).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_orphan", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

WARN = "crash-orphan 의심 — N 재판정 필요"


def test_contract_1_all_three_agree_is_quiet():
    suspect, lines = c48.crash_orphan_verdict(266, 266, 266)
    text = "\n".join(lines)
    assert suspect is False
    assert "3자 일치" in text
    assert WARN not in text


def test_contract_2_c264_signature_raises_warning_with_axes():
    # 죽은 세션의 orphan 행: ledger max=264 · HEAD=loop(cycle 263) · task_state=263.
    suspect, lines = c48.crash_orphan_verdict(264, 263, 263)
    text = "\n".join(lines)
    assert suspect is True
    assert WARN in text
    assert "HEAD=263" in text and "task_state=263" in text
    assert "ledger_last=264" in text


def test_contract_2b_single_axis_divergence_is_still_suspicion():
    # task_state만 갈려도 의심이다 — 어느 축이 죽었는지는 손이 가린다.
    suspect, lines = c48.crash_orphan_verdict(264, 264, 263)
    assert suspect is True
    assert "task_state=263" in "\n".join(lines)


def test_contract_3_none_axis_is_undecidable_not_match():
    # HEAD가 비-loop 커밋(관측 126 사각): 남은 축이 일치해도 «3자 일치»는 금물.
    suspect, lines = c48.crash_orphan_verdict(266, None, 266)
    text = "\n".join(lines)
    assert suspect is False
    assert "3자 일치" not in text
    assert "판정 불가 축 1" in text and "판정 불가는 일치가 아니다" in text
    assert "관측 126" in text


def test_contract_3b_both_axes_none_is_fully_undecidable():
    suspect, lines = c48.crash_orphan_verdict(266, None, None)
    text = "\n".join(lines)
    assert suspect is False
    assert "판정 불가 축 2" in text
    assert "3자 일치" not in text and WARN not in text


def test_contract_4_no_auto_decrement():
    # 눈은 산술을 만지지 않는다: orphan 행이 있어도 N은 max+1 그대로이고,
    # 경고문이 «자동 차감은 하지 않았다»를 스스로 말한다.
    n, mode = c48.cycle_number_and_mode([262, 263, 264])  # 264 = 합성 orphan 행
    assert (n, mode) == (265, "회고")
    _, lines = c48.crash_orphan_verdict(264, 263, 263)
    assert "자동 차감은 하지 않았다" in "\n".join(lines)


def test_contract_5_head_subject_parser():
    assert c48.head_loop_cycle("loop(cycle 266): ★㉷ 집행") == 266
    assert c48.head_loop_cycle("loop(cycle 7)") == 7
    assert c48.head_loop_cycle("feat: 다른 트랙 커밋") is None
    assert c48.head_loop_cycle("Revert \"loop(cycle 266): x\"") is None
