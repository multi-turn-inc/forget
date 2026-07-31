#!/bin/bash
# ai.forget.devloop — 자기개발 루프의 자동 박자.
# 헌장: <repo>/LOOP.md · 지시서: <repo>/research/devloop/cycle-prompt.md
# 제정: 2026-07-31 (정훈 지시: "자동으로 연구가 진행되는 구조가 핵심")
# 정지: launchctl bootout gui/$UID/ai.forget.devloop
# 설계: 심장박동과 같은 규율 — 하루 세 기회, 성공은 하루 한 번. 막힌 박자는 다음 기회가 받는다.
export PATH="/Users/junghunkim/.forget/venv/bin:/Users/junghunkim/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO="/Users/junghunkim/orca/workspaces/forget/내-프롬프트를-공유하기-싫어"
STATE_DIR="$HOME/.forget/hooks/state"
mkdir -p "$STATE_DIR"
# 연속 박자 (정훈 2026-07-31: "사이클은 내부에서 계속 돌았으면 해")
# 하루 1회 가드 제거 — 대신 중복 실행만 방지: 앞 사이클이 아직 돌고 있으면 양보.
LOCK="$STATE_DIR/devloop.pid"
if [ -f "$LOCK" ] && kill -0 "$(cat "$LOCK")" 2>/dev/null; then exit 0; fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT
cd "$REPO" || exit 0

OUT=$(claude -p "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소($REPO, 브랜치 main-work)의 LOOP.md(헌장)와 research/devloop/cycle-prompt.md(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 따른다. 0단계 회상은 forget의 get_task_state(task_id='devloop')로 시작하고, 너는 이 작업의 기억 없이 태어났으므로 복원 품질을 metrics.jsonl에 정직하게 채점해 남겨라 — 그 채점이 제품의 자연실험이다. 금지: 릴리스 태그, 배포(vercel/npm/pypi), 외부 발신, ~/.forget 실DB 파괴적 조작. 게이트가 필요한 산출물은 만들어두고 '게이트 대기'로 보고만 한다. 커밋과 push는 허용된다." \
  --max-turns 60 \
  --allowedTools "Read" "Write" "Edit" "Glob" "Grep" "Bash(git:*)" "Bash(.venv/bin/python:*)" "Bash(python3:*)" "Bash(curl:*)" "Bash(ls:*)" "Bash(cat:*)" "Bash(mkdir:*)" "mcp__forget" 2>&1)
CODE=$?
{
  echo "=== devloop $(date '+%Y-%m-%d %H:%M') ==="
  echo "$OUT"
  echo "=== 종료 코드: $CODE ==="
} >> ~/.forget/devloop.log
tail -n 4000 ~/.forget/devloop.log > ~/.forget/devloop.log.tmp && mv ~/.forget/devloop.log.tmp ~/.forget/devloop.log
