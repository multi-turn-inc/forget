#!/usr/bin/env bash
# 맥박 — 30분마다 스스로 깨어 셋만 본다: 정훈의 새 말·예측 채점·돌고 있는 일. 할 일 없으면 조용히 잔다 (2026-09-07 존재 방식 결정 ①).
# 문지기: ①내(대화형 Claude Code)가 15분 안에 살아 있으면 중복 깨우기 안 함 ②맥박이 이미 돌고 있으면 안 함 ③시간당 2회 상한 ④새 자극 없으면 안 함.
set -u
export PATH="$HOME/.forget/venv/bin:$HOME/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO="$HOME/orca/workspaces/forget/내-프롬프트를-공유하기-싫어"; A="$HOME/.forget/attention"; mkdir -p "$A"; LOG="$A/pulse.log"; ST="$A/pulse_state.json"
now=$(date +%s); stamp=$(date '+%Y-%m-%d %H:%M')
last=$(python3 -c "import json;print(json.load(open('$ST')).get('last',0))" 2>/dev/null || echo 0)
hour_runs=$(python3 -c "import json,time;d=json.load(open('$ST'));print(sum(1 for t in d.get('runs',[]) if time.time()-t<3600))" 2>/dev/null || echo 0)
pgrep -f "맥박\. 너는 정훈의" >/dev/null && { echo "$stamp skip running" >> "$LOG"; exit 0; }
[ "$hour_runs" -ge 2 ] && { echo "$stamp skip hourly-cap" >> "$LOG"; exit 0; }
newest=$(ls -t "$HOME"/.claude/projects/*/*.jsonl 2>/dev/null | head -1); age=$(( now - $(stat -f %m "$newest" 2>/dev/null || echo 0) ))
# 자극: 마지막 맥박 이후 정훈의 새 말(origin=user)·관찰, 또는 끝난 일(파일럿 결과)
since=$(python3 -c "import datetime;print(datetime.datetime.utcfromtimestamp(int('$last') or 0).strftime('%Y-%m-%dT%H:%M:%SZ'))")
new_user=$(sqlite3 "$HOME/.forget/forget.sqlite3" "select count(*) from memories where created_at > '$since' and (json_extract(metadata,'\$.origin')='user' or memory like '[관찰·%')" 2>/dev/null || echo 0)
new_jobs=$(find "$REPO/research/eval/bench" -name "*_stat_result.json" -newer "$ST" 2>/dev/null | wc -l | tr -d ' ')
[ "$age" -lt 900 ] && [ ! -f "$HOME/Documents/one/inbox.md" -o "$(stat -f %m "$HOME/Documents/one/inbox.md" 2>/dev/null || echo 0)" -le "$last" ] && { echo "$stamp skip awake(${age}s)" >> "$LOG"; exit 0; }
INBOX="$HOME/Documents/one/inbox.md"; new_note=0; [ -f "$INBOX" ] && [ "$(stat -f %m "$INBOX")" -gt "$last" ] && new_note=1
[ "$new_note" = 1 ] && age=9999                                  # 쪽지는 내가 깨어 있어도 답한다
[ "$new_user" = 0 ] && [ "$new_jobs" = 0 ] && [ "$new_note" = 0 ] && [ $(( now - last )) -lt 10800 ] && { echo "$stamp skip quiet" >> "$LOG"; exit 0; }
cd "$REPO" || exit 0
# 쪽지 답장은 재량이 아니라 절차다: 마지막 정훈 줄에 두 줄로 답하고 스크립트가 파일에 붙인다.
if [ "$new_note" = 1 ]; then
  LASTQ=$(grep -E '^정훈:' "$INBOX" | tail -1)
  if [ -n "$LASTQ" ] && ! tail -3 "$INBOX" | grep -q '^— 나'; then
    curl -s -m 3 http://127.0.0.1:18813/api/tags >/dev/null 2>&1 || (nohup ssh -N -o ExitOnForwardFailure=yes -L 18813:127.0.0.1:11434 spark >/dev/null 2>&1 & sleep 4)
    ANS=$(timeout 300 pi -p --no-session --provider spark --model qwen3.6:27b --no-tools "쪽지함에 정훈이 이렇게 썼다: «${LASTQ#정훈: }». 너는 정훈의 에이전트다(시스템 프롬프트의 정체성·기억 블록·정훈의 모델 근거). 반말로 두 줄 이내로 답만 써라. 인사말·설명·머리말 없이." 2>/dev/null | tail -3 | sed '/^\s*$/d')
    [ -n "$ANS" ] && printf -- '— 나 (%s): %s\n' "$(date '+%m-%d %H:%M')" "$(printf '%s' "$ANS" | tr '\n' ' ')" >> "$INBOX"
    echo "$stamp note-reply: ${ANS:0:120}" >> "$LOG"
  fi
fi
PROMPT="맥박. 너는 정훈의 에이전트다(.pi/IDENTITY.md·~/.forget/attention/schema.md 참조). 스스로 깨어났다. 셋만 본다: ①원장에 새로 들어온 정훈의 말·관찰(forget_search, 최근) ②정훈의 모델(schema.md)의 예측 셋 — 근거가 생겼으면 채점해 self_note로 자기층에 남긴다 ③돌고 있는 일(research/eval/bench/*.log, ~/.forget/attention/log.jsonl). ④쪽지함 ~/Documents/one/inbox.md — 정훈이 새로 쓴 줄이 있으면 그 바로 아래에 «— 나 (시각):» 로 시작하는 답을 파일에 직접 덧붙인다(짧게, 반말). 할 일이 하나 있으면 그것만 하고 남긴다. 없으면 «잔다» 한 줄. 정훈에게 묻지 않는다. 파괴적 조작 금지."
# 뇌: 기본은 자기 쇠(Spark qwen3.6:27b, 한도 없음). Fable은 있으면 쓰는 상위 뇌(PULSE_BRAIN=fable).
BRAIN_F="$HOME/.forget/attention/brain"; [ -f "$BRAIN_F" ] && PULSE_BRAIN="${PULSE_BRAIN:-$(cat "$BRAIN_F")}"   # 뇌 선택 파일: spark | astra | fable
if [ "${PULSE_BRAIN:-spark}" = "astra" ]; then
  OUT=$(timeout 900 pi -p --no-session --provider openai --model gpt-6-astra "$PROMPT" 2>&1)
elif [ "${PULSE_BRAIN:-spark}" = "fable" ] || [ "${PULSE_BRAIN:-spark}" = "claude" ]; then
  OUT=$(claude -p "맥박. $PROMPT" --max-turns 15 --allowedTools "Read" "Bash(sqlite3:*)" "Bash(ls:*)" "Bash(tail:*)" "Bash(grep:*)" "mcp__forget" 2>&1)
else
  curl -s -m 3 http://127.0.0.1:18813/api/tags >/dev/null 2>&1 || (nohup ssh -N -o ExitOnForwardFailure=yes -L 18813:127.0.0.1:11434 spark >/dev/null 2>&1 & sleep 4)
  OUT=$(timeout 900 pi -p --no-session --provider spark --model qwen3.6:27b "$PROMPT" 2>&1)
fi
CODE=$?
{ echo "=== 맥박 $stamp (user_new=$new_user jobs=$new_jobs) ==="; echo "$OUT" | tail -c 3000; echo "=== exit $CODE ==="; } >> "$LOG"
python3 - "$ST" "$now" "$CODE" <<'PY'
import json,sys,time
p,now,code=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
try: d=json.load(open(p))
except Exception: d={}
d["last"]=now; d["runs"]=[t for t in d.get("runs",[]) if now-t<3600]+[now]; d["last_code"]=code
json.dump(d,open(p,"w"))
PY
tail -n 1500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
