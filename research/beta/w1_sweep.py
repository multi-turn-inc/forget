"""β W1 — Tier-1 sweep: variants x families x pressure x budget, judge-free.

Cells: {single, dual, dedup} x ({p=0} + {crosstalk, synthetic[, organic]} x
{0.3, 0.6, 0.9}) x k {4, 8, 16, 42} x 470 queries. Contamination enters BOTH
layers at equal pressure (donor obs -> obs layer for crosstalk; pool items
serve as their own compressed form for synthetic/organic). Dual evidence
credit is reported as strict (turn-only) and session-mapped bounds; within-
pair comparisons share the mapping, so bounds cancel in differences.

    python research/beta/w1_sweep.py [--instances N]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import DATASETS  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "w1_results.jsonl"
KS = (4, 8, 16, 42)
PS = (0.3, 0.6, 0.9)
DEDUP_T = 0.92


def load_all():
    data = json.loads(DATASETS["s"].read_text())
    qids = [d["question_id"] for d in data if "_abs" not in d["question_id"]]
    qtype = {d["question_id"]: d["question_type"] for d in data}
    caches = {}
    for qid in [d["question_id"] for d in data]:
        f = CACHE / f"{qid}.npz"
        if f.exists():
            caches[qid] = np.load(f)
    return qids, qtype, caches


def crosstalk(qid, caches, m, m_obs, rng):
    donors = [q for q in caches if q != qid]
    rng.shuffle(donors)
    raw, obs = [], []
    for d in donors:
        if sum(len(x) for x in raw) < m:
            raw.append(caches[d]["turn_emb"])
        if sum(len(x) for x in obs) < m_obs:
            obs.append(caches[d]["obs_emb"])
        if sum(len(x) for x in raw) >= m and sum(len(x) for x in obs) >= m_obs:
            break
    r = np.concatenate(raw)[:m] if raw else np.zeros((0, 384), np.float32)
    o = np.concatenate(obs)[:m_obs] if obs else np.zeros((0, 384), np.float32)
    return r, o


def pool_sample(pool, m, rng):
    idx = rng.sample(range(len(pool)), min(m, len(pool)))
    return pool[idx]


def greedy_dedup(emb, order):
    """Seeded greedy near-dup removal; returns kept boolean mask."""
    kept = np.zeros(len(emb), dtype=bool)
    kept_rows = []
    for i in order:
        if not kept_rows:
            kept[i] = True
            kept_rows.append(emb[i])
            continue
        sims = np.stack(kept_rows) @ emb[i]
        if sims.max() < DEDUP_T:
            kept[i] = True
            kept_rows.append(emb[i])
    return kept


def deliver(scores, payload_ids, k_max=42):
    seen, order = set(), []
    for i in np.argsort(-scores):
        pid = payload_ids[i]
        if pid not in seen:
            seen.add(pid)
            order.append(pid)
            if len(order) == k_max:
                break
    return order


def measure(order, ans_turn_ids, ans_sess, payload_kind):
    out = {}
    for k in KS:
        top = order[:k]
        strict_hits = [p for p in top if p[0] == "t" and p[1] in ans_turn_ids]
        sess_hits = strict_hits + [p for p in top if p[0] == "o" and p[1] in ans_sess]
        out[f"k{k}"] = {
            "hit": bool(strict_hits), "recall": len({p[1] for p in strict_hits}) / len(ans_turn_ids),
            "hit_sess": bool(sess_hits),
        }
    return out


def run_variant(c, cont_raw, cont_obs, variant, rng):
    q = c["q_emb"]
    t_emb, t_ans, t_sess = c["turn_emb"], c["turn_ans"], c["turn_sess"]
    o_emb, o_sess = c["obs_emb"], c["obs_sess"]
    ans_turn_ids = {i for i in range(len(t_ans)) if t_ans[i]}
    ans_sess = set(c["ans_sess"].tolist())
    if not ans_turn_ids:
        return None

    if variant == "single":
        emb = np.concatenate([t_emb, cont_raw])
        ids = [("t", i) for i in range(len(t_emb))] + [("j", i) for i in range(len(cont_raw))]
        order = deliver(emb @ q, ids)
        return measure(order, ans_turn_ids, ans_sess, ids)

    # dual / dedup: obs layer and raw layer with split budgets
    raw_emb = np.concatenate([t_emb, cont_raw])
    raw_ids = [("t", i) for i in range(len(t_emb))] + [("j", i) for i in range(len(cont_raw))]
    obs_emb = np.concatenate([o_emb, cont_obs])
    obs_ids = [("o", int(o_sess[i])) for i in range(len(o_emb))] + \
              [("jo", i) for i in range(len(cont_obs))]

    if variant == "dedup":
        for emb_arr, ids_name in ((raw_emb, "raw"), ):
            pass  # dedup applied below to raw layer (obs bullets are already unique-ish)
        order_idx = list(range(len(raw_emb)))
        rng.shuffle(order_idx)
        keep = greedy_dedup(raw_emb, order_idx)
        raw_emb = raw_emb[keep]
        raw_ids = [rid for rid, kp in zip(raw_ids, keep) if kp]

    out = {}
    for k in KS:
        ko = k // 2
        kr = k - ko
        obs_top = deliver(obs_emb @ q, obs_ids, ko)
        raw_top = deliver(raw_emb @ q, raw_ids, kr)
        top = obs_top + raw_top
        strict = [p for p in top if p[0] == "t" and p[1] in ans_turn_ids]
        sess = strict + [p for p in top if p[0] == "o" and p[1] in ans_sess]
        out[f"k{k}"] = {"hit": bool(strict),
                        "recall": len({p[1] for p in strict}) / len(ans_turn_ids),
                        "hit_sess": bool(sess)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", type=int, default=0, help="subsample for smoke")
    args = ap.parse_args()
    qids, qtype, caches = load_all()
    if args.instances:
        qids = qids[: args.instances]
    pools = {"synthetic": np.load(CACHE / "pool_synthetic.npz")["emb"]}
    org = CACHE / "pool_organic.npz"
    if org.exists():
        pools["organic"] = np.load(org)["emb"]
    else:
        print("NOTE: organic pool absent — sweep runs crosstalk+synthetic; "
              "rerun after translation for organic cells", flush=True)

    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["qid"], r["variant"], r["family"], r["p"]))

    started = time.time()
    with OUT.open("a") as f:
        for n_i, qid in enumerate(qids, 1):
            c = caches.get(qid)
            if c is None:
                continue
            n_turns = len(c["turn_emb"])
            n_obs = len(c["obs_emb"])
            r_q = int(c["turn_ans"].sum())
            cells = [("none", 0.0)] + [(fam, p) for fam in
                                       (["crosstalk", "synthetic"] + (["organic"] if "organic" in pools else []))
                                       for p in PS]
            for fam, p in cells:
                m = round(p / (1 - p) * n_turns) if p else 0
                m_obs = round(p / (1 - p) * n_obs) if p else 0
                rng = random.Random(f"{qid}|{fam}|{p}")
                if p == 0:
                    cont_raw = np.zeros((0, 384), np.float32)
                    cont_obs = np.zeros((0, 384), np.float32)
                elif fam == "crosstalk":
                    cont_raw, cont_obs = crosstalk(qid, caches, m, m_obs, rng)
                else:
                    cont_raw = pool_sample(pools[fam], m, rng)
                    cont_obs = pool_sample(pools[fam], m_obs, rng)
                for variant in ("single", "dual", "dedup"):
                    if (qid, variant, fam, p) in done:
                        continue
                    res = run_variant(c, cont_raw, cont_obs, variant, random.Random(f"{qid}|{variant}|{fam}|{p}"))
                    if res is None:
                        continue
                    f.write(json.dumps({"qid": qid, "type": qtype[qid], "r": r_q,
                                        "variant": variant, "family": fam, "p": p, **res}) + "\n")
            if n_i % 20 == 0:
                f.flush()
                el = (time.time() - started) / 60
                print(f"[{n_i}/{len(qids)}] {el:.0f}m", flush=True)
    print("sweep complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
