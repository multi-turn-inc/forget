#!/usr/bin/env python3
"""PreCompact hook: register the session in forget before compaction shreds context.

Design contract (research/ideas/observer-consolidation.md §4.5):
- capture is judgment-free — no LLM, no salience filtering, stamp and go
- the transcript file on disk IS the lossless ledger; this hook's job is to
  make it *findable*: a pointer + mechanical digest, source_role="tool"
  (deterministic extraction of verbatim content = tool observation, green)
- fail-open: any error exits 0 silently; a dead forget server must never
  block Claude Code
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp/forget/http/junghunkim")
TAIL_BYTES = 400_000
SNIPPET_LIMIT = 200
USER_SNIPPETS = 3


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
        return " ".join(part for part in parts if part)
    return ""


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
        if kind == "user":
            text = _text_of((entry.get("message") or {}).get("content")).strip()
            if text and not text.startswith(("<local-command", "<command-name", "[SYSTEM")):
                user_snippets.append(text[:SNIPPET_LIMIT])
    return {
        "counts": counts,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_snippets": user_snippets[-USER_SNIPPETS:],
        "tail_only": size > TAIL_BYTES,
    }


def main() -> None:
    hook_input = json.load(sys.stdin)
    transcript_path = str(hook_input.get("transcript_path") or "")
    session_id = str(hook_input.get("session_id") or "unknown")
    trigger = str(hook_input.get("trigger") or "auto")
    if not transcript_path or not os.path.exists(transcript_path):
        return
    digest = _digest(transcript_path)
    snippets = " / ".join(digest["user_snippets"]) or "(없음)"
    text = (
        f"세션 캡처 (PreCompact/{trigger}): 세션 {session_id} — "
        f"user {digest['counts']['user']}·assistant {digest['counts']['assistant']} 메시지"
        f"{' (꼬리 표본)' if digest['tail_only'] else ''}, {digest['first_ts']}~{digest['last_ts']}. "
        f"최근 사용자 발화: {snippets}. 전문: {transcript_path}"
    )
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "add_memory",
            "arguments": {
                "text": text,
                "infer": False,
                "source_role": "tool",
                "metadata": {
                    "hook": "PreCompact",
                    "session_id": session_id,
                    "transcript_path": transcript_path,
                    "trigger": trigger,
                },
            },
        },
    }
    request = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request, timeout=5).read()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
