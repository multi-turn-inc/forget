#!/usr/bin/env python3
"""c92 보조 — 쓰기 형태 확인 (읽기 전용).

왜 필요한가. c92의 `add_memory` 응답이 `memories_created: 9`를 돌려줬다 — 한 텍스트가
9개 사실로 쪼개졌다. 그런데 관측 48은 얼어붙음의 절반을 "루프의 쓰기 문체(길이)"에
귀속했다. 만약 쪼개기가 서버 거동이고 초기 8월 행들이 통째로 저장된 것이라면,
귀속의 정확한 이름은 '문체'가 아니라 **추출 거동**이다. 공표한 귀속을 스스로 검사한다.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "hooks"))

import forget_turnrecall as hook  # noqa: E402
from forget_project import layered_filter  # noqa: E402


def rows_for(needle: str, query: str, top_k: int = 60):
    flt = {"AND": [layered_filter("forget"), {"memory": {"icontains": needle}}]}
    result = hook._rpc("search_memories",
                       {"query": query, "top_k": top_k, "recall": "low", "filters": flt},
                       timeout=30)
    return result.get("results") or []


def report(title: str, rows: list) -> None:
    print(f"\n[{title}] {len(rows)}건")
    for r in sorted(rows, key=lambda x: str(x.get("created_at") or "")):
        text = str(r.get("memory") or "")
        print(f"  {str(r.get('created_at'))[:19]} len={len(text):<5} {text[:78]}")
    if rows:
        lens = [len(str(r.get("memory") or "")) for r in rows]
        print(f"  → len 최소 {min(lens)} / 최대 {max(lens)} / 합 {sum(lens)}")


def main():
    report("c92가 방금 쓴 행 (사이클 92)", rows_for("사이클 92", "devloop 사이클 92 진단"))
    report("대조 — c91이 쓴 행", rows_for("사이클 91 결정", "devloop 사이클 91"))
    report("대조 — 트리오 원본 (c43)", rows_for("사이클 43 발견", "devloop 사이클 43 발견"))


if __name__ == "__main__":
    main()
