#!/usr/bin/env bash
# Pre-publish dress rehearsal: walk the exact funnel a beta user walks,
# from the built artifacts, in a sandbox that cannot touch real configs.
#
#   bash scripts/rehearse-funnel.sh
#
# Requires: dist/*.whl built, python3, node. Exits non-zero on the first
# broken step. Found 2026-07-24: HOME alone does not isolate Codex —
# forget-connect honors CODEX_HOME (correct product behavior), so the
# sandbox must override both.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/forget-rehearsal-XXXXXX")"
PORT=8899
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$SANDBOX"
}
trap cleanup EXIT

step() { printf '\n== %s\n' "$1"; }

step "wheel install into a clean venv"
WHEEL="$(ls "$ROOT"/dist/forget_ai-*.whl | sort | tail -1)"
python3 -m venv "$SANDBOX/venv"
"$SANDBOX/venv/bin/pip" install -q "${WHEEL}[server]"
"$SANDBOX/venv/bin/forget-server" --help >/dev/null

step "server boots from the wheel and answers MCP"
export FORGET_HOME="$SANDBOX/home" MEM1_DB_PATH="$SANDBOX/home/forget.sqlite3"
"$SANDBOX/venv/bin/forget-server" run --port "$PORT" >"$SANDBOX/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 40); do
  "$SANDBOX/venv/bin/forget-server" status --port "$PORT" >/dev/null 2>&1 && break
  sleep 0.5
done
"$SANDBOX/venv/bin/forget-server" status --port "$PORT"
python3 - "$PORT" <<'EOF'
import json, sys, urllib.request
url = f"http://127.0.0.1:{sys.argv[1]}/mcp/rehearsal-app/http/rehearsal-user"
def rpc(name, args, i=1):
    req = urllib.request.Request(url, data=json.dumps({
        "jsonrpc": "2.0", "id": i, "method": "tools/call",
        "params": {"name": name, "arguments": args}}, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(json.loads(urllib.request.urlopen(req, timeout=15).read())["result"]["content"][0]["text"])
rpc("add_memory", {"text": "리허설 사용자는 다크 모드를 선호한다.", "infer": False})
top = rpc("search_memories", {"query": "다크 모드 선호", "top_k": 1}, 2)["results"][0]
assert "다크 모드" in top["memory"], top
assert top.get("trust", {}).get("light"), top
print(f"add -> search OK (trust: {top['trust']['light']})")
EOF

step "npm tarball connect / bare doctor / disconnect round-trip"
TGZ="$SANDBOX/pack"
mkdir -p "$TGZ"
(cd "$ROOT/packages/forget-connect" && npm pack --silent --pack-destination "$TGZ" >/dev/null)
tar -xzf "$TGZ"/forget-connect-*.tgz -C "$TGZ"
BIN="$TGZ/package/bin/forget-connect.js"
# Both overrides matter: HOME for Claude Code/Desktop, CODEX_HOME for Codex.
export HOME="$SANDBOX/fakehome" CODEX_HOME="$SANDBOX/fakehome/.codex"
mkdir -p "$HOME/.claude" "$CODEX_HOME"
echo '{}' >"$HOME/.claude/settings.json"

FORGET_MCP_URL="http://localhost:$PORT/mcp" node "$BIN" \
  --user-id rehearsal-user --app-id rehearsal-app --yes
node "$BIN" doctor | tee "$SANDBOX/doctor.out"
grep -q "Scope detected from installed config" "$SANDBOX/doctor.out"
node "$BIN" disconnect --yes
if grep -q forget "$HOME/.claude/settings.json"; then
  echo "FAIL: disconnect left forget hooks in settings.json" >&2
  exit 1
fi
if [ -e "$HOME/.forget/hooks" ] && [ -n "$(ls -A "$HOME/.forget/hooks" 2>/dev/null)" ]; then
  echo "FAIL: disconnect left hook scripts behind" >&2
  exit 1
fi

printf '\nfunnel rehearsal: ALL GREEN\n'
