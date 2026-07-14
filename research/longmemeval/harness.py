"""LongMemEval harness for forget — Tier 0 baseline.

Faithful pipeline: ingest each instance's haystack into an isolated forget
scope (scope isolation = the route we fixed 2026-07-13), retrieve with the
current engine, let a reader LLM answer from retrieved context, judge with
the benchmark's own per-type prompt. Reader and judge default to gpt-4o so
numbers are comparable to the published Mem0/Zep figures.

    python research/longmemeval/harness.py --dataset oracle --n 30 --strata
    python research/longmemeval/harness.py --dataset s --n 500

Pre-registered tiers: gtm/validation-criteria.md experiment 5. Do not tune
on these instances — hold out for improvement work.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research" / "longmemeval-data"
OUT = ROOT / "research" / "longmemeval" / "runs"
DATASETS = {
    "oracle": DATA / "longmemeval_oracle.json",
    "s": DATA / "longmemeval_s_cleaned.json",
}

JUDGE_TEMPLATES = {
    "default": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "temporal-reasoning": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {q}\n\nRubric: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "abstention": "I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the model correctly identifies the question as unanswerable. The model could say that the information is incomplete, or some other information is given but the asked information is not.\n\nQuestion: {q}\n\nExplanation: {a}\n\nModel Response: {r}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only.",
}


def judge_template(qtype: str) -> str:
    if qtype in ("single-session-user", "single-session-assistant", "multi-session"):
        return JUDGE_TEMPLATES["default"]
    return JUDGE_TEMPLATES.get(qtype, JUDGE_TEMPLATES["default"])


def stratified_sample(data: list[dict], n: int, rng: random.Random,
                      exclude_ids: set[str] | None = None) -> list[dict]:
    exclude_ids = exclude_ids or set()
    by_type: dict[str, list[dict]] = defaultdict(list)
    for inst in data:
        if inst["question_id"] in exclude_ids:
            continue
        by_type[inst["question_type"]].append(inst)
    picked: list[dict] = []
    types = sorted(by_type)
    per = max(1, n // len(types))
    for t in types:
        pool = by_type[t][:]
        rng.shuffle(pool)
        picked.extend(pool[:per])
    rng.shuffle(picked)
    return picked[:n]


def dev_ids(data: list[dict], n: int) -> set[str]:
    """The exact question_ids used by the seed-42 dev sample, to hold them
    out of the validation draw."""
    return {inst["question_id"] for inst in stratified_sample(data, n, random.Random(42))}


def ingest_instance(client: httpx.Client, scope: str, inst: dict) -> int:
    client.request("DELETE", "/v1/memories/", json={"user_id": scope, "app_id": "lme"})
    stored = 0
    dates = inst.get("haystack_dates") or []
    for si, session in enumerate(inst["haystack_sessions"]):
        date = dates[si] if si < len(dates) else inst.get("question_date", "2026-01-01")
        created = normalize_date(date)
        for turn in session:
            text = f"{turn['role']}: {turn['content']}"
            resp = client.post("/v1/memories/", json={
                "text": text, "infer": False, "user_id": scope, "app_id": "lme",
                "created_at": created,
            })
            resp.raise_for_status()
            stored += 1
    return stored


def normalize_date(date: str) -> str:
    date = date.strip().replace(" (", "T").rstrip(")")
    if "T" not in date:
        date += "T12:00:00"
    return date


def retrieve(client: httpx.Client, scope: str, question: str, top_k: int) -> list[dict]:
    resp = client.post("/v3/memories/search/", json={
        "query": question, "top_k": top_k, "temporal_rerank": True,
        "filters": {"user_id": scope, "app_id": "lme"},
    })
    resp.raise_for_status()
    return resp.json()["results"]


READER_SYS = (
    "You are answering a question using a user's past conversation history. "
    "The retrieved memories below are excerpts from earlier sessions, each prefixed "
    "with the speaker role. Answer the question concisely using only this evidence. "
    "If the evidence does not contain the answer, say you don't have that information."
)


def read_answer(oai: OpenAI, model: str, question: str, qdate: str, memories: list[dict]) -> str:
    # Surface each memory's date — temporal-reasoning questions are
    # unanswerable without it, and the date is already stored, just not
    # previously shown to the reader.
    lines = []
    for m in memories:
        date = (m.get("created_at") or "")[:10]
        lines.append(f"- [{date}] {m['memory']}")
    context = "\n".join(lines) or "(no memories retrieved)"
    prompt = f"Today's date: {qdate}\n\nRetrieved memories (each tagged with its date):\n{context}\n\nQuestion: {question}"
    resp = oai.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": READER_SYS}, {"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip()


def judge(oai: OpenAI, model: str, inst: dict, hyp: str) -> bool:
    abst = "_abs" in inst["question_id"]
    template = JUDGE_TEMPLATES["abstention"] if abst else judge_template(inst["question_type"])
    prompt = template.format(q=inst["question"], a=inst["answer"], r=hyp)
    resp = oai.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.choices[0].message.content.strip().lower().startswith("yes")


def _with_retry(fn, tries=4):
    delay = 2.0
    for attempt in range(tries):
        try:
            return fn()
        except Exception:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            time.sleep(delay)
            delay *= 2


def run_instance(inst, url, oai, reader_model, judge_model, top_k):
    scope = f"lme-{inst['question_id']}"
    with httpx.Client(base_url=url, timeout=180) as client:
        _with_retry(lambda: ingest_instance(client, scope, inst))
        memories = retrieve(client, scope, inst["question"], top_k)
    hyp = _with_retry(lambda: read_answer(oai, reader_model, inst["question"],
                                          inst.get("question_date", ""), memories))
    correct = _with_retry(lambda: judge(oai, judge_model, inst, hyp))
    return {
        "question_id": inst["question_id"], "question_type": inst["question_type"],
        "question": inst["question"], "answer": inst["answer"], "hypothesis": hyp,
        "n_retrieved": len(memories), "correct": correct,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=DATASETS, default="oracle")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--strata", action="store_true", help="stratified sample by question_type")
    ap.add_argument("--url", default="http://localhost:8001")  # dedicated bench server, never the dogfood one
    ap.add_argument("--reader-model", default="gpt-4o")
    ap.add_argument("--judge-model", default="gpt-4o")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--held-out", action="store_true",
                    help="draw a stratified sample disjoint from the seed-42 dev set")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 1

    data = json.loads(DATASETS[args.dataset].read_text())
    rng = random.Random(args.seed)
    if args.held_out:
        exclude = dev_ids(data, args.n)
        insts = stratified_sample(data, args.n, rng, exclude_ids=exclude)
    elif args.strata:
        insts = stratified_sample(data, args.n, rng)
    else:
        insts = data[: args.n]
    oai = OpenAI()
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = args.tag or f"{args.dataset}-n{len(insts)}"

    results = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_instance, inst, args.url, oai, args.reader_model,
                               args.judge_model, args.top_k) for inst in insts]
        for i, fut in enumerate(futures, 1):
            try:
                r = fut.result()
                results.append(r)
                mark = "✓" if r["correct"] else "✗"
                print(f"[{i}/{len(insts)}] {mark} {r['question_type']:26} ret={r['n_retrieved']}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(insts)}] ERROR {exc}", flush=True)

    by_type: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_type[r["question_type"]].append(r["correct"])
    overall = sum(r["correct"] for r in results) / len(results) if results else 0.0

    summary = {
        "dataset": args.dataset, "n": len(results), "top_k": args.top_k,
        "reader": args.reader_model, "judge": args.judge_model,
        "overall_accuracy": round(overall, 4),
        "by_type": {t: {"acc": round(sum(v) / len(v), 4), "n": len(v)} for t, v in sorted(by_type.items())},
        "elapsed_s": round(time.time() - started, 1),
    }
    (OUT / f"{stamp}.results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    (OUT / f"{stamp}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
