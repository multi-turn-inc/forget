#!/usr/bin/env python3
"""c69 — F1 사슬 재현의 **잔여** 불일치를 규명한다 (read-only, $0).

피드백 보정(+0.05 등, breakdown 미노출)을 넣어 F1이 크게 개선됐으나 0이 되지 않았다.
잔여를 '미미하다'로 접지 않는다 — 잔여의 크기·부호·집중을 보고, 남은 보정을 지목한다.
(c67 자기규율: 부재/미미로부터 안전을 추론하지 마라.)

    .venv/bin/python research/devloop/scripts/c69_f1_residual.py
"""
from __future__ import annotations

import collections
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c69 = _load("c69_centering_prototype")
c68 = c69.c68

QUERIES = list(c68.ON_REAL)[:4] + list(c69.FRESH_OFF)[:4]


def main() -> None:
    fb_adj = c69.load_feedback_adjust()
    nonzero = {k: v for k, v in fb_adj.items() if v}
    print(f"피드백 보정: 전체 {len(fb_adj)}행, 0이 아닌 것 {len(nonzero)}행")
    print(f"  보정값 분포: {dict(collections.Counter(round(v, 4) for v in nonzero.values()))}")

    diffs: collections.Counter = collections.Counter()
    bad_rows = []
    total = 0
    for label, q in QUERIES:
        for r in c69.probe_pool(q, c69.POOL_TOP_K):
            total += 1
            best = None
            for fb in (False, True):
                cand = c69.compose_score(
                    r["rule"], r["vector"], entity_boost=r["entity_boost"],
                    keyword=r["keyword"], feedback_adjust=fb_adj.get(r["id"], 0.0),
                    superseded=r["superseded"], session_capture=r["session_capture"],
                    scope_fallback=fb)
                d = r["score"] - cand
                if best is None or abs(d) < abs(best[0]):
                    best = (d, fb)
            d = round(best[0], 4)
            diffs[d] += 1
            if abs(d) > 0.0002:
                bad_rows.append((d, r, fb_adj.get(r["id"], 0.0)))

    ok = sum(n for d, n in diffs.items() if abs(d) <= 0.0002)
    print(f"\n총 {total}행  일치 {ok} ({100.0 * ok / total:.2f}%)  불일치 {total - ok}")
    print("\n관측−재조립 차이 분포 (상위 12):")
    for d, n in diffs.most_common(12):
        tag = "  ← 일치" if abs(d) <= 0.0002 else ""
        print(f"  {d:+.4f}  {n:>5}행{tag}")

    print(f"\n불일치 표본 (최대 8건) — 남은 보정을 지목하기 위해:")
    for d, r, fb in sorted(bad_rows, key=lambda x: -abs(x[0]))[:8]:
        print(f"  차이={d:+.4f}  관측={r['score']:.4f}  rule={r['rule']:.4f} "
              f"vec={r['vector']:.4f} fb={fb:+.2f} sup={r['superseded']} "
              f"cap={r['session_capture']} ent={r['entity_boost']} kw={r['keyword']}")
        print(f"     {r['text'][:76]}")

    if bad_rows:
        signs = collections.Counter("양" if d > 0 else "음" for d, _r, _f in bad_rows)
        print(f"\n  부호 분포: {dict(signs)}")
        print("  (양수만이면 내가 못 넣은 **가산** 보정, 음수만이면 못 넣은 **감산**/곱셈 보정이다.)")
        mags = collections.Counter(round(abs(d), 3) for d, _r, _f in bad_rows)
        print(f"  절대값 분포: {dict(mags.most_common(8))}")


if __name__ == "__main__":
    main()
