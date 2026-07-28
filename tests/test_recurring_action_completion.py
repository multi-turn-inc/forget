"""#14 회귀: 감시의 성공은 감시의 종료가 아니다."""
from forget.store import _context_completion_match, _context_recurring_action

MONITOR = "Monitor PR #13 for maintainer comments, reviews, and checks."


def _match(action: str, observed_first_action: str, **observed_extra):
    return _context_completion_match(
        action_text=action,
        row={"first_action": observed_first_action, "notes": ""},
        observed={"first_action": observed_first_action, **observed_extra},
        trace_payload={},
    )


def test_no_change_observation_keeps_monitor_open() -> None:
    # 이슈의 라이브 재현: 열람 성공 + 변화 없음 → 완료로 오독되던 케이스
    result = _match(MONITOR, "Fetched PR #13: open, draft, mergeable — 0 comments, 0 reviews, 0 checks from maintainers")
    assert result["matched"] is False
    assert result["mode"] == "recurring_no_state_change"


def test_state_change_lets_monitor_complete() -> None:
    result = _match(MONITOR, "PR #13: maintainer posted new comments and reviews — changes requested, checks now failing")
    assert result["matched"] is True


def test_explicit_marking_always_completes() -> None:
    result = _match(MONITOR, "checked PR #13, nothing new", completed_next_action=MONITOR)
    assert result["matched"] is True
    assert result["mode"] == "explicit_text"


def test_non_recurring_lexical_overlap_unchanged() -> None:
    result = _match(
        "Update the README quickstart with the resolved storage path",
        "Edited README quickstart section documenting resolved storage path default",
    )
    assert result["matched"] is True


def test_recurring_detector_scope() -> None:
    assert _context_recurring_action("Poll the CI status every hour")
    assert _context_recurring_action("배포 파이프라인을 모니터링한다")
    assert not _context_recurring_action("Write the migration script")
