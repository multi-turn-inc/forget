#!/bin/bash
# forget 설치 스크립트 v0 — "쉽게 장기기억을" (사용자 하네스 헌장, P-U-0 후속).
# 목표 사용자 경험: curl -fsSL https://…/install.sh | bash  (배포는 게이트 뒤 —
# 지금은 로컬 실측 전용: bash scripts/install.sh)
#
# 하는 일: ①forget-ai[server] 설치 (자체 venv ~/.forget/venv-user — 시스템
# 파이썬 불오염) ②로그인 서비스 등록(launchd/systemd) ③pi가 있으면 접착
# 확장을 글로벌 배치 ④상태 인쇄. 멱등 — 재실행 안전.
#
# 시뮬 노브 (P-U-0 실측용): FORGET_INSTALL_PREFIX(기본 ~/.forget) ·
# FORGET_INSTALL_WHEEL(로컬 wheel 경로 — 미지정 시 PyPI, 게이트 전이라 로컬 필수) ·
# FORGET_INSTALL_NO_SERVICE=1 (서비스 등록 스킵) · FORGET_INSTALL_NO_PI=1
set -euo pipefail

PREFIX="${FORGET_INSTALL_PREFIX:-$HOME/.forget}"
VENV="$PREFIX/venv-user"
WHEEL="${FORGET_INSTALL_WHEEL:-}"

say() { printf '\033[1m[forget]\033[0m %s\n' "$*"; }

command -v python3 >/dev/null || { echo "python3가 필요합니다 (>=3.11)"; exit 1; }
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "python3 >= 3.11 필요 (현재 $PYVER)"; exit 1; }

say "① forget 설치 ($VENV)"
mkdir -p "$PREFIX"
[ -d "$VENV" ] || python3 -m venv "$VENV"
if [ -n "$WHEEL" ]; then
  "$VENV/bin/pip" install -q --upgrade "${WHEEL}[server]"
else
  "$VENV/bin/pip" install -q --upgrade "forget-ai[server]"
fi
say "   설치됨: $("$VENV/bin/forget-server" --help 2>/dev/null | head -1 || echo forget-server)"

if [ "${FORGET_INSTALL_NO_SERVICE:-0}" != "1" ]; then
  say "② 로그인 서비스 등록"
  "$VENV/bin/forget-server" install-service
else
  say "② 서비스 등록 스킵 (FORGET_INSTALL_NO_SERVICE=1) — 수동: $VENV/bin/forget-server run"
fi

if [ "${FORGET_INSTALL_NO_PI:-0}" != "1" ] && command -v pi >/dev/null 2>&1; then
  say "③ pi 하네스 확장 배치"
  EXT_DIR="${FORGET_PI_EXT_DIR:-$HOME/.pi/agent/extensions}"
  mkdir -p "$EXT_DIR"
  SRC_EXT="$(dirname "$0")/../.pi/extensions/forget.ts"
  if [ -f "$SRC_EXT" ]; then
    cp "$SRC_EXT" "$EXT_DIR/forget.ts"
    say "   $EXT_DIR/forget.ts (pi가 자동 로드)"
  else
    say "   확장 원본을 찾지 못함 — 저장소에서 실행하세요"
  fi
else
  say "③ pi 미설치 또는 스킵 — 하네스 없이 기억층만 (MCP: /mcp/forget/http/<user>)"
fi

say "④ 완료. 확인:"
say "   curl -s http://localhost:8000/openapi.json | head -c 60"
say "   MCP 주소: http://localhost:8000/mcp/forget/http/\$USER"
