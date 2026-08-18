"""c48_step0_check.reverify_contradictions — 자기보고의 외부 대조 (c162, 관측 88 · P47).

왜 이 파일이 있는가. `step5_write_reverified`는 절차 5의 재조회 확인을 보고하는 원장
필드인데, 쓰기 순서가 `원장 append → 커밋 → push → record_task_state → 재조회`(관측 55
수용 기준 ②, c96)라서 **필드가 사는 행이 필드가 보고하는 사건보다 먼저 쓰인다**. 값은
구조적으로 의도 선언이며, 진위는 다음 사이클의 파트 S만 판정할 수 있다.

c162 실측: 필드 69행(c93~c161)·결측 0행이라 겉보기 준수율 100%인데, 외부 대조가 가능한
40행 중 **1건이 모순**(c155)이었고 c161이 2호가 됐다. 이 파일은 그 대조 산술을 회귀 아래
둔다 — 계기가 자기 하드 가드를 갖지 않으면 같은 병을 한 층 위에서 반복한다(probe_guard
모듈 서두의 자기 검증 논지와 같은 이유).

가장 중요한 단언은 `unmeasured`의 분리다. 파트 S는 c93 처치 이후에만 인쇄되므로 그 이전
행은 *모순 없음*이 아니라 *잴 수 없음*이다. 둘이 한 칸에 섞이는 순간 이 계기는 자기가
고발하는 병(자기보고의 존재를 검사의 존재로 읽기)에 스스로 걸린다.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_reverify", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

FIELD = c48.REVERIFY_FIELD


def row(cycle, *, claim=None, note=None):
    r = {"cycle": cycle}
    if claim is not None:
        r[FIELD] = claim
    if note is not None:
        r["restore_note"] = note
    return r


def test_landed_write_is_agreement():
    # N이 True를 적었고 N+1의 파트 S가 '일치'를 인쇄했다 = 자기보고가 관측과 맞다.
    out = c48.reverify_contradictions([
        row(10, claim=True),
        row(11, note="파트 S 정본: `ledger_last=10 / task_state_cycle=10 → 판정=일치`"),
    ])
    assert out["checked"] == 1
    assert out["agree"] == 1
    assert out["contradictions"] == []


def test_lagged_write_contradicts_the_self_report():
    # c155의 실제 형태: 자기보고 True인데 다음 사이클 파트 S가 '지연'을 봤다.
    out = c48.reverify_contradictions([
        row(155, claim=True),
        row(156, note="파트 S 정본: `ledger_last=155 / task_state_cycle=154 → 판정=지연`"),
    ])
    assert out["contradictions"] == [(155, "지연")]
    assert out["agree"] == 0


def test_missing_part_s_verdict_is_unmeasured_not_clean():
    # 핵심 단언. 파트 S 이전 구간(판정 문면 없음)은 모순 0에 섞이면 안 된다 —
    # 섞이는 순간 '자기보고의 존재'가 '검사의 존재'로 읽힌다(관측 88의 병 그 자체).
    out = c48.reverify_contradictions([
        row(50, claim=True),
        row(51, note="파트 S가 아직 없던 시절의 복원 노트"),
    ])
    assert out["unmeasured"] == 1
    assert out["checked"] == 0
    assert out["contradictions"] == []


def test_last_field_row_is_pending_not_agreement():
    # 후속 원장 행이 없는 마지막 행은 '일치'가 아니라 **미판정**이다. 그 대조는
    # 다음 세션의 파트 S가 한다 — c161이 정확히 이 자리였다.
    out = c48.reverify_contradictions([
        row(160, claim=True),
        row(161, claim=True, note="…→ 판정=일치`"),
    ])
    assert out["pending"] == 161
    assert out["checked"] == 1  # c160만 대조됐다


def test_prose_receipts_are_separated_from_bare_true():
    # c93·c94는 claim/epoch id를 담은 산문이었고 c95부터 맨 True다. 필드는 영수증으로
    # 태어나 boolean으로 굳었다 — 그 퇴화가 계수로 보여야 한다.
    out = c48.reverify_contradictions([
        row(93, claim="true — 재조회로 c93 세대 확인(claim 85d972cb · epoch 945c9506)"),
        row(94, claim=True, note="→ 판정=일치`"),
    ])
    assert out["prose_receipts"] == [93]
    assert out["field_rows"] == [93, 94]


def test_deferred_value_makes_no_claim_and_so_cannot_be_contradicted():
    # c162가 자기 행에 쓴 값. 관측 88을 주조한 사이클이 같은 행에서 맨 True를 쓰면
    # 그것이 곧 관측의 반례다 — 그래서 주장하지 않는다. 주장이 없으면 반증도 없고,
    # 그 사실이 '일치'로 뭉뚱그려지지 않도록 `deferred`로 **따로** 센다.
    out = c48.reverify_contradictions([
        row(162, claim="미정 — 이 필드는 record_task_state보다 먼저 쓰인다(관측 88)"),
        row(163, note="→ 판정=지연`"),
    ])
    assert out["deferred"] == [162]
    assert out["prose_receipts"] == []   # 유보는 영수증이 아니다
    assert out["contradictions"] == []   # 주장이 없으므로 반증 불가


def test_field_absent_rows_are_not_counted():
    # 필드가 없는 행은 분모에 들어가지 않는다(c0~c92 구간).
    out = c48.reverify_contradictions([row(1), row(2), row(3, claim=True)])
    assert out["field_rows"] == [3]


def test_ahead_verdict_is_not_a_contradiction_of_the_previous_row():
    # c162가 자기 첫 판본에서 낸 오판의 회귀. c95는 True를 적었고 c96 파트 S는 '앞섬'을
    # 인쇄했다 — 그러나 앞섬은 `task_state_cycle > ledger_last`, 즉 세대가 존재하고
    # **앞서** 있다는 뜻이므로 c95의 쓰기는 착지했다. 병은 c96 선행 세션의 완주 선기재다
    # (관측 55의 실전 첫 발화). 남의 병으로 c95를 고발하면 관측 74의 모양이 된다.
    out = c48.reverify_contradictions([
        row(95, claim=True),
        row(96, note="파트 S 앞섬 분기 발화 — `→ 판정=앞섬`"),
    ])
    assert out["contradictions"] == []
    assert out["ahead"] == [96]
    assert out["agree"] == 1


def test_falsey_self_report_is_never_a_contradiction():
    # False를 적은 행은 실패를 이미 시인한 것이다 — 모순으로 세지 않는다.
    out = c48.reverify_contradictions([
        row(20, claim=False),
        row(21, note="→ 판정=지연`"),
    ])
    assert out["contradictions"] == []
    assert out["agree"] == 1


# --- c167 (P51): 라이브 고발 블록과 계열 함수의 사본 분기 ---------------------
#
# c167 P47 판정에서 실측된 병: 같은 계기가 같은 행에 두 판정을 인쇄했다.
# 계열 함수는 c166을 `유보`로 면책하는데(:168 "주장하지 않은 행은 반증될 주장이 없다")
# 라이브 블록은 같은 행에 `★ 모순`을 찍었다. 유보 개념이 그쪽에만 없었기 때문이다.
# 벌한 대상이 하필 정직이었다 — 유보 서식은 맨 `True`를 피하려고 도입된 것이다.


def test_deferral_predicate_reads_the_reserved_forms():
    assert c48.is_deferred("미정 — c167 파트 S가 판정")
    assert c48.is_deferred("유보")


def test_bool_self_report_is_a_claim_not_a_deferral():
    # bool은 의도 선언이지만 **주장은 주장이다** — 유보로 새면 c155·c161이 면책된다.
    assert not c48.is_deferred(True)
    assert not c48.is_deferred(False)


def test_live_mark_does_not_accuse_a_reserved_row():
    # c166의 실제 값. 이것이 P47 판정에서 잡힌 거짓 양성 1건이다.
    assert c48.reverify_claim_mark("미정 — c167 파트 S가 판정") == "  (유보 — 주장 없음)"


def test_live_mark_still_accuses_a_true_claim():
    # 참 양성이 죽지 않았는지 — c155·c161은 계속 고발되어야 한다.
    assert c48.reverify_claim_mark(True) == "★ 모순"


def test_live_mark_is_silent_when_the_field_is_absent():
    assert c48.reverify_claim_mark("**필드 없음**") == "  (주장 없음)"
    assert c48.reverify_claim_mark("") == "  (주장 없음)"


def test_live_mark_accuses_exactly_what_the_series_counts():
    """두 경로가 갈라지지 않는지 — 이 절의 존재 이유.

    사본이 둘이면 다시 갈라진다. **불변식**: 파트 S가 `지연`을 본 행에 대해
    라이브 블록의 `★ 모순`과 계열의 `contradictions` 편입은 동치여야 한다.

    자기 불리 — 이 단언의 첫 판본은 *"계열이 `deferred`로 분류한 행은 고발되지
    않는다"*였고 **틀렸다**. `False`는 유보가 아니라 실패의 시인이며, 유보가
    아니면서도 고발되지 않는다. 술어를 `deferred` 여부로 좁혀 쓴 것이 나의 오류이고
    테스트가 그것을 잡았다 — 계기가 아니라 **내 명세**가 틀린 경우다.
    """
    claims = ["미정 — c167 파트 S가 판정", "유보", True, False, "청구 산문"]
    rows = []
    for i, c in enumerate(claims):
        rows.append(row(100 + 2 * i, claim=c))
        rows.append(row(101 + 2 * i, note="→ 판정=지연`"))
    out = c48.reverify_contradictions(rows)
    counted = {c for c, _ in out["contradictions"]}
    for i, c in enumerate(claims):
        accused = c48.reverify_claim_mark(c) == "★ 모순"
        assert accused is ((100 + 2 * i) in counted), c
