#!/usr/bin/env python3
"""MUS v0 — 기억 유용성 점수 (정의 정본: docs/recallbench.md §MUS).

구성 3축 (v0 — 각 [0,1], 산술평균):
  bank      = RECALL-BENCH 은행 통과율 (재생 실측)
  situation = 상황 좌석 정밀도 ((적중 + 무관침묵) / 10질의)
  outcome   = 최근 30일 record_context_outcome에서 helped / (helped+noise)
스냅샷은 series=recallbench.mus 기억으로 기록 — 시계열 승계가 정본 유지.
"""
import json, os, re, sqlite3, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
URL = os.environ.get("FORGET_MCP_URL", "http://localhost:8000/mcp/forget/http/junghunkim")

def bank_rate():
    out = subprocess.run([sys.executable, os.path.join(ROOT, "replay.py")],
                         capture_output=True, text=True, timeout=300).stdout
    m = re.search(r"은행 (\d+)표본 · PASS (\d+)", out)
    return int(m.group(2)) / int(m.group(1)), out

def situation_rate():
    eval_path = os.environ.get("PM8_EVAL", "/private/tmp/claude-501/-Users-junghunkim-orca-workspaces-forget----------------/45dc8302-58e8-4d35-adce-c97499f29a78/scratchpad/pm8_eval.py")
    out = subprocess.run([sys.executable, eval_path], capture_output=True, text=True, timeout=600).stdout
    m = re.search(r"상황 적중 (\d)/5.*오발 (\d)/5", out)
    hit, fp = int(m.group(1)), int(m.group(2))
    return (hit + (5 - fp)) / 10.0

def outcome_rate():
    """v0.1 (2026-08-30): turn_recall 채널 한정 + 기억-귀속 평결만 —
    helped(none) / (none + selection_failure). reasoning_failure는 하류 몫."""
    conn = sqlite3.connect(os.path.expanduser("~/.forget/forget.sqlite3"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""SELECT o.failure_stage FROM context_outcomes o
        WHERE o.created_at > datetime('now', '-30 days')
          AND o.failure_stage IN ('none', '', 'selection_failure')
          AND o.trace_id IN (SELECT trace_id FROM context_traces
                             WHERE payload LIKE '%turn_recall%')""").fetchall()
    if not rows:
        return None
    helped = sum(1 for r in rows if r["failure_stage"] in ("none", ""))
    return helped / len(rows)

def main():
    # v0.2 (2026-08-30, 정훈: «라벨은 쓰지마»): outcome 라벨 축 폐기 —
    # context_outcomes는 라벨러의 성격을 재는 수치였다(정의 2회 요동이 자백).
    # 점수는 행동-결합 축만: bank(세계가 채점한 실전 사고의 재생) +
    # situation(고정 계약 세트). 실사용 앵커는 점수 밖 — P-V-1 정정 빈도(행동)
    # 와 향후 ε-보류 개입(헌장이 승인한 유일한 인과 라벨).
    bank, bank_out = bank_rate()
    situ = situation_rate()
    comps = {"bank": round(bank, 3), "situation": round(situ, 3)}
    mus = round(sum(comps.values()) / len(comps), 3)
    print(f"MUS v0.2 = {mus}  {comps}")
    text = (f"MUS v0.2 스냅샷: {mus} — bank {comps['bank']} · situation {comps['situation']}"
            f" (라벨 축 폐기 — 정의: docs/recallbench.md)")
    req = urllib.request.Request(URL, data=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "add_memory", "arguments": {
            "text": text, "user_id": "junghunkim",
            "metadata": {"series": "recallbench.mus3"}}}}).encode(),
        headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=15).read()
    print("스냅샷 기록 (series=recallbench.mus3 — 시계열 승계 자동)")

if __name__ == "__main__":
    main()
