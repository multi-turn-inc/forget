#!/usr/bin/env python3
"""F2 원인 조사 (사이클 18, 읽기 전용): turnrecall 훅의 검색을 라이브 :8000에
그대로 재생해 heartbeat·pash 기억의 실제 점수와 임계 통과 여부를 실측한다."""
import json
import urllib.request

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
    res = rpc("search_memories", {"query": PROMPT, "top_k": 8})
    print(f"query[:60]: {PROMPT[:60]}")
    for it in res.get("results") or []:
        md = it.get("metadata") or {}
        pair = bool(md.get("superseded_by") or md.get("supersedes"))
        flags = []
        if md.get("hook"):
            flags.append("hook")
        if pair:
            flags.append("conflict-pair")
        text = (it.get("memory") or "")[:90].replace("\n", " ")
        print(f"{float(it.get('score') or 0):.4f}  {str(it.get('id',''))[:8]}  "
              f"[{','.join(flags) or '-'}]  {text}")


if __name__ == "__main__":
    main()
