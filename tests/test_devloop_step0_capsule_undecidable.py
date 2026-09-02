"""c48_step0_check 캡슐 축 «판정 불가»(비도달) 분리 + 프레임 인용문 배제 (c286 신설 — 계기 큐 ㉳·㉩′ 집행).

왜 이 파일이 있는가. 두 건 다 «깨진 devloop 소유 계기의 자기 수리»(봉쇄 중·제품 코드 0행)이고
둘 다 파트 O(상태형 계수기) 이웃이다.

**㉳ — 비도달과 무용이 한 값(miss)에 합쳐져 있었다 (P67 한계 ④ · c192·c230 표본).**
캡슐 축 `restore_grade_capsule`의 정의역은 {miss, partial}뿐이었다. c192는 1세션이 «판정
불가»를 산문에 적고 2세션이 miss로 **대체**했고, c230은 SessionStart 훅 무발화를 «어휘 4치
제약»으로 miss에 **강제** 기재했다(c286 재실측 `tmp/c286_capsule_census.py`: 두 행 다 필드값
miss·산문만 «판정 불가» · 분포 miss 142·partial 53·무기재 91). 그래서 «캡슐 miss 연속»은
«캡슐이 왔는데 무용»과 «캡슐이 오지 않았다»를 한 수로 셌다. 처치 = 셋째 값
`CAPSULE_UNDECIDABLE`을 원장 어휘로 열고, `field_streak(exclude=…)`가 그 값의 행을
**정의역 밖**(연속을 잇지도 끊지도 않음)으로 빼 `excluded`에 따로 돌려준다. 캡슐 축은 c91
원장 파생 필드이고 지시서 절차 0의 4치는 종합 축 어휘라 지시서 개정 불요(c285 회고 확인).
소급 편집 0 — c192·c230은 miss인 채다.

**㉩′ — 서식을 말하는 문장을 서식을 쓰는 문장으로 읽었다 (c284 «미해석 1»).**
c283 `work`가 서식 이름 «프레임 = 자기행 포함 cN»을 **인용**했고(리터럴 `cN`·선언 아님)
`FRAME_LOOSE_RX`가 그것을 «미해석»으로 세어 실원장 회귀가 «미해석 1»을 인쇄했다. 셋째
서식 출현이 아니라 느슨 탐침의 인용문 거짓 양성이다. c286 센서스(`tmp/c286_frame_next_census.py`
— 정본 136자리·비정본 4자리)는 인용의 모양이 셋임을 냈다(리터럴 `cN` · 토큰을 닫는 따옴표
«「프레임 =」» · 코드 식별자 «= old_n»). 처치 = `FRAME_LITERAL_RX`로 그 자리를 건너뛰고
`quoted_frame_fields`가 셋째 갈래에 이름을 준다 — 실원장 항등식은 «해석 ∨ 미해석 ∨ 인용»으로
닫힌다. 같은 필드에 진짜 미해석이 함께 있으면 그것은 여전히 돌려준다.

관행 ⑯: 능력은 **합성 표본**으로 고정하고, 실 원장에는 프레임 독립 항등식만 걸고 분포는
**인쇄**한다. `tests/test_devloop_step0_ordinals.py` 캡슐 절은 무접촉(구판 호출 = exclude
없음 = 결과 동일이 계약 ④).
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_capsule_undecidable", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

FIELD = "restore_grade_capsule"
UND = c48.CAPSULE_UNDECIDABLE
EXC = c48.STREAK_EXCLUDE[FIELD]


def _rows(pairs):
    """(cycle, restore_grade_capsule) 목록을 원장 행 모양으로. 합성 주입 경로."""
    return [{"cycle": c, FIELD: v} for c, v in pairs]


# ── ㉳ 계약 ①~⑥ ──────────────────────────────────────────────────────────────

def test_undecidable_neither_breaks_nor_extends_the_miss_streak():
    """★ ㉳의 핵 (계약 ①). 비도달 행은 정의역 밖이다 — 연속을 잇지도 끊지도 않는다.
    구판(exclude 없음)은 같은 표본에서 중단으로 읽어 연속 1을 냈다: 비도달이 «캡슐
    유용»으로 계상되는 방향이다."""
    rows = _rows([(1, "partial"), (2, "miss"), (3, UND), (4, "miss")])
    st = c48.field_streak(rows, FIELD, "miss", EXC)
    assert st["streak"] == 2, st
    assert st["break"] == (1, "partial"), st
    assert st["excluded"] == [3], st
    assert st["domain"] == 3 and st["off_value"] == [1], st
    old = c48.field_streak(rows, FIELD, "miss")
    assert old["streak"] == 1 and old["break"] == (3, UND), old


def test_undecidable_at_the_tail_keeps_the_ledger_frame():
    """계약 ②. 마지막 행이 비도달이어도 프레임(`frame_last`)은 그 행이다 — 프레임은
    «원장 행 cN까지»이고 제외 행도 원장에 있다. 연속은 그 앞 miss 둘이다."""
    rows = _rows([(1, "miss"), (2, "miss"), (3, UND)])
    st = c48.field_streak(rows, FIELD, "miss", EXC)
    assert st["streak"] == 2 and st["frame_last"] == 3, st
    assert st["span"] == (1, 2) and st["excluded"] == [3], st


def test_all_undecidable_is_unmeasured_not_zero():
    """계약 ③. 전 행 비도달이면 정의역 0 = **미측정**이다('연속 0'이 아니다) —
    `span` None이 인쇄의 «미측정» 분기를 연다. 제외 목록은 그대로 돌려준다."""
    st = c48.field_streak(_rows([(1, UND), (2, UND)]), FIELD, "miss", EXC)
    assert st["streak"] == 0 and st["domain"] == 0 and st["span"] is None, st
    assert st["excluded"] == [1, 2] and st["frame_last"] == 2, st


def test_default_exclude_reproduces_the_old_result():
    """계약 ④ (무접촉 보증). exclude를 주지 않으면 구판과 값이 같다 — `excluded` 키만
    빈 목록으로 추가된다. ordinals 캡슐 절이 이 호출 형태로 살아 있다."""
    rows = _rows([(1, "partial"), (2, "miss"), (3, "partial"), (4, "miss"), (5, "miss")])
    st = c48.field_streak(rows, FIELD, "miss")
    assert st["streak"] == 2 and st["domain"] == 5 and st["break"] == (3, "partial")
    assert st["off_value"] == [1, 3] and st["span"] == (1, 5) and st["frame_last"] == 5
    assert st["excluded"] == []


def test_exclude_registry_targets_only_the_capsule_axis():
    """계약 ⑤. 제외값 등록은 캡슐 축뿐이다 — `fixed`·`rt` 계수기의 정의역은 무접촉.
    어휘값 자체도 고정한다(원장 기재 어휘 = 계기 어휘, 사본 없음)."""
    assert UND == "판정 불가"
    assert set(c48.STREAK_EXCLUDE) == {FIELD}
    for _, field, _, _ in c48.STREAK_COUNTERS:
        if field != FIELD:
            assert c48.STREAK_EXCLUDE.get(field, ()) == ()


def test_real_ledger_undecidable_is_a_partition_of_the_old_domain():
    """실 원장 **인쇄 전용** + 프레임 독립 항등식: 제외 정의역 + 제외 행 = 구판 정의역,
    그리고 제외판 연속 ≥ 구판 연속(제외는 중단만 걷어낼 수 있다). 현재 «판정 불가»
    행 수는 인쇄만 한다 — 0이든 아니든 assert하지 않는다(관행 ⑯·관측 106 경계)."""
    ledger = ROOT / "research" / "devloop" / "metrics.jsonl"
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    new = c48.field_streak(rows, FIELD, "miss", EXC)
    old = c48.field_streak(rows, FIELD, "miss")
    assert new["domain"] + len(new["excluded"]) == old["domain"], (new, old)
    assert new["streak"] >= old["streak"], (new, old)
    assert new["frame_last"] == old["frame_last"]
    print(f"[인쇄] 캡슐 축 «{UND}» 행 = {len(new['excluded'])}건 / 정의역(구판) {old['domain']}행"
          f" · miss 연속 제외판 {new['streak']} · 구판 {old['streak']}")


# ── ㉩′ 계약 ⑦~⑨ ─────────────────────────────────────────────────────────────

#: c283 `work`의 모양을 뜬 합성 표본 — 서식 이름을 인용한다(리터럴 cN·선언 아님).
C283_SHAPED = {
    "cycle": 283,
    "work": ("파트 O FRAME_RX가 «프레임 = 자기행 포함 cN» 서식을 못 읽어 정직 기재를 "
             "«선언 프레임 무기재»로 인쇄하던 사각 수리."),
}


def test_quoted_format_name_is_not_an_unparsed_frame():
    """★ ㉩′의 핵 (계약 ⑦). 서식 이름의 인용(리터럴 cN)은 선언도 미해석도 아니다 —
    구판 느슨 탐침은 이것을 «미해석»으로 세어 실원장 회귀에 «미해석 1»을 냈다."""
    assert c48.declared_frames(C283_SHAPED) == {}
    assert c48.unparsed_frame_fields(C283_SHAPED) == {}


def test_quote_does_not_hide_a_real_unparsed_frame_in_the_same_field():
    """계약 ⑧. 인용을 건너뛰되 같은 필드의 진짜 미해석은 여전히 돌려준다 — 인용 하나가
    미해석을 가리면 관측 104의 침묵이 재발한다."""
    row = {"cycle": 9,
           "frictions_note": ("«프레임 = 자기행 포함 cN» 서식 얘기. 값은 **3연속**"
                              "[프레임 = 직전 행까지 c8].")}
    got = c48.unparsed_frame_fields(row)
    assert set(got) == {"frictions_note"}, got
    assert got["frictions_note"].startswith("프레임 = 직전 행까지 c8"), got


def test_literal_regex_does_not_swallow_numbered_frames():
    """계약 ⑨ (거짓 음성 억제 팔). 리터럴 배제기는 숫자 프레임에 걸리지 않는다 —
    «프레임 = 자기행 포함 c9»는 정본 서식으로 계속 읽힌다."""
    row = {"cycle": 9, "frictions_note": "**2연속**[프레임 = 자기행 포함 c9]."}
    assert c48.FRAME_LITERAL_RX.search(row["frictions_note"]) is None
    assert c48.declared_frames(row) == {"frictions_note": 9}
    assert c48.unparsed_frame_fields(row) == {}
    assert c48.quoted_frame_fields(row) == {}


def test_bracket_quoted_token_and_code_identifier_are_quotations():
    """계약 ⑩ (c286 센서스의 나머지 두 모양). «「프레임 =」 기재 122쌍»(토큰을 닫는 따옴표)과
    «(직전 프레임 = old_n)»(코드 식별자)도 인용이다 — 리터럴 `cN`만 배제하면 실원장에
    «미해석 2»가 남았다(c286 실측). 셋 다 `quoted_frame_fields`가 이름을 붙인다."""
    row = {
        "cycle": 284,
        "frictions_note": "「프레임 =」 기재 122쌍 중 해석 106·미해석 16 → 수리 후 122·0",
        "work": "move_frame이 perm_report['settlement_prev'](직전 프레임 = old_n)로 싣는다.",
    }
    assert c48.declared_frames(row) == {}
    assert c48.unparsed_frame_fields(row) == {}
    assert c48.quoted_frame_fields(row) == {"frictions_note": 1, "work": 1}


def test_korean_unknown_format_is_still_unparsed_not_quoted():
    """계약 ⑪ (한계 경계 고정). 한글로 시작하는 미지 서식은 여전히 «미해석»이다 — 배제기는
    닫는 따옴표·ASCII 식별자만 인용으로 본다. 선언된 한계: ASCII 식별자로 시작하는
    미지 서식은 인용으로 오분류된다(침묵이 아니라 «인용» 계수로 이동)."""
    row = {"cycle": 5, "frictions_note": "fixed 0 = **3연속**[프레임 = 직전 행까지 c4]."}
    assert c48.unparsed_frame_fields(row) != {}
    assert c48.quoted_frame_fields(row) == {}
    shape = {"cycle": 6, "frictions_note": "**1연속**[프레임 = N=6]."}
    assert c48.unparsed_frame_fields(shape) == {}
    assert c48.quoted_frame_fields(shape) == {"frictions_note": 1}
