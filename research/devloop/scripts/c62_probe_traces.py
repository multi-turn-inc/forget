#!/usr/bin/env python3
"""c62 보조 — 서버측 trace로 '훅이 돌았는가'를 판정한다 (읽기 전용 URI 연결).

동일 프롬프트·동일 훅 빌드·34분 간격의 두 세션이 주입 0 대 3. 세션 ledger 가설(H1)은
반증됐다(주입된 3개 id가 침묵 세션의 seen 집합에 없다). 남은 판별:
  (H2) 훅 미실행 — 하네스가 UserPromptSubmit을 돌리지 않았다
  (H3) 훅 실행 + 게이트 침묵 — 평탄도/의미바닥/임계가 전량 탈락시켰다

body A1(fd30a68)이 검색에 trace="turn_recall"을 붙여 서버측에 남기므로, 훅이 돌았다면
그 시각에 context_traces 행이 있다. 행 존재 → H3, 부재 → H2. 이것이 훅의 자기 보고가
아닌 독립 채널이다.

안전: sqlite3 file:...?mode=ro 로 연다. 쓰기 없음.
"""
import glob
import json
import os
import sqlite3

DB = os.path.expanduser("~/.forget/forget.sqlite3")  # 도그푸드 실DB — 읽기 전용으로만
if not os.path.exists(DB):
    raise SystemExit(f"DB 부재: {DB} (후보: {glob.glob(os.path.expanduser('~/.forget/*.sqlite3'))})")
print(f"DB: {DB}  ({os.path.getsize(DB)//1024//1024} MB, 읽기 전용 연결)\n")

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

# 창: c61 2차 런(15:01Z) 직전부터 c62(15:35Z) 이후까지.
WINDOW = ("2026-08-06T14:50", "2026-08-06T16:10")
rows = conn.execute(
    "SELECT trace_id, task_id, substr(query,1,60) AS q, "
    "       json_array_length(candidate_ids) AS n_cand, "
    "       json_array_length(selected_ids) AS n_sel, created_at, substr(payload,1,120) AS pay "
    "FROM context_traces WHERE created_at >= ? AND created_at <= ? ORDER BY created_at",
    WINDOW,
).fetchall()
print(f"[창 {WINDOW[0]} ~ {WINDOW[1]}] context_traces {len(rows)}행")
for r in rows:
    print(f"  {r['created_at']}  cand={r['n_cand']:<3} sel={r['n_sel']:<3} task={r['task_id'][:12]:<12} q={r['q']!r}")
    if r["pay"] and r["pay"] != "{}":
        print(f"      payload: {r['pay']}")

# turn_recall 계열만 — source 라벨은 payload에 앉는다.
print("\n[turn_recall 라벨 행 — 최근 20]")
recent = conn.execute(
    "SELECT trace_id, created_at, substr(query,1,50) AS q, "
    "       json_array_length(candidate_ids) AS n_cand, json_array_length(selected_ids) AS n_sel, payload "
    "FROM context_traces ORDER BY created_at DESC LIMIT 60"
).fetchall()
shown = 0
for r in recent:
    payload = r["payload"] or ""
    if "turn_recall" not in payload:
        continue
    try:
        meta = json.loads(payload)
    except Exception:
        meta = {}
    print(f"  {r['created_at']}  cand={r['n_cand']:<3} sel={r['n_sel']:<3} "
          f"source={meta.get('source') or meta.get('trace') or '?'}  q={r['q']!r}")
    shown += 1
    if shown >= 20:
        break
if shown == 0:
    print("  (payload에 turn_recall 라벨 0행 — 라벨 저장 경로 확인 필요)")

print("\n[전체 규모]")
total = conn.execute("SELECT COUNT(*) FROM context_traces").fetchone()[0]
span = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM context_traces").fetchone()
print(f"  context_traces 총 {total}행, 범위 {span[0]} ~ {span[1]}")
conn.close()
