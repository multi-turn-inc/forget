"""c48_step0_check.status_stamp_reconcile — 상태줄 ↔ 판정문 정합 (c169, 관측 90 처치 · P54).

왜 이 파일이 있는가. 파트 D의 판별 입력은 각 절의 `- 상태:` **한 줄**이다. 그 줄을 쓰는
손과 판정문을 쓰는 손은 같은 손이되 **다른 줄**이고, 상태줄만 내려가고 판정문이 없으면
파트 D는 그 예측을 시계에서 내리고 **영원히 침묵한다** — 침묵이 "판정 완료"로 읽힌다.

가장 중요한 단언 셋.

① **판정문의 서식지는 셋이다** (관측 98). 순진한 자[尺](`MARK_RE` 단독)로 재면 c169 실측
   기준 시계 아래 38건 중 **23건**이 "판정문 부재"로 나오고 그 23건은 전부 판정문을
   갖고 있다. 서식지를 더할 때마다 23 → 8 → 0. 아래 세 회귀가 서식지를 **각각** 고정한다 —
   `VERDICT_HABITATS`에서 하나를 빼면 대응하는 테스트가 깨진다.

② **고발의 문턱은 «도장 없음»이 아니라 «표지 자체가 없음»이다.** `_is_verdict_line`이
   도장 없는 진짜 처분 줄을 버린다는 것은 c124 손 판정(P18·P26·P28·P29)으로 이미
   측정돼 있다. 그 기지의 오류를 고발로 승격하면 계기는 첫날 늑대소년이 된다(관측 87).

③ **두 방향 모두 인쇄된다.** 조용한 쪽(상태줄 단독 하강)과 안전한 쪽(도장 단독) 둘 다.
   어느 쪽도 침묵이어서는 안 된다는 것이 관측 90의 기대 동작이다.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
# 명시 삽입 — 계기가 내부에서 넣어주는 것에 기대면 테스트 순서에 의존한다.
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_status_stamp", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

HEAD = "## P90 — 합성 표본 (등록 사이클 1)\n\n"


def test_status_dropped_without_any_verdict_line_is_accused():
    """★ 관측 90의 진짜 고발 대상 — 상태줄만 내려가고 판정문이 없다."""
    rec = c48.status_stamp_reconcile(HEAD + "- 상태: (a) 지지 · (b) 반증\n")
    assert rec["silent_drop"] == ["P90"]
    assert rec["down"] == ["P90"]
    assert rec["clean_down"] == []


def test_plain_bullet_habitat_clears_the_accusation():
    """서식지 ① 평문 불릿 — `- **판정 (c76, …)**: 적중`."""
    rec = c48.status_stamp_reconcile(
        HEAD + "- 상태: (a) 지지\n\n- **판정 (c76, 2026-08-08)**: 적중.\n")
    assert rec["silent_drop"] == []
    assert rec["clean_down"] == ["P90"]
    assert rec["sections"]["P90"]["habitat_hits"]["불릿"] == 1


def test_star_prefixed_bullet_habitat_clears_the_accusation():
    """서식지 ② 강조 접두 — P44의 `- **★ 판정 (사이클 160 …)**`.

    `MARK_RE`의 `\\*{0,2}`는 `★`를 넘기지 못한다. 이 회귀를 깨려면
    `VERDICT_HABITATS`의 `불릿-강조접두` 항을 빼면 된다.
    """
    rec = c48.status_stamp_reconcile(
        HEAD + "- 상태: (a) 지지\n\n"
        "- **★ 판정 (사이클 160 적대 감사 — 표본 창 c155~c160 마감).** 지지.\n")
    assert rec["silent_drop"] == []
    assert rec["sections"]["P90"]["habitat_hits"]["불릿-강조접두"] == 1


def test_heading_habitat_clears_the_accusation():
    """서식지 ③ 소제목 — P15의 `### P15 — 판정 (audit-70 위임 …)`.

    `###`는 절을 끊지 않는다(끊는 것은 `## `). 이 줄은 그 절의 몸 안에 있다.
    """
    rec = c48.status_stamp_reconcile(
        HEAD + "- 상태: (a) 반증 · (b) 지지\n\n"
        "### P90 — 판정 (audit-70 위임 판정 · 대차대조 기재 = 사이클 71)\n\n본문.\n")
    assert rec["silent_drop"] == []
    assert rec["sections"]["P90"]["habitat_hits"]["소제목"] == 1


def test_unstamped_marker_is_counted_but_not_accused():
    """표지는 있으나 무도장 — c124가 이미 잰 v2의 거래이지 고발이 아니다."""
    rec = c48.status_stamp_reconcile(HEAD + "- 상태: 폐기\n\n- **처분**: 폐기한다.\n")
    assert rec["silent_drop"] == []
    assert rec["unstamped_down"] == ["P90"]
    assert rec["clean_down"] == []


def test_stamp_only_is_flagged_as_the_safe_direction():
    """★ 안전한 쪽 — 도장 달린 판정 줄이 있는데 상태줄 전건이 시계 위."""
    rec = c48.status_stamp_reconcile(
        HEAD + "- 상태: (a) 시계-가동 · (b) 시계-가동\n\n"
        "- **판정 (c100, 2026-08-10)**: 지지.\n")
    assert rec["stamp_only"] == ["P90"]
    assert rec["stamp_only_new"] == ["P90"], "상수 밖 절은 고발돼야 한다"
    assert rec["stamp_only_known"] == []


def test_hand_maintained_constant_splits_known_stamp_only():
    """기지분은 상수가 가른다 — 매 사이클 고발하면 그 인쇄가 소음이 된다(관측 87).

    상수의 값은 **사유**이며, 사유 없는 등재는 면죄부다(P54 (c) 반증 조건).
    """
    assert "P4" in c48.STAMP_ONLY_ADJUDICATED
    assert c48.STAMP_ONLY_ADJUDICATED["P4"].strip(), "사유 없는 등재는 면죄부다"
    rec = c48.status_stamp_reconcile(
        "## P4 — 합성 표본 (등록 사이클 1)\n\n- 상태: 시계-미시작\n\n"
        "- **처분 (사이클 78, 2026-08-08): 집행 시작** — 판정이 아니라 착공 선언.\n")
    assert rec["stamp_only_known"] == ["P4"]
    assert rec["stamp_only_new"] == []


def test_partially_judged_section_is_its_own_bucket():
    """팔 일부만 판정났는데 표지가 없다 — 같은 병의 약한 판본, 별도 칸."""
    rec = c48.status_stamp_reconcile(
        HEAD + "- 상태: (a) 지지 · (b) 시계-가동\n")
    assert rec["partial_drop"] == ["P90"]
    assert rec["silent_drop"] == [], "부분 하강을 조용한 하강으로 세면 분모가 오염된다"


def test_unrecorded_arm_is_neither_open_nor_closed():
    """`무기재`는 하자 라벨이다 — 판정으로도 시계로도 세지 않는다."""
    rec = c48.status_stamp_reconcile(HEAD + "- 상태: 무기재\n")
    assert rec["sections"]["P90"] == {**rec["sections"]["P90"], "open": 0, "closed": 0}
    assert rec["silent_drop"] == []


def test_duplicate_pid_is_reported_with_both_line_numbers():
    """중복 pid — 이 눈은 **먼저**를, 파트 D의 `recs`는 **나중**을 택한다(정반대)."""
    text = (HEAD + "- 상태: (a) 지지\n\n- **판정 (c1, 2026-08-01)**: 지지.\n\n"
            "## P90 — 같은 번호 다른 예측 (등록 사이클 2)\n\n- 상태: 반증\n")
    rec = c48.status_stamp_reconcile(text)
    assert list(rec["duplicate_pids"]) == ["P90"]
    assert len(rec["duplicate_pids"]["P90"]) == 2
    # 먼저 나온 절이 이긴다 — 그 절은 판정문을 갖고 있으므로 고발되지 않는다.
    assert rec["silent_drop"] == []


def test_non_prediction_heading_closes_the_section():
    """`## ` 비-P 헤딩 아래의 판정문은 앞 절 것이 아니다 — 절 경계 위임의 계약."""
    rec = c48.status_stamp_reconcile(
        HEAD + "- 상태: (a) 지지\n\n## 게이트 종속 상태표\n\n"
        "- **판정 (c99, 2026-08-09)**: 지지.\n")
    assert rec["silent_drop"] == ["P90"], "절 밖 판정문이 고발을 지우면 거짓 음성이다"


def test_live_ledger_has_no_silent_drop():
    """실 대장 대조 — 합성 표본만으로는 자[尺]가 현실을 못 본다는 사실을 못 잡는다.

    c169 실측: 시계 아래 36건 중 **표지 자체 없음 0건**. 이 단언이 깨지는 날은
    누군가 상태줄만 내리고 판정문을 안 쓴 날이며, 그것이 P54 (a)의 표본이다.
    """
    from c124_retro_prep import PRED  # noqa: PLC0415
    rec = c48.status_stamp_reconcile(PRED.read_text(encoding="utf-8"))
    assert rec["silent_drop"] == []
    assert rec["down"], "시계 아래가 0건이면 이 눈은 아무것도 재지 않은 것이다"


def test_live_ledger_duplicate_pids_are_the_two_known_ones():
    """c169 실측 = P7 · P39. **P39만 기지였고 P7은 오늘 발견분**(관측 99).

    개명 패킷(게이트 대기)이 승인돼 번호가 갈리면 이 단언이 깨진다 — 그때 이 줄을
    고치는 손은 곧 그 개명을 집행한 손이다.
    """
    from c124_retro_prep import PRED  # noqa: PLC0415
    rec = c48.status_stamp_reconcile(PRED.read_text(encoding="utf-8"))
    assert sorted(rec["duplicate_pids"]) == ["P39", "P7"]
