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
