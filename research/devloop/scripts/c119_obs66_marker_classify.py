#!/usr/bin/env python3
"""c119 · 관측 66 ② 보조 — 실DB에서 발견된 폴백 표지 행의 성질 판별 (읽기 전용).

질문: events/context_traces의 'fallback→v1'/'recall_layer' 표지 행이
텔레메트리(서버가 폴백 사실을 기록)인가, 콘텐츠 인용(질의·기억 본문이
그 문자열을 담았을 뿐)인가 — 관측 36 계열(기록이 측정을 오염) 판별.

인쇄 규약: 질의·본문 원문 무인쇄, sha8·필드명·건수만 (관측 37 승계).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3

MARKERS = ("fallback→v1", "recall_layer")


def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def has_marker(text: str) -> bool:
    return any(marker in text for marker in MARKERS)


def main() -> None:
    db = os.path.expanduser("~/.forget/forget.sqlite3")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    print("[events] event_type 분포 상위 8:")
    rows = conn.execute(
        "SELECT event_type, COUNT(*) FROM events GROUP BY event_type "
        "ORDER BY 2 DESC LIMIT 8").fetchall()
    for event_type, count in rows:
        print(f"   {event_type} x{count}")

    print("[events] SEARCH 이벤트 실존:")
    rows = conn.execute(
        "SELECT event_type, COUNT(*) FROM events "
        "WHERE event_type LIKE '%SEARCH%' GROUP BY event_type").fetchall()
    print(f"   {rows if rows else '없음'}")

    print("[events] 표지 행의 서식지·성질:")
    query = ("SELECT id, event_type, created_at, payload, results FROM events "
             "WHERE payload LIKE ? OR results LIKE ? OR payload LIKE ? OR results LIKE ?")
    args = [f"%{m}%" for m in MARKERS for _ in (0, 1)]
    for rid, event_type, created_at, payload, results in conn.execute(query, args):
        habitat = []
        if payload and has_marker(payload):
            habitat.append("payload")
        if results and has_marker(results):
            habitat.append("results")
        nature = "판별불가"
        try:
            data = json.loads(payload or "null") or {}
            body_fields = {}
            for key in ("text", "messages", "query", "memory", "facts"):
                if data.get(key):
                    body_fields[key] = data[key]
            body_blob = json.dumps(body_fields, ensure_ascii=False)
            nature = ("콘텐츠 인용(본문 필드)" if has_marker(body_blob)
                      else "본문 밖 — 텔레메트리 후보")
        except Exception:
            pass
        print(f"   id={str(rid)[:8]} type={event_type} at={created_at} "
              f"서식지={habitat} 성질={nature}")

    print("[context_traces] 표지 행의 서식지·성질:")
    query = ("SELECT trace_id, created_at, payload FROM context_traces "
             "WHERE payload LIKE ? OR payload LIKE ?")
    for tid, created_at, payload in conn.execute(query, [f"%{m}%" for m in MARKERS]):
        data = json.loads(payload)
        source = data.get("source") or "-"
        query_text = str(data.get("trace_query")
                         or (data.get("search_payload") or {}).get("query") or "")
        in_query = has_marker(query_text)
        rest = json.dumps(
            {k: v for k, v in data.items() if k not in ("trace_query", "search_payload")},
            ensure_ascii=False)
        in_rest = has_marker(rest)
        print(f"   trace={str(tid)[:8]} at={created_at} source={source} "
              f"표지위치: query={in_query} 기타필드={in_rest} qsha8={sha8(query_text)}")

    conn.close()
    print("[끝]")


if __name__ == "__main__":
    main()
