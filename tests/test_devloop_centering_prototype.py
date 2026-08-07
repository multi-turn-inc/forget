"""사이클 69 — 중심화 프로토타입의 판정 산술을 순수 함수로 고정한다.

이 사이클이 발견한 것 중 **테스트로 굳혀야 하는 것**만 담는다:
  ① 점수의 아핀 분해: score = 0.275 + rule×0.45 + 0.275×cos (물려받은 "vector=raw cosine"
     기술의 정정). 이 산술이 틀리면 게이트 축의 모든 연역이 무너진다.
  ② 척도 불변 통계: P22 (b)의 문자 기준(band 폭)이 **척도 의존**이라는 사실. 곱셈 재척도
     아래서 band는 변하고 R·AUC·d는 변하지 않는다 — 이 성질이 "문자 기준을 그대로 이행하면
     거짓 판정 기계가 된다"는 주장의 전부이므로 주장 대신 테스트로 둔다.
  ③ 두 기준의 불일치 노출: literal_vs_invariant는 어느 쪽이 옳은지 정하지 않고 agree=False를
     낸다(내 대체 기준을 내가 '충족'으로 채점하지 않기 위한 코드 수준 장치).
  ④ 사슬 재현에 **breakdown에 없는 보정**이 필요하다는 사실(피드백 ±).
"""
from __future__ import annotations

import importlib.util
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "research", "devloop", "scripts")


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(SCRIPTS, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def c69():
    return _load("c69_centering_prototype")


# ---------------------------------------------------------------- ① 아핀 분해
def test_score_decomposes_into_affine_constant_and_cosine(c69):
    """score = 0.275 + rule×0.45 + 0.275×cos — vector가 (cos+1)/2이기 때문이다.

    c68이 넘긴 "vector는 raw cosine"이 옳다면 상수항 0.275는 존재하지 않는다.
    이 테스트가 실패하면 정정이 틀렸다는 뜻이므로 게이트 축의 연역을 다시 봐야 한다.
    """
    for rule, cos in ((0.0, 0.0), (0.0, 0.7), (0.3, 0.64), (1.0, 1.0)):
        vector = (cos + 1.0) / 2.0
        assert c69.compose_score(rule, vector) == pytest.approx(
            0.275 + rule * 0.45 + 0.275 * cos, abs=1e-4)


def test_zero_relevance_row_clears_gate_from_the_constant_alone(c69):
    """어휘 관련성이 0인 행도 cos가 충분히 크면 게이트를 넘는다 — 상수항의 귀결.

    문턱은 affine_floor_cosine()이고, 그 아래/위에서 판정이 갈려야 한다.
    """
    floor = c69.affine_floor_cosine(0.45)
    assert floor == pytest.approx((0.45 - 0.275) / 0.275, abs=1e-9)
    just_below = c69.compose_score(0.0, (floor - 0.01 + 1.0) / 2.0)
    just_above = c69.compose_score(0.0, (floor + 0.01 + 1.0) / 2.0)
    assert just_below < 0.45 <= just_above


def test_affine_floor_moves_with_the_gate(c69):
    """게이트를 올리면 필요한 cos도 올라간다 — 단조성이 깨지면 연역이 무효다."""
    assert c69.affine_floor_cosine(0.40) < c69.affine_floor_cosine(0.50)


# ---------------------------------------------- ② 문자 기준은 척도 의존이다
def test_band_is_scale_dependent_but_invariants_are_not(c69):
    """모든 점수를 c배 하면 band는 c배 되고 R·AUC·d는 **불변**이다.

    이것이 P22 (b)의 문자 기준("폭이 0.0246보다 넓어지는가")을 척도를 바꾸는 처치에
    그대로 적용하면 안 되는 이유다. 주장이 아니라 성질로 고정한다.
    """
    on = [0.70, 0.75, 0.80, 0.90]
    off = [0.50, 0.55, 0.60, 0.62]
    base = c69.separation_stats(on, off)
    for factor in (2.0, 0.5, 10.0):
        scaled = c69.separation_stats([x * factor for x in on],
                                      [x * factor for x in off])
        # 척도 의존: gap은 정확히 factor배
        assert scaled["gap"] == pytest.approx(base["gap"] * factor, rel=1e-9)
        # 척도 불변
        assert scaled["ratio"] == pytest.approx(base["ratio"], rel=1e-9)
        assert scaled["auc"] == pytest.approx(base["auc"], rel=1e-9)
        assert scaled["cohen_d"] == pytest.approx(base["cohen_d"], rel=1e-9)


def test_auc_is_one_exactly_when_a_separating_constant_exists(c69):
    """AUC=1.0 ⟺ 분리 상수 존재. 두 기준이 같은 사실을 재는지 확인한다."""
    sep = c69.separation_stats([0.70, 0.80], [0.50, 0.60])
    assert sep["auc"] == 1.0 and sep["gap"] > 0
    overlap = c69.separation_stats([0.55, 0.80], [0.50, 0.60])
    assert overlap["auc"] < 1.0 and overlap["gap"] < 0


def test_separation_stats_refuses_tiny_samples(c69):
    """표본 1개로는 산포가 정의되지 않는다 — None을 내고 0으로 접지 않는다."""
    assert c69.separation_stats([0.7], [0.5])["ratio"] is None
    assert c69.separation_stats([], [])["auc"] is None


# ------------------------------------------- ③ 두 기준의 불일치를 드러낸다
def test_literal_and_invariant_disagreement_is_surfaced(c69):
    """척도만 키운 처치는 문자 기준을 통과하고 불변 기준에서 탈락해야 한다 — agree=False."""
    baseline = c69.separation_stats([0.70, 0.75, 0.80, 0.90],
                                    [0.50, 0.55, 0.60, 0.62])
    # 척도를 10배 키우면 band는 커지지만 분리력은 그대로다.
    verdict = c69.literal_vs_invariant(baseline, {**baseline, "band": 0.9})
    assert verdict["literal_pass"] is True
    assert verdict["invariant_pass"] is False      # R이 baseline과 같으므로 '초과'가 아니다
    assert verdict["agree"] is False


def test_literal_vs_invariant_agrees_when_both_improve(c69):
    treated = c69.separation_stats([0.70, 0.75, 0.80, 0.90],
                                   [0.40, 0.45, 0.50, 0.52])
    baseline = c69.separation_stats([0.70, 0.75, 0.80, 0.90],
                                    [0.50, 0.55, 0.60, 0.62])
    verdict = c69.literal_vs_invariant(baseline, {**treated, "band": 0.10})
    assert verdict["literal_pass"] is True
    assert verdict["invariant_pass"] is True
    assert verdict["agree"] is True


def test_missing_band_is_not_scored_as_pass(c69):
    """band가 없으면 '판정 불가'이며 '통과'로 접지 않는다."""
    baseline = c69.separation_stats([0.70, 0.80], [0.50, 0.60])
    verdict = c69.literal_vs_invariant(baseline, {**baseline, "band": None})
    assert verdict["literal_pass"] is None
    assert verdict["agree"] is None


# ------------------------------------ ④ breakdown에 없는 보정이 필요하다
def test_feedback_adjustment_is_needed_to_reproduce_the_chain(c69):
    """피드백 보정은 score_breakdown에 없다 — 빼면 정확히 그만큼 틀린다.

    c69 1차 런의 F1 불일치 135/3200(4.22%)이 전부 +0.0500이었던 사실의 고정.
    """
    without = c69.compose_score(0.1, 0.9)
    with_pos = c69.compose_score(0.1, 0.9, feedback_adjust=0.05)
    assert with_pos - without == pytest.approx(0.05, abs=1e-9)
    with_neg = c69.compose_score(0.1, 0.9, feedback_adjust=-0.15)
    assert without - with_neg == pytest.approx(0.15, abs=1e-9)


def test_demotions_apply_multiplicatively_in_product_order(c69):
    """세션 캡처 ×0.5 · superseded ×0.45 · 스코프 폴백 ×0.88 (store.py 순서)."""
    plain = c69.compose_score(0.2, 0.8)
    assert c69.compose_score(0.2, 0.8, session_capture=True) == pytest.approx(
        round(plain * 0.5, 4), abs=1e-4)
    assert c69.compose_score(0.2, 0.8, scope_fallback=True) == pytest.approx(
        round(plain * 0.88, 4), abs=1e-4)


def test_score_is_clamped_to_unit_interval(c69):
    assert c69.compose_score(1.0, 1.0, entity_boost=0.14, keyword=1.0) <= 1.0
    assert c69.compose_score(0.0, 0.0, feedback_adjust=-0.35) >= 0.0
