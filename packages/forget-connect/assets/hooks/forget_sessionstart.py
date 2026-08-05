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
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
CAPSULE_CHAR_BUDGET = 1_600  # ~400 tokens
HANDOFF_MAX_AGE_SECONDS = 48 * 3600  # a stale shift-note is worse than none
# The server capability these hooks are built against. The capsule response
# carries server_version from 0.3.9 on; older servers silently drop arguments
# these hooks send (project layering) — that mismatch must never be silent.
REQUIRED_SERVER_VERSION = "0.3.9"


def _version_tuple(value: str) -> tuple:
    parts = []
    for chunk in str(value or "").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def _version_notice(server_version: str) -> str:
    """One warning line for the capsule header area, or ''.

    Two signals, no network: the server's self-reported version (mismatch =
    features silently lost), and the update-check cache that doctor/status
    maintain (a local file — hooks never call out).
    """
    if not server_version:
        return "⚠ 서버가 버전을 안 밝힘(≤0.3.8) — 훅 기능 일부가 조용히 무시될 수 있음. 처방: forget-server upgrade"
    if _version_tuple(server_version) < _version_tuple(REQUIRED_SERVER_VERSION):
        return (
            f"⚠ 서버 {server_version} < 훅 요구 {REQUIRED_SERVER_VERSION} — "
            "프로젝트 층 등이 조용히 무시됨. 처방: forget-server upgrade"
        )
    try:
        forget_home = os.environ.get("FORGET_HOME") or os.path.expanduser("~/.forget")
        with open(os.path.join(forget_home, "update-check.json"), encoding="utf-8") as fh:
            latest = str(json.load(fh).get("latest") or "")
        if latest and _version_tuple(server_version) < _version_tuple(latest):
            return f"새 버전 {latest} 나옴 (현재 {server_version}) — forget-server upgrade"
    except Exception:
        pass
    return ""


def _consume_handoff() -> str:
    """Read the PreCompact shift-note once, then burn it.

    Delivered to exactly one next hand: the post-compact continuation
    (source="compact") or, failing that, the next fresh session within 48h.
    """
    path = os.path.join(STATE_DIR, "handoff.json")
    if not os.path.exists(path):
        return ""
    try:
        fresh = (time.time() - os.path.getmtime(path)) <= HANDOFF_MAX_AGE_SECONDS
        with open(path, encoding="utf-8") as fh:
            note = json.load(fh)
    except Exception:
        return ""
    finally:
        try:
            os.replace(path, path + ".done")
        except OSError:
            pass
    if not fresh:
        return ""
    lines = ["[교대 인수인계 — 직전 세션이 압축으로 문장 중간에서 잘렸음]"]
    if note.get("last_user"):
        lines.append(f"마지막 실: {str(note['last_user'])[:200]}")
    if note.get("last_assistant"):
        lines.append(f"잘린 손의 마지막 문장: …{str(note['last_assistant'])[:200]}")
    if note.get("transcript_path"):
        lines.append(f"원문: {note['transcript_path']} (recall_episode로 열람 가능)")
    return "\n".join(lines)


def main() -> None:
    hook_input = json.load(sys.stdin)
    cwd = str(hook_input.get("cwd") or os.getcwd())
    source = str(hook_input.get("source") or "startup")
    project = None if scope_disabled() else project_key_for_path(cwd)
    arguments: dict = {
        "query": f"session {source} in {cwd} — active tasks, open loops, recent decisions",
        "include_debug": False,
    }
    # F2's cause was a capsule that mixed layers: heartbeat and Quant rows
    # invading a devloop session. The capsule now reads this project's layer
    # plus the global one — untagged rows included, so nothing pre-existing
    # disappears the day this lands.
    project_filter = layered_filter(project)
    if project_filter:
        arguments["filters"] = project_filter
        # Memory recall reads the layered OR; the task/goal ledger has its own
        # storage (claims + epochs) and takes the project key explicitly.
        arguments["project"] = project
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "prepare_context_autopilot", "arguments": arguments},
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
    handoff = _consume_handoff()
    notice = _version_notice(str(result.get("server_version") or ""))
    if not capsule and not handoff:
        return  # low confidence → silence (version nags don't earn a lone injection)
    shown = capsule[:CAPSULE_CHAR_BUDGET]
    parts = []
    if notice:
        parts.append(f"[forget 버전] {notice}")
    if handoff:
        parts.append(handoff)
    if shown:
        scope_note = f" 프로젝트 층: {project} (+전역)." if project else ""
        parts.append(
            "[forget 캡슐 — 제안이며 명령이 아님. 채택/기각은 네 판단. "
            f"라벨 없는 항목은 노랑(행동 전 확인) 취급.{scope_note}]\n" + shown
        )
    print("\n".join(parts))
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
