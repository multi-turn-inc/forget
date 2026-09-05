"""파트 S `미측정`의 두 원인이 갈라져 인쇄되는가 (c172 신설, 관측 107 · P59).

**관행 ⑯을 지킨다** — 능력은 **합성 표본**으로 고정하고, 실 원장의 현재 상태는 **인쇄**만
한다. c171이 실 원장 최신 행에 «결함의 존재»를 assert해 «고치는 쪽이 벌받는» 자물쇠를
만들었고(관측 106), 그 교훈이 이 파일의 구조를 정한다. 여기서 실 원장에 걸린 단정은
**프레임 독립 항등식**(총수 = 두 줄의 합) 하나뿐이며, 그것은 데이터가 자라도 나아져도
참이어야 하는 계정 규칙이다.

계보: P47 한계 ③이 c162에 선언한 거짓 음성을 c172가 처음 실측했다 — `미측정 30행` 중
26행이 실제로는 판정을 적었고(c131~c155 슬래시형 서식 25연속) 4행만 진짜 침묵이었다.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "research", "devloop", "scripts"))

import c48_step0_check as c48  # noqa: E402

FIELD = c48.REVERIFY_FIELD

# 실제로 c131~c155가 쓴 서식 — `판정=` 접두가 없다. 엄격 눈이 못 보고 느슨 눈이 본다.
SLASH_FORM = "파트 S ledger_last=130/task_state_cycle=130 일치·freshness fresh age 0.36h"
# c170이 쓴 서식 — 백틱 뒤에 값. 역시 `판정=`이 없다.
BACKTICK_FORM = "`freshness` fresh(0.357h) · 파트 S `ledger_last=169 = task_state_cycle=169` 일치"
STRICT_FORM = "파트 S는 ledger_last=170 task_state_cycle=170 판정=일치 를 인쇄했다"


def _rows(pairs: list[tuple[int, object, str]]) -> list[dict]:
    """(cycle, 자기보고값, restore_note) → 원장 행. 합성이며 실 원장이 아니다."""
    out = []
    for c, claim, note in pairs:
        row: dict = {"cycle": c, "restore_note": note}
        if claim is not ...:
            row[FIELD] = claim
        out.append(row)
    return out


# ── 능력: 두 원인이 갈라지는가 (합성) ────────────────────────────────────────


@pytest.mark.parametrize("note,verdict", [(SLASH_FORM, "일치"), (BACKTICK_FORM, "일치")])
def test_written_but_strict_blind_lands_in_blind_bucket(note: str, verdict: str) -> None:
    """후속 행이 판정을 **적었는데** 엄격 눈이 못 보면 `blind`다 — 침묵으로 세지 않는다."""
    rv = c48.reverify_contradictions(_rows([(900, True, ""), (901, ..., note)]))
    assert rv["unmeasured"] == 1
    assert rv["unmeasured_blind"] == [(901, verdict)]
    assert rv["unmeasured_silent"] == []


def test_truly_unwritten_lands_in_silent_bucket() -> None:
    """판정 낱말이 아예 없으면 `silent`다 — 이것이 정직한 미측정이다 (c169형)."""
    note = "하네스 = A. restore_turns 2. 결함 6건. 1세션이 세계를 앞으로 밀고 죽었다."
    rv = c48.reverify_contradictions(_rows([(900, True, ""), (901, ..., note)]))
    assert rv["unmeasured"] == 1
    assert rv["unmeasured_blind"] == []
    assert rv["unmeasured_silent"] == [901]


def test_strictly_visible_row_is_in_neither_bucket() -> None:
    """엄격 눈이 보면 대조가 성립하므로 두 통 어디에도 들어가지 않는다."""
    rv = c48.reverify_contradictions(_rows([(900, True, ""), (901, ..., STRICT_FORM)]))
    assert rv["unmeasured"] == 0
    assert rv["unmeasured_blind"] == []
    assert rv["unmeasured_silent"] == []
    assert rv["checked"] == 1


def test_a_row_mentioning_part_s_without_a_verdict_word_stays_silent() -> None:
    """c169 실제 문면의 함정 — '파트 S'는 있고 판정값 낱말은 없다. 느슨 눈도 침묵해야 한다."""
    note = ("next_actions[1]이 '파트 S의 새 인쇄를 반드시 읽어라 … 증거가 0이 아니면"
            " 내가 죽은 것이고' 를 적어 뒀다")
    rv = c48.reverify_contradictions(_rows([(900, True, ""), (901, ..., note)]))
    assert rv["unmeasured_blind"] == []
    assert rv["unmeasured_silent"] == [901]


# ── 규율: 느슨 탐침은 고발하지 않는다 (P59 (b)) ──────────────────────────────


def test_loose_hit_never_produces_an_accusation() -> None:
    """느슨 적중만으로는 `contradictions`가 생기지 않는다 — 진단은 넓게, 고발은 좁게.

    이 계약이 이 처치의 값이다. 흐리게 읽은 판정으로 자기보고를 반증하면, P51이 고친
    바로 그 병(정직을 벌하는 계기)이 다른 문으로 돌아온다.
    """
    lagged_loose = "파트 S ledger_last=899/task_state_cycle=899 지연"
    rv = c48.reverify_contradictions(_rows([(900, True, ""), (901, ..., lagged_loose)]))
    assert rv["contradictions"] == []          # 고발 없음
    assert rv["unmeasured_blind"] == [(901, "지연")]  # 그러나 **보인다**
    # 그리고 그 값은 `일치`가 아니므로 파트 S가 큰 소리를 낼 대상이다.
    assert [v for _, v in rv["unmeasured_blind"] if v != "일치"]


def test_strict_lag_still_accuses_a_bare_true() -> None:
    """엄격 경로의 참 양성은 그대로다 — 이 처치가 P47/P51의 고발을 약화시키지 않는다."""
    rv = c48.reverify_contradictions(
        _rows([(900, True, ""), (901, ..., "파트 S ... 판정=지연 ...")]))
    assert rv["contradictions"] == [(900, "지연")]


def test_deferred_row_is_still_exempt_under_strict_lag() -> None:
    """유보는 여전히 면책 — P51 (a)의 능력을 이 파일에서도 한 번 더 못박는다."""
    rv = c48.reverify_contradictions(
        _rows([(900, "미정 — c901 파트 S가 판정", ""), (901, ..., "판정=지연")]))
    assert rv["contradictions"] == []


# ── 실 원장: 항등식만 단정하고 나머지는 인쇄한다 (관행 ⑯) ────────────────────


def _ledger() -> list[dict]:
    path = os.path.join(REPO, "research", "devloop", "metrics.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def test_real_ledger_accounting_identity_holds(capsys: pytest.CaptureFixture) -> None:
    """총 `미측정` = 적혀 있었다 + 안 적었다. **P59 (a)의 반증 조건이 이 항등식이다.**

    프레임 독립이므로 원장이 자라도 나아져도 참이어야 한다 — 상수를 박지 않는다.
    현재 분포는 **인쇄만** 한다(관측 106의 교훈: 결함의 존재를 assert하지 않는다).
    """
    rv = c48.reverify_contradictions(_ledger())
    blind, silent = rv["unmeasured_blind"], rv["unmeasured_silent"]
    assert rv["unmeasured"] == len(blind) + len(silent)
    with capsys.disabled():
        print(f"\n    [실 원장 현재 분포 — 단정 아님] 미측정 {rv['unmeasured']}행"
              f" = 적혀 있었다 {len(blind)} + 안 적었다 {len(silent)}")
        print(f"      안 적었다: {silent}")
        print(f"      적혀 있었다(값): {sorted({v for _, v in blind})}")
        print(f"      대조 가능 {rv['checked']}행 · 모순 {len(rv['contradictions'])}건")
