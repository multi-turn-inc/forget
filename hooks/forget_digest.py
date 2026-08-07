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
MACHINE_PREFIXES = ("<local-command", "<command-name", "[SYSTEM", "#")


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


def main() -> None:
    hook_input = json.load(sys.stdin)
    transcript_path = str(hook_input.get("transcript_path") or "")
    session_id = str(hook_input.get("session_id") or "unknown")
    if not transcript_path or not os.path.exists(transcript_path):
        return
    state = _load_state(session_id)
    digested_upto = int(state.get("digested_upto") or 0)
    turns = _new_turns(transcript_path, digested_upto)
    aged = turns[:-RECENT_WINDOW_TURNS] if len(turns) > RECENT_WINDOW_TURNS else []
    if len(aged) < DIGEST_BATCH_TURNS:
        return

    messages: list[dict] = []
    spent = 0
    consumed = 0
    last_line = digested_upto
    for turn in aged:
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
            "session_id": session_id,
            "turn_range": [prev_turns + 1, prev_turns + consumed],
            "transcript_path": transcript_path,
        }
        try:
            _rpc("add_memory", {"messages": messages, "infer": True, "metadata": metadata})
        except Exception:
            return  # offset must not advance — the next Stop retries (spec ①)

    state.update({
        "digested_upto": last_line,
        "digested_turns": prev_turns + consumed,
        "last_run": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    })
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(_state_path(session_id), "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
