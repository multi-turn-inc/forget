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
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "research", "devloop", "scripts"))
import pytest  # noqa: E402
from queue_mover import (FrameMismatch, move_frame, recalc_permanent_table,  # noqa: E402
                         shift_queue_frame)

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
