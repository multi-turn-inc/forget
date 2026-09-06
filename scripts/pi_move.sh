#!/usr/bin/env bash
# 이사: 최신 Claude Code 세션을 pi 세션으로 이식하고, 사이드카를 pi 쪽으로 돌린 뒤, pi를 그 세션으로 연다 (2026-09-07).
#   scripts/pi_move.sh                       # 기본: openai/gpt-5.5
#   scripts/pi_move.sh spark qwen3.6:27b     # Spark 로컬 모델(무료·데이터 불출)
#   scripts/pi_move.sh openai-codex gpt-5.6-terra
set -euo pipefail
cd "$(dirname "$0")/.."
PROVIDER="${1:-openai}"; MODEL="${2:-gpt-5.5}"
SRC=$(ls -t ~/.claude/projects/*/*.jsonl | head -1)
DST_DIR="$HOME/.pi/agent/sessions/$(pwd | sed 's#/#-#g')--"
mkdir -p "$DST_DIR"
STAMP=$(date -u +%Y-%m-%dT%H-%M-%S-000Z)
OUT="$DST_DIR/${STAMP}_transplant-$(basename "$SRC" .jsonl | cut -c1-8)-tail.jsonl"
.venv/bin/python scripts/session_transplant.py "$SRC" --tail-only -o "$OUT"
pkill -f attention_sidecar.py || true; sleep 1
nohup .venv/bin/python scripts/attention_sidecar.py --harness pi >> ~/.forget/attention/sidecar.log 2>&1 &
echo "사이드카 → pi 세션 추적. 원장·블록은 그대로."
exec pi --session "$OUT" --provider "$PROVIDER" --model "$MODEL"
