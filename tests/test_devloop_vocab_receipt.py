# -*- coding: utf-8 -*-
"""vocab_receipt(㉺ 집행 · 관측 128 ③) 회귀 — 합성 픽스처만 (관측 100·106 경계).

실대장 값을 상수로 박지 않는다(관측 100: 실 원장 상수는 자기 사이클 수확에
붉어진다). 결함을 기대 상태로 잠그지 않는다(관측 106) — 계약은 분류 술어와
서식·미측정 강등이지, 오늘의 위반 수가 아니다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                "research", "devloop", "scripts"))
from vocab_receipt import format_receipt, receipt, run_for_harvest  # noqa: E402

KNOWN = ("P39",)


def test_contract_1_split_fresh_vs_known():
    """계약 ①: 분류 술어 = KNOWN_VOCAB_OFFENDERS 등재 여부 — 파트 P와 동일."""
    errors = [("P39", ["어휘 밖 값 'x'"]), ("P70", ["어휘 밖 값 'y'"])]
    rec = receipt(errors, KNOWN)
    assert [pid for pid, _ in rec["known"]] == ["P39"]
    assert [pid for pid, _ in rec["fresh"]] == ["P70"]


def test_contract_2_clean_ledger_prints_zero():
    """계약 ②: 위반 0 → 신규 0·기지 0, 서식에 «신규 위반 0» 명시."""
    rec = receipt([], KNOWN)
    assert rec["fresh"] == [] and rec["known"] == []
    text = "\n".join(format_receipt(10, rec, 16))
    assert "신규 위반 0" in text
    assert "대장 10건" in text


def test_contract_3_fresh_violation_is_loud():
    """계약 ③: 신규 위반은 pid·원문·하드 에러 표지를 전부 인쇄한다 — 침묵 없음."""
    errors = [("P99", ["어휘 밖 값 '미판정'"])]
    rec = receipt(errors, KNOWN)
    text = "\n".join(format_receipt(5, rec, 16))
    assert "P99" in text and "'미판정'" in text
    assert "하드 에러" in text and "지금 처치하라" in text
    assert "신규 위반 0" not in text


def test_contract_4_known_only_stays_clean():
    """계약 ④: 기지 등재분만 있으면 «신규 위반 0» 유지 + 기지 줄 별도 인쇄
    (늑대소년 방지 — 파트 P가 KNOWN_VOCAB_OFFENDERS를 도입한 이유와 동일)."""
    errors = [("P39", ["a", "b"])]
    rec = receipt(errors, KNOWN)
    text = "\n".join(format_receipt(7, rec, 16))
    assert "신규 위반 0" in text
    assert "[기지·게이트 대기] P39: 2건" in text


def test_contract_5_gate_failure_is_unmeasured_not_zero(capsys):
    """계약 ⑤: 게이트 고장 → None(미측정) 반환 + 미측정 인쇄 — 0으로 접지 않는다."""
    def broken_load():
        raise RuntimeError("synthetic gate failure")

    out = run_for_harvest(load=broken_load)
    assert out is None
    printed = capsys.readouterr().out
    assert "미측정" in printed and "위반 0" in printed  # "'위반 0'으로 읽지 말 것" 경고문


def test_contract_6_injected_load_counts_fresh(capsys):
    """계약 ⑥: 주입 로더 경로 — 반환값 = 신규 위반 수 (harvest_stat 종료 코드의 피연산자)."""
    def load():
        return 3, [("P39", ["k"]), ("P77", ["f1"]), ("P88", ["f2"])], 16, KNOWN

    assert run_for_harvest(load=load) == 2
    assert "신규 2" in capsys.readouterr().out
