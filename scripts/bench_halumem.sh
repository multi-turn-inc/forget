#!/usr/bin/env bash
# HaluMem-Medium을 forget에 돌린다 (2026-09-07, BENCHMARK-SURVEY 결론 «새로 만들지 말고 돌리자»).
#   scripts/bench_halumem.sh [users=1] [version=pilot]   # 1) 추출·갱신·QA 수집  2) 판정(evaluation.py, OPENAI_MODEL)
# 격리: 벤치 전용 DB(research/eval/bench/db/halumem-<version>.sqlite3). 실DB는 건드리지 않는다.
# 모델: 답변·판정 = OPENAI_MODEL(기본 gpt-4o — 논문 판정 모델). 키는 pi auth에서 꺼내 환경으로만 넘긴다(출력 금지).
set -uo pipefail
cd "$(dirname "$0")/.."
USERS="${1:-1}"; VER="${2:-pilot}"
export FORGET_REPO="$PWD"
export MEM1_DB_PATH="$PWD/research/eval/bench/db/halumem-$VER.sqlite3"
export MEM1_ALLOWED_SCOPES='*:*' MEM1_RECALL_TEMPORAL=0 FORGET_TRACE_VERBOSE=0
export OPENAI_API_KEY="$(pi auth print-api-key --provider openai)"
export OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o}" OPENAI_TEMPERATURE=0 OPENAI_TIMEOUT=120
export HALUMEM_LIMIT_USERS="$USERS" RETRY_TIMES=3 WAIT_TIME_LOWER=2 WAIT_TIME_UPPER=6 OPENAI_MAX_TOKENS=1024
PY="$HOME/.forget/venv/bin/python"
cd research/eval/bench/HaluMem/eval
echo "== 수집: users=$USERS version=$VER db=$MEM1_DB_PATH model=$OPENAI_MODEL"
"$PY" eval_forget.py --version "$VER" 2>&1
echo "== 판정"
"$PY" evaluation.py --frame forget --version "$VER" 2>&1 | tail -40
