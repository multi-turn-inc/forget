---
description: Recall dial — pick a gear (low·medium·high·extra)
argument-hint: "[low|medium|high|extra]"
allowed-tools: Bash(~/.forget/venv/bin/forget-server recall:*)
---
<!-- forget-connect:command v1 — delete this line to keep your edits across upgrades -->

Current dial:
!`~/.forget/venv/bin/forget-server recall status 2>/dev/null | head -1`

Argument: "$ARGUMENTS"

- If the argument is a gear name (low|medium|high|extra), immediately run
  `~/.forget/venv/bin/forget-server recall use <gear>` and print only the
  dial line from its output — no commentary.
- If there is no argument, use AskUserQuestion to let the user pick a gear
  (arrow keys). Question: "Recall gear" / header: "recall" / 4 options,
  appending "(current)" to the label of the current gear:
  · low — instant search (~0.2s, no LLM)
  · medium — currently shares low's engine
  · high — an LLM reads 40 candidates (~3s)
  · extra — reads 100 candidates in full (~5s)
  Apply the selection with `recall use` and print only the dial line.
- Any other argument: answer with one line — "Settings live in /forget-settings".
