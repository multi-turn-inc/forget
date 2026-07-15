"""O1 — write-time observation compression (Mastra-style), ceiling test.

Ports the frontier pattern into our harness: an Observer LLM reads each
haystack session at WRITE time and emits dated, compressed observation
bullets. Serving mode 'context' (O1a) puts ALL observations in the reader's
context (no retrieval — Mastra's configuration); mode 'retrieval' (O1b)
ingests observations into forget and retrieves top_k (our product shape).

O1 uses gpt-4o as the Observer to measure the CEILING of the approach.
O2 will swap in a local model (4090) — the local-quality-gap (H5)
measurement. Observations are cached per (observer_model, question_id) so
serving modes and repeat runs reuse them.

    python research/longmemeval/observer.py --n 42 --held-out --seed 7 --mode context
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import (DATASETS, dev_ids, ingest_instance, judge, normalize_date,
                     retrieve, stratified_sample)

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "observations"
OUT = ROOT / "runs"

OBSERVER_SYS = """You are a memory observer. You read one session of a user's conversation with an assistant and record compressed observations for long-term memory.

Rules:
- Output a bullet list. Each bullet starts with the session date in brackets.
- Capture: stable user facts, preferences, life events, plans, quantities, named entities, and anything the user did or decided. Also capture assistant recommendations the user acted on.
- When the session mentions when something happened relative to the session date, record the RESOLVED absolute date in parentheses.
- Be specific: keep numbers, names, dates exactly. One fact per bullet.
- Skip pleasantries, filler, and generic assistant explanations that carry no user-specific information.
- 3-15 bullets per session depending on information density."""


def observe_session(oai: OpenAI, model: str, session: list[dict], date: str) -> str:
    convo = "\n".join(f"{t['role']}: {t['content']}" for t in session
                      if "role" in t and "content" in t)
    for attempt in range(4):
        try:
            r = oai.chat.completions.create(
                model=model, temperature=0, max_tokens=700,
                messages=[{"role": "system", "content": OBSERVER_SYS},
                          {"role": "user", "content": f"Session date: {date}\n\nSession:\n{convo}\n\nObservations:"}],
            )
            return r.choices[0].message.content.strip()
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def get_observations(oai: OpenAI, observer_model: str, inst: dict, session_workers: int = 4) -> list[dict]:
    CACHE.mkdir(exist_ok=True)
    cache_file = CACHE / f"{observer_model}--{inst['question_id']}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    dates = inst.get("haystack_dates") or []
    sessions = inst["haystack_sessions"]
    entries: list[dict | None] = [None] * len(sessions)
    with ThreadPoolExecutor(max_workers=session_workers) as pool:
        futs = {pool.submit(observe_session, oai, observer_model, s,
                            dates[i] if i < len(dates) else ""): i
                for i, s in enumerate(sessions)}
        for fut, i in futs.items():
            entries[i] = {"date": dates[i] if i < len(dates) else "",
                          "observations": fut.result()}
    cache_file.write_text(json.dumps(entries, ensure_ascii=False, indent=1))
    return entries


def answer_context_mode(oai: OpenAI, reader_model: str, inst: dict, entries: list[dict]) -> str:
    memory = "\n\n".join(e["observations"] for e in entries)
    prompt = (f"Today's date: {inst.get('question_date', '')}\n\n"
              f"Long-term memory (dated observations from all past sessions, chronological):\n{memory}\n\n"
              f"Question: {inst['question']}\nAnswer concisely. "
              f"If the memory does not contain the answer, say you don't have that information.")
    for attempt in range(4):
        try:
            r = oai.chat.completions.create(
                model=reader_model, temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return r.choices[0].message.content.strip()
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 * (attempt + 1))


def _model_slug(model: str) -> str:
    return model.replace("/", "-").replace(":", "-")


def run_one(inst, oai, observer_model, reader_model, mode, url, top_k, obs_client=None):
    entries = get_observations(obs_client or oai, observer_model, inst)
    if mode == "context":
        hyp = answer_context_mode(oai, reader_model, inst, entries)
        n_ctx = sum(len(e["observations"]) for e in entries)
    else:  # retrieval / hybrid / dual — observations (± raw turns) into forget
        from harness import read_answer
        # scope carries the observer model so concurrent runs with different
        # observers never clobber each other's server-side stores
        slug = _model_slug(observer_model)
        scope = f"lmeobs-{slug}-{inst['question_id']}"
        raw_scope = f"lmeraw-{slug}-{inst['question_id']}"
        with httpx.Client(base_url=url, timeout=180) as client:
            client.request("DELETE", "/v1/memories/", json={"user_id": scope, "app_id": "lme"})
            for e in entries:
                created = normalize_date(e["date"] or inst.get("question_date", ""))
                for line in e["observations"].splitlines():
                    line = line.strip().lstrip("-• ").strip()
                    if len(line) > 8:
                        client.post("/v1/memories/", json={
                            "text": line, "infer": False, "user_id": scope,
                            "app_id": "lme", "created_at": created,
                        }).raise_for_status()
            if mode in ("hybrid", "dual"):
                # the non-destructive thesis: compressed observations for
                # cross-session reasoning PLUS raw turns as receipts for
                # detail recall. hybrid = one pool (retrieval competition);
                # dual = stratified budgets per layer (guaranteed representation)
                raw_target = scope if mode == "hybrid" else raw_scope
                if mode == "dual":
                    client.request("DELETE", "/v1/memories/", json={"user_id": raw_scope, "app_id": "lme"})
                dates = inst.get("haystack_dates") or []
                for si, session in enumerate(inst["haystack_sessions"]):
                    created = normalize_date(dates[si] if si < len(dates) else inst.get("question_date", ""))
                    for turn in session:
                        if "role" in turn and "content" in turn:
                            client.post("/v1/memories/", json={
                                "text": f"{turn['role']}: {turn['content']}", "infer": False,
                                "user_id": raw_target, "app_id": "lme", "created_at": created,
                            }).raise_for_status()
            if mode == "dual":
                half = top_k // 2
                obs_mem = retrieve(client, scope, inst["question"], half)
                raw_mem = retrieve(client, raw_scope, inst["question"], top_k - half)
                memories = obs_mem + raw_mem
            else:
                memories = retrieve(client, scope, inst["question"], top_k)
        hyp = read_answer(oai, reader_model, inst["question"], inst.get("question_date", ""),
                          memories, two_stage=True)
        n_ctx = len(memories)
    correct = judge(oai, "gpt-4o", inst, hyp)
    return {"question_id": inst["question_id"], "question_type": inst["question_type"],
            "hypothesis": hyp, "correct": correct, "n_ctx": n_ctx}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=DATASETS, default="s")
    ap.add_argument("--n", type=int, default=42)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--held-out", action="store_true")
    ap.add_argument("--mode", choices=["context", "retrieval", "hybrid", "dual"], default="context")
    ap.add_argument("--observer-model", default="gpt-4o")
    ap.add_argument("--observer-base-url", default=None,
                    help="OpenAI-compatible endpoint for the Observer (e.g. ollama "
                         "http://localhost:11435/v1) — O2: local write-time memory construction")
    ap.add_argument("--reader-model", default="gpt-4o")
    ap.add_argument("--url", default="http://localhost:8002")
    ap.add_argument("--top-k", type=int, default=42)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--complement-of", default=None,
                    help="path to a file of question_ids (or results.json lines) already "
                         "evaluated — run only the remaining instances")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    data = json.loads(DATASETS[args.dataset].read_text())
    if args.held_out:
        insts = stratified_sample(data, args.n, random.Random(args.seed),
                                  exclude_ids=dev_ids(data, args.n))
    elif args.n >= len(data):
        insts = data  # full protocol — stratified per-type caps would drop 100 items
    elif args.complement_of:
        prior = json.loads(Path(args.complement_of).read_text())
        done = {r["question_id"] for r in prior}
        insts = [d for d in data if d["question_id"] not in done]
    else:
        insts = stratified_sample(data, args.n, random.Random(args.seed))

    oai = OpenAI()
    obs_client = OpenAI(base_url=args.observer_base_url, api_key="local") \
        if args.observer_base_url else None
    results, started = [], time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(run_one, inst, oai, args.observer_model, args.reader_model,
                            args.mode, args.url, args.top_k, obs_client) for inst in insts]
        for i, f in enumerate(futs, 1):
            try:
                r = f.result()
                results.append(r)
                print(f"[{i}/{len(insts)}] {'✓' if r['correct'] else '✗'} "
                      f"{r['question_type']:26} ctx={r['n_ctx']}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(insts)}] ERROR {type(exc).__name__}: {exc}", flush=True)

    by_type = defaultdict(list)
    for r in results:
        by_type[r["question_type"]].append(r["correct"])
    overall = sum(r["correct"] for r in results) / len(results) if results else 0.0
    summary = {
        "experiment": "O1-observer", "mode": args.mode,
        "observer": args.observer_model, "reader": args.reader_model,
        "n": len(results), "overall_accuracy": round(overall, 4),
        "by_type": {t: {"acc": round(sum(v) / len(v), 4), "n": len(v)}
                    for t, v in sorted(by_type.items())},
        "elapsed_s": round(time.time() - started, 1),
    }
    OUT.mkdir(exist_ok=True)
    tag = args.tag or f"o1-{args.mode}-{args.dataset}-seed{args.seed}-n{len(results)}"
    (OUT / f"{tag}.results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    (OUT / f"{tag}.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
