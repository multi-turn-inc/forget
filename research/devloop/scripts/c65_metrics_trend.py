#!/usr/bin/env python3
"""사이클 65 계측 — 회고의 입력인 **지표 추세**를 원장 전문(全文) 없이 뜬다 (읽기 전용).

왜 스크립트인가. metrics.jsonl은 65행 323KB이고 그 대부분이 산문 note다. 회고가
요구하는 것(LOOP.md '개선 절차': 지표 추세)은 그 산문이 아니라 **수치 열**이다.
전문을 컨텍스트에 올리면 회고가 자기 원장을 읽느라 예산을 다 쓰고, 무엇보다
c48_step0_check.py가 금지한 tail/cat/head 습관의 우회로가 된다. 그래서 열만 뽑는다.

계보(사이클 27 마찰 '코퍼스 선정법 미기록'): 회고가 인용하는 숫자는 재현 절차와 함께
커밋되어야 한다. 이 파일이 그 절차다 — 다음 회고(c70)가 같은 명령으로 같은 표를 얻는다.

**이 스크립트는 번호 결정에 쓰지 않는다.** 번호·모드의 정본은 c48_step0_check.py다.
"""

from __future__ import annotations

import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

# 회고가 추세를 보는 열. note류(산문)는 의도적으로 제외한다.
COLS = ["cycle", "date", "restore_turns", "restore_grade",
        "recall_hits", "recall_misses", "frictions_logged", "frictions_fixed", "tests"]


def main() -> None:
    rows = []
    keysets: dict[frozenset, list[int]] = {}
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append(obj)
            keysets.setdefault(frozenset(obj.keys()), []).append(obj.get("cycle"))

    rows.sort(key=lambda r: r.get("cycle", -1))
    print(f"[원장] rows={len(rows)}  path={os.path.relpath(LEDGER, REPO)}")

    head = "  ".join(f"{c:>16s}" if c == "restore_grade" else f"{c:>10s}" for c in COLS)
    print(head)
    for r in rows:
        cells = []
        for c in COLS:
            v = r.get(c, "—")
            cells.append(f"{str(v):>16s}" if c == "restore_grade" else f"{str(v):>10s}")
        print("  ".join(cells))

    # 스키마 표류 — 어떤 사이클이 어떤 키셋을 썼는지. 열 추가/삭제는 자[尺] 변경이다.
    print(f"\n[스키마 표류] 서로 다른 키셋 {len(keysets)}종")
    base = None
    for ks, cycles in sorted(keysets.items(), key=lambda kv: min(c for c in kv[1] if c is not None)):
        span = f"c{min(cycles)}~c{max(cycles)}" if len(cycles) > 1 else f"c{cycles[0]}"
        if base is None:
            base = ks
            print(f"  {span:12s} n={len(cycles):2d}  기준 키셋 {len(ks)}개: {sorted(ks)}")
        else:
            print(f"  {span:12s} n={len(cycles):2d}  +{sorted(ks - base)}  -{sorted(base - ks)}")

    # 추세 요약 — 결론 문장은 인쇄하지 않는다(c48 규약). 숫자만.
    def series(col: str) -> list[tuple[int, object]]:
        return [(r["cycle"], r.get(col)) for r in rows if r.get(col) is not None]

    print("\n[추세 — 최근 15사이클]")
    for col in ("restore_turns", "recall_hits", "recall_misses", "frictions_logged",
                "frictions_fixed", "tests"):
        s = series(col)[-15:]
        print(f"  {col:18s} " + " ".join(f"{v}" for _, v in s))

    grades: dict[str, int] = {}
    for _, g in series("restore_grade"):
        grades[str(g)] = grades.get(str(g), 0) + 1
    print(f"  restore_grade 전기간 분포: {dict(sorted(grades.items(), key=lambda kv: -kv[1]))}")

    turns = [v for _, v in series("restore_turns") if isinstance(v, (int, float))]
    if turns:
        uniq = sorted(set(turns))
        print(f"  restore_turns 전기간: n={len(turns)} 값역={uniq} "
              f"평균={sum(turns) / len(turns):.2f} 최근10평균={sum(turns[-10:]) / len(turns[-10:]):.2f}")


def notes(which: list[int]) -> None:
    """지정 사이클의 restore_note만 인쇄 — `restore_turns`가 무엇을 세었는지 대조용.

    c65 회고의 핵심 질문(같은 '1'과 같은 '4'가 같은 자로 재어졌는가)은 수치 열로는
    답이 안 나온다. 그 턴에 무슨 일이 있었는지는 note에만 있다. 전문 정독을 피하려고
    사이클을 지정해 뽑는다.
    """
    with open(LEDGER, encoding="utf-8") as fh:
        rows = [json.loads(ln) for ln in fh if ln.strip()]
    by_cycle = {r.get("cycle"): r for r in rows}
    for c in which:
        r = by_cycle.get(c)
        if r is None:
            print(f"[c{c}] 없음")
            continue
        print(f"\n[c{c}] restore_turns={r.get('restore_turns')} "
              f"grade={r.get('restore_grade')}\n  {r.get('restore_note', '—')}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--notes":
        notes([int(x) for x in sys.argv[2].split(",")])
    else:
        main()
