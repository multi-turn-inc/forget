"""봉쇄 계측의 자[尺] — c48_step0_check.blockade_rows / queue_intersection (c151).

왜 이 둘이 감시 아래로 들어오는가. audit-150 §3이 실측한 결함은 파서 버그가 아니라
**재지 않은 술어**였다: 규약이 '미커밋 파일'을 '타 세션 활성'의 프록시로 43사이클간
썼는데, 활성을 재는 코드는 없었다. 비-WIP 시험("장기 mtime 불변")은 루프가 c31에
자기 손으로 성문해 두었고 43사이클간 집행되지 않았다(frictions.md:515-516).

재는 코드가 붙었으니 자[尺]도 고정한다. 선례: c82가 part_a 파싱을, c71이 번호·모드
산술을 같은 이유로 회귀 아래 넣었다 — "루프의 판단 전부가 이 스크립트 출력에
의존하는데 파서의 절반이 무감시다"(audit-80 §3-(b)).
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "devloop" / "scripts" / "c48_step0_check.py"
spec = importlib.util.spec_from_file_location("c48_step0_check_blockade", SCRIPT)
c48 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c48)


# ---- blockade_rows -------------------------------------------------------------

def test_unreadable_paths_stay_visible_instead_of_vanishing():
    """핵심 성질 — 못 읽은 경로는 목록에서 빠지지 않는다.

    빠지면 "봉쇄 3건 전부 무접촉" 같은 거짓 **전수** 주장이 만들어진다. 자기규율
    8회차의 회귀 고정: 0건은 '없음'과 '못 봄'을 구별하지 않는다. 행은 남고 판정만
    '판정 불가'다 — compare_fingerprint의 UNKNOWN 규율과 같은 방향.
    """
    rows = c48.blockade_rows([("사라진.py", None)], head_ct=1000.0, now_ts=2000.0)
    assert len(rows) == 1
    path, since_now, vs_head, verdict = rows[0]
    assert (path, since_now, vs_head) == ("사라진.py", None, None)
    assert verdict.startswith("판정 불가")


def test_touched_and_untouched_split_at_the_harvest_commit():
    """c150 실측 형상의 축소판: 하나는 수확 이후 손댐(활성), 하나는 그 전에 멈춤."""
    head = 100_000.0
    now = head + 3600.0 * 10
    rows = c48.blockade_rows(
        [("활성.jsonl", head + 3600.0), ("정지.py", head - 3600.0 * 90)], head, now)
    assert [r[3] for r in rows] == ["수확 이후 접촉", "수확 이후 무접촉"]
    assert rows[0][1] == pytest.approx(9.0)      # now 대비 9시간 경과
    assert rows[1][2] == pytest.approx(-90.0)    # HEAD 대비 90시간 전


def test_verdict_vocabulary_stops_short_of_calling_it_dead():
    """판정은 '무접촉'까지만 말한다 — '죽은 WIP'는 사람의 판단이고 계기의 몫이 아니다.

    이 스크립트의 상시 규약("결론 문장을 상수로 인쇄하지 않는다")의 회귀 고정.
    """
    rows = c48.blockade_rows([("정지.py", 0.0)], head_ct=100_000.0, now_ts=200_000.0)
    verdict = rows[0][3]
    assert "무접촉" in verdict
    assert "죽" not in verdict and "폐기" not in verdict


def test_empty_input_yields_no_rows_not_a_claim():
    assert c48.blockade_rows([], head_ct=1.0, now_ts=2.0) == []


# ---- queue_intersection --------------------------------------------------------

def test_intersection_is_the_direction_that_can_lift_the_blockade():
    """audit-150 §3의 비대칭.

    루프가 매 사이클 인쇄해 온 것은 '내 변경분 ∩ 봉쇄'(= 내가 밟지 않았다)였고,
    봉쇄를 풀 증명은 '코드 큐 ∩ 봉쇄'(= 내 일이 남의 파일과 무관하다)다.
    c150 실측 = 후자 0건(큐는 store.py, 봉쇄 5건에 없음).
    """
    blockade = ["forget/proxy.py", "tests/test_forget_proxy.py",
                "research/replay/candidates_v0.jsonl"]
    assert c48.queue_intersection(blockade, ("forget/store.py",)) == []
    assert c48.queue_intersection(blockade, ("forget/proxy.py",)) == ["forget/proxy.py"]


def test_intersection_does_not_invent_directory_containment():
    """디렉터리 접두 매칭을 짐작하지 않는다 — 짐작은 관측 63이 태어난 자리다."""
    assert c48.queue_intersection(["forget/store.py"], ("forget/",)) == []


def test_default_queue_is_the_declared_constant():
    """기본 인자가 선언 상수를 따라간다 — 큐가 바뀌면 인쇄와 검사가 함께 움직인다."""
    assert c48.queue_intersection(list(c48.CODE_QUEUE_PATHS)) == sorted(c48.CODE_QUEUE_PATHS)
