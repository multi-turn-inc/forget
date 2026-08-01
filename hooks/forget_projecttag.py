#!/usr/bin/env python3
"""PreToolUse hook: stamp the originating project onto every memory write.

The write side of project layering. The recall side can filter by
metadata.project only if something puts it there, and the one thing that
knows which repo a session is working in is the hook — the forget server is a
shared local daemon with no idea of any client's cwd, and asking the agent to
remember to pass a project key would make correctness depend on the model's
diligence (and on the user configuring scopes, which is the failure this whole
design exists to avoid).

So the tag is attached mechanically, by rewriting the tool input in flight
(`updatedInput`). No permissionDecision is returned: the hook adds provenance,
it does not decide whether a write is allowed.

Only add_memory is tagged. add_memories takes no metadata, and
record_task_state has no metadata field at all — tagging the task ledger (the
F2 friction: heartbeat/Quant task rows invading the devloop capsule) needs a
server-side field first. Deliberately out of scope here.

Fail-open: on any error, print nothing and exit 0 — the write proceeds
untagged, which recall reads as the global layer.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from forget_project import classify_layer, project_key_for_path, scope_disabled  # noqa: E402

TAGGED_TOOLS = {"mcp__forget__add_memory", "add_memory"}
TAGGER_VERSION = "cwd-git-v1"


def _write_text(tool_input: dict) -> str:
    """What the classifier reads: the fact being saved, however it arrived."""
    text = str(tool_input.get("text") or "")
    if text:
        return text
    messages = tool_input.get("messages")
    if isinstance(messages, list):
        parts = [str(m.get("content") or "") for m in messages if isinstance(m, dict)]
        return " ".join(part for part in parts if part)
    return ""


def main() -> None:
    hook_input = json.load(sys.stdin)
    if str(hook_input.get("tool_name") or "") not in TAGGED_TOOLS:
        return
    if scope_disabled():
        return
    tool_input = hook_input.get("tool_input")
    if not isinstance(tool_input, dict):
        return
    project = project_key_for_path(hook_input.get("cwd") or os.getcwd())
    if not project:
        return  # no project to be about → leave it in the global layer
    metadata = tool_input.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    if metadata.get("project"):
        return  # an explicit caller outranks detection
    metadata["project"] = project
    metadata.setdefault("scope_layer", classify_layer(_write_text(tool_input)))
    metadata.setdefault("project_tagger", TAGGER_VERSION)
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": {**tool_input, "metadata": metadata},
                }
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
