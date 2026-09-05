"""An assembled context must not be empty while candidates exist.

Measured 2026-08-23 on eval set v1, stratum machine_resume (the one with real
`used` gold): six of 28 queries retrieved ten candidates each and assembled
zero or one memory. The budget loop did `break` on the first candidate that
did not fit, so one long memory at the front swallowed the chance of every
shorter memory behind it — and the resume-workspace line had already eaten
453 to 779 of the 800-token budget before the loop began.

Silence is not recall. These tests pin three properties:
  1. a candidate that does not fit is skipped, not fatal
  2. if nothing fits, the top candidate is truncated in rather than dropped
  3. the assembled context still respects the budget it was given
"""
import os
import uuid

import pytest

os.environ.setdefault("MEM1_DB_PATH", "/tmp/forget-test-starvation.sqlite3")

from forget import store  # noqa: E402
from forget.db import init_db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "starve.sqlite3"))
    monkeypatch.setenv("MEM1_RECALL_TEMPORAL", "0")
    init_db()
    yield


def _add(user: str, text: str) -> None:
    store.add_memories({"messages": [{"role": "user", "content": text}], "user_id": user,
                        "infer": False, "hebbian": False})


def _assemble(user: str, query: str, budget: int) -> dict:
    return store.assemble_context({
        "query": query, "filters": {"user_id": user},
        "budget_tokens": budget, "record_trace": False,
    })


def test_a_long_first_candidate_does_not_starve_the_rest():
    user = f"st-{uuid.uuid4().hex[:8]}"
    _add(user, "캐시 배치 " + "아주 긴 서술이 계속 이어진다 " * 60)     # 예산을 혼자 넘는 후보
    # 서로 다른 사실이어야 한다 — 숫자만 다른 문장은 근접중복 필터가 정당하게 지운다.
    for fact in ("캐시 배치 실측에서 프리픽스가 불변이었다",
                 "캐시 배치 실측 워밍은 133밀리초로 끝났다",
                 "캐시 배치 실측 대조군은 매 턴 재계산했다",
                 "캐시 배치 실측 결론은 안정도가 위치를 정한다는 것이다"):
        _add(user, fact)
    result = _assemble(user, "캐시 배치 실측", budget=200)
    assert result["selected_count"] >= 2, (
        f"긴 후보 하나가 뒤의 짧은 후보를 삼켰다 (selected={result['selected_count']})")


def test_nothing_fits_still_returns_something():
    user = f"st-{uuid.uuid4().hex[:8]}"
    _add(user, "캐시 배치 " + "예산보다 훨씬 긴 문장이 반복된다 " * 80)
    result = _assemble(user, "캐시 배치", budget=60)
    assert result["selected_count"] == 1, "후보가 있는데 빈 맥락을 돌려줬다 — 침묵은 회상이 아니다"
    assert result["context"].strip(), "선택은 셌는데 맥락 문자열이 비었다"


def test_the_budget_is_still_respected():
    user = f"st-{uuid.uuid4().hex[:8]}"
    for i in range(30):
        _add(user, f"캐시 배치 실측 기록 {i}: " + "토큰을 먹는 서술 " * 12)
    budget = 300
    result = _assemble(user, "캐시 배치 실측", budget=budget)
    assert result["selected_count"] >= 1
    # 기아 방지가 예산 초과 허가증이 되어선 안 된다 (자른 1건 예외는 예산 안에서 자른다)
    assert int(result["used_tokens"]) <= budget, f"{result['used_tokens']} > {budget}"


def test_truncation_is_marked_so_the_reader_knows():
    user = f"st-{uuid.uuid4().hex[:8]}"
    _add(user, "캐시 배치 " + "잘릴 수밖에 없는 긴 서술 " * 80)
    result = _assemble(user, "캐시 배치", budget=60)
    memories = result.get("memories") or []
    assert memories and memories[0].get("context_truncated") is True
