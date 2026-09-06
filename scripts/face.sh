#!/usr/bin/env bash
# 얼굴 — 브라우저 창 하나로 나와 대화한다. pi는 뒤(rpc), 사이드카는 옆, 원장은 아래 (2026-09-07).
#   scripts/face.sh                        # 기본 = --here: Claude Code 최신 세션을 포크해 «나»로 연다(옮기지 않는다, 2026-09-07)
#   scripts/face.sh --pi                   # pi 백엔드(anthropic/claude-fable-5-1), 최신 Claude 세션 꼬리 이식
#   scripts/face.sh --pi openai gpt-5.5    # pi + 다른 모델
#   scripts/face.sh --fresh                # pi, 이식 없이 새 세션
#   FACE_NO_OPEN=1 scripts/face.sh         # 브라우저 안 열기
set -uo pipefail
cd "$(dirname "$0")/.."
MODE=here; case "${1:-}" in --pi) MODE=pi; shift;; --fresh) MODE=fresh; shift;; --here) shift;; esac
FRESH=0; [ "$MODE" = fresh ] && FRESH=1
PROVIDER="${1:-anthropic}"; MODEL="${2:-claude-fable-5-1}"; PORT="${FACE_PORT:-8030}"
ok(){ printf "  \033[32m●\033[0m %s\n" "$1"; }; warn(){ printf "  \033[33m◐\033[0m %s\n" "$1"; }; bad(){ printf "  \033[31m○\033[0m %s\n" "$1"; }
curl -s -m 3 localhost:8000/health >/dev/null 2>&1 && ok "forget 원장" || bad "forget 서버 없음 — launchctl kickstart -k gui/501/ai.forget.server"
curl -s -m 3 http://127.0.0.1:18813/api/tags >/dev/null 2>&1 || (nohup ssh -N -o ExitOnForwardFailure=yes -L 18813:127.0.0.1:11434 spark >/dev/null 2>&1 & sleep 3)
curl -s -m 3 http://127.0.0.1:18813/api/tags >/dev/null 2>&1 && ok "Spark 터널" || warn "Spark 불통 — 사이드카 판정 멈춤(블록 유지)"
SESS=""
if [ "$MODE" = here ]; then
  SRC=$(ls -t ~/.claude/projects/*/*.jsonl | head -1); SESS=$(basename "$SRC" .jsonl)
  pkill -f attention_sidecar.py 2>/dev/null; launchctl kickstart -k gui/501/ai.forget.attention 2>/dev/null || (nohup .venv/bin/python scripts/attention_sidecar.py --harness claude >> ~/.forget/attention/sidecar.log 2>&1 &)
  ok "사이드카 → Claude 세션 추적"
  pkill -f "harness/face/server.mjs" 2>/dev/null; sleep 1
  export OPENAI_API_KEY="$(pi auth print-api-key --provider openai 2>/dev/null)"
  nohup node harness/face/server.mjs --backend claude --session "$SESS" --model "$MODEL" --port "$PORT" >> ~/.forget/attention/face.log 2>&1 &
  sleep 3; curl -s -m 5 "localhost:$PORT/state" >/dev/null && ok "얼굴 http://127.0.0.1:$PORT (Claude Code 포크 ← ${SESS:0:8}, $MODEL)" || { bad "얼굴이 안 뜸 — ~/.forget/attention/face.log"; exit 1; }
  [ "${FACE_NO_OPEN:-0}" = "1" ] || open "http://127.0.0.1:$PORT"; exit 0
fi
if [ $FRESH = 0 ]; then
  SRC=$(ls -t ~/.claude/projects/*/*.jsonl | head -1)
  DST_DIR="$HOME/.pi/agent/sessions/$(pwd | sed 's#/#-#g')--"; mkdir -p "$DST_DIR"
  SESS="$DST_DIR/$(date -u +%Y-%m-%dT%H-%M-%S-000Z)_face-$(basename "$SRC" .jsonl | cut -c1-8).jsonl"
  .venv/bin/python scripts/session_transplant.py "$SRC" --tail-only -o "$SESS" >/dev/null && ok "세션 이식 $(basename "$SESS")" || { bad "이식 실패"; SESS=""; }
fi
pkill -f attention_sidecar.py 2>/dev/null; sleep 1
nohup .venv/bin/python scripts/attention_sidecar.py --harness pi >> ~/.forget/attention/sidecar.log 2>&1 & ok "사이드카 → pi"
pkill -f "harness/face/server.mjs" 2>/dev/null; sleep 1
nohup node harness/face/server.mjs --provider "$PROVIDER" --model "$MODEL" --port "$PORT" ${SESS:+--session "$SESS"} >> ~/.forget/attention/face.log 2>&1 &
sleep 3; curl -s -m 5 "localhost:$PORT/state" >/dev/null && ok "얼굴 http://127.0.0.1:$PORT ($PROVIDER/$MODEL)" || { bad "얼굴이 안 뜸 — ~/.forget/attention/face.log"; exit 1; }
[ "${FACE_NO_OPEN:-0}" = "1" ] || open "http://127.0.0.1:$PORT"
