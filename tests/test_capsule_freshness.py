"""Capsule freshness: fast-layer state must carry its age (field note F1, #devloop).

Design contract (LOOP.md persona model): goal/next-action are fast-layer
state — without an age annotation and a staleness warning they harden into
false "current" facts, which is exactly the failure Momento (2606.00832)
names: treating prior session history as current context without
re-validation.
"""

from datetime import datetime, timedelta, timezone

from forget.store import _render_context_capsule_text, _state_age_hours, _state_age_label


def _capsule(age_hours):
    recorded = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return {
        "goal": "베타 런치 준비",
        "status": "in_progress",
        "next_action": {"action": "데모 영상 녹화"},
        "state_recorded_at": recorded,
        "state_age_hours": float(age_hours),
    }


def test_age_travels_with_the_goal_line():
    text = _render_context_capsule_text(_capsule(3))
    assert "현재 목표: 베타 런치 준비" in text
    assert "시간 전 기록" in text.splitlines()[0]


def test_stale_state_gets_a_warning_line():
    text = _render_context_capsule_text(_capsule(49))
    assert "⚠ 상태 신선도" in text
    assert "재검증 후 행동" in text
    # the warning must sit early enough to survive budget trimming
    assert text.splitlines().index(next(l for l in text.splitlines() if "⚠" in l)) <= 3


def test_fresh_state_has_no_warning():
    text = _render_context_capsule_text(_capsule(2))
    assert "⚠ 상태 신선도" not in text


def test_stale_threshold_is_configurable(monkeypatch):
    monkeypatch.setenv("MEM1_CAPSULE_STALE_HOURS", "1")
    assert "⚠ 상태 신선도" in _render_context_capsule_text(_capsule(2))
    monkeypatch.setenv("MEM1_CAPSULE_STALE_HOURS", "100")
    assert "⚠ 상태 신선도" not in _render_context_capsule_text(_capsule(49))


def test_age_helpers_handle_garbage():
    assert _state_age_hours(None) is None
    assert _state_age_hours("") is None
    assert _state_age_hours("not-a-date") is None
    assert _state_age_label(None) == ""
    assert _state_age_label(0.2) == "방금 기록"
    assert "일 전 기록" in _state_age_label(60)


def test_capsule_without_age_renders_unchanged():
    text = _render_context_capsule_text(
        {"goal": "g", "status": "s", "next_action": {"action": "a"}}
    )
    assert "기록)" not in text and "⚠" not in text
