"""Review point 1+2 — make distributional proximity a measurement.

(a) Family-level: cosine similarity distributions of each contamination
    family's items to recipient queries.
(b) Per-query: reproduce each recipient's actual crosstalk donor set (same
    seeded RNG as the sweep) and regress harm on mean donor similarity.
(c) Headroom (review point 4): report M(0,k) baselines and relative harm.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
ROWS = [json.loads(l) for l in (HERE / "w1_results.jsonl").read_text().splitlines() if l.strip()]


def cell(v, f, p):
    return {r["qid"]: r for r in ROWS if r["variant"] == v and r["family"] == f and r["p"] == p}


qids = sorted({r["qid"] for r in ROWS})
caches = {q: np.load(CACHE / f"{q}.npz") for q in qids}
pools = {n: np.load(CACHE / f"pool_{n}.npz")["emb"] for n in ("synthetic", "organic")}

print("=" * 70)
print("(a) 계열별 질의 대비 유사도 분포 (전 질의 평균)")
print("=" * 70)
rng = random.Random(0)
sample_q = rng.sample(qids, 100)
for fam in ("synthetic", "organic"):
    sims = []
    for q in sample_q:
        qv = caches[q]["q_emb"]
        s = pools[fam] @ qv
        sims.append([np.mean(s), np.percentile(s, 95), np.max(s)])
    m = np.mean(sims, axis=0)
    print(f"  {fam:>10}: mean {m[0]:.3f} · p95 {m[1]:.3f} · max {m[2]:.3f}")
# crosstalk: donor turns (다른 인스턴스 턴)
sims = []
for q in sample_q:
    qv = caches[q]["q_emb"]
    donors = rng.sample([x for x in qids if x != q], 8)
    s = np.concatenate([caches[d]["turn_emb"] @ qv for d in donors])
    sims.append([np.mean(s), np.percentile(s, 95), np.max(s)])
m = np.mean(sims, axis=0)
print(f"  {'crosstalk':>10}: mean {m[0]:.3f} · p95 {m[1]:.3f} · max {m[2]:.3f}")
# 자기 스토어(증거의 경쟁 상대) 참조점
sims = [np.mean(caches[q]["turn_emb"] @ caches[q]["q_emb"]) for q in sample_q]
print(f"  {'(자기 턴)':>10}: mean {np.mean(sims):.3f}  ← 증거가 사는 유사도 대역")

print()
print("=" * 70)
print("(b) per-query harm ~ donor 유사도 (crosstalk p=0.9, k=8, single)")
print("=" * 70)
b, c = cell("single", "none", 0.0), cell("single", "crosstalk", 0.9)
xs, ys = [], []
for qid in c:
    cch = caches[qid]
    n_turns = len(cch["turn_emb"])
    m_need = round(0.9 / 0.1 * n_turns)
    r = random.Random(f"{qid}|crosstalk|0.9")
    donors = [x for x in qids if x != qid]  # 스윕과 동일 재현
    # 주의: 스윕은 caches 전체 키(500) 기준 셔플 — 동일 목록 재구성
    all_qids = sorted(caches.keys())
    donors = [x for x in all_qids if x != qid]
    r.shuffle(donors)
    got, sel = 0, []
    for d in donors:
        if got >= m_need:
            break
        sel.append(d)
        got += len(caches[d]["turn_emb"])
    qv = cch["q_emb"]
    top_sims = []
    for d in sel:
        s = caches[d]["turn_emb"] @ qv
        top_sims.append(np.sort(s)[-8:])  # 경쟁은 상위 항목이 결정
    donor_top = float(np.mean(np.sort(np.concatenate(top_sims))[-8:]))
    harm = int(b[qid]["k8"]["hit"]) - int(c[qid]["k8"]["hit"])
    xs.append(donor_top)
    ys.append(harm)
xs, ys = np.array(xs), np.array(ys)
med = np.median(xs)
lo, hi = ys[xs <= med], ys[xs > med]
print(f"  donor top-유사도 저(n={len(lo)}): harm {lo.mean()*100:.1f}pp")
print(f"  donor top-유사도 고(n={len(hi)}): harm {hi.mean()*100:.1f}pp")
rho = np.corrcoef(xs, ys)[0, 1]
print(f"  point-biserial 상관: {rho:.3f}")

print()
print("=" * 70)
print("(c) headroom: M(0,k) 기저와 상대 harm (crosstalk p=0.9)")
print("=" * 70)
for k in (4, 8, 16, 42):
    m0 = np.mean([r[f"k{k}"]["hit"] for r in b.values()])
    m9 = np.mean([r[f"k{k}"]["hit"] for r in c.values()])
    rel = (m0 - m9) / m0 * 100
    err_ratio = (1 - m9) / (1 - m0) if m0 < 1 else float("inf")
    print(f"  k={k:>2}: M(0)={m0:.3f} M(0.9)={m9:.3f} · 절대 {100*(m0-m9):.1f}pp · "
          f"상대 {rel:.1f}% · 오류배율 ×{err_ratio:.2f}")
