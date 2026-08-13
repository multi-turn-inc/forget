#!/bin/bash
# 섀도 주기 — 통일 곡선에 두 변형을 나란히 채점 (정훈-예측기 v0, 2026-08-13).
# ① 기준선: Spark 27B prompt-only (기존 동작 그대로, 기본 상태 파일)
# ② 쌍둥이: 4090 vllm twin_v1 LoRA (터널 8024, 변형별 상태 파일)
# 한쪽 엔진이 죽어도 다른 쪽은 채점한다 — 실패는 로그로만.

DAEMON="$HOME/.forget/twin/shadow_daemon.py"

/usr/bin/python3 "$DAEMON" || echo "[cycle] baseline 실패 $(date '+%F %T')"

TWIN_URL="http://127.0.0.1:8024/v1/chat/completions" \
TWIN_MODEL="twin_v1" \
TWIN_VARIANT="twin_v1_sft/qwen3.5-9b" \
/usr/bin/python3 "$DAEMON" || echo "[cycle] twin_v1 실패 $(date '+%F %T')"
