#!/usr/bin/env python3
"""Session capture + mechanical outcome labeling (PreCompact and SessionEnd).

Two judgment-free jobs, each fail-open on its own:
1. capture — register the session in forget: pointer + mechanical digest,
   source_role="tool" (green). The transcript on disk is the lossless ledger;
   this makes it findable.
2. outcome — if a SessionStart capsule was offered this session (state file
   exists), measure mechanically whether the session echoed it and record a
   context outcome against the capsule's trace. This is the crudest possible
   label (all-or-none echo, substring match); its job is to start the data
   flywheel, not to be right — retire it when a learned labeler exists
   (observer W2) or when per-memory matching lands.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
TAIL_BYTES = 400_000
SNIPPET_LIMIT = 200
USER_SNIPPETS = 3
ASSISTANT_BLOB_LIMIT = 300_000
PROBE_MIN_LEN = 12  # sessionstart의 장부 프로브 최소 길이와 일치해야 함
PROBE_MAX_LEN = 80


def _rpc(name: str, arguments: dict, timeout: int = 5) -> None:
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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _digest(transcript_path: str) -> dict:
    with open(transcript_path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - TAIL_BYTES))
        tail = fh.read().decode("utf-8", errors="replace")
    lines = [line for line in tail.splitlines() if line.strip()]
    if size > TAIL_BYTES and lines:
        lines = lines[1:]  # first line of a mid-file seek is usually truncated
    user_snippets: list[str] = []
    assistant_parts: list[str] = []
    assistant_len = 0
    counts = {"user": 0, "assistant": 0}
    first_ts = last_ts = ""
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        kind = entry.get("type")
        if kind not in counts:
            continue
        counts[kind] += 1
        ts = str(entry.get("timestamp") or "")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        text = _text_of((entry.get("message") or {}).get("content")).strip()
        if kind == "user":
            # skill expansions and system payloads arrive as user-role messages;
            # real typed utterances are short — length is the cheapest tell
            if text and len(text) <= 600 and not text.startswith(("<local-command", "<command-name", "[SYSTEM", "#")):
                user_snippets.append(text[:SNIPPET_LIMIT])
        elif text and assistant_len < ASSISTANT_BLOB_LIMIT:
            assistant_parts.append(text)
            assistant_len += len(text)
    return {
        "counts": counts,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_snippets": user_snippets[-USER_SNIPPETS:],
        "assistant_blob": _normalize(" ".join(assistant_parts)),
        "tail_only": size > TAIL_BYTES,
    }


def _capture(hook_input: dict, digest: dict, transcript_path: str, session_id: str) -> None:
    event = str(hook_input.get("hook_event_name") or "PreCompact")
    label = str(hook_input.get("trigger") or hook_input.get("reason") or "auto")
    snippets = " / ".join(digest["user_snippets"]) or "(없음)"
    text = (
        f"세션 캡처 ({event}/{label}): 세션 {session_id} — "
        f"user {digest['counts']['user']}·assistant {digest['counts']['assistant']} 메시지"
        f"{' (꼬리 표본)' if digest['tail_only'] else ''}, {digest['first_ts']}~{digest['last_ts']}. "
        f"최근 사용자 발화: {snippets}. 전문: {transcript_path}"
    )
    _rpc(
        "add_memory",
        {
            "text": text,
            "infer": False,
            "source_role": "tool",
            "metadata": {
                "hook": event,
                "session_id": session_id,
                "transcript_path": transcript_path,
                "trigger": label,
            },
        },
    )


def _outcome(digest: dict, session_id: str) -> None:
    state_path = os.path.join(STATE_DIR, f"{session_id}.json")
    if not os.path.exists(state_path):
        return
    with open(state_path, encoding="utf-8") as fh:
        state = json.load(fh)
    trace_id = str(state.get("trace_id") or "")
    if not trace_id:
        os.replace(state_path, state_path + ".done")
        return
    blob = digest["assistant_blob"]
    echoed = []
    for line in state.get("capsule_lines") or []:
        probe = _normalize(str(line))[:PROBE_MAX_LEN]
        if len(probe) >= PROBE_MIN_LEN and probe in blob:
            echoed.append(probe[:40])
    memory_ids = state.get("memory_ids") or []
    _rpc(
        "record_context_outcome",
        {
            "trace_id": trace_id,
            "used_memory_ids": memory_ids if echoed else [],
            "missing_memory_ids": [],
            "harmful_memory_ids": [],
            "first_action_productive": bool(echoed),
            "user_correction_required": False,
            "metadata": {
                "labeler": "mechanical-echo-v1",
                "session_id": session_id,
                "echo_count": len(echoed),
                "echoed_probes": echoed[:5],
                "granularity": "all-or-none",
            },
        },
        timeout=6,
    )
    os.replace(state_path, state_path + ".done")


def main() -> None:
    hook_input = json.load(sys.stdin)
    transcript_path = str(hook_input.get("transcript_path") or "")
    session_id = str(hook_input.get("session_id") or "unknown")
    if not transcript_path or not os.path.exists(transcript_path):
        return
    digest = _digest(transcript_path)
    try:
        _capture(hook_input, digest, transcript_path, session_id)
    except Exception:
        pass
    # Outcome is a session-final label: a mid-session compact must not consume
    # the offer ledger, or usage after the compact goes unmeasured.
    if str(hook_input.get("hook_event_name") or "") == "SessionEnd":
        try:
            _outcome(digest, session_id)
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
