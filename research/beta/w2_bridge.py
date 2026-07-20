"""β W2 — Tier-2 bridge: does retrieval harm propagate to answer harm?

Cells: {p=0, p=0.9 crosstalk} x {k=8, k=42} x {single, dual} on a stratified
200-query subsample. The delivery set for each cell is computed exactly as in
the Tier-1 sweep (same seeded contamination), its payload texts are assembled,
and the frozen two-stage reader + benchmark judge score correctness. Bridge
question: cells with lower evidence-hit should show lower QA accuracy, and the
per-query hit->correct contingency quantifies how much the reader salvages.
Sub-analysis: knowledge-update contamination resistance.
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import DATASETS, READER_SYS_V3, judge, read_answer  # noqa: E402

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
OUT = HERE / "w2_bridge.jsonl"
OBS_DIR = ROOT / "research" / "longmemeval" / "observations"

DATA = {d["question_id"]: d for d in json.loads(DATASETS["s"].read_text())}
ROWS = [json.loads(l) for l in (HERE / "w1_results.jsonl").read_text().splitlines() if l.strip()]
QIDS = sorted({r["qid"] for r in ROWS})
QTYPE = {r["qid"]: r["type"] for r in ROWS}
qids_all = sorted(p.stem for p in CACHE.glob("*.npz") if not p.stem.startswith("pool"))

CELLS = [("none", 0.0, 8), ("none", 0.0, 42), ("crosstalk", 0.9, 8), ("crosstalk", 0.9, 42)]


def texts_for(qid):
    """Reconstruct turn texts and observation bullets, index-aligned to cache."""
    inst = DATA[qid]
    turns = []
    for session in inst["haystack_sessions"]:
        for t in session:
            if "role" in t and "content" in t:
                turns.append(f"{t['role']}: {t['content']}")
    obs = []
    of = OBS_DIR / f"gpt-4o--{qid}.json"
    if of.exists():
        for e in json.loads(of.read_text()):
            for line in e["observations"].splitlines():
                line = line.strip().lstrip("-• ").strip()
                if len(line) > 8:
                    obs.append(line)
    return turns, obs


def donor_texts(qid, n_need, rng):
    """Same seeded donor stream as the sweep, returning texts."""
    donors = [x for x in qids_all if x != qid]
    rng.shuffle(donors)
    out, got = [], 0
    for d in donors:
        dt, _ = texts_for(d)
        for t in dt:
            out.append(t)
        got += len(dt)
        if got >= n_need:
            break
    return out[:n_need]


def deliver_texts(qid, variant, fam, p, k):
    c = np.load(CACHE / f"{qid}.npz")
    turns, obs = texts_for(qid)
    n = len(c["turn_emb"])
    q = c["q_emb"]
    if fam == "none":
        cont_raw_emb = np.zeros((0, c["turn_emb"].shape[1]), np.float32)
        cont_raw_txt = []
        cont_obs_emb = np.zeros((0, c["turn_emb"].shape[1]), np.float32)
        cont_obs_txt = []
    else:
        m = round(p / (1 - p) * n)
        m_obs = round(p / (1 - p) * len(obs))
        rng = random.Random(f"{qid}|crosstalk|0.9")
        donors = [x for x in qids_all if x != qid]
        rng.shuffle(donors)
        raw_e, raw_t, obs_e, obs_t, gr, go = [], [], [], [], 0, 0
        for d in donors:
            dc = np.load(CACHE / f"{d}.npz")
            dt, do = texts_for(d)
            if gr < m:
                raw_e.append(dc["turn_emb"]); raw_t += dt; gr += len(dt)
            if go < m_obs:
                obs_e.append(dc["obs_emb"]); obs_t += do; go += len(do)
            if gr >= m and go >= m_obs:
                break
        cont_raw_emb = np.concatenate(raw_e)[:m] if raw_e else np.zeros((0, 384), np.float32)
        cont_raw_txt = raw_t[:m]
        cont_obs_emb = np.concatenate(obs_e)[:m_obs] if obs_e else np.zeros((0, 384), np.float32)
        cont_obs_txt = obs_t[:m_obs]

    raw_emb = np.concatenate([c["turn_emb"], cont_raw_emb])
    raw_txt = turns + cont_raw_txt
    if variant == "single":
        top = np.argsort(-(raw_emb @ q))[:k]
        return [raw_txt[i] for i in top]
    # dual
    obs_emb = np.concatenate([c["obs_emb"], cont_obs_emb])
    obs_txt = obs + cont_obs_txt
    ko = k // 2; kr = k - ko
    o_top = np.argsort(-(obs_emb @ q))[:ko] if len(obs_emb) else []
    r_top = np.argsort(-(raw_emb @ q))[:kr]
    return [obs_txt[i] for i in o_top] + [raw_txt[i] for i in r_top]


def run(args):
    qid, variant, fam, p, k, oai = args
    inst = DATA[qid]
    payload = deliver_texts(qid, variant, fam, p, k)
    memories = [{"memory": t, "created_at": inst.get("question_date", "")} for t in payload]
    hyp = read_answer(oai, "gpt-4o", inst["question"], inst.get("question_date", ""),
                      memories, two_stage=True, reader_sys=READER_SYS_V3)
    correct = judge(oai, "gpt-4o", inst, hyp)
    return {"qid": qid, "type": QTYPE[qid], "variant": variant,
            "family": fam, "p": p, "k": k, "correct": correct}


def main():
    rng = random.Random(20)
    by_type = defaultdict(list)
    for q in QIDS:
        by_type[QTYPE[q]].append(q)
    sample = []
    per = 200 // len(by_type)
    for t, qs in by_type.items():
        rng.shuffle(qs)
        sample += qs[:per]
    print(f"bridge sample: {len(sample)}", flush=True)
    done = set()
    if OUT.exists():
        for l in OUT.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                done.add((r["qid"], r["variant"], r["family"], r["p"], r["k"]))
    oai = OpenAI()
    jobs = [(q, v, fam, p, k, oai) for q in sample for v in ("single", "dual")
            for (fam, p, k) in CELLS if (q, v, fam, p, k) not in done]
    print(f"jobs: {len(jobs)}", flush=True)
    with OUT.open("a") as f, ThreadPoolExecutor(max_workers=6) as pool:
        for i, res in enumerate(pool.map(lambda a: _safe(run, a), jobs), 1):
            if res:
                f.write(json.dumps(res) + "\n")
            if i % 50 == 0:
                f.flush()
                print(f"[{i}/{len(jobs)}]", flush=True)
    summarize()


def _safe(fn, a):
    for _ in range(3):
        try:
            return fn(a)
        except Exception as e:  # noqa
            time.sleep(3)
    return None


def summarize():
    rows = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()]
    print("\n═ Tier-2 bridge: QA accuracy ═")
    agg = defaultdict(list)
    for r in rows:
        agg[(r["variant"], r["family"], r["p"], r["k"])].append(r["correct"])
    for (v, fam, p, k), vals in sorted(agg.items()):
        print(f"  {v:>6} {fam:>9} p={p} k={k:>2}: {np.mean(vals):.3f} (n={len(vals)})")
    # knowledge-update resistance
    print("\n═ knowledge-update 오염 내성 (single) ═")
    for k in (8, 42):
        c0 = [r["correct"] for r in rows if r["type"] == "knowledge-update"
              and r["variant"] == "single" and r["family"] == "none" and r["k"] == k]
        c9 = [r["correct"] for r in rows if r["type"] == "knowledge-update"
              and r["variant"] == "single" and r["family"] == "crosstalk" and r["k"] == k]
        if c0 and c9:
            print(f"  k={k}: clean {np.mean(c0):.3f} vs contaminated {np.mean(c9):.3f} "
                  f"(Δ{(np.mean(c0)-np.mean(c9))*100:+.1f}pp)")


if __name__ == "__main__":
    main()
