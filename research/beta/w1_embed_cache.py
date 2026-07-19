"""β W1 — one-time embedding cache for the Tier-1 sweep.

Embeds, once, everything every sweep cell will ever score:
  per instance: turns (+has_answer, session idx), gpt-4o observation
  entries (+session idx), the query          -> cache/{qid}.npz
  pools: synthetic-EN contaminants           -> cache/pool_synthetic.npz
(C-crosstalk needs no pool: donor turns are other instances' cached turns.
 C-organic-EN pool is built by translate_organic.py, embedded on completion.)

    python research/beta/w1_embed_cache.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import DATASETS  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache"
OBS_DIR = ROOT / "research" / "longmemeval" / "observations"
OBS_MODEL = "gpt-4o"


def synthetic_pool_en(n: int, rng: random.Random) -> list[str]:
    """English synthetic junk mirroring the organic taxonomy (newsbot,
    probe, doc-chunk, fragment, session-exhaust, near-duplicate)."""
    channels = ["TechDigest", "DevWeekly", "AIRoundup", "StackReport", "BuildLog"]
    topics = ["a new open-source vector search library", "a lightweight embedding model",
              "a Rust rewrite case study", "GPU price trends", "an agent framework comparison",
              "a static site generator", "a monorepo build tool", "a Kubernetes alternative",
              "a type system debate", "a developer burnout survey", "an AI regulation vote",
              "a startup funding round"]
    sources = ["github.com", "dev.to", "huggingface.co", "techcrunch.com",
               "news.ycombinator.com", "arxiv.org"]
    exhaust = ["Verified the {} pipeline end-to-end and everything played back correctly.",
               "The next priority is automating {} inside the production workflow.",
               "Wrapped up the audit; the handoff doc separates past wins from current state of {}.",
               "Implemented the {} panel with duplicate checkout blocking and per-plan readiness."]
    things = ["browser-to-bridge", "billing", "gallery transition", "ingestion", "export",
              "notification", "session-restore", "theme-toggle"]
    pool: list[str] = []
    while len(pool) < n:
        kind = rng.random()
        topic, src = rng.choice(topics), rng.choice(sources)
        pts = rng.randint(40, 1900)
        if kind < 0.30:
            pool.append(f"[{rng.choice(channels)}] Covered {topic} — the repo got {pts} points. (source: {src})")
        elif kind < 0.50:
            pool.append(rng.choice(exhaust).format(rng.choice(things)))
        elif kind < 0.65:
            pool.append(f"Opinions were split on {topic}, especially around performance. (source: {src})")
        elif kind < 0.75:
            pool.append(f"## Project Profile: section {rng.randint(1,9)}/9 — deployment checklist, "
                        f"env vars, and rollback notes for the {rng.choice(things)} service.")
        elif kind < 0.85:
            pool.append("Integration probe — written from the ops console for connectivity check.")
        elif kind < 0.93:
            pool.append(f"the point of {topic} is ultimately cost")  # fragment
        else:  # near-duplicate pair
            base = rng.choice(exhaust).format(rng.choice(things))
            pool.append(base)
            pool.append(base.replace("end-to-end", "fully").replace("production", "prod"))
    rng.shuffle(pool)
    return pool[:n]


def main() -> int:
    from fastembed import TextEmbedding
    CACHE.mkdir(exist_ok=True)
    model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        e = np.array(list(model.embed(texts)), dtype=np.float32)
        return e / np.linalg.norm(e, axis=1, keepdims=True)

    # pools
    pool_file = CACHE / "pool_synthetic.npz"
    if not pool_file.exists():
        texts = synthetic_pool_en(6000, random.Random(42))
        np.savez_compressed(pool_file, emb=embed(texts))
        (CACHE / "pool_synthetic.texts.json").write_text(json.dumps(texts))
        print("synthetic pool: 6000 embedded", flush=True)

    data = json.loads(DATASETS["s"].read_text())
    started = time.time()
    for idx, inst in enumerate(data, 1):
        out = CACHE / f"{inst['question_id']}.npz"
        if out.exists():
            continue
        turns, ans, sess = [], [], []
        for si, session in enumerate(inst["haystack_sessions"]):
            for t in session:
                if "role" in t and "content" in t:
                    turns.append(f"{t['role']}: {t['content']}")
                    ans.append(bool(t.get("has_answer")))
                    sess.append(si)
        obs_texts, obs_sess = [], []
        obs_file = OBS_DIR / f"{OBS_MODEL}--{inst['question_id']}.json"
        if obs_file.exists():
            for si, e in enumerate(json.loads(obs_file.read_text())):
                for line in e["observations"].splitlines():
                    line = line.strip().lstrip("-• ").strip()
                    if len(line) > 8:
                        obs_texts.append(line)
                        obs_sess.append(si)
        ans_sess = {inst["haystack_session_ids"].index(s)
                    for s in inst["answer_session_ids"]
                    if s in inst["haystack_session_ids"]}
        np.savez_compressed(
            out,
            turn_emb=embed(turns), turn_ans=np.array(ans), turn_sess=np.array(sess),
            obs_emb=embed(obs_texts), obs_sess=np.array(obs_sess),
            q_emb=embed([inst["question"]])[0],
            ans_sess=np.array(sorted(ans_sess)),
        )
        if idx % 25 == 0:
            el = (time.time() - started) / 60
            print(f"[{idx}/500] {el:.0f}m elapsed", flush=True)
    print("cache complete", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
