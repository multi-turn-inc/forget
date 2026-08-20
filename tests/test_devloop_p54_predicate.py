"""관측 112 처치 회귀 — «표지 없음»과 «도장 없음»은 다른 술어다 (사이클 174).

병. P54 등록문은 대조군을 **23**으로 적었고 그 23은 «도장 없음»의 수인데 표의 머리는
«표지 없음»이었다. 값은 정확히 살아남고 술어만 바뀌었으므로 «수를 대조하라»는 기존
규율로는 잡히지 않는다(대조하면 23 = 23으로 통과한다). 처치는 두 술어를 **각각 계산해
라벨과 함께 인쇄**하는 것이고, 이 파일이 그 계약을 고정한다.

규율. 합성 텍스트만 쓴다 — 실 대장(`predictions.md`)에 «결함이 있다»고 assert하지
않는다(관행 ⑯·⓴). 실 대장의 수는 사이클마다 바뀌므로 그것을 상수로 박으면 다음
사이클의 수확이 이 테스트를 붉게 만들고, 그 붉음은 결함이 아니라 자물쇠다(관측 100·106).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "research", "devloop", "scripts"))

from c48_step0_check import status_stamp_reconcile  # noqa: E402


#: 네 절이 네 가지 조합을 만든다. 상태줄은 전건 «지지» = 시계 아래(하강).
FIXTURE = """
## P900 — 불릿 판정문 + 도장

- 상태: 지지

- **판정 (사이클 500)** — 적중.

## P901 — 강조 접두(★) 판정문 + 도장. 순진한 자[尺]는 이것을 놓친다.

- 상태: 지지

- **★ 판정 (사이클 501)** — 적중.

## P902 — 불릿 판정문이 있으나 **도장 없음**

- 상태: 지지

- **판정** — 적중.

## P903 — 표지 자체가 없다

- 상태: 지지

본문만 있다.
"""


@pytest.fixture(scope="module")
def rec():
    return status_stamp_reconcile(FIXTURE)


def test_네_절이_모두_하강으로_읽힌다(rec):
    assert sorted(rec["down"]) == ["P900", "P901", "P902", "P903"]


def test_세_서식지_잣대는_표지_없는_절만_고발한다(rec):
    # ★ 절(P901)은 서식지 2종이 잡으므로 고발 대상이 아니다.
    assert rec["silent_drop"] == ["P903"]


def test_순진한_잣대의_표지_없음은_강조접두_절을_포함한다(rec):
    """이 셋이 «23 → 8 → 0» 계열의 8에 해당하는 축이다."""
    assert sorted(rec["naive_silent"]) == ["P901", "P903"]


def test_도장_없음은_표지_없음의_상위집합이며_별_술어다(rec):
    """관측 112의 핵심. 두 술어의 값이 **다르다**는 것이 계약이다."""
    silent = set(rec["naive_silent"])
    unstamped = set(rec["naive_unstamped"])
    # 표지가 없으면 도장도 없다 — 포함 관계는 구조적이다.
    assert silent <= unstamped
    # 그러나 같지 않다: P902는 표지가 있고 도장이 없다.
    assert unstamped - silent == {"P902"}
    assert len(silent) != len(unstamped), (
        "두 술어가 같은 수를 내면 이 회귀는 관측 112를 재지 못한다")


def test_고발_축과_별_축이_따로_계산된다(rec):
    """상수가 아니라 계산임을 고정한다 — 상수였던 것이 병의 매개였다."""
    for pid, r in rec["sections"].items():
        assert r["narrow_markers"] >= r["narrow_stamped"], pid
        assert r["markers"] >= r["narrow_markers"], pid


def test_실_대장에서도_두_술어가_각각_계산된다():
    """실 대장 스모크 — **값을 박지 않는다.** 부등식만 본다(관행 ⑯)."""
    from c124_retro_prep import PRED
    live = status_stamp_reconcile(PRED.read_text(encoding="utf-8"))
    assert set(live["silent_drop"]) <= set(live["naive_silent"])
    assert set(live["naive_silent"]) <= set(live["naive_unstamped"])
