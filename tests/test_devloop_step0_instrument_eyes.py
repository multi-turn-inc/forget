"""c48_step0_check — 상설 계기 인용·표본 칸 눈 (㉶+㉬ 병합, c196 · am-195 §4-① · P68).

왜 이 파일이 있는가. P64 (b)·P65 (b)가 같은 두 사이클(c191·c192)에서 동시 반증됐다 —
상설 계기 ㉮·㉭의 값이 원장에서 동시 무인용. 이 눈은 그 재발을 다음 사이클 step 0
화면에 올린다. 셋 다 순수 함수이므로 합성 표본으로 회귀에 건다.

가장 중요한 단언 셋.

① **정의역은 직독이다** — `permanent_instruments`는 instrument-queue.md 텍스트에서
   처분 «상설» 항을 읽는다. 명단을 상수로 박으면 다음 상설 계기가 태어날 때 이 눈이
   침묵한다(관측 119의 정의역 미선언 재발). 어휘 없는 신입은 «어휘 미등록»으로 뜬다.

② **진단 전용** — `instrument_citation`은 후보와 문맥만 반환한다. 자동 판정 필드가
   없다는 것 자체가 계약이다(P65 (c) 거짓 양성 0/2 → 자동 판정 금지).

③ **탈소음** — `sample_cell_scan`은 판정 도장 c196+ 절만 질의 후보에 넣고, 구판은
   계수만 한다(am-195 §4-①: 소급 없음 — 구판 51건 일괄 고발은 경보 피로의 재발 경로).
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_instrument_eyes", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

QUEUE = """# 계기 큐

## 미집행 잔고 (프레임 N=195)

| 항 | 내용 | 기원 | 비고 |
|---|---|---|---|
| ㉯ | 미집행 계기 | 관측 118 | 이월 — 상설 아님(잔고 절은 정의역 밖) |

## 집행·해소 이력

| 항 | 내용 | 처분 |
|---|---|---|
| ㉲ | 일회성 census | **c193 집행·해소** |
| ㉰ | 미계기화 «N연속» 탐지 | c191 건설 — 파트 O 상설 |
| ㉮ | 범위∖계수 검산 | c188 건설 — 상설 (P64 판정 c193) |
| ㉭ | 선언∖정본 대조 | c189 건설 — 상설 |
| ㉹ | 신입 상설 계기 | c199 건설 — 상설 |
"""


def test_roster_reads_only_permanent_rows_from_history_section():
    """① 정의역 직독 — «집행·해소 이력»의 «상설» 항만, 잔고 절·일회성 처분은 제외."""
    roster = c48.permanent_instruments(QUEUE)
    assert [r["marker"] for r in roster] == ["㉰", "㉮", "㉭", "㉹"]


def test_embedded_instrument_is_marked_out_of_domain():
    """«파트 O 상설»은 내장 계기 — 인용 눈의 정의역 밖으로 표시된다."""
    roster = {r["marker"]: r for r in c48.permanent_instruments(QUEUE)}
    assert roster["㉰"]["embedded"] is True
    assert roster["㉮"]["embedded"] is False
    assert roster["㉭"]["embedded"] is False


def test_new_permanent_instrument_without_vocab_is_loud_not_silent():
    """① 어휘 없는 신입(㉹)은 «어휘 미등록»으로 인쇄된다 — 침묵이 아니다."""
    roster = c48.permanent_instruments(QUEUE)
    row = {"cycle": 195, "work": "range_count 검산 값 인용"}
    by = {r["marker"]: r for r in c48.instrument_citation(row, roster)}
    assert by["㉹"]["status"] == "어휘 미등록"
    assert by["㉰"]["status"] == "내장"


def test_citation_candidate_carries_hits_and_context_for_hand_reading():
    """② 후보 + 문맥 반환 — 자동 판정 필드는 없다(판정은 손 몫)."""
    roster = [r for r in c48.permanent_instruments(QUEUE) if not r["embedded"]]
    row = {"cycle": 195, "predictions_note": "오늘 검산 결과 불일치 0건"}
    by = {r["marker"]: r for r in c48.instrument_citation(row, roster)}
    assert by["㉮"]["status"] == "적혀 있었다"
    assert set(by["㉮"]["hits"]) == {"불일치", "검산"}
    assert by["㉮"]["ctx"] and all("…" in c for c in by["㉮"]["ctx"])
    assert by["㉭"]["status"] == "안 적었다"
    assert by["㉭"]["hits"] == []
    assert "verdict" not in by["㉮"] and "accused" not in by["㉮"]


HEAD_NEW_OK = ("## P90 — 합성 (등록 사이클 1)\n\n- 상태: (a) 지지\n\n"
               "- **판정 (사이클 196)** — 창 c191~c195. **표본 = 5건 [원장 행]**\n")
HEAD_NEW_MISSING = ("## P91 — 합성 (등록 사이클 1)\n\n- 상태: (a) 지지\n\n"
                    "- **판정 (사이클 197)** — 창 없음.\n")
HEAD_NEW_ZERO = ("## P92 — 합성 (등록 사이클 1)\n\n- 상태: (a) 지지\n\n"
                 "- **판정 (사이클 196)** — 표본 = 0건.\n")
HEAD_LEGACY = ("## P93 — 합성 (등록 사이클 1)\n\n- 상태: (a) 지지 · (b) 반증\n\n"
               "- **판정 (사이클 193)** — 창 c188~c192.\n")
HEAD_UNSTAMPED = ("## P94 — 합성 (등록 사이클 1)\n\n- 상태: (a) 지지\n\n"
                  "- **판정 (c76, 2026-08-08)**: 적중.\n")
HEAD_NOT_SUPPORTED = ("## P95 — 합성 (등록 사이클 1)\n\n- 상태: (a) 반증\n\n"
                      "- **판정 (사이클 196)** — 표본 칸 없음이지만 지지 아님.\n")


def test_sample_cell_scan_partitions_new_legacy_and_blind():
    """③ 탈소음 분류 — 신규 보유/질의 후보/구판/도장-무표기 사각이 갈라진다."""
    text = "\n".join([HEAD_NEW_OK, HEAD_NEW_MISSING, HEAD_NEW_ZERO,
                      HEAD_LEGACY, HEAD_UNSTAMPED, HEAD_NOT_SUPPORTED])
    scan = c48.sample_cell_scan(text, since=196)
    assert [(p, l, n) for p, l, n in scan["new_ok"]] == [("P90", 196, 5)]
    assert sorted(scan["candidates"]) == [("P91", 197, "표본 칸 부재"),
                                          ("P92", 196, "표본 = 0건")]
    assert scan["legacy"] == ["P93"]
    assert scan["unstamped"] == ["P94"]


def test_legacy_supported_sections_are_counted_not_accused():
    """③ 구판 «지지»는 질의 후보가 아니다 — 소급 없음(감사는 c200 몫)."""
    scan = c48.sample_cell_scan(HEAD_LEGACY, since=196)
    assert scan["legacy"] == ["P93"]
    assert scan["candidates"] == []


def test_landing_cycle_is_the_max_stamp_in_section():
    """재판정 절은 마지막 도장이 착지 사이클이다 — c193 판정 후 c196 재판정이면 신규."""
    text = ("## P96 — 합성 (등록 사이클 1)\n\n- 상태: (a) 지지\n\n"
            "- **판정 (사이클 193)** — 1차.\n- **판정 (사이클 196)** — 재판정, 표본 칸 없음.\n")
    scan = c48.sample_cell_scan(text, since=196)
    assert scan["candidates"] == [("P96", 196, "표본 칸 부재")]
