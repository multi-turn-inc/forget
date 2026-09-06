#!/usr/bin/env bash
# 이사 — 사전 점검 → 이식 → 사이드카 pi 추적 → pi 기동. 한 줄로 끝나야 한다 (2026-09-07 UX).
#   scripts/pi_move.sh                          # anthropic/claude-fable-5-1
#   scripts/pi_move.sh spark qwen3.6:27b        # Spark 로컬(무료·데이터 불출)
#   scripts/pi_move.sh --check                  # 점검만
set -uo pipefail
cd "$(dirname "$0")/.."
CHECK=0; [ "${1:-}" = "--check" ] && { CHECK=1; shift; }
PROVIDER="${1:-anthropic}"; MODEL="${2:-claude-fable-5-1}"
ok(){ printf "  \033[32m●\033[0m %s\n" "$1"; }; warn(){ printf "  \033[33m◐\033[0m %s\n" "$1"; }; bad(){ printf "  \033[31m○\033[0m %s\n" "$1"; }
echo "이사 점검"
curl -s -m 3 localhost:8000/health >/dev/null 2>&1 && ok "forget 원장 :8000" || { bad "forget 서버가 안 뜸 — launchctl kickstart -k gui/501/ai.forget.server"; }
if curl -s -m 3 http://127.0.0.1:18813/api/tags >/dev/null 2>&1; then ok "Spark 터널 :18813"; else
  warn "Spark 터널 없음 — 연다"; (nohup ssh -N -o ExitOnForwardFailure=yes -L 18813:127.0.0.1:11434 spark >/dev/null 2>&1 &); sleep 3
  curl -s -m 3 http://127.0.0.1:18813/api/tags >/dev/null 2>&1 && ok "Spark 터널 :18813" || bad "Spark 불통 — 사이드카 게이트·판정이 멈춘다(블록은 유지)"; fi
if [ "$PROVIDER" = "anthropic" ]; then
  if pi auth check --provider anthropic 2>/dev/null | grep -q ready; then ok "Anthropic 로그인 ($MODEL)"; else
    bad "Anthropic 로그인 안 됨 — pi를 열고 /login 에서 Anthropic을 고른 뒤 다시"; [ $CHECK = 1 ] || exit 1; fi
fi
[ $CHECK = 1 ] && { .venv/bin/python scripts/attention_sidecar.py --status; exit 0; }
SRC=$(ls -t ~/.claude/projects/*/*.jsonl | head -1)
DST_DIR="$HOME/.pi/agent/sessions/$(pwd | sed 's#/#-#g')--"; mkdir -p "$DST_DIR"
OUT="$DST_DIR/$(date -u +%Y-%m-%dT%H-%M-%S-000Z)_transplant-$(basename "$SRC" .jsonl | cut -c1-8)-tail.jsonl"
R=$(.venv/bin/python scripts/session_transplant.py "$SRC" --tail-only -o "$OUT") && ok "세션 이식 $(echo "$R" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"{d[\"entries\"]}항목 · {d[\"bytes\"]//1024}KB · 압축 {d[\"compaction\"]}회")')" || { bad "이식 실패"; exit 1; }
pkill -f attention_sidecar.py 2>/dev/null; sleep 1
nohup .venv/bin/python scripts/attention_sidecar.py --harness pi >> ~/.forget/attention/sidecar.log 2>&1 &
ok "사이드카 → pi 세션 추적 (블록 $(python3 -c 'import json,os;print(len(json.load(open(os.path.expanduser("~/.forget/attention/state.json"))).get("block",[])))' 2>/dev/null || echo 0)줄 유지)"
echo; exec pi --session "$OUT" --provider "$PROVIDER" --model "$MODEL" --name "이사 $(date +%m/%d\ %H:%M)"
