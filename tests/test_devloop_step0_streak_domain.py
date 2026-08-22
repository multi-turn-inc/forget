"""c48_step0_check — 상태형 계수기의 **정의역** (c191 신설, 관측 119 · 계기 큐 ㉰).

왜 이 파일이 있는가. P52는 «N연속»을 세는 손을 계기로 옮겼다. 그 처치는 집행됐고
**지금도 작동 중이며**, 다만 자기가 계기화한 둘에만 걸려 있었다. 그 경고문 바로
옆에서 세 번째 계수기(`rt` 불변)가 **20사이클간** 표류했다 — c189 주장 50 · 참값 58.
씨앗은 «연속»이 아니라 c170 감사가 쓰던 **창의 크기 30**이었다(관측 96의 정의 그대로).

**병이 아니라 처치의 정의역이 문제였다.** 그래서 이 파일이 거는 것은 두 가지다.

① **rt 편입**(수용 기준 ③). 값 서식이 «N**사이클** 연속»이라 구판 `STREAK_VALUE_RX`는
   그 계수기를 **한 번도 못 봤다** — 표류가 첫 겹이고, 표류를 잡을 대조기가 서식을
   몰랐던 것이 둘째 겹이다. 두 겹을 한 사이클에 막는다.

② **정의역 자체의 탐지기**(수용 기준 ④). 관측 119가 물은 것은
   *"셋 중 하나가 밖이었다면 **넷째가 있는지 아무도 모른다**"*이다. 손이 유지하는
   스냅샷 목록은 그 물음에 답하지 못한다(다섯째는 목록에 없으므로 영원히 안 보인다).
   `uninstrumented_streaks`는 어휘를 선언하지 않고 원장에서 긁어 군집한다.

관행 ⑯: **능력은 합성 표본으로 고정**하고 실 원장에는 **프레임 독립 항등식**만 건다.
실 원장에 «미계기화 N가족»을 상수로 박으면 다음 손이 그 계수기를 계기화할 때
고치는 쪽이 벌을 받는다(관측 106의 자물쇠 · c191 자신이 방금 6가족을 인쇄했다).
"""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "research" / "devloop" / "scripts"
sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_streak_domain", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)

LEDGER = ROOT / "research" / "devloop" / "metrics.jsonl"


def _ledger():
    rows = []
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


# ─────────────────────────── ① rt 편입 (수용 기준 ③) ───────────────────────────

def test_value_rx_sees_the_cycle_infix_form():
    """`rt` 계수기의 실제 서식은 «N사이클 연속»이다 — 구판이 못 보던 자리."""
    assert c48.STREAK_VALUE_RX.findall("`rt` **50사이클 연속** 2.00") == ["50"]


def test_value_rx_still_sees_the_bare_form():
    """확장이 기존 두 계수기의 서식을 깨지 않는다(회귀 방향)."""
    assert c48.STREAK_VALUE_RX.findall("캡슐 miss **71연속**") == ["71"]


def test_rt_counter_is_registered_on_a_machine_readable_field():
    """계기화의 전제 — 이 계수기는 원장 **열**에서 재계산된다(산문이 아니라).

    미계기화 계수기 셋(«넷째에서 정지»·«커밋 스코프 미측정»·«HAND 수행 회차»)이
    밖에 남은 이유가 정확히 이것이다: 전용 열이 없어 상태가 산문에만 산다.
    """
    entry = [e for e in c48.STREAK_COUNTERS if e[1] == "restore_turns"]
    assert len(entry) == 1, c48.STREAK_COUNTERS
    _, field, value, vocab = entry[0]
    assert value == 2 and vocab == r"`rt`", entry[0]
    assert any(field in r for r in _ledger()), "원장에 restore_turns 열이 없다"


def test_field_streak_counts_rt_backwards_to_the_break():
    """자[尺] 고정 — 합성 표본. 끊긴 행은 세지 않는다."""
    rows = [{"cycle": c, "restore_turns": v} for c, v in
            [(1, 3), (2, 2), (3, 3), (4, 2), (5, 2), (6, 2)]]
    st = c48.field_streak(rows, "restore_turns", 2)
    assert st["streak"] == 3 and st["break"] == (3, 3), st
    assert st["domain"] == 6, st
    # 라벨은 «연속»이고 값은 «정의역»이 아니다 — 관측 96의 정중앙.
    assert st["streak"] != st["domain"]


# ────────────────────── ② 정의역 탐지기 (수용 기준 ④) ──────────────────────

def _prose(cycle, note):
    return {"cycle": cycle, "restore_note": note}


def test_detector_reports_a_live_recurring_uninstrumented_counter():
    """넷째를 찾는 것이 이 눈의 존재 이유다."""
    rows = [_prose(c, f"서열 18′ 프라임 = 넷째에서 **{c - 169}사이클 연속** 정지")
            for c in range(174, 191)]
    got = c48.uninstrumented_streaks(rows)
    assert len(got) == 1, got
    assert got[0]["cycles"] == list(range(174, 191)), got[0]
    assert got[0]["series"][-1] == (190, 21), got[0]


def test_detector_does_not_report_an_instrumented_counter():
    """자기 처치를 자기가 «미처치»로 고발하지 않는다 — c191 첫 실행이 낸 실측 결함.

    어휘 정본 `` `rt` ``는 **장식이 곧 식별자**다. 판정을 라벨 키(장식 제거본)에
    걸면 이 계수기는 계기화한 그 사이클에도 «X»로 인쇄된다.
    """
    rows = [_prose(c, f"`rt` **{c - 131}사이클 연속** 2.00") for c in range(178, 191)]
    assert c48.uninstrumented_streaks(rows) == []


def test_detector_ignores_a_dead_counter():
    """생존 창 밖은 고발하지 않는다 — 죽은 계수기를 매 사이클 적으면 소음기가 된다."""
    rows = [_prose(c, f"게이트 무승인 **{c - 131}사이클 연속**") for c in range(135, 157)]
    rows += [_prose(c, "무관한 산문") for c in range(157, 191)]
    assert c48.uninstrumented_streaks(rows) == []


def test_detector_ignores_a_one_off_claim():
    """재발 문턱 아래 = 에피소드. 한 번 적힌 «3연속»은 계수기가 아니다."""
    rows = [_prose(c, "무관한 산문") for c in range(180, 190)]
    rows.append(_prose(190, "간접 판정이 **3연속** 참이었다"))
    assert c48.uninstrumented_streaks(rows) == []


# ─────────────────── 실 원장 — 프레임 독립 항등식만 (관행 ⑯) ───────────────────

def test_real_ledger_report_satisfies_its_own_predicate():
    """수를 박지 않는다. 인쇄된 가족이 **자기 술어를 만족하는지**만 건다."""
    rows = _ledger()
    last = max(int(r["cycle"]) for r in rows)
    got = c48.uninstrumented_streaks(rows)
    for d in got:
        assert len(d["cycles"]) >= c48.STREAK_RECUR_MIN, d
        assert d["cycles"][-1] >= last - c48.STREAK_LIVE_WINDOW + 1, d
    print(f"\n[c191 실측] 미계기화·재발·생존 가족 {len(got)}건 "
          f"(프레임 = 원장 최종 c{last}): {[d['key'] for d in got]}")


def test_real_ledger_rt_streak_is_frame_dependent_and_printed_not_asserted():
    """`rt` 연속값은 프레임에 따라 변한다 — 상수로 박으면 다음 사이클이 붉어진다."""
    rows = _ledger()
    st = c48.field_streak(rows, "restore_turns", 2)
    assert st["frame_last"] == max(int(r["cycle"]) for r in rows)
    assert st["streak"] >= 1 and st["streak"] <= st["domain"]
    print(f"\n[c191 실측] rt 불변 2 연속 = {st['streak']} "
          f"(프레임 = 원장 최종 c{st['frame_last']} · 정의역 {st['domain']}행 · "
          f"중단 {st['break']})")
