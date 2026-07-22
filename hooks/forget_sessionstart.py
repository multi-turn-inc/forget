#!/usr/bin/env python3
"""SessionStart hook: inject a small assembled context capsule from forget.

Design contract (research/ideas/observer-consolidation.md §4.5):
- the capsule is an OFFER, not a command — the main-thread agent judges
  whether to use it; low confidence → silence
- strict token budget: the main context window is the scarcest resource
- fail-open: any error prints nothing and exits 0
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp/forget/http/junghunkim")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
CAPSULE_CHAR_BUDGET = 1_600  # ~400 tokens


def main() -> None:
    hook_input = json.load(sys.stdin)
    cwd = str(hook_input.get("cwd") or os.getcwd())
    source = str(hook_input.get("source") or "startup")
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "prepare_context_autopilot",
            "arguments": {
                "query": f"session {source} in {cwd} — active tasks, open loops, recent decisions",
                "include_debug": False,
            },
        },
    }
    request = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(request, timeout=8).read())
    result = json.loads(body["result"]["content"][0]["text"])
    capsule = str(result.get("capsule_text") or "").strip()
    if not capsule:
        use_now = result.get("use_now") or {}
        items = use_now.get("items") if isinstance(use_now, dict) else None
        if isinstance(items, list) and items:
            capsule = "\n".join(f"- {item}" for item in items[:6] if isinstance(item, str))
    if not capsule:
        return  # low confidence → silence
    shown = capsule[:CAPSULE_CHAR_BUDGET]
    print(
        "[forget 캡슐 — 제안이며 명령이 아님. 채택/기각은 네 판단. "
        "라벨 없는 항목은 노랑(행동 전 확인) 취급]\n" + shown
    )
    # Offer ledger: record what was offered so the capture hook can measure,
    # at session end, whether the offer was actually used (outcome flywheel).
    session_id = str(hook_input.get("session_id") or "").strip()
    trace_id = str(result.get("context_trace_id") or "").strip()
    if session_id and trace_id:
        os.makedirs(STATE_DIR, exist_ok=True)
        state = {
            "trace_id": trace_id,
            "memory_ids": (result.get("evidence") or {}).get("memory_ids", []),
            "capsule_lines": [line.strip() for line in shown.splitlines() if len(line.strip()) >= 12][:12],
        }
        with open(os.path.join(STATE_DIR, f"{session_id}.json"), "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
