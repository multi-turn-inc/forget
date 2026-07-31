#!/bin/sh
# forget — https://forget.sh
# One memory for your AI, on your machine. This installer:
#   1. puts forget-ai into its own venv at ~/.forget/venv (PEP 668-safe)
#   2. registers the login service (launchd/systemd)
#   3. wires Claude Code / Codex / Claude Desktop to one canonical pool
# Reversible: `npx forget-connect disconnect` + delete ~/.forget
set -eu

say() { printf '%s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1; }

if ! need python3; then
  say "forget needs python3 (>= 3.10). Install it, then re-run:"
  say "  curl -fsSL forget.sh | sh"
  exit 1
fi

VENV="$HOME/.forget/venv"
say "→ installing forget-ai into $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade 'forget-ai[server]'

say "→ registering the login service"
if ! "$VENV/bin/forget-server" install-service; then
  say "  (service install failed — you can run it in the foreground instead:"
  say "   $VENV/bin/forget-server run)"
fi

if need npx; then
  say "→ connecting your AI clients (Claude Code / Codex / Claude Desktop)"
  npx -y forget-connect --yes || say "  (skipped — run 'npx forget-connect' yourself)"
else
  say "→ node not found — after installing node, run: npx forget-connect"
fi

say ""
say "→ checkup (forget-server doctor)"
if "$VENV/bin/forget-server" doctor; then
  DOCTOR_OK=1
else
  DOCTOR_OK=0
fi
say ""
if [ "$DOCTOR_OK" = "0" ]; then
  say "✗ install finished but the checkup found problems — fix the lines above,"
  say "  then re-run: $VENV/bin/forget-server doctor"
  say "  (stuck? send that exact output to whoever told you about forget.)"
  exit 1
fi
say "✳ forget is running — one memory, on this machine, at ~/.forget"
say ""
say "  The first day or two are quiet BY DESIGN: nothing to recall yet."
say "  Doctor green means it is accumulating. The payoff arrives the first"
say "  time a new session already knows what you were doing."
say ""
say "  Now the reboot ritual. Three minutes, and you will feel the difference:"
say "    1. start any real task in your AI (claude, codex — anything)"
say "    2. kill the session mid-task. Really quit it."
say "    3. reopen. It starts with a handover, not a hello —"
say "       your goal, the next step, what changed while you were gone."
say ""
say "  A stateless agent is a brilliant stranger, every time."
say "  This one is becoming a colleague."
say ""
say "  check:  $VENV/bin/forget-server doctor   ·   npx forget-connect doctor"
say "  undo:   npx forget-connect disconnect    ·   rm -rf ~/.forget"
