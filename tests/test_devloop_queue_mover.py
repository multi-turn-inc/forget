"""계기 큐 ㉷ 회귀 — queue_mover 상설 모듈 (c266 건설).

계약 대상 = research/devloop/scripts/queue_mover.py. 합성 픽스처만 사용 —
실원장 값 상수 금지(관측 100·106: 실값 고정은 결함을 기대 상태로 잠근다).

계약:
  ① 큐 블록: 헤더 프레임 교체 + 마지막 적중 칸만 +1 (앞 칸 인용값 무접촉)
  ② 취소선(`~~`) 칸 = 동결 스킵 — 증분 0 (㉵ⓑ 승계)
  ③ 다중 적중 칸 = 무접촉 보고
  ④ `###` 이하 산문 무접촉 (과거 프레임 기록)
  ⑤ 헤더 프레임 불일치 = FrameMismatch (이중 실행·crash-orphan 가드)
  ⑥ 상설 표: 산식 `N − anchor + 1` 재계산 + 헤더 프레임 교체 (㉷ 본체)
  ⑦ 상설 표 드리프트(손-누락으로 뒤처진 값)를 한 번에 정위로 + drift 보고 — 침묵 수리 금지
  ⑧ 상설 절의 불릿(정산 이력 산문) 무접촉
  ⑨ ㉨ 영수증: 직전 프레임 «cN 정산» 불릿 존재 → present=True·행 번호 (c284 집행)
  ⑩ ㉨ 영수증: 부재·무기재 → present=False·silent_missing에 포함·인쇄에 «!!» (침묵 금지)
  ⑪ ㉨ 영수증: «cA~cB 정산 줄 공백» 기재는 정산 줄이 아니되(present=False) 침묵 소멸과 갈린다(kind='gap')
  ⑫ ㉨ 영수증: 범위 불릿 «cA~cB 정산»은 구간 전체를 덮고, 불릿 2개인 프레임은 duplicates 보고 — move_frame이 perm_report에 싣는다
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "research", "devloop", "scripts"))
import pytest  # noqa: E402
from queue_mover import (FrameMismatch, format_settlement_receipt, move_frame,  # noqa: E402
                         recalc_permanent_table, settlement_receipt, shift_queue_frame)

FIXTURE = """\
# 게이트 큐 — 합성 픽스처

## 큐 (프레임 N=100 · 경과 산식 = N − start + 1)

| 서열 | 청구 | 경과 |
|---|---|---|
| 1 | 알파 (12사이클째에 상신) | 40사이클째 |
| 2 | 브라보 | ~~7사이클째~~ 해소 |
| 3 | 찰리 | 9사이클째 · 3사이클째 |
| 4 | 델타 | 산문만 |

### 정산 (c99)

- 과거 프레임의 기록: 40사이클째라고 적혀 있었다.

## 상설 파생 계수기 (조건부 절 밖)

| 계수기 | 앵커 | 산식 | 프레임 N=100 값 |
|---|---|---|---|
| 에코 연속 정지 | **c61** | `N − 61 + 1` | **40사이클째** |

- 불릿 산문: 프레임 90에서 30사이클째였다 — 이 줄은 기록이다.
"""


def _moved(old=100, new=101, text=FIXTURE):
    return move_frame(text, old, new)


def test_queue_header_and_last_hit_cell_incremented():  # 계약 ①
    out, q, _ = _moved()
    assert "## 큐 (프레임 N=101" in out
    assert "| 1 | 알파 (12사이클째에 상신) | 41사이클째 |" in out
    assert q["changed"] and q["changed"][0][1:] == (40, 41)
    # 인용값(앞 칸)은 무접촉
    assert "12사이클째에 상신" in out


def test_strikethrough_cell_frozen():  # 계약 ②
    out, q, _ = _moved()
    assert "~~7사이클째~~" in out
    assert any("7사이클째" in cell for _, cell in q["skipped"])


def test_multi_hit_cell_untouched():  # 계약 ③
    out, q, _ = _moved()
    assert "9사이클째 · 3사이클째" in out
    assert len(q["bad"]) == 1


def test_prose_below_settlement_untouched():  # 계약 ④
    out, _, _ = _moved()
    assert "과거 프레임의 기록: 40사이클째라고 적혀 있었다." in out


def test_frame_mismatch_raises():  # 계약 ⑤
    with pytest.raises(FrameMismatch):
        shift_queue_frame(FIXTURE.splitlines(), 999, 1000)


def test_permanent_table_recalculated_from_formula():  # 계약 ⑥
    out, _, p = _moved()
    assert "프레임 N=101 값" in out
    assert "| **41사이클째** |" in out  # 101 − 61 + 1
    assert p["header"] == (100, 101)
    assert p["rows"] and p["rows"][0][1:] == (61, 40, 41)
    assert p["drift"] == []


def test_permanent_table_drift_repaired_and_reported():  # 계약 ⑦ — ㉷의 심장
    stale = FIXTURE.replace("프레임 N=100 값", "프레임 N=95 값") \
                   .replace("| **40사이클째** |", "| **35사이클째** |")
    lines = stale.splitlines()
    p = recalc_permanent_table(lines, 101)
    out = "\n".join(lines)
    assert "| **41사이클째** |" in out           # 증분(35→36)이 아니라 재계산(→41)
    assert "프레임 N=101 값" in out
    assert p["drift"] == [(lines.index([l for l in lines if "에코" in l][0]) + 1, 35, 40)]


def test_permanent_section_bullets_untouched():  # 계약 ⑧
    out, _, _ = _moved()
    assert "프레임 90에서 30사이클째였다 — 이 줄은 기록이다." in out


# ── ㉨ 영수증 (c284) — 합성 불릿 계열만. 실원장 프레임 값 상수 금지(관측 100·106).
SETTLE_TAIL = """\

- **c95 정산**: N=95 · 드리프트 0.
- **c96~c97 정산 줄 공백 (c98 기재)**: 두 프레임의 정산 줄이 쓰이지 않았다.
- **c98 정산**: N=98.
- **c99 정산**: N=99 · 드리프트 0.
- **c100 정산**: N=100 · 드리프트 0.
"""


def test_settlement_receipt_present():  # 계약 ⑨
    lines = (FIXTURE + SETTLE_TAIL).splitlines()
    r = settlement_receipt(lines, 100)
    assert r["present"] is True and r["kind"] == "settle"
    assert lines[r["line"] - 1].startswith("- **c100 정산**")
    assert r["silent_missing"] == []
    assert format_settlement_receipt(r)[0].endswith("1비트 = 1")


def test_settlement_receipt_absent_is_loud():  # 계약 ⑩ — ㉨의 심장
    tail = SETTLE_TAIL.replace("- **c100 정산**: N=100 · 드리프트 0.\n", "")
    lines = (FIXTURE + tail).splitlines()
    r = settlement_receipt(lines, 100)
    assert r["present"] is False and r["kind"] is None
    assert 100 in r["silent_missing"]
    head = format_settlement_receipt(r)[0]
    assert head.startswith("[㉨] !!") and "부재·무기재" in head
    # 불릿 계열이 아예 없어도 침묵하지 않는다
    r0 = settlement_receipt(FIXTURE.splitlines(), 100)
    assert r0["present"] is False and r0["silent_missing"] == [100]


def test_settlement_gap_record_is_not_silent():  # 계약 ⑪
    lines = (FIXTURE + SETTLE_TAIL).splitlines()
    r = settlement_receipt(lines, 97)
    assert r["present"] is False and r["kind"] == "gap"
    assert r["recorded_gaps"] == [96, 97]
    assert 97 not in r["silent_missing"]
    assert "기재된 공백" in format_settlement_receipt(r)[0]


def test_settlement_range_bullet_and_duplicates_via_move_frame():  # 계약 ⑫
    tail = SETTLE_TAIL.replace("- **c98 정산**: N=98.\n", "- **c98~c99 정산**: 두 프레임 합본.\n")
    out, _, p = move_frame(FIXTURE + tail, 100, 101)
    r = p["settlement_prev"]
    assert r["prev_frame"] == 100 and r["present"] is True
    assert r["duplicates"] == [99]          # 범위 불릿 + 단일 c99 불릿
    assert 98 not in r["silent_missing"]    # 범위가 덮는다
    assert "- **c98~c99 정산**: 두 프레임 합본." in out  # 불릿 무접촉
