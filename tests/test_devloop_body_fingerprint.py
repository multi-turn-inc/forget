"""c48_step0_check.compare_fingerprint — P21 처치(몸 지문)의 판정 논리 회귀 감시.

스크립트는 research/devloop/scripts/에 살지만 **판정 도구**이므로 감시 대상이다
(선례: tests/test_gate_audit_aggregate.py).

이 테스트가 지키는 성질은 하나다: **모르는 것을 '일치'로 보고하지 않는다.**
관측 30(c66)의 병리가 조용한 흡수였다 — 몸이 바뀌었는데 아무 계기도 그것을
말하지 않아 루프가 다섯 사이클을 틀린 전제로 돌았다. 채취 실패를 '일치'로
접어버리는 지문은 그 병리를 정확히 재생산하므로, 그 경로를 못으로 박아둔다.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

compare = c48.compare_fingerprint
UNKNOWN = c48.UNKNOWN

BASE = {"dist_info": "forget_ai-0.4.0", "store_vec": "MEB1:384"}


def test_identical_is_match():
    assert compare(dict(BASE), dict(BASE)) == ("일치", [], [])


def test_changed_value_demands_recalibration():
    verdict, changed, unknown = compare({**BASE, "store_vec": "MEB1:1024"}, dict(BASE))
    assert verdict == "재교정 필요"
    assert changed == ["store_vec"]
    assert unknown == []


def test_unacquired_field_is_never_reported_as_match():
    """채취 실패(서버 정지·lsof 미승인 등)는 '일치'가 아니라 '판정 불가'다."""
    verdict, changed, unknown = compare({**BASE, "store_vec": UNKNOWN}, dict(BASE))
    assert verdict == "판정 불가"
    assert changed == []
    assert unknown == ["store_vec"]


def test_new_key_absent_from_baseline_is_unknown_not_match():
    """지문 정의를 넓히는 것은 자[尺] 변경이고 baseline 커밋으로만 승인된다."""
    verdict, changed, unknown = compare({**BASE, "new_axis": "x"}, dict(BASE))
    assert verdict == "판정 불가"
    assert unknown == ["new_axis"]


def test_missing_baseline_file_never_yields_match():
    verdict, changed, unknown = compare(dict(BASE), {})
    assert verdict == "판정 불가"
    assert sorted(unknown) == sorted(BASE)


def test_real_change_outranks_unknown():
    """변경과 미채취가 함께면 변경이 이긴다 — 재교정 사유를 미지에 묻지 않는다."""
    verdict, changed, unknown = compare(
        {"dist_info": "forget_ai-0.5.0", "store_vec": UNKNOWN}, dict(BASE))
    assert verdict == "재교정 필요"
    assert changed == ["dist_info"]
    assert unknown == ["store_vec"]


def test_editable_target_extracts_decoded_path():
    """c197 확장: editable 설치는 미채취가 아니라 대상 경로가 지문이다."""
    text = json.dumps({"dir_info": {"editable": True},
                       "url": "file:///Users/x/%EB%82%B4-repo"})
    assert c48.editable_target(text) == "/Users/x/내-repo"


def test_editable_target_never_guesses():
    """editable 선언 없음·깨진 JSON·비 file 스킴은 전부 None — UNKNOWN 경로 유지."""
    assert c48.editable_target(json.dumps({"url": "file:///x"})) is None
    assert c48.editable_target("not json") is None
    assert c48.editable_target(json.dumps(
        {"dir_info": {"editable": True}, "url": "https://pypi.org/x"})) is None
    assert c48.editable_target(json.dumps(["dir_info"])) is None


def test_baseline_file_covers_every_fingerprint_key():
    """baseline과 지문 정의가 어긋나면 대조가 영구 '판정 불가'로 죽는다.

    part_body()가 채취하는 키 집합을 여기 고정한다 — 한쪽만 고치면 이 테스트가 깨진다.
    """
    baseline = json.loads((ROOT / "research" / "devloop" / "body-fingerprint.json")
                          .read_text(encoding="utf-8"))["fingerprint"]
    expected = {"dist_info", "installed_vs_repo", "effective_embedding",
                "embedding_resolution", "checks_embedding", "store_vec"}
    assert set(baseline) == expected
