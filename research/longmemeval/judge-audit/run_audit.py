"""Adversarial judge audit for LongMemEval (Penfield-style).

Measures the false-accept rate (FAR) of the benchmark judge against
deliberately-wrong probe answers, and the false-reject rate (FRR) against
verbatim correct answers. Uses the exact same judge templates as the
published harness (imported, not copied — one source of truth).

    python research/longmemeval/judge-audit/run_audit.py --judge-model gpt-4o --votes 3

Probes: probes/batch-*.jsonl with {question_id, question_type, strategy, probe_answer}.
Verbatim probes are synthesized here from the answer key (no generation step).
Output: audit-results.jsonl (every vote) + audit-summary.json (FAR/FRR by
type × strategy with Wilson 95% CI).
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from harness import JUDGE_TEMPLATES, judge_template  # noqa: E402

from openai import OpenAI  # noqa: E402

DATA = HERE.parent.parent / "longmemeval-data" / "longmemeval_s_cleaned.json"


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def load_probes() -> list[dict]:
    key = {x["question_id"]: x for x in json.load(open(DATA))}
    probes: list[dict] = []
    for f in sorted(glob.glob(str(HERE / "probes" / "batch-*.jsonl"))):
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            p = json.loads(line)
            p["question"] = key[p["question_id"]]["question"]
            p["answer"] = key[p["question_id"]]["answer"]
            probes.append(p)
    # verbatim probes from the answer key itself — measures FRR
    for qid, item in key.items():
        probes.append({
            "question_id": qid, "question_type": item["question_type"],
            "strategy": "verbatim", "probe_answer": str(item["answer"]),
            "question": item["question"], "answer": item["answer"],
        })
    return probes


def judge_once(oai: OpenAI, model: str, p: dict) -> bool:
    abst = p["question_id"].endswith("_abs")
    template = JUDGE_TEMPLATES["abstention"] if abst else judge_template(p["question_type"])
    prompt = template.format(q=p["question"], a=p["answer"], r=p["probe_answer"])
    resp = oai.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip().lower().startswith("yes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge-model", default="gpt-4o")
    ap.add_argument("--votes", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY required", file=sys.stderr)
        return 1
    oai = OpenAI()
    probes = load_probes()
    print(f"{len(probes)} probes × {args.votes} votes = {len(probes)*args.votes} calls")

    out = open(HERE / "audit-results.jsonl", "w")

    def run(p: dict) -> dict:
        votes = [judge_once(oai, args.judge_model, p) for _ in range(args.votes)]
        rec = {**{k: p[k] for k in ("question_id", "question_type", "strategy")},
               "votes": votes, "accepted": sum(votes) > len(votes) / 2}
        return rec

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for rec in ex.map(run, probes):
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done += 1
            if done % 100 == 0:
                print(f"[{done}/{len(probes)}]", flush=True)
    out.close()

    # summarize: FAR for wrong-answer strategies, FRR for verbatim
    buckets: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for line in open(HERE / "audit-results.jsonl"):
        r = json.loads(line)
        buckets[(r["strategy"], r["question_type"])].append(r["accepted"])
        buckets[(r["strategy"], "_overall")].append(r["accepted"])

    summary: dict = {"judge_model": args.judge_model, "votes": args.votes, "cells": {}}
    for (strat, qtype), accepts in sorted(buckets.items()):
        n = len(accepts)
        if strat == "verbatim":
            k = n - sum(accepts)  # rejections of correct answers
            rate_name = "FRR"
        else:
            k = sum(accepts)      # acceptances of wrong answers
            rate_name = "FAR"
        lo, hi = wilson_ci(k, n)
        summary["cells"][f"{strat}|{qtype}"] = {
            rate_name: round(k / n, 4), "n": n,
            "wilson95": [round(lo, 4), round(hi, 4)],
        }
    json.dump(summary, open(HERE / "audit-summary.json", "w"), indent=1, ensure_ascii=False)
    for cell, v in summary["cells"].items():
        if cell.endswith("_overall"):
            print(cell, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
