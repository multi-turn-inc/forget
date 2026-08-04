---
description: forget settings — status, doctor, weekly report, cloud usage
argument-hint: "[doctor|weekly|usage]"
allowed-tools: Bash(~/.forget/venv/bin/forget-server recall:*), Bash(~/.forget/venv/bin/forget-server status:*), Bash(~/.forget/venv/bin/forget-server doctor:*), Bash(~/.forget/venv/bin/forget-server weekly:*), Bash(npx forget-connect doctor:*)
---
<!-- forget-connect:command v1 — delete this line to keep your edits across upgrades -->

Recall dial:
!`~/.forget/venv/bin/forget-server recall status 2>/dev/null`

Argument: "$ARGUMENTS"

- `doctor`: run `~/.forget/venv/bin/forget-server doctor`. If every line is ✓,
  say "healthy" in one line; if any ✗, explain only that line's prescription (→)
  and ask before running it.
- `weekly`: run `~/.forget/venv/bin/forget-server weekly`; summarize the numbers only.
- `usage`: run `~/.forget/venv/bin/forget-server recall cloud-usage` and show the
  output as is.
- No argument: combine the dial output above with
  `~/.forget/venv/bin/forget-server status` into a settings screen of at most
  4 lines: dial / server + memory count / LLM / anything unusual (only when
  present). End with a short pointer: gear changes are /forget.
  If deep recall is off: a running local LLM (Ollama · LM Studio) attaches
  automatically; forget cloud (forget.sh/cloud) is the no-GPU alternative —
  never install anything on the user's behalf.
