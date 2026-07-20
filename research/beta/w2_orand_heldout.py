"""OR/AND split held-out confirmation on a second embedder (MiniLM cache).

The split was made after seeing bge-small Tier-1 data; this replicates the
two-sign prediction on an independent embedding space. Pre-registered
expectation: disjunctive types show low-r harm > high-r; aggregation types
invert. Single variant, crosstalk p=0.9, k=8.
"""
import json, random
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache-minilm"
qids_all = sorted(p.stem for p in CACHE.glob("*.npz") if not p.stem.startswith("pool"))
caches = {q: np.load(CACHE / f"{q}.npz") for q in qids_all}
ROWS = [json.loads(l) for l in (HERE / "w1_results.jsonl").read_text().splitlines() if l.strip()]
qids = sorted({r["qid"] for r in ROWS})
qtype = {r["qid"]: r["type"] for r in ROWS}

def hit_at(emb, ids, q, ans_idx, k=8):
    seen, cnt = set(), 0
    for i in np.argsort(-(emb @ q)):
        pid = ids[i]
        if pid in seen: continue
        seen.add(pid); cnt += 1
        if pid[0] == "t" and pid[1] in ans_idx: return True
        if cnt == k: break
    return False

res = {}
for n_i, qid in enumerate(qids, 1):
    c = caches[qid]; q = c["q_emb"]
    ans_idx = {i for i in range(len(c["turn_ans"])) if c["turn_ans"][i]}
    if not ans_idx: continue
    n = len(c["turn_emb"]); m = 9 * n
    rng = random.Random(f"{qid}|crosstalk|0.9")
    donors = [x for x in qids_all if x != qid]; rng.shuffle(donors)
    cont, got = [], 0
    for d in donors:
        if got >= m: break
        cont.append(caches[d]["turn_emb"]); got += len(caches[d]["turn_emb"])
    cont_emb = np.concatenate(cont)[:m]
    emb = np.concatenate([c["turn_emb"], cont_emb])
    ids = [("t", i) for i in range(n)] + [("j", i) for i in range(len(cont_emb))]
    ids0 = [("t", i) for i in range(n)]
    res[qid] = {"r": len(ans_idx),
                "h0": hit_at(c["turn_emb"], ids0, q, ans_idx),
                "h1": hit_at(emb, ids, q, ans_idx)}
    if n_i % 100 == 0: print(f"[{n_i}/{len(qids)}]", flush=True)

groups = {"disjunctive": {"single-session-user","single-session-assistant","single-session-preference","knowledge-update"},
          "aggregation": {"multi-session","temporal-reasoning"}}
print("\n═ OR/AND held-out (MiniLM, crosstalk p=0.9, k=8) ═")
for gname, types in groups.items():
    qs = [q for q in res if qtype[q] in types]
    rs = sorted(res[q]["r"] for q in qs); med = rs[len(rs)//2]
    lo = [q for q in qs if res[q]["r"] <= med]; hi = [q for q in qs if res[q]["r"] > med]
    def harm(ql): return np.mean([int(res[q]["h0"]) - int(res[q]["h1"]) for q in ql]) * 100
    print(f"  {gname}: 저r(n={len(lo)}) {harm(lo):.1f}pp vs 고r(n={len(hi)}) {harm(hi):.1f}pp (r중위 {med})")
