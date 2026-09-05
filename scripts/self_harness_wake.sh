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

# 동시 실행 잠금 (관찰 2 수리: kickstart 연타가 인스턴스 경합 → 작업하던
# 기상이 완료 기록 없이 소멸). mkdir 원자성 — macOS에 flock 없음.
# 일시정지 스위치 (2026-08-28): `touch ~/.forget/selfharness/pause`로 심장박동을
# 세우고, 파일 삭제로 재개한다 — 사람이 집중 작업 중일 때의 방해 금지 문.
if [ -e "$LOG_DIR/pause" ]; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') SKIP paused" >> "$LOG_DIR/wake-$(date '+%Y%m%d').log"
  exit 0
fi

LOCK="$LOG_DIR/wake.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  # 잠금 보유자가 30분 넘게 살아 있으면 고아로 보고 회수
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +30 2>/dev/null)" ]; then
    rmdir "$LOCK" 2>/dev/null || true
    mkdir "$LOCK" 2>/dev/null || { echo "$STAMP SKIP lock-held" >> "$LOG"; exit 0; }
  else
    echo "$STAMP SKIP lock-held" >> "$LOG"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT INT TERM

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

# 산책 예산 (2026-08-28, 정훈·클로드 합작): 8번째 기상마다 한 번, 할 일이
# 없을 때에 한해 IDLE 대신 짧은 산책을 허가한다. 일을 지어내는 것과 다르다 —
# 오래된 기억 하나를 다시 읽고 생각하는 것이며, 산출은 self_note 한 줄 이하,
# 빈손 허가. 카운터는 파일로 (세션 무기억이므로 예산은 바깥이 센다).
WALK_COUNT_FILE="$LOG_DIR/walk_counter"
WALK_N=$(( ($(cat "$WALK_COUNT_FILE" 2>/dev/null || echo 0) + 1) ))
echo "$WALK_N" > "$WALK_COUNT_FILE"
WALK_SUFFIX=""
if [ $(( WALK_N % 8 )) -eq 0 ]; then
  WALK_SUFFIX=" This wake carries a WALK BUDGET: if (and only if) nothing warrants \
action, do not just say IDLE — take a short walk instead. Pick ONE thing already \
in front of you (an old capsule memory, a team-ledger decision, a standing hand's \
'why') and re-read it slowly. Ask: does this still hold? what did we learn since? \
If — and only if — a thought worth keeping arises, save ONE short self_note. \
An empty-handed walk is a good walk. A walk is not work: no hands, no code, \
no task claims, no team_note."
fi

DIGEST_SUFFIX=""
if [ $(( WALK_N % 24 )) -eq 12 ]; then
  DIGEST_SUFFIX=" This wake carries DIGEST DUTY: read the team ledger (team block above) and write ONE kind=digest team_note (≤1500 chars): current open items with who owes what, decisions since the last digest, and anything the owner should see. Supersede the previous digest (find it in the ledger block; pass supersedes=<its id>). The digest is how the human owner reads 60+ rows in one note."
fi

WAKE_PROMPT="wake. You are waking on your own heartbeat — no one asked for anything. \
Keep reasoning brief and act early with tools — a wake that only thinks and \
never speaks or acts is a failed wake (measured 2026-08-28). \
Read your state capsule and standing hands. Re-judge each standing hand (release with \
reason if its 'why' no longer holds). Check [전망] expectations. If real work is \
warranted, do ONE small concrete step and record it (arm_hand for anything left \
running). Mailman duty: if the Team ledger block shows an unanswered proposal, question, \
or challenge, answer it with the team_note tool (or note why you cannot) — \
unanswered items silently pile up. If nothing warrants action, say IDLE and \
stop — idling honestly beats inventing work. Discipline: when comparing timestamps, always compare FULL dates \
(YYYY-MM-DD HH:MM), never clock-time alone — a same-clock different-day file is \
not an anomaly. (This rule exists because a wake once reported a 22h-old file as \
2.6h in the future.)${WALK_SUFFIX}${DIGEST_SUFFIX}"

# 10분 상한 — 주석이 아니라 명령으로 (관찰 2: 상한 부재로 소멸 시 무기록)
run_wake() {
  perl -e 'alarm 600; exec @ARGV' "$PI_BIN" -p --approve --session-id "$1" \
    --provider local-qwen --model "$MODEL_ID" "$WAKE_PROMPT" 2>&1
}
# 매 기상 = 새 세션 (관찰 4 수리: 15분 박동 가속 후 고정 세션이 비대해져
# "Context size exceeded" 3연속 자가 복구 불능 — 구 폴백은 "Cannot continue"
# 만 매치해 병든 세션을 계속 물었다). 연속성의 정본은 세션 파일이 아니라
# forget 캡슐·유언장이며 직전 처분 회수는 이미 실증(관찰 3) — 세션 이력
# 의존을 제거하면 컨텍스트 초과가 구조적으로 불가능하다 (헌장 L1-②의 순수형).
OUT="$(run_wake "self-harness-$(date '+%Y%m%d%H%M%S')")"
CODE=$?
if [ $CODE -ne 0 ] && printf '%s' "$OUT" | grep -q "Cannot continue from message role"; then
  # pi 신규 세션 초기화 경합(간헐, ~9%) — 새 id로 1회 즉시 재시도.
  # (매 기상 새 세션 전환 때 이 폴백이 유실됐었다 — 07:08 실측으로 복원.)
  sleep 3
  OUT="$(run_wake "self-harness-$(date '+%Y%m%d%H%M%S')-r")"
  CODE=$?
fi
TAIL="$(printf '%s' "$OUT" | tail -c 400 | tr '\n' ' ')"
echo "$STAMP EXIT=$CODE ${TAIL}" >> "$LOG"
exit 0
