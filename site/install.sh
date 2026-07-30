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
say "✳ forget is running — one memory pool, on this machine, at ~/.forget"
say "  try it: tell your AI something worth remembering, start a new session, ask again."
say "  check:  $VENV/bin/forget-server status   ·   npx forget-connect doctor"
say "  undo:   npx forget-connect disconnect    ·   rm -rf ~/.forget"
