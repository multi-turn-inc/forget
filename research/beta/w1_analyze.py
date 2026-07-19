"""β W1 — preliminary readout of the Tier-1 sweep against C1–C4.

Descriptive surfaces + paired sign tests (full cluster-robust GLM reserved
for the paper analysis pass).
"""
from __future__ import annotations

import json
from collections import defaultdict
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROWS = [json.loads(l) for l in (HERE / "w1_results.jsonl").read_text().splitlines() if l.strip()]
KS = (4, 8, 16, 42)


def cell(variant, family, p):
    return {r["qid"]: r for r in ROWS if r["variant"] == variant
            and r["family"] == family and r["p"] == p}


def hit_rate(rows, k):
    vals = [r[f"k{k}"]["hit"] for r in rows.values()]
    return sum(vals) / len(vals) if vals else float("nan")


def sign_test(base, treat, k):
    common = set(base) & set(treat)
    w = sum(1 for q in common if treat[q][f"k{k}"]["hit"] and not base[q][f"k{k}"]["hit"])
    l = sum(1 for q in common if base[q][f"k{k}"]["hit"] and not treat[q][f"k{k}"]["hit"])
    n = w + l
    p = sum(comb(n, i) for i in range(0, min(w, l) + 1)) / 2 ** n * 2 if n else 1.0
    return w, l, min(p, 1.0)


print("=" * 72)
print("C1 — 해악 곡면 H(p,k) = hit(0,k) − hit(p,k)  [variant=single]")
print("=" * 72)
for fam in ("crosstalk", "organic", "synthetic"):
    base = {p: cell("single", "none", 0.0) for p in [0]}[0]
    print(f"\n  {fam}:")
    print(f"    {'p':>5} " + " ".join(f"k={k:>2}" for k in KS))
    for p in (0.3, 0.6, 0.9):
        c = cell("single", fam, p)
        harms = [hit_rate(base, k) - hit_rate(c, k) for k in KS]
        print(f"    {p:>5} " + " ".join(f"{h*100:>4.1f}" for h in harms))

print("\nC1 판정용: crosstalk p=0.9에서 H(k=4) − H(k=42) =", end=" ")
b, c = cell("single", "none", 0.0), cell("single", "crosstalk", 0.9)
gap4 = hit_rate(b, 4) - hit_rate(c, 4)
gap42 = hit_rate(b, 42) - hit_rate(c, 42)
print(f"{(gap4-gap42)*100:.1f}pp  (기준 ≥15pp)")

print("\n" + "=" * 72)
print("C2 — r-사분위 층화  [single, crosstalk, p=0.9, k=8]")
print("=" * 72)
c = cell("single", "crosstalk", 0.9)
b = cell("single", "none", 0.0)
rs = sorted(r["r"] for r in c.values())
qcut = [rs[len(rs) // 4], rs[len(rs) // 2], rs[3 * len(rs) // 4]]
buckets = defaultdict(list)
for qid, r in c.items():
    quart = sum(r["r"] > t for t in qcut)
    harm = int(b[qid]["k8"]["hit"]) - int(r["k8"]["hit"])
    buckets[quart].append(harm)
for quart in sorted(buckets):
    v = buckets[quart]
    print(f"  r-사분위 {quart+1} (n={len(v)}): 평균 해악 {sum(v)/len(v)*100:.1f}pp")

print("\n" + "=" * 72)
print("C3 — dedup 역설  [dual vs dedup]")
print("=" * 72)
for fam, p in (("none", 0.0), ("crosstalk", 0.9), ("organic", 0.9), ("synthetic", 0.9)):
    du, de = cell("dual", fam, p), cell("dedup", fam, p)
    for k in (8, 42):
        d_hit, e_hit = hit_rate(du, k), hit_rate(de, k)
        w, l, pv = sign_test(de, du, k)  # dual wins = dedup의 손실
        print(f"  {fam:>9} p={p} k={k:>2}: dual {d_hit:.3f} vs dedup {e_hit:.3f} "
              f"(Δ{(d_hit-e_hit)*100:+.1f}pp, dual승 {w}/패 {l}, p={pv:.4f})")

print("\n" + "=" * 72)
print("C4 — 계열 대비  [single, p=0.9]")
print("=" * 72)
for k in (4, 8, 42):
    row = []
    for fam in ("crosstalk", "organic", "synthetic"):
        h = hit_rate(b, k) - hit_rate(cell("single", fam, 0.9), k)
        row.append(f"{fam} {h*100:.1f}pp")
    print(f"  k={k:>2}: " + " · ".join(row))

print("\n" + "=" * 72)
print("보조 — dual vs single (오염 하 듀얼 이득), strict 기준")
print("=" * 72)
for fam, p in (("none", 0.0), ("crosstalk", 0.9)):
    s, d = cell("single", fam, p), cell("dual", fam, p)
    for k in (8, 42):
        print(f"  {fam:>9} p={p} k={k:>2}: single {hit_rate(s,k):.3f} vs dual {hit_rate(d,k):.3f}")
