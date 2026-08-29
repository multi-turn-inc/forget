"""계기 ㉭(선언∖정본-diff 검산)의 계약 — c189 신설, 관측 116 수용 기준 ③.

왜 이 파일이 있는가. 관측 116은 c185가 «표 부기 1(A-168.1 행 44차)»를 세 채널에 선언하고
**완주**했는데 정본의 그 행이 43차에서 멈춰 있어서 났다. 계기가 그 대조를 대신하되,
계기 자신이 조용히 망가지면 같은 병이 한 층 아래에서 재발한다. 이 파일이 그 층을 잡는다.

**실-원장 값을 상수로 박지 않는다** — 관측 100(«회귀가 자기 사이클의 수확에 붉어진다»)과
관측 106(«회귀가 결함을 기대 상태로 잠갔다»)의 선례. 전부 합성 diff·합성 산문으로 검사한다.

계약 다섯 + ㉵ⓐ 셋 (c251 추가 — audit-250 R2 소비):
① **프레임 이동뿐인 행을 «실질 편집»으로 읽지 않는다** — 이것이 이 계기의 존재 이유다.
   프레임 이동은 매 사이클 전 행을 만지므로, 가르지 못하면 계기는 항상 «부기 있음»을 내고
   관측 116을 **원리적으로 못 잡는다**.
② **실질 편집을 프레임 이동으로 읽지 않는다** — 반대 방향의 거짓 음성.
③ **관측 116의 서식을 재현하면 질의가 뜬다** — 부기 선언 + 그 행은 프레임 이동뿐.
④ **신규/소멸 행을 ID 집합 차로 센다.**
⑤ **선언과 정본이 맞으면 침묵한다** — 정직한 사이클을 벌하지 않는다(관측 118의 교훈:
   정직 판정기의 오차는 정직한 쪽을 defame한다).
⑥ **취소선 동결 행은 «행이 없다» 질의에서 제외된다** — 해소 행은 보존+동결이라
   diff 부재가 정상이다(A-192.1 거짓 양성 14연속의 근절 규칙 ㉵ⓐ).
⑦ **동결 행이라도 재증분(frame_only)이면 질의가 산다** — ⓑ 승계 실패의 검출
   채널을 ㉵ⓐ가 침묵시키지 않는다.
⑧ **비동결 대상의 «행이 없다» 질의는 그대로 산다** — 수리가 제외를 넓히지 않는다.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c189_declare_diff.py"


def _load():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("c189_declare_diff", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    assert SCRIPT.exists(), f"계기 정본이 없다: {SCRIPT}"
    return _load()


# ── 계약 ① 프레임 이동뿐인 행은 실질 편집이 아니다 (이 계기의 존재 이유) ────────
def test_frame_only_row_is_not_substantive(mod):
    diff = (
        "--- a/research/devloop/gate-queue.md\n"
        "+++ b/research/devloop/gate-queue.md\n"
        "-| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 그대로 | **20사이클째** |\n"
        "+| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 그대로 | **21사이클째** |\n"
    )
    d = mod.parse_diff(diff)
    assert d["frame_only"] == ["A-168.1"]
    assert d["substantive"] == []


# ── 계약 ② 실질 편집은 프레임 이동으로 숨지 않는다 ────────────────────────────
def test_substantive_edit_is_detected_even_with_frame_move(mod):
    diff = (
        "-| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 그대로 | **20사이클째** |\n"
        "+| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 그대로 **★ 48차 표본 추가** | **21사이클째** |\n"
    )
    d = mod.parse_diff(diff)
    assert d["substantive"] == ["A-168.1"]
    assert d["frame_only"] == []


# ── 계약 ③ 관측 116의 서식을 재현하면 질의가 뜬다 ────────────────────────────
def test_observation_116_shape_raises_a_query(mod):
    decl = mod.parse_declaration(
        "**c185 정산**: 신규 상신 **0** · 해소 **0** · 서열 변동 **0** · "
        "**표 부기 1**(A-168.1 행 44차 — 세 갈래)"
    )
    assert decl["counts"]["표 부기"] == 1
    assert decl["부기_대상"] == ["A-168.1"]
    diff = (
        "-| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 | **17사이클째** |\n"
        "+| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 | **18사이클째** |\n"
    )
    d = mod.parse_diff(diff)
    # 부기를 선언했는데 그 행은 프레임 이동뿐 — 정확히 관측 116이다.
    assert decl["부기_대상"][0] in d["frame_only"]


# ── 계약 ④ 신규/소멸 행은 ID 집합 차로 센다 ──────────────────────────────────
def test_added_and_removed_rows_are_counted_by_id_set(mod):
    diff = (
        "+| 24 | **A-189.1** (신규 청구) | \"승인\" | 근거 | **1사이클째** |\n"
        "-| 9 | **A-101.1** (해소된 청구) | \"승인\" | 근거 | **80사이클째** |\n"
    )
    d = mod.parse_diff(diff)
    assert d["added"] == ["A-189.1"]
    assert d["removed"] == ["A-101.1"]


# ── 계약 ⑤ 선언과 정본이 맞으면 침묵한다 (정직을 벌하지 않는다 — 관측 118) ────
def test_declaration_matching_canon_is_silent(mod):
    decl = mod.parse_declaration(
        "신규 상신 **0** · 해소 **0** · 서열 변동 **0** · **표 부기 1**(A-168.1 행 48차)"
    )
    diff = (
        "-| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 | **20사이클째** |\n"
        "+| 18' | **A-168.1** (검출기 어휘) | \"승인\" | 근거 **★ 48차 표본** | **21사이클째** |\n"
    )
    d = mod.parse_diff(diff)
    assert decl["counts"]["신규 상신"] == 0 and not d["added"]
    assert decl["counts"]["해소"] == 0 and not d["removed"]
    assert decl["부기_대상"][0] in d["substantive"]


# ── 계약 ⑥ 취소선 동결 행은 «행이 없다» 질의에서 제외된다 (㉵ⓐ — c251) ──────
def test_frozen_row_absent_from_diff_is_excluded_with_note(mod):
    canon = (
        "| **26** | **A-192.1** (해소된 청구 — 보존 행) | \"승인\" | 효과 | "
        "**~~1사이클째~~ → 상신 당일 해소** (조건 소멸) |\n"
        "| 30 | **A-241.1** (살아 있는 청구) | \"승인\" | 효과 | **10사이클째** |\n"
    )
    frozen = mod.frozen_ids(canon)
    assert frozen == {"A-192.1"}, "동결 술어가 이동기 ㉵ⓑ와 갈렸다"
    # 기전 재현(한계 ① 과수집): 이동기 서술의 ID가 부기 대상으로 오독된다.
    decl = mod.parse_declaration(
        "**표 부기 1**(서열 1′ 재실측) · 취소선 스킵 1행 = A-192.1 재증분 0"
    )
    assert "A-192.1" in decl["부기_대상"]
    d = mod.parse_diff("")  # 동결 행은 diff에 없는 것이 정상이다
    q, notes = mod.build_queries(decl, d, frozen)
    assert not any("A-192.1" in x for x in q), f"동결 행이 질의됐다: {q}"
    assert any("A-192.1" in x and "동결" in x for x in notes), notes


# ── 계약 ⑦ 동결 행의 재증분(frame_only)은 여전히 질의된다 (ⓑ 승계 실패 채널) ──
def test_frozen_row_reincremented_is_still_queried(mod):
    decl = mod.parse_declaration("**표 부기 1**(A-192.1 행)")
    diff = (
        "-| **26** | **A-192.1** (해소) | \"승인\" | 효과 | **~~1사이클째~~ → 해소** **59사이클째** |\n"
        "+| **26** | **A-192.1** (해소) | \"승인\" | 효과 | **~~1사이클째~~ → 해소** **60사이클째** |\n"
    )
    d = mod.parse_diff(diff)
    assert d["frame_only"] == ["A-192.1"]
    q, notes = mod.build_queries(decl, d, {"A-192.1"})
    assert any("프레임 이동뿐" in x for x in q), "㉵ⓐ가 ⓑ 승계-실패 검출 채널을 침묵시켰다"
    assert notes == []


# ── 계약 ⑧ 비동결 대상의 «행이 없다» 질의는 그대로 산다 ─────────────────────
def test_unfrozen_absent_target_is_still_queried(mod):
    decl = mod.parse_declaration("**표 부기 1**(A-168.1 행 49차)")
    q, notes = mod.build_queries(decl, mod.parse_diff(""), frozen=set())
    assert any("A-168.1" in x and "행이 없다" in x for x in q)
    assert notes == []


# ── 자기 서술 계약: 선언된 한계가 문서에 살아 있는가 (관행 ⑮) ───────────────
def test_declared_limits_are_present(mod):
    doc = mod.__doc__ or ""
    for mark in ["한계", "프레임 이동", "고발이 아니라 질의", "서열 변동은 이 눈 밖",
                 "취소선 동결", "㉵ⓐ"]:
        assert mark in doc, f"선언된 한계가 문서에서 사라졌다: {mark}"
