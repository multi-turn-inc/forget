#!/usr/bin/env python3
"""c92 보조 — `filters.memory.icontains`가 실제로 적용되는가 (읽기 전용, 자기 반증용).

왜. c92 §B는 `{"memory": {"icontains": "[devloop]"}}`로 열거해 "'[devloop]' 기억행 123건"을
인쇄했다. 그런데 c92_write_shape_probe의 반환에 `[devloop]`가 없는 task_state 행이 다수
섞여 나왔다 — **필터가 무시되고 있다는 신호**. 공표 직전에 내 숫자를 스스로 검사한다.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "hooks"))

import forget_turnrecall as hook  # noqa: E402
from forget_project import layered_filter  # noqa: E402

NEEDLE = "[devloop]"


def run(label, flt, top_k=200):
    args = {"query": "devloop 사이클 발견 결정", "top_k": top_k, "recall": "low"}
    if flt is not None:
        args["filters"] = flt
    rows = hook._rpc("search_memories", args, timeout=40).get("results") or []
    hit = sum(1 for r in rows if NEEDLE in str(r.get("memory") or ""))
    print(f"  {label:22s} returned={len(rows):<4} 그중 '{NEEDLE}' 포함 = {hit}")
    return rows, hit


def main():
    print("[필터 적용 여부 — 같은 질의, 필터만 다르게]")
    run("필터 없음", None)
    run("icontains 단독", {"memory": {"icontains": NEEDLE}})
    run("AND layered", {"AND": [layered_filter("forget"), {"memory": {"icontains": NEEDLE}}]})
    print("  → 세 줄의 returned가 같으면 icontains는 **무시**된 것이다(§B의 123은 무효).")

    print("\n[신뢰 가능한 계수 — 파이썬측 필터로 깊게 열거]")
    for k in (200, 400):
        args = {"query": "devloop 사이클 발견 결정 판정 선택", "top_k": k, "recall": "low",
                "filters": layered_filter("forget")}
        rows = hook._rpc("search_memories", args, timeout=60).get("results") or []
        dev = [r for r in rows if NEEDLE in str(r.get("memory") or "")]
        elig = [r for r in dev if hook._injection_eligible(r)]
        lens = sorted((len(str(r.get("memory") or "")) for r in dev), reverse=True)
        print(f"  top_k={k:<4} returned={len(rows):<4} '{NEEDLE}' 행={len(dev):<4} "
              f"그중 훅 자격={len(elig):<4} 길이 상위5={lens[:5]}")
    print("  ※ 이 계수도 **질의 의존 상한**이다 — 전수 열거가 아니라 '이 질의로 도달한 수'.")
    print("    정직한 표현: '≥N건 확인' (전수 주장 불가). §B 문면을 이 형태로 정정한다.")


if __name__ == "__main__":
    main()
