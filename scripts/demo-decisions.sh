#!/usr/bin/env bash
# 30-second demo: mine a repo's decision history, then ask "why" and get
# answers with receipts. Requires a running local forget server and jq.
#
#   scripts/demo-decisions.sh <repo-url-or-path> "<question>" [limit]
set -euo pipefail

REPO=${1:?usage: demo-decisions.sh <repo-url-or-path> "<question>" [limit]}
QUESTION=${2:?a question is required}
LIMIT=${3:-300}
SERVER=${FORGET_URL:-http://localhost:8000}
SCOPE="demo-$(basename "$REPO" .git)"
PYTHON=${FORGET_PYTHON:-python3}

if [ -d "$REPO" ]; then
  SRC="$REPO"
else
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  echo "· cloning commit history (blobless, no code leaves its host) …"
  git clone --bare --filter=tree:0 --quiet "$REPO" "$TMP/repo.git"
  SRC="$TMP/repo.git"
fi

# idempotent reruns: clear this demo scope before importing
jq -n --arg u "$SCOPE" '{user_id: $u, app_id: "demo"}' \
| curl -s -X DELETE "$SERVER/v1/memories/" \
    -H 'Content-Type: application/json' -d @- -o /dev/null || true

echo "· mining decisions …"
"$PYTHON" -m forget.importers.git "$SRC" --user-id "$SCOPE" --app-id demo \
  --url "$SERVER" --limit "$LIMIT"

echo
echo "Q: $QUESTION"
jq -n --arg q "$QUESTION" --arg u "$SCOPE" \
  '{query: $q, filters: {user_id: $u, app_id: "demo"}, top_k: 3}' \
| curl -s -X POST "$SERVER/v3/memories/search/" \
    -H 'Content-Type: application/json' -d @- \
| jq -r 'if (.results | length) == 0 then "A: (no decision found — try another question)"
    else .results[] |
      "A: \(.memory[0:160])\n   [\(.metadata.repo // "?")@\(.metadata.commit // "?") · \(.metadata.author // "?") · \(.created_at[0:10])]"
    end'
