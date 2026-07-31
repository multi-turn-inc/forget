"""롤링 응고의 순수 로직 검증 — API 없이 돈다 (runner 프로토타입, P5).

불변식: (1) tool_use/tool_result 쌍은 경계에서 찢어지지 않는다,
(2) splice 후에도 역할 교대가 성립한다, (3) 원래 과업 원문은 항상 보존된다.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "research", "devloop", "runner")
)

from forget_runner import choose_cut_index, splice_consolidated  # noqa: E402


def _u(text="ok"):
    return {"role": "user", "content": text}


def _u_result(n=1):
    return {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": "out"}
            for i in range(n)
        ],
    }


def _a_tooluse(n=1):
    return {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": f"t{i}", "name": "bash", "input": {}}
            for i in range(n)
        ],
    }


def _a_text():
    return {"role": "assistant", "content": [{"type": "text", "text": "done"}]}


def _tool_pairs(k):
    msgs = []
    for _ in range(k):
        msgs += [_a_tooluse(), _u_result()]
    return msgs


def test_cut_lands_on_assistant():
    msgs = [_u("과업")] + _tool_pairs(10) + [_a_text()]
    cut = choose_cut_index(msgs, keep_recent=5)
    assert cut > 0
    assert msgs[cut]["role"] == "assistant"


def test_cut_never_orphans_tool_result():
    # keep_recent가 tool_result 위에 떨어져도 경계는 assistant까지 내려온다
    msgs = [_u("과업")] + _tool_pairs(8)
    for keep in range(1, len(msgs)):
        cut = choose_cut_index(msgs, keep_recent=keep)
        if cut:
            first_kept = msgs[cut]
            assert first_kept["role"] == "assistant", f"keep={keep}"


def test_too_short_returns_zero():
    msgs = [_u("과업"), _a_text()]
    assert choose_cut_index(msgs, keep_recent=12) == 0


def test_splice_preserves_original_prompt_and_alternation():
    msgs = [_u("원래 과업 문장")] + _tool_pairs(10) + [_a_text()]
    cut = choose_cut_index(msgs, keep_recent=5)
    out = splice_consolidated(msgs, cut, "다이제스트 본문", "원래 과업 문장")
    assert out[0]["role"] == "user"
    assert "원래 과업 문장" in out[0]["content"]
    assert "다이제스트 본문" in out[0]["content"]
    assert out[1]["role"] == "assistant"
    # 역할 교대 성립
    for a, b in zip(out, out[1:]):
        assert a["role"] != b["role"]
    # 최근 창은 원문 그대로
    assert out[1:] == msgs[cut:]


def test_splice_shrinks():
    msgs = [_u("과업")] + _tool_pairs(20)
    cut = choose_cut_index(msgs, keep_recent=6)
    out = splice_consolidated(msgs, cut, "d", "과업")
    assert len(out) < len(msgs)
    assert len(out) == 1 + (len(msgs) - cut)
