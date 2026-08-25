#!/bin/bash
# 자기 하네스 H-2 — 무유도 주기 기상 (헌장: docs/self-harness-design.md).
# launchd ai.forget.selfharness가 90분 주기로 실행. 정본은 repo, 설치본은
# ~/.forget/bin/self_harness_wake.sh (수동 복사 배포 — 배포 반사 대상).
#
# 규율: ①프로바이더 local-qwen 고정 (무의도 과금 방지 — P-H-0′ 공시 사건)
# ②터널 사망 시 기상 스킵 (fail-quiet — 스킵도 로그에 남겨 P-H-2 분모 계산)
# ③기상 프롬프트는 붙박이 "wake" — 무유도: 재수화 블록이 나르는 상태만 보고
#   스스로 결정한다 ④한 기상 최대 8분 (겹침 방지는 launchd가 보장).
set -u
LOG_DIR="$HOME/.forget/selfharness"
mkdir -p "$LOG_DIR"
STAMP="$(date '+%Y-%m-%dT%H:%M:%S%z')"
LOG="$LOG_DIR/wake-$(date '+%Y%m%d').log"

MODEL_ID="${SELF_HARNESS_MODEL:-Qwen3.8-27B-UD-Q4_K_XL.gguf}"
TUNNEL="${FORGET_LLAMA_URL:-http://127.0.0.1:18812/v1}"
REPO="${SELF_HARNESS_REPO:-$HOME/orca/workspaces/forget/내-프롬프트를-공유하기-싫어}"
PI_BIN="${SELF_HARNESS_PI:-$HOME/.nvm/versions/node/v22.22.0/bin/pi}"
# launchd 환경엔 nvm PATH가 없다 — pi의 `env node` 셔뱅이 EXIT=127로 죽는다
# (첫 자동 기상 실측). node 디렉터리를 PATH 앞에 박는다.
export PATH="$(dirname "$PI_BIN"):$PATH"

if ! curl -s -m 5 "$TUNNEL/models" > /dev/null 2>&1; then
  echo "$STAMP SKIP tunnel-dead" >> "$LOG"
  exit 0
fi

cd "$REPO" || { echo "$STAMP FAIL no-repo" >> "$LOG"; exit 0; }

WAKE_PROMPT="wake. You are waking on your own heartbeat — no one asked for anything. \
Read your state capsule and standing hands. Re-judge each standing hand (release with \
reason if its 'why' no longer holds). Check [전망] expectations. If real work is \
warranted, do ONE small concrete step and record it (arm_hand for anything left \
running). If nothing warrants action, say IDLE and stop — idling honestly beats \
inventing work."

OUT="$("$PI_BIN" -p --approve --session-id self-harness \
  --provider local-qwen --model "$MODEL_ID" \
  "$WAKE_PROMPT" 2>&1)"
CODE=$?
TAIL="$(printf '%s' "$OUT" | tail -c 400 | tr '\n' ' ')"
echo "$STAMP EXIT=$CODE ${TAIL}" >> "$LOG"
exit 0
