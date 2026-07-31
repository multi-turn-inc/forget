"""롤링 응고의 순수 로직 검증 — API 없이 돈다 (runner 프로토타입, P5).

불변식: (1) tool_use/tool_result 쌍은 경계에서 찢어지지 않는다,
(2) splice 후에도 역할 교대가 성립한다, (3) 원래 과업 원문은 항상 보존된다,
(4) 최근 창은 메시지 개수가 아니라 **토큰 길이**로 잰다 — 거대한 도구 결과
하나가 창을 통째로 차지할 수 있고, 작은 메시지 여럿이 들어올 수도 있다.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "research", "devloop", "runner")
)

from forget_runner import (  # noqa: E402
    choose_cut_index,
    estimate_message_tokens,
    splice_consolidated,
)


def _u(text="ok"):
    return {"role": "user", "content": text}


def _u_result(chars=200):
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t0", "content": "x" * chars}],
    }


def _a_tooluse():
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "t0", "name": "bash", "input": {}}],
    }


def _a_text():
    return {"role": "assistant", "content": [{"type": "text", "text": "done"}]}


def _tool_pairs(k, result_chars=200):
    msgs = []
    for _ in range(k):
        msgs += [_a_tooluse(), _u_result(result_chars)]
    return msgs


def _tok(msgs):
    return sum(estimate_message_tokens(m) for m in msgs)


def test_cut_lands_on_assistant():
    msgs = [_u("과업")] + _tool_pairs(10) + [_a_text()]
    cut = choose_cut_index(msgs, keep_tokens=300)
    assert cut > 0
    assert msgs[cut]["role"] == "assistant"


def test_cut_never_orphans_tool_result_any_budget():
    msgs = [_u("과업")] + _tool_pairs(8)
    for keep in range(50, _tok(msgs) + 500, 50):
        cut = choose_cut_index(msgs, keep_tokens=keep)
        if cut:
            assert msgs[cut]["role"] == "assistant", f"keep_tokens={keep}"


def test_recent_window_measured_in_tokens_not_messages():
    # 같은 keep_tokens에서, 메시지가 크면 적게 남고 작으면 많이 남아야 한다
    big = [_u("과업")] + _tool_pairs(10, result_chars=4000)
    small = [_u("과업")] + _tool_pairs(10, result_chars=50)
    keep = 2000
    cut_big = choose_cut_index(big, keep_tokens=keep)
    cut_small = choose_cut_index(small, keep_tokens=keep)
    kept_big = len(big) - cut_big
    kept_small = len(small) - cut_small if cut_small else len(small)
    assert kept_big < kept_small
    # 남긴 창은 항상 keep_tokens 이상을 담보(경계 하향은 창을 키울 뿐 줄이지 않음)
    if cut_big:
        assert _tok(big[cut_big:]) >= min(keep, _tok(big[1:]))


def test_giant_last_message_still_kept():
    # 마지막 메시지 하나가 창 예산을 초과해도 최소한 그 메시지는 유지
    msgs = [_u("과업")] + _tool_pairs(6) + [_a_tooluse(), _u_result(chars=50_000)]
    cut = choose_cut_index(msgs, keep_tokens=1000)
    assert cut > 0
    assert msgs[cut]["role"] == "assistant"
    assert cut <= len(msgs) - 2  # 마지막 쌍(assistant+거대 result)은 창에 남는다


def test_too_short_returns_zero():
    msgs = [_u("과업"), _a_text()]
    assert choose_cut_index(msgs, keep_tokens=30_000) == 0


def test_splice_preserves_original_prompt_and_alternation():
    msgs = [_u("원래 과업 문장")] + _tool_pairs(10) + [_a_text()]
    cut = choose_cut_index(msgs, keep_tokens=300)
    out = splice_consolidated(msgs, cut, "다이제스트 본문", "원래 과업 문장")
    assert out[0]["role"] == "user"
    assert "원래 과업 문장" in out[0]["content"]
    assert "다이제스트 본문" in out[0]["content"]
    assert out[1]["role"] == "assistant"
    for a, b in zip(out, out[1:]):
        assert a["role"] != b["role"]
    assert out[1:] == msgs[cut:]


def test_splice_shrinks():
    msgs = [_u("과업")] + _tool_pairs(20)
    cut = choose_cut_index(msgs, keep_tokens=500)
    out = splice_consolidated(msgs, cut, "d", "과업")
    assert len(out) < len(msgs)
    assert len(out) == 1 + (len(msgs) - cut)
