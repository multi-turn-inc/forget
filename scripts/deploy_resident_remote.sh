#!/usr/bin/env bash
# 상주를 늘 켜진 서버로 옮긴다 (2026-09-07, 정훈 «노트북을 닫더라도 계속 생각을 돌릴 수 있어야»).
# 대상: ssh 별칭 azure-trading-korea (Azure B2ats_v2 · 2vCPU · RAM 1GiB · 64GB · Ubuntu 24.04).
# 실행은 정훈 손:  scripts/deploy_resident_remote.sh            # 처음 배치(슬림 원장 포함)
#                  scripts/deploy_resident_remote.sh --sync     # 코드·원장만 다시 밀기
# 1GiB 제약: 로컬 임베딩 모델 대신 OpenAI 임베딩(text-embedding-3-small), 뇌는 Astra(API 키). 구독 OAuth는 서버에서 `codex login` 뒤 brain=codex로.
set -euo pipefail
HOST="${REMOTE_HOST:-azure-trading-korea}"
RDIR="${REMOTE_DIR:-~/forget}"
cd "$(dirname "$0")/.."
LOCAL_DB="$HOME/.forget/forget.sqlite3"
SLIM="/tmp/forget-slim.sqlite3"
ok(){ printf "  \033[32m●\033[0m %s\n" "$1"; }

echo "== 1) 슬림 원장 뽑기(기억·이력·정정·작업·관찰만, 기록/트레이스 제외)"
rm -f "$SLIM"
sqlite3 "$LOCAL_DB" "VACUUM INTO '$SLIM';"
sqlite3 "$SLIM" "DELETE FROM context_traces; DELETE FROM events; DELETE FROM context_observations; DELETE FROM request_logs; DELETE FROM usage_events; DELETE FROM trace_export_audits; VACUUM;"
ok "슬림 원장 $(du -h "$SLIM" | cut -f1) · 기억 $(sqlite3 "$SLIM" 'select count(*) from memories')건"

echo "== 2) 코드·원장 밀기"
rsync -az --delete --exclude '.venv' --exclude 'node_modules' --exclude '__pycache__' --exclude 'research/eval/bench' --exclude 'gtm' --exclude '*.sqlite3*' --exclude '.git' ./ "$HOST:$RDIR/"
rsync -az "$SLIM" "$HOST:~/.forget/forget.sqlite3"
rsync -az ~/.forget/attention/schema.md ~/.forget/attention/brain "$HOST:~/.forget/attention/" 2>/dev/null || true
rsync -az .pi/IDENTITY.md "$HOST:$RDIR/.pi/IDENTITY.md"
[ -f ~/.one_telegram_token ] && rsync -az ~/.one_telegram_token "$HOST:~/.one_telegram_token"
mkdir -p /tmp/one && rsync -az ~/Documents/one/telegram_owner.txt "$HOST:~/Documents/one/" 2>/dev/null || true
ok "밀었다"

[ "${1:-}" = "--sync" ] && { ssh "$HOST" 'systemctl --user restart forget-resident forget-telegram 2>/dev/null || true'; ok "재시작"; exit 0; }

echo "== 3) 서버 준비(venv·의존성·서비스)"
OPENAI_KEY="$(pi auth print-api-key --provider openai 2>/dev/null || true)"
ssh "$HOST" "OPENAI_KEY='$OPENAI_KEY' RDIR='$RDIR' bash -s" <<'REMOTE'
set -e
cd "$RDIR"
mkdir -p ~/.forget/attention ~/Documents/one ~/.config/systemd/user
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e . --no-deps
.venv/bin/pip install -q fastapi uvicorn numpy pydantic httpx
# 환경: 1GiB라 로컬 임베딩 금지 → OpenAI 임베딩, 뇌 Astra(API)
cat > ~/.forget/resident.env <<ENV
MEM1_DB_PATH=$HOME/.forget/forget.sqlite3
FORGET_REPO=$RDIR
OPENAI_API_KEY=$OPENAI_KEY
MEM1_EMBEDDING_PROVIDER=openai
MEM1_EMBEDDING_MODEL=text-embedding-3-small
MEM1_EMBEDDING_API_KEY=$OPENAI_KEY
BODY_TICK=15
BODY_SLEEP_MAX=900
ENV
chmod 600 ~/.forget/resident.env
echo astra > ~/.forget/attention/brain
cat > ~/.config/systemd/user/forget-resident.service <<UNIT
[Unit]
Description=forget resident (상주)
After=network-online.target
[Service]
WorkingDirectory=$RDIR
EnvironmentFile=$HOME/.forget/resident.env
ExecStart=$RDIR/.venv/bin/python -m harness.body.resident
Restart=always
RestartSec=10
MemoryMax=600M
[Install]
WantedBy=default.target
UNIT
cat > ~/.config/systemd/user/forget-telegram.service <<UNIT
[Unit]
Description=forget telegram bridge (다리)
After=network-online.target
[Service]
WorkingDirectory=$RDIR
EnvironmentFile=$HOME/.forget/resident.env
ExecStart=$RDIR/.venv/bin/python scripts/telegram_bridge.py
Restart=always
RestartSec=10
[Install]
WantedBy=default.target
UNIT
loginctl enable-linger "$USER" >/dev/null 2>&1 || true
systemctl --user daemon-reload
systemctl --user enable --now forget-resident forget-telegram
sleep 5
systemctl --user --no-pager status forget-resident forget-telegram | grep -E "Active|Main PID" | head -4
free -m | awk 'NR==2{print "RAM used/avail:", $3, $7}'
REMOTE
ok "서버에서 상주·다리가 systemd(user, linger)로 돈다 — 재부팅도 넘긴다"
echo
echo "다음: 맥의 텔레그램 다리는 끈다(중복 답 방지):  launchctl bootout gui/501/ai.one.telegram"
echo "      맥의 상주도 끈다:                         launchctl bootout gui/501/ai.forget.resident"
echo "      원장 되가져오기(맥이 깨어 있을 때):       scripts/sync_ledger_remote.sh  (다음에 만든다)"
