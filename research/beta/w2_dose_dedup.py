"""β W2 — (A) donor-stratified dose-response (causal margin manipulation)
        (B) dedup cause accounting (review point 6).

A: donors ranked by top similarity to the recipient query; contaminate at
p=0.9 from near/mid/far donor terciles; measure hit@k. If the margin law is
causal, harm(near) >> harm(far) with the tercile mean-similarity as dose.

B: reproduce the dedup arm recording WHAT it deleted: evidence-copy
false-positive rate (deleted items that were evidence) and evidence loss.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
KS = (4, 8, 16, 42)
DEDUP_T = 0.92

qids_all = sorted(p.stem for p in CACHE.glob("*.npz") if not p.stem.startswith("pool"))
caches = {q: np.load(CACHE / f"{q}.npz") for q in qids_all}
ROWS = [json.loads(l) for l in (HERE / "w1_results.jsonl").read_text().splitlines() if l.strip()]
qids = sorted({r["qid"] for r in ROWS})  # _abs 제외된 470


def deliver_hit(emb, ids, q, ans_idx, k_max=42):
    seen, out = set(), []
    for i in np.argsort(-(emb @ q)):
        pid = ids[i]
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
            if len(out) == k_max:
                break
    res = {}
    for k in KS:
        top = out[:k]
        hits = {p[1] for p in top if p[0] == "t" and p[1] in ans_idx}
        res[f"k{k}"] = {"hit": bool(hits), "recall": len(hits) / len(ans_idx)}
    return res


def main() -> None:
    # ── A: 용량-반응 ──────────────────────────────────────────────
    out_a = []
    for n_i, qid in enumerate(qids, 1):
        c = caches[qid]
        q = c["q_emb"]
        ans_idx = {i for i in range(len(c["turn_ans"])) if c["turn_ans"][i]}
        if not ans_idx:
            continue
        donors = [d for d in qids_all if d != qid]
        top_sim = {d: float((caches[d]["turn_emb"] @ q).max()) for d in donors}
        ranked = sorted(donors, key=lambda d: -top_sim[d])
        t = len(ranked) // 3
        terciles = {"near": ranked[:t], "mid": ranked[t:2 * t], "far": ranked[2 * t:]}
        n_turns = len(c["turn_emb"])
        m = 9 * n_turns
        base_ids = [("t", i) for i in range(n_turns)]
        for name, pool in terciles.items():
            rng = random.Random(f"{qid}|dose|{name}")
            order = pool[:]
            rng.shuffle(order)
            cont, got = [], 0
            for d in order:
                if got >= m:
                    break
                cont.append(caches[d]["turn_emb"])
                got += len(caches[d]["turn_emb"])
            cont_emb = np.concatenate(cont)[:m]
            emb = np.concatenate([c["turn_emb"], cont_emb])
            ids = base_ids + [("j", i) for i in range(len(cont_emb))]
            res = deliver_hit(emb, ids, q, ans_idx)
            dose = float(np.mean([top_sim[d] for d in order[:len(cont)]]))
            out_a.append({"qid": qid, "tercile": name, "dose": dose, **res})
        if n_i % 50 == 0:
            print(f"A [{n_i}/{len(qids)}]", flush=True)
    (HERE / "w2_dose.jsonl").write_text("\n".join(json.dumps(r) for r in out_a))

    # 집계
    print("\n═ A: 용량-반응 (p=0.9, single) ═")
    base = {}
    for r in ROWS:
        if r["variant"] == "single" and r["family"] == "none":
            base[r["qid"]] = r
    for name in ("near", "mid", "far"):
        rows = [r for r in out_a if r["tercile"] == name]
        dose = np.mean([r["dose"] for r in rows])
        line = f"  {name:>4} (dose={dose:.3f}): "
        for k in KS:
            h0 = np.mean([base[r["qid"]][f"k{k}"]["hit"] for r in rows])
            h1 = np.mean([r[f"k{k}"]["hit"] for r in rows])
            line += f"k{k} {100*(h0-h1):.1f}pp  "
        print(line, flush=True)

    # ── B: dedup 원인 회계 ────────────────────────────────────────
    print("\n═ B: dedup 회계 ═")
    for fam, p in (("none", 0.0), ("crosstalk", 0.9)):
        tot_removed = tot_removed_ev = tot_ev = 0
        ev_cov_lost = []
        for qid in qids[:200]:  # 회계는 200 서브샘플로 충분 (선등록 명시)
            c = caches[qid]
            n_turns = len(c["turn_emb"])
            ans = c["turn_ans"]
            if p == 0:
                emb = c["turn_emb"]
                is_ev = list(ans)
            else:
                m = 9 * n_turns
                rng = random.Random(f"{qid}|crosstalk|{p}")
                donors = [x for x in qids_all if x != qid]
                rng.shuffle(donors)
                cont, got = [], 0
                for d in donors:
                    if got >= m:
                        break
                    cont.append(caches[d]["turn_emb"])
                    got += len(caches[d]["turn_emb"])
                cont_emb = np.concatenate(cont)[:m]
                emb = np.concatenate([c["turn_emb"], cont_emb])
                is_ev = list(ans) + [False] * len(cont_emb)
            order = list(range(len(emb)))
            random.Random(f"{qid}|dedup").shuffle(order)
            kept = np.zeros(len(emb), dtype=bool)
            kept_rows = []
            for i in order:
                if not kept_rows:
                    kept[i] = True
                    kept_rows.append(emb[i])
                    continue
                if (np.stack(kept_rows) @ emb[i]).max() < DEDUP_T:
                    kept[i] = True
                    kept_rows.append(emb[i])
            removed = ~kept
            n_ev = int(ans.sum())
            tot_removed += int(removed.sum())
            tot_removed_ev += int(sum(1 for i in range(len(emb)) if removed[i] and is_ev[i]))
            tot_ev += n_ev
            lost = sum(1 for i in range(n_turns) if removed[i] and ans[i])
            ev_cov_lost.append(lost / n_ev if n_ev else 0)
        print(f"  {fam} p={p}: 삭제 {tot_removed}개 중 증거 {tot_removed_ev} "
              f"(FP율 {tot_removed_ev/tot_removed*100:.2f}%) · "
              f"증거 손실률 {tot_removed_ev/tot_ev*100:.1f}% · "
              f"질의당 평균 증거손실 {np.mean(ev_cov_lost)*100:.1f}%", flush=True)


if __name__ == "__main__":
    main()
