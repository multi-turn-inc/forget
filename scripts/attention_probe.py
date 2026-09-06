#!/usr/bin/env python3
"""활성 재순위 전/후 프로브 (2026-09-07). 허브 넷이 떨어지고 표적이 올라오면 장치가 맞는 것."""
from __future__ import annotations
import json, sys, time, urllib.request
sys.path.insert(0, ".")
from forget import activation as A

URL = "http://localhost:8000/mcp/forget/http/junghunkim"
HUBS = {"be8e46b8-f796-4f7f-9563-fdb084d9544b", "f011264b-be39-47f5-a409-b151a49cde74",
        "89e2bbed-14fb-4f10-8677-3a09b942a8de", "88883dfd-ff6d-40de-b167-cba3fb66ebc1", "6ad2180d-2e02-4904-93b3-69900eea6e41"}
PROBES = [
    ("케어콜 효돌과 경쟁하지 않는다 ChatGPT 시리와 경쟁", "효돌·케어콜과 경쟁하지 않는다"),
    ("LoRA 실패 판단 톤은 배웠고 판단은 못 배웠다", "LoRA 판정"),
    ("정훈이 forget E2EE 피봇을 결정한 이유", "E2EE"),
    ("도란 캐릭터 A 조약돌 새 선택", "조약돌"),
    ("Signal 교훈 프로토콜 열고 서비스로 과금", "Signal 교훈"),
    ("정훈 미국 이주 목표 법인 설립 보류", "미국 이주"),
    ("DGX Spark 접속 방법", "spark"),
    ("하네스를 직접 만들자는 결정", "하네스를 직접"),
    ("정훈을 관찰하는 것이 목표", "관찰"),
]

def search(q, limit=40):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_memories", "arguments": {"query": q, "limit": limit}}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    d = json.load(urllib.request.urlopen(req, timeout=60))
    return json.loads(d["result"]["content"][0]["text"]).get("results", [])

def rank_of(results, needle):
    for i, r in enumerate(results):
        if needle.lower() in str(r.get("memory", "")).lower():
            return i + 1
    return None

t0 = time.time(); stats = A.load_stats(refresh="--refresh" in sys.argv); print(f"stats: {len(stats['stats'])} ids, {time.time()-t0:.1f}s")
tot_hub_before = tot_hub_after = 0; rows = []
for q, needle in PROBES:
    res = search(q)
    before = res[:5]; after = A.rerank(res, stats)[:5]
    hb = sum(1 for r in before if r["id"] in HUBS); ha = sum(1 for r in after if r["id"] in HUBS)
    mb = sum(1 for r in before if A.is_machine_record(r.get("memory", ""))); ma = sum(1 for r in after if A.is_machine_record(r.get("memory", "")))
    tot_hub_before += hb; tot_hub_after += ha
    rows.append((q[:28], rank_of(res[:5], needle), rank_of(A.rerank(res, stats)[:10], needle), hb, ha, mb, ma))
print(f"{'probe':30} {'표적 전':>7} {'표적 후':>7} {'허브 전/후':>10} {'기계 전/후':>10}")
for q, rb, ra, hb, ha, mb, ma in rows:
    print(f"{q:30} {str(rb):>7} {str(ra):>7} {hb:>4}/{ha:<5} {mb:>4}/{ma:<5}")
print(f"허브 합계(상위5): {tot_hub_before} → {tot_hub_after}")
