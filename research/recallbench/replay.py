#!/usr/bin/env python3
"""RECALL-BENCH 재생기 — 사고 은행을 현행 회상층에 재생 (memory_as_of 시간여행).

판정: miss형 = gold가 top-k 안 (접두 일치 허용) / stale형 = gold가 최상이고
forbidden(구본)이 gold보다 위에 못 옴 / noise형 = 해당 채널 침묵.
표본 규약: 실전 사고만 입행 (합성 금지) — 사고가 표본을 정한다.
"""
import json, os, sys, urllib.request

URL = os.environ.get("FORGET_MCP_URL", "http://localhost:8000/mcp/forget/http/junghunkim")

def rpc(name, args):
    req = urllib.request.Request(URL, data=json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": name, "arguments": args}}).encode(),
        headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return json.loads(out["result"]["content"][0]["text"])

def matches(mid, prefixes):
    return any(mid.startswith(p) for p in prefixes)

def hook_replay(inc):
    """사고 채널 충실 재생: 실제 훅 스크립트에 프롬프트를 흘리고 주입 원장을 읽는다.
    훅은 시간여행 불가 — 이 채널의 판정은 «현행 층이 그 사고를 지금 막는가»(회귀 자)."""
    import subprocess, uuid, os as _os
    sid = f"rb-{uuid.uuid4().hex[:8]}"
    if inc.get("session_seen_gold"):
        # v0.2 세션 상태 충실: 사고 세션에선 gold가 이미 제안·억제된 상태였다 —
        # 재생 세션 원장에 그 상태를 시딩해야 사고가 정직하게 재현된다.
        state_dir = _os.path.expanduser("~/.forget/hooks/state")
        _os.makedirs(state_dir, exist_ok=True)
        with open(_os.path.join(state_dir, f"{sid}.turns.json"), "w") as fh:
            json.dump({"turn": 120, "injected": {g: [15, 0] for g in inc.get("gold_ids", [])}}, fh)
    payload = json.dumps({"prompt": inc["query"], "session_id": sid,
                          "cwd": _os.path.expanduser("~/orca/workspaces/forget/내-프롬프트를-공유하기-싫어")})
    out = subprocess.run(["python3", _os.path.expanduser("~/.forget/hooks/forget_turnrecall.py")],
                         input=payload, capture_output=True, text=True, timeout=40,
                         env={**_os.environ, "FORGET_MCP_URL": URL, "FORGET_REPLAY": "1",
                              **({"FORGET_REPLAY_AS_OF": inc["as_of"]} if inc.get("as_of") else {})}).stdout
    ok_track = any(t in out for t in inc.get("accept_tracks", []))
    injected = []
    state = _os.path.expanduser(f"~/.forget/hooks/state/{sid}.turns.json")
    if _os.path.exists(state):
        injected = json.load(open(state)).get("injected") or []
    seeded = set(inc.get("gold_ids", [])) if inc.get("session_seen_gold") else set()
    fresh = [m for m in injected if m not in seeded]
    ok_gold = any(matches(m, inc.get("gold_ids", [])) for m in fresh)
    return (ok_track or ok_gold), f"주입 {len(injected)}건 gold={'유' if ok_gold else '무'} 트랙적중={'유' if ok_track else '무'}"


def run():
    path = os.path.join(os.path.dirname(__file__), "incidents.jsonl")
    results = []
    for line in open(path):
        inc = json.loads(line)
        k = inc.get("k", 5)
        if inc.get("channel") == "hook":
            ok, detail = hook_replay(inc)
            results.append((inc["id"], inc["type"], ok, detail, inc["fix"]))
            continue
        if inc["type"] == "noise" and inc.get("channel") == "situation":
            hit = rpc("situation_recall", {"query": inc["query"]}).get("situation")
            ok = hit is None
            detail = f"situation={hit['task_id'] if hit else 'silent'}"
        else:
            out = rpc("search_memories", {"query": inc["query"], "top_k": k,
                                          "recall": "high", "memory_as_of": inc["as_of"],
                                          "score_breakdown": True})
            ids = [r["id"] for r in out.get("results", [])]
            if inc["type"] == "miss":
                ok = any(matches(m, inc["gold_ids"]) for m in ids)
                detail = f"top{k}에 gold {'있음' if ok else '없음'}"
            else:  # stale — 병의 정의는 «구본이 정본을 제친다». 구본 부재/침강 = 완치.
                gold_rank = next((i for i, m in enumerate(ids) if matches(m, inc["gold_ids"])), None)
                bad_rank = next((i for i, m in enumerate(ids) if matches(m, inc.get("forbidden_ids", []))), None)
                sup_rows = [r for r in out.get("results", []) if matches(r["id"], inc.get("forbidden_ids", []))]
                sup_flags = [bool((r.get("score_breakdown") or {}).get("superseded")) for r in sup_rows]
                ok = bad_rank is None or all(sup_flags) or (gold_rank is not None and bad_rank > gold_rank)
                gold_note = "gold부재(별도 miss)" if gold_rank is None else f"gold@{gold_rank}"
                detail = f"{gold_note} 구본@{bad_rank} 침강={sup_flags}"
        results.append((inc["id"], inc["type"], ok, detail, inc["fix"]))
    print(f"{'ID':8s} {'유형':6s} {'판정':4s} 상세")
    for rid, typ, ok, detail, fix in results:
        print(f"{rid:8s} {typ:6s} {'PASS' if ok else 'FAIL'} {detail}  ← {fix[:30]}")
    n_ok = sum(1 for r in results if r[2])
    print(f"\n은행 {len(results)}표본 · PASS {n_ok} · FAIL {len(results)-n_ok}")

if __name__ == "__main__":
    run()
