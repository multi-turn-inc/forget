#!/usr/bin/env python3
"""«정훈이 말하기 전에 블록에 이미 있었나» — goal:observe-junghun 둘째 판정 지표 (2026-09-07).

정의: 턴 회상 훅(forget_turnrecall)이 어떤 턴에 기억을 주입했을 때, 그 기억이 그 시각 직전 사이드카 블록에
이미 들어 있었으면 «선점». 선점률 = 선점 주입 / 전체 주입. 분모가 0이면(훅이 침묵만 했으면) 판정 불가.
재료: ~/.forget/hooks/state/turnrecall_gate.jsonl(주입한 턴의 시각) × context_traces(payload에 turn_recall — 그 턴의 후보 selected_ids,
훅이 실제로 넣은 부분집합의 근사) · ~/.forget/attention/log.jsonl(judge 행의 block_ids). 근사임을 표기한다.
"""
from __future__ import annotations
import json, os, sys, time
from datetime import datetime, timezone

GATE = os.path.expanduser("~/.forget/hooks/state/turnrecall_gate.jsonl")
LOG = os.path.expanduser(os.getenv("FORGET_ATTENTION_DIR", "~/.forget/attention")) + "/log.jsonl"


def _ts(s: str) -> float:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def main() -> int:
    since = time.time() - float(sys.argv[1]) * 3600 if len(sys.argv) > 1 else 0
    snaps = []   # (ts, set(ids))
    if os.path.exists(LOG):
        for l in open(LOG):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get("kind") == "judge" and "block_ids" in d:
                snaps.append((_ts(d["at"]), set(d["block_ids"])))
    snaps.sort()
    gate_times = []
    if os.path.exists(GATE):
        for l in open(GATE):
            try:
                d = json.loads(l)
            except Exception:
                continue
            if d.get("action") == "injected" and float(d.get("at", 0)) >= since:
                gate_times.append((float(d["at"]), int(d.get("picks") or 0)))
    import sqlite3
    db = os.path.expanduser(os.getenv("MEM1_DB_PATH", "~/.forget/forget.sqlite3"))
    traces = []
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        for tid, at, sel in conn.execute("SELECT trace_id, created_at, selected_ids FROM context_traces WHERE payload LIKE '%turn_recall%' AND created_at > ?",
                                          (datetime.fromtimestamp(since, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),)):
            try:
                traces.append((_ts(at), json.loads(sel)))
            except Exception:
                pass
    inj = []
    for gat, picks in gate_times:
        near = [(abs(t - gat), ids) for t, ids in traces if abs(t - gat) < 30]
        if near and picks:
            ids = sorted(near)[0][1][:picks]      # 근사: 상위 picks개가 주입됐다고 본다
            inj.append((gat, ids))
    total = pre = 0
    for at, ids in inj:
        block = set()
        for ts, b in snaps:
            if ts <= at:
                block = b
            else:
                break
        for i in ids:
            if not i:
                continue
            total += 1
            pre += 1 if i in block else 0
    print(f"블록 스냅샷 {len(snaps)} · 훅 주입 턴 {len(inj)} · 주입 기억 {total} · 선점 {pre} · 선점률 {(pre / total * 100):.0f}%" if total else
          f"블록 스냅샷 {len(snaps)} · 훅 주입 턴 {len(inj)} · 주입 기억 0 — 판정 불가(분모 0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
