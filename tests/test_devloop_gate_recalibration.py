"""c68 — 게이트 재교정 판정 산술의 회귀 감시.

이 테스트가 지키는 성질은 하나로 요약된다: **판정은 실전 표본과 대조군만으로 나오고,
미채취는 '이상 없음'이 아니며, 잡음보다 좁은 구간을 '분리'로 부르지 않는다.**
관측 32(자기질의 퇴화 팔이 "처치 성공"을 만들 뻔했다)의 수용 기준 ①을 코드로 고정한다.
"""
from __future__ import annotations

import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "research", "devloop", "scripts",
                      "c68_gate_recalibration.py")


def _load():
    spec = importlib.util.spec_from_file_location("c68_gate_recalibration", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_empty_arm_is_undecidable_not_clean():
    """미채취를 '분리'로 접지 않는다 — c67 설계 결정 ②의 승계."""
    m = _load()
    assert m.verdict_band([], [0.5, 0.6])["verdict"] == "판정 불가"
    assert m.verdict_band([0.7, 0.8], [])["verdict"] == "판정 불가"
    assert m.verdict_band([], [])["t_min"] is None


def test_c68_measured_sample_lands_in_noise():
    """c68 실측(ON-real 최저 0.6346 / OFF 최고 0.6037)은 '잡음 안'이다.

    구간 폭 0.0246 < OFF 산포 0.0462이므로 권고 상수가 존재해도 분리로 부르지 않는다.
    """
    m = _load()
    on_real = [0.6346, 0.6445, 0.6986, 0.7900, 0.7485, 0.8104, 0.7300, 0.6800]
    off = [0.5718, 0.5575, 0.5841, 0.5901, 0.5747, 0.5660, 0.6037, 0.5755]
    got = m.verdict_band(on_real, off)
    assert got["verdict"] == "잡음 안"
    assert got["t_min"] == 0.61                 # 오탐 0을 사는 최소 그리드값
    assert abs(got["t_max"] - 0.6346) < 1e-9
    assert got["band"] < got["off_scale"]


def test_overlap_is_reported_as_no_separation():
    """ON-real 최저가 OFF 최고보다 낮으면 어떤 상수도 분리하지 못한다."""
    m = _load()
    got = m.verdict_band([0.55, 0.61], [0.58, 0.62])
    assert got["verdict"] == "분리 불가"


def test_wide_separation_is_reported_as_separation():
    """대조군 산포보다 넓은 구간은 '분리'로 부른다 — 판정이 한쪽으로만 굳지 않는다."""
    m = _load()
    got = m.verdict_band([0.90, 0.95], [0.40, 0.41, 0.42])
    assert got["verdict"] == "분리"
    assert got["band"] > got["off_scale"]


def test_more_samples_can_only_shrink_the_band():
    """P22 (a)의 연역을 산술로 고정: 표본을 더하면 구간은 넓어질 수 없다."""
    m = _load()
    on_real = [0.70, 0.75, 0.80]
    off = [0.50, 0.52]
    base = m.verdict_band(on_real, off)
    # OFF에 더 높은 최고점이 추가되면 t_min이 올라간다
    grown_off = m.verdict_band(on_real, off + [0.60])
    # ON-real에 더 낮은 top-1이 추가되면 t_max가 내려간다
    grown_on = m.verdict_band(on_real + [0.66], off)
    for grown in (grown_off, grown_on):
        assert grown["band"] is None or grown["band"] <= base["band"] + 1e-9
