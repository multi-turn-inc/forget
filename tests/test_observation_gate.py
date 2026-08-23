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


def test_tool_call_markup_is_rejected_by_sanitize() -> None:
    # 실원장 실표본 (2026-08-23): 에이전트 자신의 도구 호출 인자가 "사용자가 말한
    # 지속 사실"로 저장돼 있었다 — 동일 사본 3개 포함 21건. 마크업은 발화가 아니다.
    from forget.memory_engine import low_value_memory_reason

    for junk in (
        'User said: <parameter name="source_role">assistant',
        'User said: <parameter name="metadata">{"cycle": 61, "track": "devloop"}',
        '<invoke name="add_memory">',
    ):
        assert low_value_memory_reason(junk) == "tool_call_markup", junk
    # XML을 *이야기하는* 정상 산문은 통과해야 한다 — 개발자의 원장이다.
    for prose in (
        "HTML의 <div> 태그 안에 파라미터를 넣는 설계는 기각했다",
        "함수 매개변수(parameter) 명명 규칙을 snake_case로 정했다",
    ):
        assert low_value_memory_reason(prose) == "", prose


def test_a_bare_dot_cli_argument_is_not_a_sentence_boundary() -> None:
    # 실사례 (2026-08-23): "pip install -e . --no-deps"의 홀로 선 마침표가 문장
    # 끝으로 읽혀 "--no-deps) → launchctl …"라는 머리 없는 조각이 원장에 남았다.
    from forget.memory_engine import split_sentences

    parts = split_sentences(
        "커밋 ad968f8 → editable 설치(pip install -e . --no-deps) → launchctl kickstart. "
        "이제 venv가 작업 트리를 임포트한다."
    )
    assert len(parts) == 2
    assert "--no-deps" in parts[0], "CLI 인자 마침표에서 문장이 잘렸다"
    # 정상 문장 분리는 그대로여야 한다.
    assert split_sentences("정훈은 커피를 마신다. 그리고 일을 시작한다.") == [
        "정훈은 커피를 마신다.", "그리고 일을 시작한다."]


def test_kill_switch_restores_old_behavior(monkeypatch) -> None:
    monkeypatch.setenv("MEM1_OBSERVATION_GATE", "0")
    facts = _facts([{"role": "assistant", "content": "Consider offering a buy-it-now option for the painting."}])
    assert facts, "gate off: assistant sentences flow through again"
