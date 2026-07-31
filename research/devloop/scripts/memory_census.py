"""기억 수 불일치 검증 — 스코프별 센서스 (사이클 8, 읽기 전용).

배경: 사이클 7 감사에서 junghunkim×forget 스코프 기억 517개 실측이 캡슐(heartbeat)의
827과 불일치했다. 원인 후보는 스코프 차이. 이 스크립트는 user_id=junghunkim 전체를
가져와 (app_id, agent_id)별로 집계해 원인을 확정한다. 실DB에는 아무것도 쓰지 않는다.

사용: .venv/bin/python research/devloop/scripts/memory_census.py
"""

import json
import urllib.request
from collections import Counter

MCP_URL = "http://localhost:8000/mcp/forget/http/junghunkim"


def mcp_call(name: str, arguments: dict):
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    ).encode()
    req = urllib.request.Request(
        MCP_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        rpc = json.load(r)
    return json.loads(rpc["result"]["content"][0]["text"])


def fetch_all(filters: dict):
    memories, page = [], 1
    while True:
        data = mcp_call(
            "get_memories", {"filters": filters, "page": page, "page_size": 200}
        )
        memories.extend(data.get("results", []))
        if not data.get("next"):
            return data.get("count"), memories
        page += 1


def main():
    total, memories = fetch_all({"user_id": "junghunkim"})
    by_scope = Counter((m.get("app_id") or "-", m.get("agent_id") or "-") for m in memories)
    report = {
        "filter": {"user_id": "junghunkim"},
        "count_reported": total,
        "count_fetched": len(memories),
        "by_app_agent": {f"{app}|{agent}": n for (app, agent), n in by_scope.most_common()},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
