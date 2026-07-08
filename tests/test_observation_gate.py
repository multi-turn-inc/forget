"""Observation gate — memories are observations about the user, not echoes.

Measured on the STALE diag corpus the ungated splitter stored 85% assistant
advice/knowledge dumps; the gate flips the default for anonymous assistant
sentences to drop, keeping only the register that records user state. Named
participants and agent-scoped adds speak AS the observed entity and bypass
the gate entirely.
"""

from forget.memory_engine import extract_memories


def _facts(messages, **kwargs):
    return extract_memories(messages, infer=True, **kwargs)


def test_anonymous_assistant_advice_is_dropped() -> None:
    facts = _facts(
        [
            {
                "role": "assistant",
                "content": (
                    "Consider offering a buy-it-now option for the live painting. "
                    "**GolfNow**: a tee time booking platform, so you can search for courses. "
                    "Remember to stay respectful and open-minded. "
                    "Do you know if any of those websites allow online booking?"
                ),
            }
        ]
    )
    assert facts == []


def test_assistant_user_state_record_is_kept() -> None:
    facts = _facts(
        [
            {
                "role": "assistant",
                "content": "Since you mentioned you don't have any debt repayment goals, we can start there.",
            }
        ]
    )
    assert len(facts) == 1


def test_named_assistant_participant_bypasses_gate() -> None:
    facts = _facts([{"role": "assistant", "name": "Planner", "content": "I work on migration plans."}])
    assert facts, "named participants are observation subjects"


def test_agent_scoped_add_bypasses_gate() -> None:
    facts = _facts([{"role": "assistant", "content": "Agent handles entity checks."}], assistant_is_subject=True)
    assert facts


def test_user_smalltalk_is_dropped_but_state_is_kept() -> None:
    facts = _facts(
        [
            {"role": "user", "content": "That sounds amazing! Thanks for the tips."},
            {"role": "user", "content": "I just moved to Austin and need a new dentist."},
        ]
    )
    assert any("Austin" in fact for fact in facts)
    assert not any("sounds amazing" in fact.lower() for fact in facts)
    assert not any(fact.lower().startswith("thanks") for fact in facts)


def test_korean_acknowledgments_are_dropped_but_state_is_kept() -> None:
    facts = _facts(
        [
            {"role": "user", "content": "좋아. 진행하자."},
            {"role": "user", "content": "결제 provider는 Paddle로 확정했어."},
        ]
    )
    assert any("Paddle" in fact for fact in facts)
    assert not any(fact.startswith(("좋아", "진행하자")) for fact in facts)


def test_session_shards_are_rejected_by_sanitize() -> None:
    from forget.memory_engine import low_value_memory_reason

    shard = '다.\\n\\n","phase":"final_answer","memory_citation":{"entries":[{"path":"MEMORY.md"'
    assert low_value_memory_reason(shard) == "session_shard"
    assert low_value_memory_reason('User is planning to move into my new home soon') == ""


def test_kill_switch_restores_old_behavior(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_OBSERVATION_GATE", "0")
    facts = _facts([{"role": "assistant", "content": "Consider offering a buy-it-now option for the painting."}])
    assert facts, "gate off: assistant sentences flow through again"
