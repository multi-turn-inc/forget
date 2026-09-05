#!/usr/bin/env python3
"""c62 — 침묵의 산술: 두 trace의 실제 점수에 훅 게이트를 그대로 적용한다 (읽기 전용).

확정된 사실 (c62_probe_traces.py):
  - 15:01:36Z (c61 2차 런, 주입 0)  q='devloop 사이클을...'  cand=5
  - 15:35:50Z (c62 이 세션, 주입 3) q='devloop 사이클을...'  cand=5
동일 질의·동일 훅 sha256·34분 간격. 훅은 **양쪽 다 실행됐다** → 침묵은 게이트 소산이다.

이 스크립트는 두 trace의 candidate 점수를 꺼내 forget_turnrecall.main()의 게이트를
같은 순서로 적용하고, 어느 단계가 몇 개를 떨어뜨렸는지 인쇄한다. 훅의 자기 보고가
아니라 서버가 남긴 점수 원본이 입력이다.
"""
import json
import os
import sqlite3
import sys

DB = os.path.expanduser("~/.forget/forget.sqlite3")
HOOK_DIR = os.path.expanduser("~/.forget/hooks")
sys.path.insert(0, HOOK_DIR)

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "forget_turnrecall_ro", os.path.join(HOOK_DIR, "forget_turnrecall.py"))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)   # main() 미호출 — 상수만 읽는다

TARGETS = [
    ("2026-08-06T15:01:36Z", "c61 2차 런 — 실측 주입 0"),
    ("2026-08-06T15:35:50Z", "c62 이 세션 — 실측 주입 3"),
]

print(f"훅 상수: gate={hook.SCORE_THRESHOLD} semantic_floor={hook.SEMANTIC_FLOOR} "
      f"flatness_margin={hook.FLATNESS_MARGIN} MAX_RECALLS={hook.MAX_RECALLS}")

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row


def candidates(payload: dict) -> list:
    """trace payload에서 후보별 (id, score, vector, metadata)를 꺼낸다."""
    out = []
    snaps = payload.get("candidate_snapshots")
    if isinstance(snaps, list) and snaps:
        for snap in snaps:
            out.append({
                "id": str(snap.get("id") or ""),
                "score": float(snap.get("score") or 0.0),
                "vector": (snap.get("score_breakdown") or {}).get("vector"),
                "metadata": snap.get("metadata") or {},
                "text": (snap.get("memory") or snap.get("text") or "")[:70].replace("\n", " "),
            })
        return out
    results = (payload.get("search_payload") or {}).get("results")
    if isinstance(results, list):
        for item in results:
            out.append({
                "id": str(item.get("id") or ""),
                "score": float(item.get("score") or 0.0),
                "vector": (item.get("score_breakdown") or {}).get("vector"),
                "metadata": item.get("metadata") or {},
                "text": (item.get("memory") or "")[:70].replace("\n", " "),
            })
    return out


for created_at, label in TARGETS:
    row = conn.execute(
        "SELECT trace_id, created_at, query, candidate_ids, selected_ids, scores, payload "
        "FROM context_traces WHERE created_at = ? AND query LIKE 'devloop 사이클%'",
        (created_at,),
    ).fetchone()
    print("\n" + "=" * 78)
    print(f"[{created_at}] {label}")
    print("=" * 78)
    if not row:
        print("  trace 없음")
        continue
    payload = json.loads(row["payload"] or "{}")
    print(f"  trace_id={row['trace_id']}  payload keys={sorted(payload.keys())[:8]}")
    scores_map = json.loads(row["scores"] or "{}")
    cands = candidates(payload)
    if not cands and scores_map:
        cands = [{"id": k, "score": float(v), "vector": None, "metadata": {}, "text": ""}
                 for k, v in scores_map.items()]
    if not cands:
        print("  후보 스냅샷 부재 — payload에 점수가 저장되지 않았다")
        print(f"  scores 원문[:200]: {(row['scores'] or '')[:200]}")
        continue
    cands.sort(key=lambda c: c["score"], reverse=True)

    scores_all = sorted((c["score"] for c in cands), reverse=True)
    median = scores_all[len(scores_all) // 2]
    spread = scores_all[0] - median
    flat = len(scores_all) >= 4 and spread < hook.FLATNESS_MARGIN
    print(f"  점수: {[round(s, 4) for s in scores_all]}")
    print(f"  top1={scores_all[0]:.4f}  중앙값={median:.4f}  spread={spread:.4f}  "
          f"margin={hook.FLATNESS_MARGIN}  → 평지판정={flat}")

    dropped = {"below_gate": 0, "flat": 0, "semantic": 0, "task_state": 0,
               "hook_ptr": 0, "conflict": 0, "pass": 0}
    for c in cands:
        md = c["metadata"]
        if md.get("hook"):
            dropped["hook_ptr"] += 1
            continue
        if md.get("assertion_kind") == "task_state":
            dropped["task_state"] += 1
            continue
        if md.get("superseded_by") or (isinstance(md.get("supersedes"), list) and md.get("supersedes")):
            dropped["conflict"] += 1
            continue
        if c["score"] < hook.SCORE_THRESHOLD:
            dropped["below_gate"] += 1
            continue
        if flat:
            dropped["flat"] += 1
            continue
        if c["vector"] is not None and float(c["vector"]) < hook.SEMANTIC_FLOOR:
            dropped["semantic"] += 1
            continue
        dropped["pass"] += 1
    print(f"  게이트 소산: {dropped}")
    print(f"  → 예측 주입 = min(pass, MAX_RECALLS) = {min(dropped['pass'], hook.MAX_RECALLS)}")
    for c in cands:
        print(f"     {c['score']:.4f} vec={c['vector']}  {c['text']}")

conn.close()
