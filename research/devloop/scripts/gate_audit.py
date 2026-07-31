"""주간 벤치: 게이트 로그 감사 (LOOP.md 벤치마크 삼각측량 — 주간 항목).

읽기 전용 — localhost:8000 REST(/v1/events/)와 MCP list_gate_log 결과를 대조해
게이트 거부율(refusals / ADD 시도)과 과압축 후보(잘못 잊음)를 집계한다.
실DB에는 아무것도 쓰지 않는다 (원칙 3·4).

사용: .venv/bin/python research/devloop/scripts/gate_audit.py [--days 30]
"""

import argparse
import datetime as dt
import json
import urllib.request
from collections import Counter

MCP_URL = "http://localhost:8000/mcp/forget/http/junghunkim"


def mcp_call(name: str, arguments: dict):
    """MCP HTTP 엔드포인트로 tools/call — cycle-prompt.md의 curl 폴백과 동일 경로."""
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


def fetch_events(cutoff: str, max_pages: int = 500):
    """cutoff(YYYY-MM-DD) 이후 이벤트를 최신순 페이지네이션으로 수집."""
    events = []
    page = 1
    while page <= max_pages:
        data = mcp_call("list_events", {"page": page, "page_size": 100})
        results = data.get("results", [])
        if not results:
            break
        events.extend(results)
        oldest = min(e["created_at"][:10] for e in results)
        if oldest < cutoff or not data.get("next"):
            break
        page += 1
    return [e for e in events if e["created_at"][:10] >= cutoff], page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()

    today = dt.date.today()
    cutoff = (today - dt.timedelta(days=args.days)).isoformat()

    events, pages = fetch_events(cutoff)
    by_type = Counter(e["event_type"] for e in events)
    adds_by_day = Counter(
        e["created_at"][:10] for e in events if e["event_type"] == "ADD"
    )

    report = {
        "window": {"from": cutoff, "to": today.isoformat()},
        "pages_fetched": pages,
        "events_total_in_window": len(events),
        "by_type": dict(by_type),
        "add_events": by_type.get("ADD", 0),
        "adds_by_day": dict(sorted(adds_by_day.items())),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
