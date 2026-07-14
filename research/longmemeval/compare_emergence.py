"""Reproduce Emergence Simple-Fast on the EXACT held-out sample our forget
harness scored, for an apples-to-apples comparison.

Emergence method (their main.py, unmodified logic): MiniLM semantic search
over raw dated turns, top_k=42, two-stage reader (extract facts -> answer),
gpt-4o. Judge is the benchmark's own per-type prompt (gpt-4o), same as our
harness — so the only difference vs our 64.3% is the memory+reader method.

    python research/longmemeval/compare_emergence.py --seed 7 --n 42 --held-out
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import DATASETS, dev_ids, judge, stratified_sample  # reuse our judge + sampling
import random

import numpy as np
from openai import OpenAI
from sentence_transformers import SentenceTransformer, util

RETRIEVAL = SentenceTransformer("all-MiniLM-L6-v2")
OAI = OpenAI()
OUT = Path(__file__).resolve().parent / "runs"


def callgpt(messages, model: str, max_tokens: int) -> str:
    for attempt in range(4):
        try:
            r = OAI.chat.completions.create(model=model, messages=messages,
                                            temperature=0.0, max_tokens=max_tokens)
            return r.choices[0].message.content
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def process_haystack(sessions, dates):
    turns = []
    for session, date in zip(sessions, dates):
        for turn in session:
            if "role" in turn and "content" in turn:
                turns.append(f"[{date}] {turn['role']}: {turn['content']}")
    emb = RETRIEVAL.encode(turns, convert_to_tensor=True)
    return emb, turns


def answer(memstruct, question, question_date, top_k=42):
    emb, turns = memstruct
    q = RETRIEVAL.encode(question, convert_to_tensor=True)
    hits = util.semantic_search(q, emb, top_k=min(top_k, len(turns)))[0]
    retrieved = [turns[h["corpus_id"]] for h in hits]
    facts = callgpt([{"role": "system", "content":
        "You are a memory summarization assistant. Extract relevant facts to answer the question. "
        "Follow this chain-of-thought:\n1. Identify key events, dates, quantities, or named entities.\n"
        "2. Extract only information relevant to the question.\n3. Write the facts in structured bullet points.\n"
        f"\nQuestion: {question}\n\nMessages:\n{json.dumps(retrieved, indent=2)}\n\nNow extract the structured facts:\n-"
    }], model="gpt-4o", max_tokens=512)
    ans = callgpt([{"role": "system", "content":
        "You are a helpful assistant. Using both the extracted facts and the original conversation turns below, "
        "answer the question as accurately and concisely as possible.\n"
        f"\nExtracted Facts:\n{facts}\n\nRetrieved Conversation Turns:\n{json.dumps(retrieved, indent=2)}\n"
        f"\nQuestion: {question}\nQuestion Date: {question_date}\nAnswer:"
    }], model="gpt-4o", max_tokens=256)
    return ans.strip()


def run_one(inst, top_k):
    mem = process_haystack(inst["haystack_sessions"], inst["haystack_dates"])
    hyp = answer(mem, inst["question"], inst.get("question_date", ""), top_k)
    correct = judge(OAI, "gpt-4o", inst, hyp)
    return {"question_id": inst["question_id"], "question_type": inst["question_type"],
            "hypothesis": hyp, "correct": correct}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=DATASETS, default="s")
    ap.add_argument("--n", type=int, default=42)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--held-out", action="store_true")
    ap.add_argument("--top-k", type=int, default=42)
    ap.add_argument("--workers", type=int, default=2)  # ST encode is heavy; keep modest
    args = ap.parse_args()

    data = json.loads(DATASETS[args.dataset].read_text())
    if args.held_out:
        insts = stratified_sample(data, args.n, random.Random(args.seed),
                                  exclude_ids=dev_ids(data, args.n))
    else:
        insts = stratified_sample(data, args.n, random.Random(args.seed))

    results, started = [], time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_one, inst, args.top_k) for inst in insts]
        for i, f in enumerate(futs, 1):
            try:
                r = f.result()
                results.append(r)
                print(f"[{i}/{len(insts)}] {'✓' if r['correct'] else '✗'} {r['question_type']}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(insts)}] ERROR {exc}", flush=True)

    by_type = defaultdict(list)
    for r in results:
        by_type[r["question_type"]].append(r["correct"])
    overall = float(np.mean([r["correct"] for r in results]))
    summary = {
        "method": "emergence-simple-fast", "n": len(results), "top_k": args.top_k,
        "overall_accuracy": round(overall, 4),
        "by_type": {t: {"acc": round(float(np.mean(v)), 4), "n": len(v)} for t, v in sorted(by_type.items())},
        "elapsed_s": round(time.time() - started, 1),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"emergence-{args.dataset}-seed{args.seed}-n{len(results)}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
