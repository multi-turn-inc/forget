"""c48_step0_check._ordinal_series — 서수 계열 추출의 필드 경계 (c166 수리, 관측 93 · P50).

왜 이 파일이 있는가. 파트 O(P46 처치)는 원장에서 "N사이클째" 계열을 뽑아 선언 앵커와
자기 대조하고 이탈을 인쇄한다. 그 추출이 **`json.dumps(row)` 한 줄을 스캔**했다.

직렬화는 값 안의 개행을 `\\n` **2문자**로 이스케이프한다 — 즉 직렬화본에는 실개행이
**0개**다. 앵커 패턴들은 하나같이 `[^\\n]{0,N}` 창으로 "같은 줄 안에서만 본다"를
표현했는데, 그 창이 종료 조건을 잃고 **필드 경계를 자유롭게 넘었다.**

실측 피해(c166 발견): 원장 c164 행에서 `predictions_note` 말미의 낱말 **"영토"**가
다음 필드 `gate_pending` 서두의 **서비스율 값 49**를 삼켜, 봉쇄 라벨(start c127)에
함의 앵커 c116짜리 **유령 이탈 1건**을 인쇄했다. 그 유령은 c165 `task_state`를 거쳐
c166에게 *"P46 (a)는 반증이다"*로 인계됐다 — 관측 74의 모양(파서의 거짓 값이 손
판정을 통과해 사실로 굳는다). 판정 직전에 잡혔고, 이 파일이 그 자리를 고정한다.

이 테스트가 지키는 계약 둘:
① **필드 경계는 넘지 않는다** — 앵커 낱말과 서수가 다른 필드면 매치 아님.
② **행당 1표본** — 한 행의 여러 필드가 같은 라벨을 인쇄해도 첫 매치만 쓴다.
   (구판과 동일한 계약이다. 행 수로 정규화되지 않으면 앵커 최빈값이 왜곡된다.)
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_ordinals", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

BLOCKADE = c48.ORDINAL_ANCHORS[0][2]   # (?:미커밋|잔존|영토)…(\d+)사이클째
SERVICE = c48.ORDINAL_ANCHORS[1][2]    # 서비스율…(\d+)사이클째


def test_anchor_word_does_not_reach_across_fields():
    """c164 회귀 — 앵커 낱말과 서수가 다른 필드에 있으면 계열에 들어가지 않는다."""
    row = {
        "cycle": 164,
        "predictions_note": "…해당 절은 영토, 무수정).",
        "gate_pending": "**c164 정산 = 신규 상신 0 · 서비스율 0(49사이클째)**",
    }
    assert c48._ordinal_series([row], BLOCKADE) == []


def test_the_swallowed_value_still_belongs_to_its_own_label():
    """같은 행에서 서비스율 라벨은 제 값을 정상 인쇄한다 — 삼켜진 쪽은 피해자가 아니다."""
    row = {
        "cycle": 164,
        "predictions_note": "…해당 절은 영토, 무수정).",
        "gate_pending": "**c164 정산 = 신규 상신 0 · 서비스율 0(49사이클째)**",
    }
    assert c48._ordinal_series([row], SERVICE) == [(164, 49)]


def test_in_field_match_is_still_found():
    """수리가 참 양성을 죽이지 않았는지 — c162 실문면."""
    row = {
        "cycle": 162,
        "tests": "**타 트랙 미커밋 5건 동일 구성 = 파트 O 인쇄 36사이클째**[start c127]",
    }
    assert c48._ordinal_series([row], BLOCKADE) == [(162, 36)]


def test_newline_inside_a_field_still_bounds_the_window():
    """필드 **안**의 실개행은 여전히 창을 끊는다 — `[^\\n]`의 본래 의도."""
    row = {"cycle": 200, "work": "미커밋 잔존\n" + "x" * 5 + "77사이클째"}
    assert c48._ordinal_series([row], BLOCKADE) == []


def test_one_sample_per_row_even_when_two_fields_print_it():
    """행당 1표본 계약 — 두 필드가 같은 라벨을 인쇄해도 첫 매치만."""
    row = {
        "cycle": 162,
        "tests": "미커밋 5건 36사이클째",
        "work": "미커밋 5건 36사이클째",
    }
    assert c48._ordinal_series([row], BLOCKADE) == [(162, 36)]


def test_non_string_fields_are_skipped_without_error():
    """원장 행에는 int·null·중첩 객체가 섞인다 — 스캔이 거기서 죽으면 안 된다."""
    row = {
        "cycle": 170,
        "recall_hits": 3,
        "evidence": {"note": "미커밋 잔존 44사이클째"},
        "work": "미커밋 잔존 44사이클째",
    }
    assert c48._ordinal_series([row], BLOCKADE) == [(170, 44)]


def test_real_ledger_c164_has_no_blockade_sample():
    """실 원장 회귀 — 수리 후 c164는 봉쇄 계열에 없다(그 행은 그 라벨을 인쇄하지 않았다)."""
    rows = c48._ledger_rows()
    by_cycle = {int(r["cycle"]): r for r in rows}
    assert 164 in by_cycle, "원장에 c164 행이 없다 — 이 테스트의 전제가 깨졌다"
    series = dict(c48._ordinal_series([by_cycle[164]], BLOCKADE))
    assert series == {}


def test_real_ledger_blockade_series_agrees_with_declared_anchor():
    """수리 후 봉쇄 계열의 모든 표본이 선언 앵커 c127과 일치하는가 — P46 (a)의 기계 확인."""
    label, start, pattern = c48.ORDINAL_ANCHORS[0]
    rows = c48._ledger_rows()
    series = c48._ordinal_series(rows, pattern)
    recent = [(c, o) for c, o in series
              if c > max(x for x, _ in series) - c48.ORDINAL_WINDOW]
    assert recent, "봉쇄 계열이 비었다 — 정규식이 원장 문면과 갈렸다"
    post = [c for c, o in recent
            if c - o + 1 != start and c >= c48.ORDINAL_TREATMENT_CYCLE]
    assert post == [], f"처치({c48.ORDINAL_TREATMENT_CYCLE}) 이후 이탈: {post}"


# ── field_streak — 상태형 계수기 (c168 신설, 관측 96 · P52) ──────────────────
#
# 왜 이 절이 있는가. P46은 **산술형** 계수기 셋만 기계화했고, 원장 산문에 살던
# **상태형** 둘은 계기 밖에서 손이 증분했다. c168 실측: `fixed` 연속 0은 3 적게,
# 캡슐 miss 연속은 29 많게 인쇄됐다 — 방향이 반대라 한 행만 보면 둘 다 정상으로
# 보인다. 캡슐 쪽 오류의 기전이 이 절이 고정하는 계약이다: 손이 인쇄한 수는
# **연속**이 아니라 **정의역 크기**였다(c161~c167 7사이클 연속 일치).


def test_field_streak_counts_consecutive_not_domain():
    """관측 96의 정중앙 — 연속과 정의역은 다른 수이고, 섞이면 안 된다."""
    rows = [
        {"cycle": 1, "restore_grade_capsule": "partial"},
        {"cycle": 2, "restore_grade_capsule": "miss"},
        {"cycle": 3, "restore_grade_capsule": "partial"},
        {"cycle": 4, "restore_grade_capsule": "miss"},
        {"cycle": 5, "restore_grade_capsule": "miss"},
    ]
    st = c48.field_streak(rows, "restore_grade_capsule", "miss")
    assert st["streak"] == 2, "역순 연속은 c4~c5 둘뿐이다"
    assert st["domain"] == 5, "정의역은 필드를 가진 행 전체다"
    assert st["streak"] != st["domain"], "이 둘이 같아지면 계약이 사라진다"
    assert st["break"] == (3, "partial")
    assert st["off_value"] == [1, 3]


def test_field_streak_ignores_rows_without_the_field():
    """필드가 없는 행은 정의역 밖이다 — '없음'을 '값 불일치'로 세면 연속이 끊긴다."""
    rows = [
        {"cycle": 1},
        {"cycle": 2, "restore_grade_capsule": "miss"},
        {"cycle": 3},
        {"cycle": 4, "restore_grade_capsule": "miss"},
    ]
    st = c48.field_streak(rows, "restore_grade_capsule", "miss")
    assert st["streak"] == 2 and st["domain"] == 2
    assert st["span"] == (2, 4) and st["break"] is None


def test_field_streak_is_order_independent():
    """원장 파일 순서에 의존하지 않는다 — cycle로 정렬해서 센다."""
    rows = [
        {"cycle": 5, "frictions_fixed": 0},
        {"cycle": 3, "frictions_fixed": 2},
        {"cycle": 4, "frictions_fixed": 0},
    ]
    st = c48.field_streak(rows, "frictions_fixed", 0)
    assert st["streak"] == 2 and st["break"] == (3, 2)


def test_field_streak_empty_domain_is_unmeasured_not_zero():
    """정의역 0은 '연속 0'이 아니라 **미측정**이다 — 인쇄가 그렇게 갈라져야 한다."""
    st = c48.field_streak([{"cycle": 1}], "restore_grade_capsule", "miss")
    assert st["streak"] == 0 and st["domain"] == 0
    assert st["span"] is None and st["frame_last"] is None


def test_real_ledger_capsule_streak_is_not_the_domain_size():
    """실 원장 회귀 — 손 인쇄가 정의역을 '연속'이라 불렀다(관측 96). 고정할 것은 **관계**다.

    ★ c169 개정 (관측 100). 구본은 `domain == 77`·`streak == 48`을 **값으로** 박았다.
    그 두 수는 이 회귀를 쓴 사이클 **자신의 원장 append**가 +1 옮긴다 — 절차 4(검증)가
    절차 5(수확)보다 먼저이므로, 구본은 c168이 초록으로 잰 직후 c168의 수확에 붉어졌고
    한 사이클을 잠복하다 c169에 실측됐다. 값이 아니라 원장에서 **다시 센다.**

    앵커(`off_value`·`break`·`span` 시작)는 과거 행이라 프레임과 무관하게 안정하다.
    같아지는 날(정의역 안의 `partial` 5건이 사라지는 날)이 오면 앵커 assert가 먼저
    깨진다 — 그때는 계약이 아니라 데이터가 바뀐 것이다.
    """
    rows = c48._ledger_rows()
    st = c48.field_streak(rows, "restore_grade_capsule", "miss")
    assert st["off_value"] == [91, 92, 93, 94, 119]
    assert st["break"] == (119, "partial")
    assert st["span"][0] == 91
    # 기계 재계산 — 계기의 반환값이 아니라 원장 행에서 독립으로 센다.
    present = sorted(int(r["cycle"]) for r in rows if "restore_grade_capsule" in r)
    assert st["domain"] == len(present), f"정의역이 재계산과 갈렸다: {st['domain']}"
    assert st["streak"] == sum(1 for c in present if c > 119), (
        f"연속이 재계산과 갈렸다: {st['streak']}")
    # ★ 이 절의 존재 이유 — 연속과 정의역은 다른 수다(관측 96).
    assert st["streak"] != st["domain"]


def test_real_ledger_fixed_streak_matches_machine_recount():
    """실 원장 회귀 — `frictions_fixed` 0 연속이 **독립 재계산**과 일치하는가.

    ★★ c171 개정 (관측 100 **재발 2호** · P55 (a) 반증). c169는 이 절의 `streak == 25`를
    재계산으로 바꿨으나 **같은 몸에 남아 있던 `break == (142, 3)`은 그대로 뒀다.** 한 절
    안에 박힌 상수가 둘이었고 하나만 고쳤다 — 그래서 처치는 «부분»이었고, 그 사실이
    c170에 드러나지 않은 이유는 **c170이 `frictions_fixed: 0`을 적었기 때문**이다.
    중단점은 값이 0이 아닌 행이 새로 들어올 때만 움직이고, 그런 행은 c142 이후 **29사이클
    동안 없었다.** 즉 c170의 «초록»은 이 절을 시험한 것이 아니라 **시험할 데이터가 없었던
    것**이며(P46 (b)·P50 (a)와 같은 공허), c171이 `fixed: 2`를 적은 즉시 붉어졌다.

    교훈은 관행 ㊽의 강한 판본이다: **회귀가 재는 값이 그 사이클 절차 5에 바뀌는지 묻고,
    한 절에 상수가 몇 개인지도 세라.** 몸을 이름에 맞춘다 — 상수를 남기지 않고,
    `field_streak`와 **다른 알고리즘**(뒤에서부터 훑기)으로 재계산해 대조한다.
    """
    rows = c48._ledger_rows()
    st = c48.field_streak(rows, "frictions_fixed", 0)
    present = [(int(r["cycle"]), r["frictions_fixed"])
               for r in rows if "frictions_fixed" in r]
    assert present, "정의역이 비었다 — 이 절의 전제가 깨졌다"

    # 독립 재계산: 최신 행부터 거꾸로 훑어 0이 이어지는 구간과 첫 비영 행을 찾는다.
    tail, break_at = 0, None
    for cycle, value in sorted(present, reverse=True):
        if value != 0:
            break_at = (cycle, value)
            break
        tail += 1

    assert st["streak"] == tail, f"연속이 독립 재계산과 갈렸다: {st['streak']} vs {tail}"
    assert st["break"] == break_at, f"중단점이 독립 재계산과 갈렸다: {st['break']} vs {break_at}"
    assert st["domain"] == len(present), f"정의역이 재계산과 갈렸다: {st['domain']}"
    # ★ 관측 96 — 연속과 정의역은 다른 수다. 이 절은 상수를 갖지 않으므로
    #   다음 사이클이 `fixed`에 무엇을 적어도 이 관계만 지키면 초록이다.
    assert st["streak"] <= st["domain"]


def test_streak_counters_table_needs_no_hand_maintained_start():
    """상태형 표는 앵커 상수를 갖지 않는다 — 손이 유지할 값이 없어야 처치가 성립한다."""
    for entry in c48.STREAK_COUNTERS:
        label, field, value, claim_rx = entry
        assert isinstance(label, str) and isinstance(field, str)
        assert len(entry) == 4, "start 상수가 끼어들면 관측 96의 처치가 무너진다"
        assert "사이클째" not in claim_rx, "산술형 자[尺]의 정규식이 섞였다"


# ── series_coverage — 계열이 «누구를» 보는가 (c171 신설, 관측 104 처치) ────────
#
# 왜 이 절이 있는가. 파트 O는 `계열 N본`이라는 **수**만 인쇄했다. 그래서 두 침묵이
# 화면에서 같은 모양이었다: 그 행이 라벨을 옳게 적어 조용한 것과, 정규식이 그 행을
# **아예 못 봐서** 조용한 것. c171 합성 주입이 그 차이를 실측했다 — 계열에 보이는
# 행(c169)에 틀린 서수를 넣으면 검출하고, 최신 행(c170)에 넣으면 **침묵한다.**
# 기전은 살아 있고 정의역이 비어 있었다(P50 (b) 반증 방향, 합성 표본).


def test_series_coverage_names_the_absent_rows():
    """계약 — 피복은 «몇 본»이 아니라 «누가 빠졌는가»를 돌려준다."""
    rows = [{"cycle": c} for c in (10, 11, 12, 13)]
    series = [(10, 1), (12, 3)]
    cov = c48.series_coverage(rows, series, window=4)
    assert cov["span"] == [10, 11, 12, 13]
    assert cov["seen"] == [10, 12]
    assert cov["absent"] == [11, 13]
    assert cov["pct"] == 50.0


def test_series_coverage_flags_the_newest_row_specifically():
    """최신 행은 특별하다 — 다음 손이 실제로 전사할 행이 그것이다."""
    rows = [{"cycle": c} for c in (10, 11)]
    assert c48.series_coverage(rows, [(10, 1)], window=4)["newest_seen"] is False
    assert c48.series_coverage(rows, [(11, 2)], window=4)["newest_seen"] is True


def test_series_coverage_empty_series_is_unmeasured_not_full():
    """계열 0본은 '피복 100%'가 아니라 **미측정**이다 — pct는 None이어야 한다."""
    cov = c48.series_coverage([{"cycle": 5}], [], window=4)
    assert cov["pct"] is None and cov["absent"] == []
    assert cov["newest"] == 5 and cov["newest_seen"] is False


def test_real_ledger_blockade_coverage_is_incomplete_and_says_so():
    """실 원장 회귀 — 봉쇄 계열은 창을 다 덮지 못한다. 그 사실이 수로 나와야 한다.

    이 절은 «결함이 있다»를 고정하는 것이 아니라 «결함이 보인다»를 고정한다.
    피복이 100%가 되는 날이 오면 이 assert가 먼저 깨지고, 그때는 계약이 아니라
    데이터가 바뀐 것이다(관행: 회귀가 재는 값이 그 사이클에 바뀌는지 물어라).
    """
    label, start, pattern = c48.ORDINAL_ANCHORS[0]
    rows = c48._ledger_rows()
    cov = c48.series_coverage(rows, c48._ordinal_series(rows, pattern))
    assert cov["pct"] is not None and cov["pct"] < 100.0
    assert cov["absent"], "미등재가 0이면 이 절의 전제가 사라졌다"


def test_loose_probe_finds_what_the_strict_anchor_misses():
    """관측 104의 정중앙 — «안 적었다»와 «적었는데 못 봤다»를 가를 수 있는가.

    ★★ c171 개정 (관측 100 **재발 3호**, 그리고 셋 중 가장 나쁜 판본). 구판 이름은
    `…_on_the_newest_row`였고 몸은 **실 원장 최신 행**에 대해
    `assert dict(_ordinal_series(row, strict)) == {}`를 걸었다 — 즉 *"엄격 앵커는 최신 행을
    **보지 못해야** 한다"*를 계약으로 박았다. **그것은 결함을 기대 상태로 고정한 것이다.**
    c170이 평문 *"봉쇄 44사이클째"*로 적었다는 **우연한 사실**이 계약이 됐고, 그래서
    c171이 정본 문면(`타 트랙 미커밋 잔존`)으로 **옳게** 적자 이 절이 깨졌다.
    **고치는 쪽이 벌을 받는 회귀는 회귀가 아니라 자물쇠다.**

    처치: 계약을 **능력**으로 옮긴다 — 합성 표본 두 개로 «평문은 엄격이 놓치고 느슨이
    잡는다»와 «정본 문면은 엄격이 잡는다»를 고정한다. 실 원장의 최신 행이 어느 쪽이든
    이 절은 초록이며, 최신 행의 상태를 **보고**하는 일은 파트 O의 피복 인쇄
    (`series_coverage`) 몫이다 — assert가 아니라 인쇄가 그 자리다.
    """
    label, start, strict = c48.ORDINAL_ANCHORS[0]
    loose = c48.LOOSE_ORDINAL_PROBES[label]

    # ① 평문 — 엄격은 놓치고 느슨은 잡는다 (c170이 실제로 쓴 문면).
    plain = [{"cycle": 170, "tests": "**[상태:봉쇄 44사이클째@파트 O 프레임 N=170]**"}]
    assert dict(c48._ordinal_series(plain, strict)) == {}, "엄격 앵커가 평문을 보면 안 된다"
    assert dict(c48._ordinal_series(plain, loose)) == {170: 44}, "느슨 탐침이 평문을 놓쳤다"

    # ② 정본 문면 — 엄격이 잡고, 귀속이 선언 앵커와 일치한다 (c171이 쓴 문면).
    canonical = [{"cycle": 171,
                  "tests": "**[상태:봉쇄(타 트랙 미커밋 잔존) 45사이클째"
                           "@파트 O 프레임 N=171]**"}]
    seen = dict(c48._ordinal_series(canonical, strict))
    assert seen == {171: 45}, f"엄격 앵커가 정본 문면을 놓쳤다: {seen}"
    assert 171 - seen[171] + 1 == start, "정본 문면의 귀속이 선언 앵커와 갈렸다"


def test_the_newest_row_state_is_reported_not_asserted():
    """관측 104 처치의 경계 선언 — 최신 행의 피복은 «인쇄»되고 «강제»되지 않는다.

    구판이 최신 행에 assert를 걸어 결함을 잠갔으므로(위 절), 그 자리가 비어 있다는
    사실을 명시적으로 고정한다: `series_coverage`는 미등재 목록과 최신행 여부를
    **돌려주고**, 어느 쪽 값도 이 파일이 요구하지 않는다.
    """
    rows = c48._ledger_rows()
    label, start, pattern = c48.ORDINAL_ANCHORS[0]
    cov = c48.series_coverage(rows, c48._ordinal_series(rows, pattern))
    # 계약은 «보고한다»뿐이다 — 값이 아니라 열의 존재를 잰다.
    for key in ("pct", "absent"):
        assert key in cov, f"피복 보고에 `{key}`가 없다 — 인쇄가 계약을 잃었다"
    assert isinstance(cov["absent"], list)


# ── 합집합 패턴과 «인용된 과거 값» (c171, 확장을 무른 근거) ────────────────────
#
# c171은 봉쇄 앵커를 `|봉쇄[^\n]{0,24}?(\d+)사이클째` 합집합으로 넓혀 c170 미등재를
# 닫으려 했고, **실측으로 물렀다.** 확장은 겹치는 행 c161의 값을 35 → 34로 바꿨고
# 파트 O가 `처치 후 이탈 1본 (c161) ← P46 (a) 반증`을 인쇄했다. c161 행 직독으로
# 정체 확정: `restore_note`가 *"봉쇄 34사이클째[c160 기준] → 파트 O 인쇄 35[c161]
# 정합"*이라고 **직전 프레임 값을 인용**하고 있었고, `_ordinal_series`는 필드 dict
# 순서의 첫 매치를 쓰므로 인용이 자기 주장(35)을 앞질렀다.
#
# 즉 «못 보는 행을 보이게 하는 것»과 «억지로 보는 것»은 다르고, 후자는 값을 위조했다.
# 아래 두 절은 그 교훈을 코드로 붙잡는다 — 다음 손이 같은 확장을 다시 시도하면
# 두 번째 절이 먼저 깨져서 이유를 말해준다.


def test_multi_group_union_pattern_takes_the_first_non_none_value():
    """합집합 패턴 지원 — 구판은 `m.group(1)`을 박아 써서 TypeError로 죽었다."""
    union = r"미커밋[^\n]{0,20}?(\d+)사이클째|봉쇄[^\n]{0,20}?(\d+)사이클째"
    assert c48._ordinal_series([{"cycle": 1, "work": "봉쇄 7사이클째"}], union) == [(1, 7)]
    assert c48._ordinal_series([{"cycle": 2, "work": "미커밋 9사이클째"}], union) == [(2, 9)]


def test_pattern_matching_with_no_value_group_dies_loudly():
    """값 그룹이 전부 None이면 **소리 내어** 죽는다 — 조용히 0본이 되면 '드리프트 없음'으로 오독된다."""
    import pytest
    with pytest.raises(ValueError, match="값 그룹"):
        c48._ordinal_series([{"cycle": 1, "work": "봉쇄"}], r"봉쇄(\d+)?")


def test_widening_the_blockade_anchor_would_read_a_quoted_value_as_a_claim():
    """★ 확장을 무른 근거 — 실 원장 c161에서 확장은 «인용»을 «주장»으로 읽는다.

    현행(엄격) 패턴은 c161의 자기 주장 35를 읽고 선언 앵커 c127과 일치한다.
    확장 패턴은 같은 행에서 34를 읽어 함의 앵커 c128을 만들고, 그것이 파트 O에서
    P46 (a) 반증으로 인쇄된다 — 관측 93의 유령과 같은 자리다.
    """
    rows = c48._ledger_rows()
    row = [r for r in rows if int(r["cycle"]) == 161]
    assert row, "원장에 c161 행이 없다 — 이 절의 전제가 깨졌다"
    label, start, strict = c48.ORDINAL_ANCHORS[0]

    assert dict(c48._ordinal_series(row, strict)) == {161: 35}, "c161의 자기 주장은 35다"
    assert 161 - 35 + 1 == start, "그 값은 선언 앵커와 일치한다"

    widened = strict + r"|봉쇄[^\n]{0,24}?(\d+)사이클째"
    quoted = dict(c48._ordinal_series(row, widened))
    assert quoted == {161: 34}, f"확장이 인용값 34를 읽지 않게 됐다: {quoted}"
    assert 161 - 34 + 1 != start, "34는 선언 앵커와 갈린다 — 그것이 거짓 이탈이었다"

    assert "봉쇄" not in c48.ORDINAL_ANCHORS[0][2], (
        "봉쇄 앵커에 확장이 다시 들어왔다 — c171이 실측으로 무른 변경이다."
        " 인용과 자기 주장을 가르는 설계 없이 넓히면 P46 (a)에 유령 반증이 인쇄된다"
        " (청구 A-171.1).")


# ── 인용 유령은 라벨을 가리지 않는다 (c172 세션2 신설, 관측 108) ──────────────────
#
# 왜 이 절이 위 절과 **따로** 있는가. 위 절(c171)은 *"봉쇄 앵커를 넓히면 유령이 나온다"*를
# 고정한다 — 즉 **확장을 막는** 문이다. 그런데 c172 행에서 유령이 실제로 나온 곳은
# **원터치 라벨이고 확장 없는 출하 패턴**이었다. 60자 창이 이미 충분히 넓었기 때문이다.
#
# 즉 c171의 처치는 기전이 아니라 **한 라벨의 기회**를 닫았고, 기전(`dict 순서 첫 매치`)은
# `A-171.1`로 게이트에 올라간 채 살아 있었다. 그 기전은 루프가 **권장하는 좋은 습관**이
# 방아쇠다: «감사하는 행을 인용하라». c172는 P57 피복 사각을 문서화하려고 c171 원장의
# *'원터치 30사이클째'*를 인용했고, 그 인용이 자기 행의 자기 주장(31)을 앞질렀다.
#
# 그래서 이 절이 고정하는 것은 «확장 금지»가 아니라 **판독 가능성**이다: 이탈 후보가
# 나왔을 때 인용과 자기 주장이 화면에서 갈라지는가.

ONETOUCH = c48.ORDINAL_ANCHORS[2][2]


def test_field_matches_exposes_every_field_the_row_matched():
    """`_ordinal_field_matches`는 첫 매치에서 멈추지 않고 dict 순서로 전량 돌려준다."""
    row = {"cycle": 900, "a": "원터치 7사이클째", "n": 5, "b": "원터치 9사이클째",
           "c": "관계없는 산문"}
    assert c48._ordinal_field_matches(row, ONETOUCH) == [("a", 7), ("b", 9)]


def test_field_matches_dies_loudly_when_no_value_group():
    """계열 추출과 **같은** 하드 실패 계약 — 조용히 넘기면 사각이 생긴다."""
    import pytest
    with pytest.raises(ValueError, match="값 그룹"):
        c48._ordinal_field_matches({"cycle": 1, "work": "원터치"}, r"원터치(\d+)?")


def test_a_quoted_ordinal_in_an_earlier_field_outranks_the_self_claim():
    """★ 관측 108의 기전 — **합성 표본**으로 고정한다 (관행 ⑯).

    실 원장 c172가 정확히 이 모양이었다. 그러나 이 절은 실 원장을 읽지 않는다:
    `A-171.1`이 승인돼 기전이 고쳐지면 실 원장 기반 assert는 **고치는 쪽을 벌한다**
    (c171의 관측 106이 그 자물쇠였다). 능력은 합성으로, 실 데이터는 인쇄로.
    """
    row = {
        "cycle": 900,
        # 앞 필드 = 다른 사이클의 값을 **인용**한다. 루프가 권장하는 습관이다.
        "predictions_note": "c171은 자기 원장에 *'원터치 30사이클째(c171 미등재)'*로 적었다",
        # 뒤 필드 = 이 행의 **자기 주장**. 파트 O 인쇄를 그대로 전사한 값.
        "tests": "**인스턴스 원터치 대기 31사이클째** [start c142 · 프레임 N=172]",
    }
    # 계열은 첫 매치를 쓴다 = 인용값. 이것이 거짓 이탈의 출처다.
    assert dict(c48._ordinal_series([row], ONETOUCH)) == {900: 30}
    # 필드별 판독은 둘을 **갈라** 보여 준다 — 손이 판정할 수 있는 최소 재료.
    assert c48._ordinal_field_matches(row, ONETOUCH) == [
        ("predictions_note", 30), ("tests", 31)]


def test_series_value_is_always_the_first_field_match():
    """계약 증인 — 실 원장 전 행·전 앵커에서 계열 값 == 필드별 판독의 **첫** 값.

    프레임 독립이고 데이터가 자라도 참이어야 한다. `A-171.1`이 «필드 화이트리스트»로
    해결되면 이 계약은 **의도적으로** 깨진다 — 그때 이 절이 붉어지는 것이 옳다.
    이 절은 결함을 잠그지 않는다(결함은 «첫 매치»가 아니라 «첫 매치를 판정에 쓰는 것»).
    """
    rows = c48._ledger_rows()
    by_cycle = {int(r["cycle"]): r for r in rows}
    for label, _start, pattern in c48.ORDINAL_ANCHORS:
        for cyc, val in c48._ordinal_series(rows, pattern):
            got = c48._ordinal_field_matches(by_cycle[cyc], pattern)
            assert got, f"{label} c{cyc}: 계열은 봤는데 필드별 판독이 비었다"
            assert got[0][1] == val, (
                f"{label} c{cyc}: 계열 {val} ≠ 첫 필드 매치 {got[0]} — 두 함수의"
                " 순회 순서가 갈렸다. 하나를 고쳤으면 둘 다 고쳐라.")


def test_deviation_is_reported_as_candidate_not_as_a_verdict():
    """★ 파트 O의 경보가 **판정 동사**를 쓰지 않는다 (관측 108 처치).

    구판 문면 = *"P46 (a)는 반증이다. 원장에 그대로 적을 것."* — 이 검출기가 정당화할
    수 없는 판정이다. 실측 2/2(c161·c172)가 거짓 양성이었고, 규약을 문자 그대로 따른
    손은 원장에 거짓 반증을 실었을 것이다. c171은 손 판독으로 막았고 c172는 자기 행을
    원리적으로 볼 수 없었다(이탈은 N+1에서만 보인다 = 관측 100의 구조).
    """
    src = SCRIPT.read_text(encoding="utf-8")
    assert "P46 (a)는 반증이다. 원장에 그대로 적을 것" not in src, (
        "무조건 반증 문면이 돌아왔다 — 인용/자기 주장 분별(`A-171.1`) 없이는"
        " 이 경보가 판정을 지시할 수 없다.")
    assert "이탈 **후보**" in src, "이탈을 «후보»로 부르는 문면이 사라졌다"
    assert "_ordinal_field_matches(by_cycle_o[c], pattern)" in src, (
        "경보가 필드별 판독을 더는 인쇄하지 않는다 — 그것이 없으면 다음 손은"
        " 프로브를 다시 써야 하고, 두 세션이 이미 그렇게 했다.")


def test_real_ledger_deviation_assert_covers_one_label_of_three():
    """★ 관행 ⑨ — 계기가 덮는 범위를 성공으로 착각하지 않는다. **다섯째 표본.**

    `test_real_ledger_blockade_series_agrees_with_declared_anchor`는
    `ORDINAL_ANCHORS[0]`(봉쇄) **하나만** 본다. 파트 O 인쇄는 셋을 본다. 그래서 유령이
    원터치에서 발화했을 때 **565 초록이 그것을 말하지 않았다.**

    이 절은 그 간극을 assert로 **선언**한다 — 넓히는 것은 의도적 행위여야 하고,
    그때 이 절이 붉어져 «무엇을 넓혔는지» 적게 만든다. 각 라벨의 현재 이탈 후보는
    **인쇄만** 한다(관행 ⑯): 후보의 존재는 라벨마다 다른 사유를 갖고, 그중 둘은
    이미 거짓 양성으로 판독됐다.
    """
    rows = c48._ledger_rows()
    by_cycle = {int(r["cycle"]): r for r in rows}
    src = Path(__file__).read_text(encoding="utf-8")
    assert "c48.ORDINAL_ANCHORS[0]\n" in src, (
        "봉쇄 전용 assert의 범위가 바뀌었다 — 셋을 다 보게 넓혔다면 이 절의"
        " 문면도 함께 고치고 사유를 적어라(간극을 조용히 닫지 않는다).")

    census = {}
    for label, _s, pattern in c48.ORDINAL_ANCHORS:
        series = c48._ordinal_series(rows, pattern)
        if not series:
            census[label] = "계열 0본"
            continue
        lo = max(c for c, _ in series) - c48.ORDINAL_WINDOW + 1
        anchors = [c - o + 1 for c, o in series if c >= lo]
        modal = max(set(anchors), key=anchors.count)
        cand = [(c, o, c48._ordinal_field_matches(by_cycle[c], pattern))
                for c, o in series if c >= lo and c - o + 1 != modal
                and c >= c48.ORDINAL_TREATMENT_CYCLE]
        census[label] = cand
    print("\n[이탈 후보 인구조사 — assert 아님, 상태 인쇄]")
    for label, cand in census.items():
        print(f"  {label}: {cand}")
    assert len(census) == len(c48.ORDINAL_ANCHORS)
