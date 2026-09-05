"""c175 회귀 — 절차 2 봉쇄의 두 술어 대조 (관측 113 처치, 판정 P63).

계약은 셋이다:
  ① 존재 술어와 활성 술어를 **둘 다** 낸다 (하나만 내면 관측 113 재발이다)
  ② 문턱 상수를 **발명하지 않는다** — 갈림 경계만 낸다
  ③ mtime 미판독을 «오래됨»으로도 «최근»으로도 세지 않는다

실 원장·실 워킹트리의 상태는 이 파일이 assert하지 않는다 — 합성 표본만 쓴다
(관행 ⑯·⓴: 실 데이터에 결함의 존재를 assert하면 고치는 쪽이 벌을 받는다).
"""

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "c48", ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py")
assert SPEC and SPEC.loader
c48 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c48)

TOUCHED = "수확 이후 접촉"
UNTOUCHED = "수확 이후 무접촉"


def _row(path, since_now, vs_head=None, verdict=UNTOUCHED):
    return (path, since_now, vs_head, verdict)


def test_devloop_owned_paths_are_not_the_blockade_operand():
    """★ 절차 2가 막는 것은 «devloop 외»다. 내 편집분이 나를 막으면 안 된다."""
    rows = [
        _row("research/devloop/frictions.md", 0.0),
        _row("tests/test_devloop_step0_ordinals.py", 0.1),
    ]
    out = c48.predicate_divergence(rows)
    assert out["foreign"] == []
    assert out["existence"] == "해제"
    assert out["activity"] == "해제"
    assert out["diverges_at_or_below"] is None


def test_both_predicates_are_reported_not_just_one():
    """계약 ① — 관측 113의 핵. 존재만 내면 이 계기는 다시 결정에 불활성이다."""
    rows = [_row("forget/proxy.py", 168.9), _row("research/devloop/frictions.md", 0.0)]
    out = c48.predicate_divergence(rows)
    assert out["existence"] == "봉쇄"
    assert out["activity"] == "문턱 의존"
    assert out["diverges_at_or_below"] == 168.9


def test_divergence_boundary_is_the_youngest_foreign_path():
    """계약 ② — 경계는 **최연소** 외부 경로다. 최고령을 쓰면 갈림을 과대 보고한다."""
    rows = [
        _row("forget/proxy.py", 168.9),
        _row("research/replay/candidates_v0.jsonl", 21.2),
        _row("research/replay/verdict_dataset_v1.jsonl", 144.2),
    ]
    out = c48.predicate_divergence(rows)
    assert out["diverges_at_or_below"] == 21.2
    assert out["youngest_path"] == "research/replay/candidates_v0.jsonl"


def test_no_threshold_constant_is_invented():
    """계약 ② — 반환값 어디에도 «며칠이면 죽었다»는 수가 없다.

    c174가 상수 23에서 겪은 것: 하드코딩된 수는 다음 손에게 **규약으로 배달된다**.
    """
    rows = [_row("forget/proxy.py", 168.9), _row("a/b.jsonl", 21.2)]
    out = c48.predicate_divergence(rows)
    # 경계값은 **입력에서 온 값**이어야 한다 — 새로 생긴 수가 아니다.
    inputs = {r[1] for r in rows}
    assert out["diverges_at_or_below"] in inputs
    assert "threshold" not in out and "T" not in out


def test_a_freshly_touched_foreign_path_makes_the_predicates_agree():
    """갈림이 없는 쪽도 낸다 — 거짓 양성 억제 팔.

    타 트랙이 실제로 살아 있으면(방금 손댐) 두 술어는 상식적인 문턱에서 일치한다.
    이 팔이 없으면 계기는 매 사이클 «갈렸다»를 외치고 곧 무시된다(관측 87의 종착지).
    """
    rows = [_row("forget/proxy.py", 0.2, verdict=TOUCHED)]
    out = c48.predicate_divergence(rows)
    assert out["existence"] == "봉쇄"
    # 경계가 0.2h이므로 T > 0.2h인 어떤 문턱에서도 활성 술어 역시 «봉쇄»다.
    assert out["diverges_at_or_below"] == 0.2


def test_unreadable_mtime_makes_the_activity_predicate_undecidable():
    """계약 ③ — 못 읽은 경로를 조용히 빼면 «전부 죽었다»는 거짓 전수 주장이 만들어진다."""
    rows = [
        _row("forget/proxy.py", 168.9),
        _row("gone/file.py", None, None, "판정 불가(stat 실패·경로 부재)"),
    ]
    out = c48.predicate_divergence(rows)
    assert out["existence"] == "봉쇄"
    assert out["activity"] == "판정 불가"
    assert out["diverges_at_or_below"] is None
    assert out["unreadable"] == 1


def test_the_rule_text_still_reads_existence():
    """★ 이 회귀가 관측 113을 살아 있게 한다.

    처치는 계기 몫만이었고 규약 문면 개정은 게이트(`A-175.1`)다. 그러므로
    `cycle-prompt.md`가 아직 **존재** 술어를 읽는다는 사실이 참인 동안,
    두 술어 대조는 «있으나 마나»가 아니라 **미해소 마찰의 표지**다.

    정훈이 A-175.1을 승인해 문면이 바뀌면 이 절이 붉어진다 — 그것이 신호다.
    붉어지면 지우지 말고 관측 113의 해소를 원장에 적어라.
    """
    text = (ROOT / "research" / "devloop" / "cycle-prompt.md").read_text(encoding="utf-8")
    assert "미커밋 변경이 있으면" in text, (
        "cycle-prompt.md 절차 2의 술어가 바뀌었다 — A-175.1이 승인됐는가? "
        "그렇다면 관측 113은 해소이고 이 회귀는 그 사실을 적은 뒤 갱신해야 한다."
    )
