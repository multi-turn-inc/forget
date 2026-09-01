"""c48_step0_check 상태형 계수기 — 이름값 미끼와 선언 프레임 (c173 신설, 관측 109·110 · P52 (a) 반증).

왜 이 파일이 있는가. P52는 상태형 계수기(원장 필드의 연속 상태를 세는 수)를 계기에
옮겼고, «손 인쇄 대 계기» 대조 줄을 붙여 *"반증 사건은 다음 손이 찾지 않아도 화면에
뜬다"*고 등록했다. c173이 그 창(c169~c173)을 판정하며 대조 줄 자체가 두 겹으로 고장난
것을 실측했다.

**관측 109 — 계수기의 이름에 값이 들어 있다.** 라벨이 *"`frictions_fixed` 0 연속"*이므로
그 계수기를 이름으로 부르는 정직한 문장이 값 추출기의 미끼가 된다. c172는
*"`fixed` 0연속은 이 행에서 **1연속**이다"*라고 적었고, 구판은 dict 순서 첫 매치를 써서
이름값 **0**을 «손 인쇄»로 읽고 *"어긋남 -1"*을 인쇄했다. 그 행의 자기 주장은 **1**이며
계기값과 **일치**한다 — 계기가 **없는 갈라짐을 고발**했다. 관측 108과 기전이 다르다:
108의 미끼는 다른 사이클의 **인용값**이었고 이것은 **이 계수기 자신의 이름**이다.
인용은 지울 수 있으나 이름은 지울 수 없다.

**그리고 이것이 절반이다 — 나머지 절반이 더 크다.** 창 c169~c172 실측으로 구판은 실제
손 인쇄 **4건 중 0건**을 잡았다: c169 *"`frictions_fixed` 0 = **26연속**"* · c170
*"`fixed` 0을 또 적는다 — **27연속**"* · c171 *"0 아니다. **28연속**"*이 전부 침묵했다.
같은 이름이 **참 양성도 가로막는다** — `fixed` 뒤의 숫자 슬롯을 이름값 0이 먼저 먹고
`[^0-9]` 창이 그 0을 넘지 못하기 때문이다. **검출률 0/4 · 거짓 경보 1.** 즉 이 대조 줄은
5사이클 동안 한 번도 작동하지 않았고, P52 (a)가 *"반증 사건은 화면에 뜬다"*고 기댄
장치가 그것이다. 처치는 **어휘 식별과 값 추출을 두 단계로 가르는 것**이다.

**관측 110 — 값의 프레임을 아무도 검사하지 않았다.** 구판은 값을 자기가 고른 한
프레임에서만 재고, 행이 **스스로 선언한** 프레임이 그 값의 프레임과 같은지는 묻지
않았다. c172는 값 **1**(자기행 포함 = 프레임 c172)에 라벨 *"[프레임 = 원장 최종 c171 ·
c172 미포함]"*을 달았다. 선언 프레임 c171의 참값은 **0**이다. 어느 쪽을 의도로 읽어도
그 행의 절반이 거짓이며, 571 초록이 그것을 말하지 않았다. **이것이 P52 (a) 반증의
실체이고, 구판이 고발한 «어긋남 -1»은 그 실체가 아니었다** — 계기는 옳은 사건을 틀린
근거로 가리켰다.

관행 ⑯을 지킨다: **능력은 합성 표본으로 고정**하고, 실 원장에는 **프레임 독립 항등식**
하나만 걸고 현재 분포는 **인쇄**한다. 실 원장에 «결함의 존재»를 assert하면 A-171.1이
승인돼 기전이 고쳐질 때 고치는 쪽이 벌을 받는다(관측 106의 자물쇠).
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_streak_frame", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

FIXED_VOCAB = c48.STREAK_COUNTERS[0][3]

#: c172 행의 모양을 그대로 뜬 합성 표본. 이름값 0이 자기 주장 1보다 **먼저** 온다 —
#: 구판이 첫 매치를 쓴 자리이고, 그 순서가 미끼의 전부다.
C172_SHAPED = {
    "cycle": 172,
    "frictions_note": (
        "**fixed 0** — 파트 F 기계 정의로 이탈한 절이 **없다**. "
        "`fixed` 0연속은 이 행에서 **1연속**이다[프레임 = 원장 최종 c171 · c172 미포함]."
    ),
}


def _rows(pairs):
    """(cycle, frictions_fixed) 목록을 원장 행 모양으로. 합성 주입 경로."""
    return [{"cycle": c, "frictions_fixed": v} for c, v in pairs]


def test_claim_matches_returns_every_mention_with_its_field():
    """계약 ①: 전량 반환이다. 첫 매치 하나로 줄이면 관측 109가 재발한다."""
    got = c48.streak_claim_matches(C172_SHAPED, FIXED_VOCAB)
    assert [v for _, v in got] == [0, 1], got
    assert {f for f, _ in got} == {"frictions_note"}, got


def test_name_value_decoy_does_not_become_a_divergence():
    """★ 관측 109 처치의 핵. 이름값 0이 있어도 자기 주장 1이 계기값과 일치하므로
    «갈라짐»이 아니다. 구판은 이 자리에서 '어긋남 -1'을 인쇄했다."""
    vals = {v for _, v in c48.streak_claim_matches(C172_SHAPED, FIXED_VOCAB)}
    # 프레임 c172(자기행 포함) 기준 계기값 = 1
    st = c48.field_streak(_rows([(170, 0), (171, 2), (172, 0)]), "frictions_fixed", 0)
    assert st["streak"] == 1, st
    assert st["streak"] in vals, (st, vals)


def test_declared_frames_are_per_field_not_first_match_of_the_row():
    """계약 ②: 프레임은 **필드별**이다. 행 단위 첫 매치는 한 계수기의 프레임으로
    다른 계수기의 값을 심판하게 되고, 그것이 관측 108·109의 공통 기전이다."""
    row = {
        "cycle": 900,
        "frictions_note": "0 연속은 **3연속**이다[프레임 = 원장 최종 c899].",
        "open_observations_note": "캡슐 miss **7연속**[프레임 = 원장 최종 c880].",
    }
    assert c48.declared_frames(row) == {
        "frictions_note": 899,
        "open_observations_note": 880,
    }


def test_row_without_frame_declaration_yields_no_frame():
    """선언이 없으면 없다고 말한다 — 없는 프레임을 추측하지 않는다."""
    assert c48.declared_frames({"cycle": 1, "frictions_note": "**5연속**이다."}) == {}


def test_frame_divergence_is_detectable_on_the_c172_shape():
    """★ 관측 110 처치의 핵. 값 1은 선언 프레임 c171에서 **0**이다 — 갈렸다.

    이 테스트가 재는 것은 «c172가 틀렸다»가 아니라 «갈라짐이 계산 가능하다»다.
    실 원장의 상태는 이 파일이 assert하지 않는다(관행 ⑯).
    """
    rows = _rows([(170, 0), (171, 2), (172, 0)])
    frame = c48.declared_frames(C172_SHAPED)["frictions_note"]
    assert frame == 171
    at_declared = c48.field_streak(
        [r for r in rows if r["cycle"] <= frame], "frictions_fixed", 0)
    at_inclusive = c48.field_streak(rows, "frictions_fixed", 0)
    assert at_declared["streak"] == 0, at_declared
    assert at_inclusive["streak"] == 1, at_inclusive
    assert at_declared["streak"] != at_inclusive["streak"]


def test_frame_agreement_is_not_flagged():
    """거짓 양성 억제 팔. c170의 모양(값 27 · 선언 프레임 c169)은 갈라지지 않는다 —
    이 팔이 없으면 계기는 매 사이클 갈라짐을 외치고 곧 무시된다(관측 87의 종착지)."""
    row = {"cycle": 170,
           "frictions_note": "`frictions_fixed` 0을 또 적는다 — **27연속**"
                             "[프레임 = 원장 최종 c169]."}
    rows = _rows([(c, 0) for c in range(143, 170)])
    frame = c48.declared_frames(row)["frictions_note"]
    st = c48.field_streak([r for r in rows if r["cycle"] <= frame], "frictions_fixed", 0)
    claims = {v for _, v in c48.streak_claim_matches(row, FIXED_VOCAB)}
    assert frame == 169
    assert st["streak"] == 27, st
    assert st["streak"] in claims, (st, claims)


def test_far_away_number_in_the_same_field_is_not_a_candidate():
    """★ 눈먼 것을 고치다 없는 갈라짐을 만들지 않는다. c172 `restore_note`의 훅 계수기
    (*"c167 이래 **6연속** 동일 증상"*)는 «캡슐» 낱말과 같은 필드에 살지만 남의 계수기다.

    필드 전체를 긁던 첫 판본은 이것을 캡슐 후보로 세어 **무기재를 «전량 불일치»로
    오고발**했다 — 관측 108이 겨눈 병을 처치 안에서 재현한 셈이다.
    """
    capsule_vocab = c48.STREAK_COUNTERS[1][3]
    row = {
        "cycle": 172,
        "restore_note": (
            "① **캡슐/SessionStart B층 훅이 또 심장박동 트랙**(*박자 2026-08-19* · "
            "shed/verified/cli.py)이고 **자기 폴백 실패를 선언**했다"
            "(*'미결: (구조적 폴백 — LLM 요약 실패)'*) — **c167 이래 6연속** 동일 증상."
        ),
    }
    assert c48.streak_claim_matches(row, capsule_vocab) == []


def test_nearby_number_after_the_vocabulary_is_a_candidate():
    """거짓 음성 억제 팔 — 창을 좁힌 대가로 참 후보를 잃지 않았음을 고정한다."""
    capsule_vocab = c48.STREAK_COUNTERS[1][3]
    row = {"cycle": 169, "open_observations_note": "캡슐 miss = **49연속**[정의역 78행]."}
    assert [v for _, v in c48.streak_claim_matches(row, capsule_vocab)] == [49]


def test_headline_credits_the_declared_frame_not_only_the_self_inclusive_one():
    """★ 관측 111 처치의 핵. 규약은 «파트 O 인쇄를 그대로 전사»(프레임 N−1)를 요구하고
    이 눈은 프레임 N에서 잰다 — 헤드라인이 자기행 포함 값만 보면 **규약을 지킨 행이
    구조적으로 언제나 «전량 불일치»가 된다.** c173 행이 정확히 그 모양이었다."""
    claims = [("restore_note", 53)]          # 전사값 = 프레임 c172
    frame_streaks = {"restore_note": 53}
    # 자기행 포함 프레임(c173)의 값은 54 — 행이 쓸 때는 알 수 없던 수다.
    assert c48.streak_headline(claims, frame_streaks, 54, 173) == [
        "[restore_note] 선언 프레임의 값 53"]


def test_headline_credits_both_rulers_when_the_row_wrote_both():
    """c169는 두 프레임을 다 적었고 P52 판정에서 «정직한 서식»으로 계상됐다 —
    어느 하나로 좁히면 그 서식이 벌을 받는다. 둘 다 이름으로 인정한다."""
    claims = [("frictions_note", 1), ("frictions_note", 2)]
    got = c48.streak_headline(claims, {"frictions_note": 1}, 2, 173)
    assert got == ["자기행 포함 프레임 c173", "[frictions_note] 선언 프레임의 값 1"]


def test_headline_stays_empty_when_neither_ruler_is_satisfied():
    """거짓 음성 억제 팔 — 처치가 «항상 적중»으로 무르지 않았음을 고정한다.
    두 자[尺] 어느 쪽도 후보에 없으면 그것이 진짜 갈라짐이다."""
    claims = [("frictions_note", 30)]        # 남의 프레임에서 인용해 온 값
    assert c48.streak_headline(claims, {"frictions_note": 1}, 2, 173) == []


def test_headline_ignores_a_frame_declared_in_another_field():
    """프레임은 필드별이다 — 한 계수기의 프레임으로 다른 계수기의 값을 심판하면
    관측 108·109·110의 공통 기전을 네 번째로 반복한다."""
    claims = [("frictions_note", 7)]
    # 선언 프레임은 restore_note 것이므로 frictions_note의 7을 정당화하지 못한다.
    assert c48.streak_headline(claims, {"restore_note": 7}, 2, 173) == []


# ── c283 — 계기 큐 ㉩ 집행 (관측 110 사각 수리: FRAME_RX 서식 변이) ──────────────
#
# 고장 표본(규율 1 인용): c280 `frictions_note`가 «[프레임 = 자기행 포함 c280·중단 c269 값 1]»
# 로 프레임을 정직 기재했으나 구판 FRAME_RX(«원장 최종 cN»만)가 못 읽어 declared_frames()
# = {} → 파트 O가 «선언 프레임 무기재»로 인쇄. c283 step 0 실측: 같은 서식이 c265~c280
# **16행 연속**이었다(구판 정규식 106쌍 해석 · 느슨 탐침 적중-미해석 16쌍). 아래는 능력을
# 합성 표본으로 고정한다(관행 ⑯) — 실 원장의 분포는 마지막 테스트가 인쇄만 한다.

#: c280 행의 모양을 그대로 뜬 합성 표본.
C280_SHAPED = {
    "cycle": 280,
    "frictions_note": (
        "종결 0·보강 0. fixed 0 = **11연속**[프레임 = 자기행 포함 c280·중단 c269 값 1]. "
        "★재발 표본 계수 **여섯째 라이브** = 총 **92건**."
    ),
}


def test_self_inclusive_frame_variant_is_parsed_as_that_cycle():
    """★ ㉩ 처치의 핵. «자기행 포함 cN»은 «원장 최종 cN»과 같은 뜻(원장 행 cN까지)이므로
    같은 프레임 값으로 읽는다. 구판은 이 표본에서 `{}`를 돌려줬다."""
    assert c48.declared_frames(C280_SHAPED) == {"frictions_note": 280}
    assert c48.unparsed_frame_fields(C280_SHAPED) == {}


def test_self_inclusive_frame_judges_the_value_at_that_frame():
    """값 11(자기행 포함 프레임 c280)은 선언 프레임 c280에서 **11**이다 — 갈라짐 없음.
    구판이 «무기재»로 침묵한 자리에서 이 눈이 이제 «후보에 있음»을 말할 수 있다."""
    rows = _rows([(269, 1)] + [(c, 0) for c in range(270, 281)])
    frame = c48.declared_frames(C280_SHAPED)["frictions_note"]
    st = c48.field_streak([r for r in rows if r["cycle"] <= frame], "frictions_fixed", 0)
    claims = {v for _, v in c48.streak_claim_matches(C280_SHAPED, FIXED_VOCAB)}
    assert st["streak"] == 11, st
    assert st["streak"] in claims, (st, claims)


def test_two_frame_shape_reads_the_first_canonical_frame():
    """c281·c282 서식 «원장 최종 c281 · 자기행 포함 시 13» — 첫 정본 서식이 프레임이고
    뒤의 «자기행 포함 시 13»은 값이지 프레임이 아니다(c 접두 없음). 확장이 이것을
    프레임 13으로 오독하면 안 된다."""
    row = {"cycle": 282,
           "frictions_note": "fixed 0 = **12연속**[프레임 = 원장 최종 c281 · 자기행 포함 시 13 · 중단 c269 값 1]."}
    assert c48.declared_frames(row) == {"frictions_note": 281}


def test_unknown_frame_syntax_is_reported_not_folded_into_absence():
    """★ 정직 기재를 무기재로 접지 않는다. «프레임 =»을 적었는데 두 정본 서식 어느 쪽도
    아니면 프레임을 **추측하지 않고** 미해석 조각을 돌려준다 — 인쇄는 «판정 불가»다."""
    row = {"cycle": 5, "frictions_note": "fixed 0 = **3연속**[프레임 = 직전 행까지 c4]."}
    assert c48.declared_frames(row) == {}
    got = c48.unparsed_frame_fields(row)
    assert set(got) == {"frictions_note"}
    assert got["frictions_note"].startswith("프레임 = 직전 행까지 c4")


def test_truly_absent_frame_is_neither_parsed_nor_unparsed():
    """무기재는 무기재다 — 느슨 탐침도 침묵해야 «무기재» 인쇄가 참이다."""
    row = {"cycle": 1, "frictions_note": "**5연속**이다."}
    assert c48.declared_frames(row) == {}
    assert c48.unparsed_frame_fields(row) == {}


def test_unparsed_is_per_field_and_excludes_parsed_fields():
    """필드별이다(관측 108·109·110 공통 기전). 읽힌 필드는 미해석 목록에 오르지 않는다."""
    row = {
        "cycle": 9,
        "frictions_note": "**2연속**[프레임 = 자기행 포함 c9].",
        "open_observations_note": "캡슐 miss **7연속**[프레임 = 뭔가 다른 c8].",
    }
    assert c48.declared_frames(row) == {"frictions_note": 9}
    assert set(c48.unparsed_frame_fields(row)) == {"open_observations_note"}


def test_real_ledger_self_inclusive_frames_are_now_read():
    """실 원장 **인쇄 전용** + 프레임 독립 항등식 하나: «프레임 =»을 적은 (행,필드)는
    해석되거나 미해석 목록에 오르거나 둘 중 하나다 — 침묵으로 사라지지 않는다.
    현재 분포(해석/미해석 수)는 인쇄만 한다(관행 ⑯)."""
    ledger = ROOT / "research" / "devloop" / "metrics.jsonl"
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    parsed = unparsed = 0
    for r in rows:
        fr = c48.declared_frames(r)
        un = c48.unparsed_frame_fields(r)
        assert not (set(fr) & set(un)), (r["cycle"], fr, un)
        for fld, v in r.items():
            if isinstance(v, str) and c48.FRAME_LOOSE_RX.search(v):
                assert fld in fr or fld in un, (r["cycle"], fld)
        parsed += len(fr)
        unparsed += len(un)
    print(f"[인쇄] «프레임 =» 기재 (행,필드) = 해석 {parsed} · 미해석 {unparsed}")


def test_real_ledger_declared_frame_never_exceeds_its_own_cycle():
    """실 원장 항등식 — **프레임 독립**이다: 어떤 행도 미래의 원장을 프레임으로
    선언할 수 없다. 데이터가 자라도, 관측 110이 고쳐져도 참이어야 한다.

    현재 분포는 **인쇄만** 한다 — 결함의 존재를 assert하지 않는다(관행 ⑯).
    """
    ledger = ROOT / "research" / "devloop" / "metrics.jsonl"
    rows = [json.loads(ln) for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert rows, "원장 행 0 — 미측정이다"
    declared = 0
    for r in rows:
        cyc = int(r["cycle"])
        for fld, fr in c48.declared_frames(r).items():
            declared += 1
            assert fr <= cyc, f"c{cyc} [{fld}] 선언 프레임 c{fr} — 미래를 프레임으로 삼았다"
    print(f"[인쇄] 상태형 프레임을 선언한 (행,필드) 쌍 = {declared}건 / 원장 {len(rows)}행")
