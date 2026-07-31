#!/usr/bin/env python3
"""F2 조사 2단계 (사이클 18): 상위 히트의 점수 성분 분해 — 라이브 srv 점수와
현재 repo 코드(local)의 score_memory를 나란히 계산해 coverage/jaccard/phrase 기여를
분리한다. repo 루트에서 실행: python3 research/devloop/scripts/f2_components.py"""
import json
import sys
import urllib.request

sys.path.insert(0, ".")
from forget.memory_engine import expanded_tokens, score_memory

PROMPT = (
    "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소(/Users/junghunkim/orca/"
    "workspaces/forget/내-프롬프트를-공유하기-싫어, 브랜치 main-work)의 LOOP.md(헌장)와 "
    "research/devloop/cycle-prompt.md(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 "
    "따른다. 0단계 회상은 forget의 get_task_state(task_id='devloop')로 시작하고, "
    "너는 이 작업의 기억 없이 태어났으므로 복원 품질을 metrics.jsonl에 정직하게 채점해 남겨라"
)[:300]


def rpc(name, arguments):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(
        "http://127.0.0.1:8000/mcp",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return json.loads(body["result"]["content"][0]["text"])


def main():
    q = expanded_tokens(PROMPT)
    print(f"q_tokens n={len(q)}")
    res = rpc("search_memories", {"query": PROMPT, "top_k": 8})
    for it in res.get("results") or []:
        text = str(it.get("memory") or "")
        m = expanded_tokens(text)
        ov = q & m
        coverage = len(ov) / len(q)
        jac = len(ov) / (len(q | m) or 1)
        phrase = sum(0.02 for t in q if t in text.lower())
        print(f"srv={float(it.get('score') or 0):.3f} local={score_memory(PROMPT, it):.3f} "
              f"cov={coverage:.2f}(+{0.45 * coverage:.3f}) jac={jac:.3f}(+{0.35 * jac:.3f}) "
              f"phrase=+{phrase:.2f} len={len(text)} | {text[:60]}".replace("\n", " "))
        print("   overlap:", sorted(ov)[:20])


if __name__ == "__main__":
    main()
