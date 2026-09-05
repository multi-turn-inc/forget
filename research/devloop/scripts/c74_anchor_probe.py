#!/usr/bin/env python3
"""c74 보조 — 하룻밤 새 평지→봉우리로 뒤집힌 앵커 2건의 봉우리 정체 검시 (읽기 전용).

'c15 eta를 알려줘' 0.0113→0.3371, '에러가 발생했나?' 0.0192→0.3184.
같은 자[尺]·같은 질의에서 spread가 30배 뛰었다면 변한 것은 스토어다 —
무엇이 새 봉우리인지 top-5를 그대로 편다.
"""
from __future__ import annotations

import json
import urllib.request

URL = "http://127.0.0.1:8000/mcp"


def rpc(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return json.loads(json.loads(urllib.request.urlopen(req, timeout=30).read())
                      ["result"]["content"][0]["text"])


def eligible(item: dict) -> bool:
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


def main() -> None:
    import sys
    queries = sys.argv[1:] or ["c15 eta를 알려줘", "에러가 발생했나?"]
    for q in queries:
        out = rpc("search_memories", {"query": q, "recall": "low",
                                      "score_breakdown": True, "top_k": 5})
        print(f"=== {q!r}")
        for item in out.get("results") or []:
            sb = item.get("score_breakdown") or {}
            tag = "ELIG" if eligible(item) else "excl"
            created = str(item.get("created_at") or "")[:19]
            print(f"  [{tag}] score={float(item.get('score') or 0):.4f} "
                  f"rule={sb.get('rule')} vec={sb.get('vector')} created={created}")
            print(f"         {str(item.get('memory') or '')[:110]!r}")


if __name__ == "__main__":
    main()
