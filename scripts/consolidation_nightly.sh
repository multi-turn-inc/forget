#!/bin/bash
# 일일 응고 심장박동 — 망각 헌장 L1-② 상시화 (게이트 개방 2026-08-26).
# launchd ai.forget.consolidation이 새벽 1회 실행. 정본 repo, 설치본 ~/.forget/bin.
# 안전장치: ①실행 전 자동 백업(일자별, 7일 보관) ②하루 실행당 응고 3일치
# 상한(--max-days 3) ③14일 문턱은 모듈 내장 ④로그 ⑤터널(요약 LLM) 없으면 스킵.
set -u
LOG_DIR="$HOME/.forget/selfharness"
mkdir -p "$LOG_DIR" "$HOME/.forget/backups"
STAMP="$(date '+%Y-%m-%dT%H:%M:%S%z')"
LOG="$LOG_DIR/consolidation.log"
TUNNEL="${FORGET_LLAMA_URL:-http://127.0.0.1:18812/v1}"
REPO="${SELF_HARNESS_REPO:-$HOME/orca/workspaces/forget/내-프롬프트를-공유하기-싫어}"

if ! curl -s -m 5 "$TUNNEL/models" > /dev/null 2>&1; then
  echo "$STAMP SKIP tunnel-dead" >> "$LOG"
  exit 0
fi

BK="$HOME/.forget/backups/forget-nightly-$(date '+%Y%m%d').sqlite3"
[ -f "$BK" ] || cp "$HOME/.forget/forget.sqlite3" "$BK"
find "$HOME/.forget/backups" -name 'forget-nightly-*.sqlite3' -mtime +7 -delete 2>/dev/null

cd "$REPO" || { echo "$STAMP FAIL no-repo" >> "$LOG"; exit 0; }
OUT="$("$REPO/.venv/bin/python" -m forget.consolidation_cycle --live --apply --yes --max-days 3 2>&1)"
CODE=$?
echo "$STAMP EXIT=$CODE $(printf '%s' "$OUT" | tail -c 300 | tr '\n' ' ')" >> "$LOG"

# 2단: 사다리 컴파일러 정기 실행 (§4.14) — 판결된 군집의 재성장만 자동 강등
# (결정론 — 과거 배치 멤버십), 신규 군집은 ~/.forget/compile_proposals/ 제안
# 큐로 게이트 대기. 가역: compile_ledgers/ 원장 + revert_compile.
COUT="$("$REPO/.venv/bin/python" -m forget.compiler --scheduled 2>&1)"
CCODE=$?
echo "$STAMP COMPILER EXIT=$CCODE $(printf '%s' "$COUT" | tail -c 300 | tr '\n' ' ')" >> "$LOG"

# 3단: MUS 야간 스냅샷 (recallbench 사이클 7) — 기억 유용성 점수의 정기 계기.
# score.py가 은행 3×+상황 3×를 직렬로 돌리므로 상한 20분. 실패해도 응고는 무사.
MOUT="$(cd "$REPO" && timeout 1200 python3 research/recallbench/score.py 2>&1 | tail -2)"
echo "$STAMP MUS $(printf '%s' "$MOUT" | tr '\n' ' ')" >> "$LOG"
exit 0
