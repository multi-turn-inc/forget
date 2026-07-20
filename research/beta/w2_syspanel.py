"""β W2 — cross-system panel (C5): rank stability clean vs contaminated.

Each system ingests the recipient's real turns plus crosstalk contaminants
through its OWN write path, then retrieves for the query. Because extractive
systems (Mem0) store derived facts without turn provenance, they are scored at
Tier 2 (QA) only; the reference engine is scored at both tiers. This asymmetry
is the paper's provenance finding, measured.

Cost-bounded: 40 stratified instances x {p=0, p=0.9} x {k=8} per system.
Contaminant stream is the SAME seeded crosstalk as the sweep.

    python research/beta/w2_syspanel.py --system mem0
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import DATASETS, READER_SYS_V3, judge, read_answer  # noqa: E402
from openai import OpenAI

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
DATA = {d["question_id"]: d for d in json.loads(DATASETS["s"].read_text())}
ROWS = [json.loads(l) for l in (HERE / "w1_results.jsonl").read_text().splitlines() if l.strip()]
QTYPE = {r["qid"]: r["type"] for r in ROWS}
qids_all = sorted(p.stem for p in CACHE.glob("*.npz") if not p.stem.startswith("pool"))
K = 8


def recipient_turns(qid):
    inst = DATA[qid]
    return [f"{t['role']}: {t['content']}"
            for s in inst["haystack_sessions"] for t in s
            if "role" in t and "content" in t]


def crosstalk_turns(qid, m, rng):
    donors = [x for x in qids_all if x != qid]
    rng.shuffle(donors)
    out = []
    for d in donors:
        out += recipient_turns(d)
        if len(out) >= m:
            break
    return out[:m]


SESSION_CAP = 12  # cost bound: cap recipient sessions (answer sessions kept)


def build_stream(qid, p, rng):
    """Timestamp-ordered (recipient turn, is_evidence) + contaminants, shuffled.
    Recipient sessions are capped (answer sessions always retained) to bound
    extractive-system ingest cost; the cap is applied identically to every
    panel system and to both conditions, and is disclosed."""
    inst = DATA[qid]
    ans_ids = set(inst["answer_session_ids"])
    idx = list(range(len(inst["haystack_sessions"])))
    keep = [i for i in idx if inst["haystack_session_ids"][i] in ans_ids]
    rest = [i for i in idx if inst["haystack_session_ids"][i] not in ans_ids]
    rng.shuffle(rest)
    keep_set = set(keep + rest[: max(0, SESSION_CAP - len(keep))])
    turns = []
    for si, s in enumerate(inst["haystack_sessions"]):
        if si not in keep_set:
            continue
        for t in s:
            if "role" in t and "content" in t:
                turns.append((f"{t['role']}: {t['content']}", bool(t.get("has_answer"))))
    if p > 0:
        m = round(p / (1 - p) * len(turns))
        for c in crosstalk_turns(qid, m, rng):
            turns.append((c, False))
    rng.shuffle(turns)
    return turns, inst["question"], inst.get("question_date", "")


def run_mem0(sample):
    from mem0 import Memory
    oai = OpenAI()
    cfg = {"embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
           "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
           "vector_store": {"provider": "qdrant", "config": {"on_disk": False}}}
    m = Memory.from_config(cfg)  # one client; user_id scopes isolate stores
    out = []
    for i, qid in enumerate(sample, 1):
        for p in (0.0, 0.9):
            rng = random.Random(f"{qid}|crosstalk|0.9")
            stream, question, qdate = build_stream(qid, p, rng)
            scope = f"beta-{qid}-{int(p*10)}"
            # ingest through Mem0's extractive write path, batched (~10 turns
            # per extraction call) to bound cost; batching is disclosed and
            # applies identically to clean and contaminated conditions.
            batch = []
            for text, _ev in stream:
                batch.append({"role": "user", "content": text})
                if len(batch) >= 10:
                    try:
                        m.add(batch, user_id=scope)
                    except Exception:  # noqa
                        pass
                    batch = []
            if batch:
                try:
                    m.add(batch, user_id=scope)
                except Exception:  # noqa
                    pass
            try:
                res = m.search(question, filters={"user_id": scope}, top_k=K)
                mems = [{"memory": r["memory"], "created_at": qdate}
                        for r in (res.get("results") or res)]
            except Exception:  # noqa
                mems = []
            hyp = read_answer(oai, "gpt-4o", question, qdate, mems, two_stage=True,
                              reader_sys=READER_SYS_V3)
            correct = judge(oai, "gpt-4o", DATA[qid], hyp)
            out.append({"system": "mem0", "qid": qid, "type": QTYPE[qid], "p": p,
                        "k": K, "n_retrieved": len(mems), "correct": correct})
        if i % 5 == 0:
            (HERE / "w2_syspanel.jsonl").open("a").write(
                "\n".join(json.dumps(r) for r in out[-10:]) + "\n")
            print(f"[{i}/{len(sample)}]", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="mem0")
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()
    rng = random.Random(30)
    from collections import defaultdict
    by = defaultdict(list)
    for q in sorted({r["qid"] for r in ROWS}):
        by[QTYPE[q]].append(q)
    sample = []
    per = args.n // len(by)
    for qs in by.values():
        rng.shuffle(qs)
        sample += qs[:per]
    print(f"panel sample: {len(sample)} · system={args.system}", flush=True)
    if args.system == "mem0":
        run_mem0(sample)
    print("done", flush=True)


if __name__ == "__main__":
    main()
