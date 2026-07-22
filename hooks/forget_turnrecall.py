#!/usr/bin/env python3
"""UserPromptSubmit hook: push-recall memories relevant to THIS turn.

The session-start capsule covers "where were we"; this covers "wait, we know
something about that" mid-session — the pull-only problem's other half. The
main context window is the scarcest resource, so the gate is strict:

- silence unless the top hit clears a relevance threshold
- a memory is offered at most once per session (repeat-suppression ledger)
- memories already offered in the session-start capsule are not re-offered
- the injection is an OFFER with trust lights; adoption stays the
  main-thread agent's judgment
- fail-open, hard 5s timeout: forget being down must never slow a turn

Known gap (deliberate): these injections are not yet linked to the outcome
flywheel (search_memories creates no context trace). Wire when per-turn
traces land server-side.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp/forget/http/junghunkim")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
SCORE_THRESHOLD = float(os.environ.get("FORGET_TURNRECALL_THRESHOLD", "0.45"))
MAX_RECALLS = 3
MEMORY_CHAR_LIMIT = 160
MIN_PROMPT_LEN = 8


def _rpc(name: str, arguments: dict, timeout: int = 5) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        FORGET_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(request, timeout=timeout).read())
    return json.loads(body["result"]["content"][0]["text"])


def _seen_ids(session_id: str) -> tuple[set[str], str]:
    seen: set[str] = set()
    offer_path = os.path.join(STATE_DIR, f"{session_id}.json")
    for candidate in (offer_path, offer_path + ".done"):
        if os.path.exists(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    seen.update(json.load(fh).get("memory_ids") or [])
            except Exception:
                pass
    turns_path = os.path.join(STATE_DIR, f"{session_id}.turns.json")
    if os.path.exists(turns_path):
        try:
            with open(turns_path, encoding="utf-8") as fh:
                seen.update(json.load(fh).get("injected") or [])
        except Exception:
            pass
    return seen, turns_path


def _remember_injected(turns_path: str, injected: list[str]) -> None:
    existing: list[str] = []
    if os.path.exists(turns_path):
        try:
            with open(turns_path, encoding="utf-8") as fh:
                existing = json.load(fh).get("injected") or []
        except Exception:
            pass
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(turns_path, "w", encoding="utf-8") as fh:
        json.dump({"injected": existing + injected}, fh, ensure_ascii=False)


def main() -> None:
    hook_input = json.load(sys.stdin)
    prompt = str(hook_input.get("prompt") or "").strip()
    session_id = str(hook_input.get("session_id") or "").strip()
    if len(prompt) < MIN_PROMPT_LEN or prompt.startswith(("/", "!", "<", "#")):
        return
    seen, turns_path = _seen_ids(session_id) if session_id else (set(), "")
    result = _rpc("search_memories", {"query": prompt[:300], "top_k": MAX_RECALLS + 2})
    picks = []
    for item in result.get("results") or []:
        if float(item.get("score") or 0.0) < SCORE_THRESHOLD:
            continue
        memory_id = str(item.get("id") or "")
        if not memory_id or memory_id in seen:
            continue
        if (item.get("metadata") or {}).get("hook"):
            continue  # session-capture pointers are for rehydration, not recall
        trust = item.get("trust") or {}
        light = str(trust.get("light") or "yellow")
        picks.append((memory_id, light, str(item.get("memory") or "")[:MEMORY_CHAR_LIMIT]))
        if len(picks) >= MAX_RECALLS:
            break
    if not picks:
        return  # below threshold or nothing new → silence
    lines = ["[forget 회상 — 이 턴과 관련된 기억 제안. green=행동 근거 OK, yellow=행동 전 확인, red=참고만]"]
    lines += [f"- ({light}) {memory}" for _, light, memory in picks]
    print("\n".join(lines))
    if session_id and turns_path:
        _remember_injected(turns_path, [memory_id for memory_id, _, _ in picks])
        _extend_offer_ledger(session_id, picks)


def _extend_offer_ledger(session_id: str, picks: list) -> None:
    """Feed turn recalls into the outcome flywheel: append their probes and
    ids to the session's offer ledger so the capture hook measures them too.
    (Discovered gap 07-22: a session answered purely from a turn recall and
    the capsule-only labeler scored it "not used".)"""
    ledger_path = os.path.join(STATE_DIR, f"{session_id}.json")
    if not os.path.exists(ledger_path):
        return  # no capsule trace this session — nothing to record against
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            state = json.load(fh)
        state["memory_ids"] = list({*(state.get("memory_ids") or []), *(memory_id for memory_id, _, _ in picks)})
        state["capsule_lines"] = (state.get("capsule_lines") or []) + [memory[:80] for _, _, memory in picks]
        with open(ledger_path, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
