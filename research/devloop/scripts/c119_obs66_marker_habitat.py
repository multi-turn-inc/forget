#!/usr/bin/env python3
"""c119 · 관측 66 ② 보조 2 — SEARCH 이벤트 results 내 표지의 정확한 서식지.

marker가 results의 어떤 JSON 경로에 사는가: 기억 본문(content 인용)인가,
독립 텔레메트리 키인가. 원문 무인쇄 — 경로와 건수만.
"""
from __future__ import annotations

import json
import os
import sqlite3

MARKERS = ("fallback→v1", "recall_layer")


def walk(node, path, hits):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in MARKERS or (isinstance(key, str) and any(m in key for m in MARKERS)):
                hits.append((path + "/" + key, "키 자체"))
            walk(value, f"{path}/{key}", hits)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk(value, f"{path}[{i}]", hits)
    elif isinstance(node, str):
        if any(m in node for m in MARKERS):
            hits.append((path, "문자열 값 내부"))


def main() -> None:
    db = os.path.expanduser("~/.forget/forget.sqlite3")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    query = ("SELECT id, event_type, created_at, results FROM events "
             "WHERE event_type = 'SEARCH' AND (results LIKE ? OR results LIKE ?)")
    for rid, event_type, created_at, results in conn.execute(
            query, [f"%{m}%" for m in MARKERS]):
        hits: list = []
        try:
            walk(json.loads(results or "null"), "", hits)
        except Exception:
            hits.append(("<파싱 실패>", "-"))
        # 경로의 배열 첨자를 지워 서식지 유형만 집계
        kinds = sorted({(p.split("[")[0].rsplit("/", 1)[-1] or p, kind) for p, kind in hits})
        print(f"id={str(rid)[:8]} at={created_at} 표지 서식지={kinds}")
    conn.close()


if __name__ == "__main__":
    main()
