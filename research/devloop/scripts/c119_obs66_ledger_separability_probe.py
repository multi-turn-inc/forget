#!/usr/bin/env python3
"""c119 · 관측 66 수용 기준 ② — 필드 발생률 계상 가능성 판정 (읽기 전용).

질문: 기존 영속 기록(훅 게이트 원장 · 서버 events · context_traces)에서
gate-v2(fallback→v1) 폴백 층을 사후 분리할 수 있는가?

설계 제약 (관측 37 승계): 질의/프롬프트 원문을 인쇄하지 않는다 — 키·건수·sha8만.
실DB는 sqlite URI mode=ro로만 연다 — 쓰기 원천 차단 (원칙 4 정신, 검색 읽기 전용 선례).
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter

HOME = os.path.expanduser("~")
LEDGER = os.path.join(HOME, ".forget", "hooks", "state", "turnrecall_gate.jsonl")
DBS = [os.path.join(HOME, ".forget", name) for name in ("mem1.sqlite3", "forget.sqlite3")]


def probe_ledger() -> None:
    print("[A] 훅 게이트 원장 —", LEDGER.replace(HOME, "~"))
    if not os.path.exists(LEDGER):
        print("    부재")
        return
    keysets: Counter = Counter()
    high_actions: Counter = Counter()
    layer_mentions = 0
    total = 0
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            total += 1
            if "recall_layer" in line or "fallback" in line:
                layer_mentions += 1
            try:
                row = json.loads(line)
            except Exception:
                continue
            keysets[tuple(sorted(row.keys()))] += 1
            if row.get("gear") == "high":
                high_actions[str(row.get("action"))] += 1
    print(f"    행 {total} · 키셋 {len(keysets)}종: " + " | ".join(
        f"{','.join(ks)} ×{n}" for ks, n in keysets.most_common()))
    print(f"    gear=high action 분포: {dict(high_actions)}")
    print(f"    recall_layer/fallback 문자열 포함 행: {layer_mentions}")
    answered = high_actions.get("injected", 0) + high_actions.get("silent_scores", 0)
    print(f"    → 분모(서버 응답 도달 high 행) = {answered}, 폴백 분자 분리 가능 키 = 없음")


def probe_db(path: str) -> None:
    short = path.replace(HOME, "~")
    print(f"[B] 실DB(읽기 전용) — {short}")
    if not os.path.exists(path):
        print("    부재")
        return
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for table, where_col in (("context_traces", "payload"), ("events", None)):
            if table not in tables:
                print(f"    {table}: 테이블 없음")
                continue
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"    {table}: {n}행")
            if table == "context_traces":
                src = Counter()
                topk = Counter()
                marker = 0
                for (payload,) in conn.execute("SELECT payload FROM context_traces"):
                    text = payload or ""
                    if "fallback→v1" in text or "recall_layer" in text:
                        marker += 1
                    try:
                        data = json.loads(text)
                    except Exception:
                        continue
                    src[str(data.get("source") or "-")] += 1
                    sp = data.get("search_payload") or {}
                    if data.get("source") == "turn_recall":
                        topk[sp.get("top_k")] += 1
                print(f"      source 분포: {dict(src)}")
                print(f"      turn_recall 행의 top_k 분포(기어 서명): {dict(topk)}")
                print(f"      recall_layer/fallback→v1 표지 포함 행: {marker}")
            else:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(events)")]
                probe_cols = [c for c in cols if c.lower() in
                              {"payload", "result", "type", "operation", "name", "kind"}]
                marker = 0
                search_n = 0
                for row in conn.execute(
                        "SELECT " + ", ".join(probe_cols) + " FROM events"):
                    joined = " ".join(str(v) for v in row if v)
                    if "SEARCH" in joined:
                        search_n += 1
                    if "fallback→v1" in joined or "recall_layer" in joined:
                        marker += 1
                print(f"      열 {cols} · SEARCH류 행 {search_n} · 폴백 표지 포함 행 {marker}")
    finally:
        conn.close()


if __name__ == "__main__":
    probe_ledger()
    for db in DBS:
        probe_db(db)
    print("[판정 재료 끝 — 해석은 frictions.md 처분 문단에]")
    sys.exit(0)
