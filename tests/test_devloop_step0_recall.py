"""c48_step0_check의 recall 계상 검산기 — P24 처치(P15 (a) 반증 처방)의 회귀 감시.

스크립트는 research/devloop/scripts/에 살지만 **판정 도구**이므로 감시 대상이다
(선례: tests/test_devloop_body_fingerprint.py).

지키는 성질 둘:
  1. **모르는 것을 '일치'로 보고하지 않는다** — 성분 4값이 유일하게 추출되지 않으면
     '추출 불가'다(0으로 접지 않는다). compare_fingerprint와 같은 규율.
  2. **audit-70 §1-a [N1]을 기계로 재현한다** — c64형(필드=구정의·산문=신정의 분열)을
     불일치로 잡고, 정상 행을 불일치로 만들지 않는다(위양성 0 대조군).

소급 자기 시험(c71 실측, 등록문 P24 정직 병기의 이행): c61~c70 실제 원장 10행에서
추출 10/10 성공, 판정은 c64 단독 불일치 · 나머지 9행 일치 — audit-70의 수작업 계수와
정확히 같다. 그 실측을 여기 고정한다(원장 행은 A6 불변이므로 이 테스트는 결정적이다).

부수 상환: part_n 산술(cycle_number_and_mode)과 part_b의 needle_reach — c64→c70
7회 재이월된 "part_n/part_a/part_b 파싱 테스트 미커버" 부채의 부분 상환.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


# ---- recall_components: 추출 ------------------------------------------------

def test_canonical_format_extracts_four_values():
    comp = c48.recall_components("정의 A — 능동 2회(hit 1·miss 1) / 주입 3건(hit 1·miss 2).")
    assert comp == {"active_hits": 1, "active_misses": 1, "active_total": 2,
                    "injected_hits": 1, "injected_misses": 2, "injected_total": 3}


def test_c70_paraphrase_zero_active_and_sum_closed_injection():
    # c70 실행형: 능동은 분해 생략(0회), 주입은 "hit 1 + 3건 miss" 의역
    note = ("정의 A **10행째** — 성분 분해 병기. **능동 검색 0회**. 계기 배제 규약 승계. "
            "**주입 4건 = 캡슐/task_state hit 1 + 훅 주입 3건 miss.** 이후 산문.")
    comp = c48.recall_components(note)
    assert comp == {"active_hits": 0, "active_misses": 0, "active_total": 0,
                    "injected_hits": 1, "injected_misses": 3, "injected_total": 4}


def test_nonzero_active_without_breakdown_is_not_guessed():
    # 능동 2회인데 hit/miss 분해가 없으면 유일 해석이 없다 — None이어야 한다
    assert c48.recall_components("능동 2회, 주입 1건(hit 1·miss 0)") is None


def test_garbage_returns_none():
    assert c48.recall_components("회상 채널 침묵 — 표본 없음") is None


def test_injection_without_any_hitmiss_is_none():
    assert c48.recall_components("능동 0회 / 주입 3건, 전부 관련") is None


# ---- recall_identity: 항등식 검산 -------------------------------------------

def test_identity_match():
    row = {"recall_hits": 1, "recall_misses": 3,
           "recall_note": "능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)"}
    verdict, detail = c48.recall_identity(row)
    assert verdict == "일치"
    assert "성분(능동 0·0 / 주입 1·3)" in detail


def test_identity_catches_c64_shape_mismatch():
    # audit-70 §1-a [N1] 그대로: 필드 miss 4 vs 성분 합 3 — 불일치로 잡혀야 한다
    row = {"recall_hits": 1, "recall_misses": 4,
           "recall_note": "능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)"}
    verdict, _ = c48.recall_identity(row)
    assert verdict == "불일치"


def test_identity_extraction_failure_is_not_silent():
    verdict, detail = c48.recall_identity(
        {"recall_hits": 0, "recall_misses": 0, "recall_note": "형식 밖 산문"})
    assert verdict == "추출 불가"
    assert "P24 (b)" in detail


# ---- 소급 자기 시험: c61~c70 실제 원장 (행은 A6 불변 → 결정적) ---------------

def test_ledger_c61_to_c70_reproduces_audit70_count():
    rows = {}
    with open(ROOT / "research" / "devloop" / "metrics.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows[r["cycle"]] = r
    verdicts = {c: c48.recall_identity(rows[c])[0] for c in range(61, 71)}
    # 추출 10/10 — P15 (b) "형식은 의역돼도 값은 나온다"의 기계 재현
    assert all(v != "추출 불가" for v in verdicts.values()), verdicts
    # audit-70 수작업 계수와 동일: c64 단독 불일치, 나머지 9행 일치 (위양성 0)
    assert verdicts.pop(64) == "불일치"
    assert set(verdicts.values()) == {"일치"}, verdicts


# ---- 이월 부채 부분 상환: part_n 산술 · part_b 니들 ---------------------------

def test_cycle_number_and_mode():
    assert c48.cycle_number_and_mode([68, 69, 70]) == (71, "일반")
    assert c48.cycle_number_and_mode([78, 79]) == (80, "적대 감사")
    assert c48.cycle_number_and_mode([73, 74]) == (75, "회고")
    # 순서 오염에도 안전해야 한다 — max+1이지 마지막+1이 아니다 (part_n 독스트링 성질)
    assert c48.cycle_number_and_mode([70, 68, 69]) == (71, "일반")


def test_needle_reach_counts_only_arrived_rules():
    capsule = "★ metrics.jsonl에 tail 금지 — 번호·모드는 스크립트가 정본"
    hits, detail = c48.needle_reach(capsule, {
        "(i)": ["devloop-self"],
        "(iii)": ["tail 금지", "cycle 필드"],
    })
    assert (hits, detail) == (1, {"(i)": 0, "(iii)": 1})
