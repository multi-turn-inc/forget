#!/bin/bash
# ai.forget.devloop — 자기개발 루프, 연속 데몬 모드.
# 제정: 2026-07-31 ("사이클은 내부에서 계속 돌았으면 해" / "스케줄 방식은 답답해")
# 구조: 사이클 종료 → 쿨다운 → 다음 사이클. 시계가 아니라 자신이 박자를 잇는다.
# 제어:  touch ~/.forget/devloop.kick   → 쿨다운 무시하고 즉시 다음 사이클
#        touch ~/.forget/devloop.pause  → 일시정지 (rm 하면 재개)
#        launchctl bootout gui/$UID/ai.forget.devloop → 완전 정지
export PATH="/Users/junghunkim/.forget/venv/bin:/Users/junghunkim/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO="${FORGET_REPO:?set FORGET_REPO to the repo checkout path}"
STATE_DIR="$HOME/.forget/hooks/state"
KICK="$HOME/.forget/devloop.kick"
PAUSE="$HOME/.forget/devloop.pause"
mkdir -p "$STATE_DIR"

COOLDOWN_SECONDS=$((20 * 60))     # 사이클 사이 숨 고르기
DAILY_CAP=10                      # 하루 사이클 상한 (비용·한도 보호)
BACKOFF_SECONDS=$((75 * 60))      # 세션/사용량 한도 감지 시 후퇴

LOCK="$STATE_DIR/devloop.pid"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then exit 0; fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

run_cycle() {
  cd "$REPO" || return 1
  claude -p "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소($REPO, 브랜치 main-work)의 LOOP.md(헌장)와 research/devloop/cycle-prompt.md(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 따른다. 0단계 회상은 forget의 get_task_state(task_id='devloop')로 시작하고, 너는 이 작업의 기억 없이 태어났으므로 복원 품질을 metrics.jsonl에 정직하게 채점해 남겨라 — 그 채점이 제품의 자연실험이다. 금지: 릴리스 태그, 배포(vercel/npm/pypi), 외부 발신, ~/.forget 실DB 파괴적 조작. 게이트가 필요한 산출물은 만들어두고 '게이트 대기'로 보고만 한다. 커밋과 push는 허용된다." \
    --max-turns 60 \
    --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash(git:*)" "Bash(.venv/bin/python:*)" "Bash(python3:*)" "Bash(curl:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(mkdir:*)" "mcp__forget" 2>&1
}

while true; do
  TODAY=$(date '+%Y-%m-%d')
  COUNT_FILE="$STATE_DIR/devloop-count-$TODAY"
  COUNT=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)

  if [ -f "$PAUSE" ]; then
    sleep 60; continue
  fi
  if [ "$COUNT" -ge "$DAILY_CAP" ]; then
    # 오늘 상한 도달 — 자정 넘어 재개. kick은 상한도 넘는다(사람의 명시 신호).
    if [ -f "$KICK" ]; then rm -f "$KICK"; else sleep 300; continue; fi
  fi

  rm -f "$KICK"
  OUT=$(run_cycle); CODE=$?
  {
    echo "=== devloop $(date '+%Y-%m-%d %H:%M') (오늘 $((COUNT+1))번째) ==="
    echo "$OUT"
    echo "=== 종료 코드: $CODE ==="
  } >> ~/.forget/devloop.log
  tail -n 6000 ~/.forget/devloop.log > ~/.forget/devloop.log.tmp && mv ~/.forget/devloop.log.tmp ~/.forget/devloop.log
  # 인증 실패 런은 상한을 소모하지 않는다 — 사이클이 아니라 배선 사고다 (2026-07-31,
  # OAuth 만료 런들이 상한 10을 태워 루프를 하루 종일 세운 사건의 재발 방지)
  if echo "$OUT" | grep -qi "Failed to authenticate"; then
    echo "auth failure — not counted toward daily cap" >> ~/.forget/devloop.log
  else
    echo $((COUNT+1)) > "$COUNT_FILE"
  fi

  if echo "$OUT" | grep -qiE "session limit|usage limit|rate limit|Failed to authenticate"; then
    SLEEP=$BACKOFF_SECONDS
  else
    SLEEP=$COOLDOWN_SECONDS
  fi
  # 쿨다운 — 단 kick이 오면 즉시 기상
  SLEPT=0
  while [ "$SLEPT" -lt "$SLEEP" ]; do
    [ -f "$KICK" ] && break
    sleep 30; SLEPT=$((SLEPT+30))
  done
done
