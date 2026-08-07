#!/usr/bin/env python3
"""Rolling consolidation stage 1 — pre-emptive digestion (Stop hook).

Spec: research/devloop/rolling-consolidation-stage1.md ①. The hook judges no
content: it ships the aged segment (every turn behind the active window) as
raw messages to add_memory(messages, infer=True), and the server's existing
extraction + observation-gate pipeline decides what is durable. Once wired,
a compaction can only evaporate turns that were already digested — that is
P4's claim, judged after 5 observed compaction events.

Cost discipline (LOOP.md 원칙 6, spec ①): at most one RPC per Stop event,
only when the aged backlog is DIGEST_BATCH_TURNS deep, capped at
BATCH_CHAR_LIMIT per call — the remainder waits for the next Stop. On any
failure the offset does not advance, so the next Stop retries; a timeout can
therefore re-send a batch — dedup is the server pipeline's job, loss is not
acceptable. Fail-open exit 0 always.

Two more spec parts live here (c79): flush() is spec ② — forget_capture calls
it at PreCompact so everything the compaction is about to evaporate reaches
forget first; the Stop path also runs spec ③ — a context-usage estimate from
transcript growth whose near_threshold flag forget_turnrecall turns into a
one-line reboot suggestion.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
RECENT_WINDOW_TURNS = 30    # active window — never digested (spec ①)
DIGEST_BATCH_TURNS = 20     # minimum aged backlog before a server call
MESSAGE_CHAR_LIMIT = 2_000  # per-message truncation
BATCH_CHAR_LIMIT = 48_000   # per-call cap; offset advances only past what was sent
FLUSH_MAX_BATCHES = 4       # PreCompact flush cap — the hook timeout bounds how much can go
MACHINE_PREFIXES = ("<local-command", "<command-name", "[SYSTEM", "#")
# ③ 임계 감시 — 문자/3.2 근사 + 시스템 오버헤드 상수 (spec ③). 거친 계기임을 안다;
# 재교정은 P4 판정(컴팩션 5사건)과 함께. 값은 환경변수로 현장 조정 가능.
CONTEXT_WINDOW_TOKENS = int(os.environ.get("FORGET_CONTEXT_WINDOW_TOKENS", "200000"))
CHARS_PER_TOKEN = 3.2
OVERHEAD_TOKENS = int(os.environ.get("FORGET_CONTEXT_OVERHEAD_TOKENS", "25000"))
NEAR_THRESHOLD_RATIO = float(os.environ.get("FORGET_NEAR_THRESHOLD_RATIO", "0.70"))


def _rpc(name: str, arguments: dict, timeout: int = 30) -> None:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request, timeout=timeout).read()


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
        return " ".join(part for part in parts if part)
    return ""


def _state_path(session_id: str) -> str:
    return os.path.join(STATE_DIR, f"digest-{session_id}.json")


def _load_state(session_id: str) -> dict:
    try:
        with open(_state_path(session_id), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _new_turns(transcript_path: str, skip_lines: int) -> list[dict]:
    """User/assistant turns past the digested offset, with 1-based line offsets.

    Digested lines are counted but never parsed; the active window is always a
    suffix of what this returns, because digestion never advances into it.
    """
    turns: list[dict] = []
    with open(transcript_path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if line_no <= skip_lines or not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            role = entry.get("type")
            if role not in ("user", "assistant"):
                continue
            text = _text_of((entry.get("message") or {}).get("content")).strip()
            if role == "user" and text.startswith(MACHINE_PREFIXES):
                text = ""  # skill expansions / system payloads — noise, not conversation
            turns.append({"line": line_no, "role": role, "text": text[:MESSAGE_CHAR_LIMIT]})
    return turns


def _digest_batch(transcript_path: str, session_id: str, state: dict, turns: list[dict], trigger: str = "stop") -> bool:
    """Send one BATCH_CHAR_LIMIT's worth from the front of `turns`.

    Advances the state offsets only on success — a failed RPC returns False
    and leaves them untouched, so the next run retries (spec ①). A stretch of
    machine-only turns (no text after filtering) advances without a call:
    their offsets are spent, not their contents.
    """
    messages: list[dict] = []
    spent = 0
    consumed = 0
    last_line = int(state.get("digested_upto") or 0)
    for turn in turns:
        if messages and spent + len(turn["text"]) > BATCH_CHAR_LIMIT:
            break
        consumed += 1
        last_line = turn["line"]
        if turn["text"]:
            messages.append({"role": turn["role"], "content": turn["text"]})
            spent += len(turn["text"])

    prev_turns = int(state.get("digested_turns") or 0)
    if messages:
        metadata = {
            # no "hook" key on purpose: metadata.hook marks session-capture
            # pointers — turn recall skips those rows and scoring demotes
            # them ×0.5. Digest memories are ordinary memories (spec ①).
            "digest": "rolling-stage1",
            "digest_trigger": trigger,
            "session_id": session_id,
            "turn_range": [prev_turns + 1, prev_turns + consumed],
            "transcript_path": transcript_path,
        }
        try:
            _rpc("add_memory", {"messages": messages, "infer": True, "metadata": metadata})
        except Exception:
            return False  # offset must not advance — the next Stop retries (spec ①)

    state["digested_upto"] = last_line
    state["digested_turns"] = prev_turns + consumed
    return True


def _update_threshold(state: dict, transcript_path: str) -> bool:
    """③ 임계 감시 — estimate context usage from transcript growth since the
    last compaction (chars/3.2 + fixed overhead). Returns True when the
    near_threshold flag flipped; forget_turnrecall consumes the flag as a
    one-line reboot suggestion. Dropping below the line also retires the
    advised marker, so the next episode gets its own single notice.
    """
    try:
        size = os.path.getsize(transcript_path)
    except OSError:
        return False
    grown = max(0, size - int(state.get("compacted_at_bytes") or 0))
    est = int(grown / CHARS_PER_TOKEN) + OVERHEAD_TOKENS
    near = est >= NEAR_THRESHOLD_RATIO * CONTEXT_WINDOW_TOKENS
    flipped = near != bool(state.get("near_threshold"))
    state["near_threshold"] = near
    state["est_tokens"] = est
    state["est_ratio"] = round(est / CONTEXT_WINDOW_TOKENS, 3)
    if not near:
        state.pop("near_threshold_advised", None)
    return flipped


def _save_state(session_id: str, state: dict) -> None:
    state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_state_path(session_id), "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False)


def flush(transcript_path: str, session_id: str) -> None:
    """② PreCompact 최종 플러시 — 미소화 구간 전체를 소화한다, 활성 창 포함.

    Called by forget_capture just before the handoff note: the compaction is
    about to evaporate everything, so the window loses its reason to be
    protected. The offset still advances only past batches actually sent — a
    failed RPC leaves the remainder to the next Stop. compacted_at_bytes is
    recorded even then: it baselines the usage estimator on the compaction
    event itself, not on the flush's luck.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return
    state = _load_state(session_id)
    turns = _new_turns(transcript_path, int(state.get("digested_upto") or 0))
    for _ in range(FLUSH_MAX_BATCHES):
        if not turns:
            break
        prev = int(state.get("digested_turns") or 0)
        if not _digest_batch(transcript_path, session_id, state, turns, trigger="precompact_flush"):
            break
        advanced = int(state.get("digested_turns") or 0) - prev
        if advanced <= 0:
            break
        turns = turns[advanced:]
    state["backlog_turns"] = len(turns)
    try:
        state["compacted_at_bytes"] = os.path.getsize(transcript_path)
    except OSError:
        pass
    state["near_threshold"] = False
    state.pop("near_threshold_advised", None)
    _save_state(session_id, state)


def main() -> None:
    hook_input = json.load(sys.stdin)
    transcript_path = str(hook_input.get("transcript_path") or "")
    session_id = str(hook_input.get("session_id") or "unknown")
    if not transcript_path or not os.path.exists(transcript_path):
        return
    state = _load_state(session_id)
    turns = _new_turns(transcript_path, int(state.get("digested_upto") or 0))
    aged = turns[:-RECENT_WINDOW_TURNS] if len(turns) > RECENT_WINDOW_TURNS else []
    prev_digested = int(state.get("digested_turns") or 0)
    if len(aged) >= DIGEST_BATCH_TURNS:
        _digest_batch(transcript_path, session_id, state, aged)
    consumed = int(state.get("digested_turns") or 0) - prev_digested
    state["backlog_turns"] = len(aged) - consumed
    flipped = _update_threshold(state, transcript_path)
    if consumed or flipped:
        _save_state(session_id, state)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
