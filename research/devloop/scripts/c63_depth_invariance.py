#!/usr/bin/env python3
"""c63 — 깊은 인출이 자[尺]를 바꾸는가, 그리고 얕은 풀이 실제로 얼마나 얇은가 (읽기 전용).

c62가 테스트로 고정한 경계: 평탄도 분포를 **주입 자격 후보**에서만 재는데
`top_k = MAX_RECALLS + 2 = 5`뿐이라, 무자격 후보(task_state claim·capture 포인터·
충돌쌍)가 2개면 자격 후보가 3개로 떨어지고 `len >= 4` 조건이 깨져 게이트가
**한 마디 없이 전면 정지**한다.

처치 후보는 "더 깊이 인출한다"이지만 그 전에 두 전제를 실측해야 한다:

  (전제 1) 깊이를 5→10으로 올려도 **상위 5개의 (id, score)가 동일**한가?
           아니라면 점수가 결과 집합에 의존한다는 뜻이고, 깊이 인상은
           자[尺]를 바꾸는 처치가 된다 (c48 규율 위반).
  (전제 2) 자격 후보를 5개 창까지 채우려면 깊이 10으로 충분한가? 그리고
           현재 깊이 5에서 자격 수 분포는 실제로 경계에 걸쳐 있는가?

입력은 도그푸드 서버가 남긴 **실제 turn_recall 질의**(과거 훅 호출의 원문)이고,
재실행은 그 trace가 쓴 filters를 그대로 쓴다. trace=는 넘기지 않는다 —
계측이 장부를 오염시키지 않도록.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "hooks"))

DB = os.path.expanduser("~/.forget/forget.sqlite3")
FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
SHALLOW = 5          # 현행 top_k (MAX_RECALLS + 2)
DEEP = 10            # 처치 후보 깊이
WINDOW = 5           # 평탄도 창 (처치 후: 자격 후보 상위 5개)
MIN_SAMPLES = 4      # 자[尺] 미변경
MARGIN = 0.03        # 자[尺] 미변경


def rpc(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        FORGET_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(request, timeout=30).read())
    return json.loads(body["result"]["content"][0]["text"])


def eligible(item: dict) -> bool:
    """훅 `_injection_eligible`의 판정을 그대로 복제 (구조적 배제 3종)."""
    md = item.get("metadata") or {}
    if md.get("hook"):
        return False
    if md.get("assertion_kind") == "task_state":
        return False
    if md.get("superseded_by"):
        return False
    supersedes = md.get("supersedes")
    if isinstance(supersedes, list) and supersedes:
        return False
    return True


def flat_verdict(scores: list[float]) -> tuple[bool, float, int]:
    if len(scores) < MIN_SAMPLES:
        return (False, float("nan"), len(scores))   # 게이트 미적용 = 전량 통과
    spread = scores[0] - scores[len(scores) // 2]
    return (spread < MARGIN, spread, len(scores))


def turn_recall_queries(limit: int) -> list[tuple[str, str, dict]]:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out, seen = [], set()
    for row in conn.execute(
        "SELECT created_at, query, filters, payload FROM context_traces "
        "ORDER BY created_at DESC LIMIT 600"
    ):
        if "turn_recall" not in (row["payload"] or ""):
            continue
        query = (row["query"] or "").strip()
        if not query or query in seen:
            continue
        seen.add(query)
        try:
            filters = json.loads(row["filters"] or "null")
        except Exception:
            filters = None
        out.append((row["created_at"], query, filters if isinstance(filters, dict) else None))
        if len(out) >= limit:
            break
    conn.close()
    return out


def main() -> None:
    samples = turn_recall_queries(20)
    print(f"실제 turn_recall 질의 {len(samples)}건 (중복 제거, 최신순) — 깊이 {SHALLOW} 대 {DEEP} 대조")
    print(f"자[尺] 고정: margin={MARGIN} min_samples={MIN_SAMPLES} window={WINDOW}\n")

    mismatch = 0
    tally = {"shallow_gate_off": 0, "deep_gate_off": 0, "rescued": 0,
             "verdict_changed": 0, "spread_changed": 0, "boundary_exact4": 0}
    rows = []
    for created_at, query, filters in samples:
        args = {"query": query[:300], "recall": "low", "score_breakdown": True}
        if filters:
            args["filters"] = filters
        shallow = rpc("search_memories", {**args, "top_k": SHALLOW}).get("results") or []
        deep = rpc("search_memories", {**args, "top_k": DEEP}).get("results") or []

        # 전제 1 — 상위 SHALLOW개의 (id, score)가 깊이에 불변인가
        head = [(str(i.get("id")), round(float(i.get("score") or 0), 6)) for i in shallow]
        deep_head = [(str(i.get("id")), round(float(i.get("score") or 0), 6)) for i in deep[:SHALLOW]]
        same = head == deep_head
        if not same:
            mismatch += 1

        # 전제 2 — 자격 풀의 두께
        s_scores = sorted((float(i.get("score") or 0) for i in shallow if eligible(i)), reverse=True)
        d_scores = sorted((float(i.get("score") or 0) for i in deep if eligible(i)), reverse=True)[:WINDOW]
        s_flat, s_spread, s_n = flat_verdict(s_scores)
        d_flat, d_spread, d_n = flat_verdict(d_scores)

        if s_n < MIN_SAMPLES:
            tally["shallow_gate_off"] += 1
            if d_n >= MIN_SAMPLES:
                tally["rescued"] += 1
        if d_n < MIN_SAMPLES:
            tally["deep_gate_off"] += 1
        if s_n == MIN_SAMPLES:
            tally["boundary_exact4"] += 1
        if s_flat != d_flat:
            tally["verdict_changed"] += 1
        if s_n >= MIN_SAMPLES and d_n >= MIN_SAMPLES and abs(s_spread - d_spread) > 1e-9:
            tally["spread_changed"] += 1

        rows.append((created_at, query, len(shallow), len(deep), s_n, d_n,
                     s_spread, d_spread, s_flat, d_flat, same))

    print(f"{'created_at':21} {'cand':>7} {'자격':>7} {'spread':>17} {'평지':>11} 불변 질의")
    for (created_at, query, sc, dc, s_n, d_n, s_spread, d_spread, s_flat, d_flat, same) in rows:
        sp = "  n/a  " if s_n < MIN_SAMPLES else f"{s_spread:.4f}"
        dp = "  n/a  " if d_n < MIN_SAMPLES else f"{d_spread:.4f}"
        print(f"{created_at:21} {sc:>3}/{dc:<3} {s_n:>3}/{d_n:<3} "
              f"{sp:>8}→{dp:<8} {str(s_flat):>5}→{str(d_flat):<5} "
              f"{'O' if same else 'X':>4} {query[:34]!r}")

    print()
    print(f"[전제 1] 상위 {SHALLOW}개 (id,score) 깊이 불변: {len(samples) - mismatch}/{len(samples)}"
          f"  (불일치 {mismatch}건)")
    print(f"[전제 1'] spread 값이 깊이로 바뀐 질의: {tally['spread_changed']}건 "
          f"/ 평지 판정이 바뀐 질의: {tally['verdict_changed']}건")
    print(f"[전제 2] 깊이 {SHALLOW}에서 게이트 무공지 정지(자격<4): {tally['shallow_gate_off']}건 "
          f"→ 깊이 {DEEP}에서 {tally['deep_gate_off']}건 (구조된 질의 {tally['rescued']}건)")
    print(f"[전제 2'] 자격 수가 최소 경계에 정확히 걸친 질의(자격=4): {tally['boundary_exact4']}건")


if __name__ == "__main__":
    main()
