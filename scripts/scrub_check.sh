#!/bin/bash
# 공개 전 오염 검사 — 히트 0이어야 통과
set -u
FAIL=0
check() {
  local label="$1"; shift
  local hits
  hits=$(grep -rInE "$1" --exclude-dir=.git --exclude=scrub_check.sh . 2>/dev/null | head -5)
  if [ -n "$hits" ]; then echo "✗ $label:"; echo "$hits"; FAIL=1; else echo "✓ $label"; fi
}
check "라이브 API 키 패턴"      "(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|m0-[A-Za-z0-9]{24,}|re_[A-Za-z0-9]{20,})"
check "Paddle/Toss 시크릿"      "(PADDLE_API_KEY|WEBHOOK_SECRET|test_sk_|live_sk_)[=:][^\$ ]"
check "서버 IP"                 "155\.230\."
check "개인 이메일"             "hebo1221"
check "사업자등록번호"          "517-86-03611"
check "터널/내부 URL"           "trycloudflare\.com"
check "구 브랜드 잔재(Enacta)"       "Enacta"
check "개인키 블록"             "BEGIN (RSA|OPENSSH|EC|ED25519)? ?PRIVATE KEY"
DB=$(find . -type f \( \
  -name "*.sqlite" -o -name "*.sqlite3" -o -name "*.db" -o \
  -name "*.sqlite-wal" -o -name "*.sqlite-shm" -o -name "*.sqlite-journal" -o \
  -name "*.sqlite3-wal" -o -name "*.sqlite3-shm" -o -name "*.sqlite3-journal" -o \
  -name "*.db-wal" -o -name "*.db-shm" -o -name "*.db-journal" \
\) ! -path "./.git/*" | head -3)
if [ -n "$DB" ]; then echo "✗ DB 파일 존재:"; echo "$DB"; FAIL=1; else echo "✓ DB 파일 없음"; fi
ENV=$(find . -name ".env*" ! -name ".env.example" | grep -v ".git" | head -3)
if [ -n "$ENV" ]; then echo "✗ .env 파일 존재:"; echo "$ENV"; FAIL=1; else echo "✓ .env 없음"; fi
exit $FAIL
