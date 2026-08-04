"""Does the rule/vector weight split actually change what surfaces? (read-only, $0)

Cycle 43. `_search_score_weights()` (store.py:4752) returns the legacy
(0.72 rule / 0.28 vector) split unless `_semantic_embedding_active()` is true —
and that helper reads the MEM1_EMBEDDING_PROVIDER *env var*, not the effective
stack. Semantic-by-default (providers.py:958) upgrades an unconfigured "local"
to fastembed/bge-small without setting any env var, so the dogfood server
computes real semantic vectors and then weights them at the split chosen for
the meaningless hash-bag channel.

This asks the falsifiable question: does that misweighting change retrieval, or
is it cosmetic? Game-resistant metric (cycle 22's method): no hand relevance
labels — measure top-1 change and rank correlation between the two weightings.

Probes are leave-one-out: a memory's own text is the query and that memory is
removed from the pool, so the decision under test is "which OTHER memory
surfaces", which is where rule and vector genuinely disagree.

Read-only: sqlite mode=ro, no model load (stored bge-small vectors are reused
as query vectors — bge-small takes no query/passage prefix, so this is faithful).

Usage:  .venv/bin/python research/devloop/scripts/score_weight_replay.py [n_probes]
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import numpy as np  # noqa: E402

from forget.memory_engine import score_memory  # noqa: E402
from forget.utils import decode_embedding  # noqa: E402

DB = os.environ.get("FORGET_DB", os.path.expanduser("~/.forget/forget.sqlite3"))
LEGACY = (0.72, 0.28)
SEMANTIC = (0.45, 0.55)
QUERY_CHARS = 300  # forget_turnrecall.py sends prompt[:300]
TOP_K = 10
SEED = 43


def load() -> list[dict]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.text_factory = bytes
    cur = con.cursor()
    cur.execute(
        "select id, memory, categories, updated_at, embedding "
        "from memories where deleted=0"
    )
    out = []
    for mem_id, text, cats, updated, raw in cur:
        dec = lambda b: b.decode(errors="replace") if isinstance(b, bytes) else (b or "")  # noqa: E731
        value = raw
        if isinstance(raw, bytes) and raw[:4] != b"MEB1":
            try:
                value = raw.decode()
            except UnicodeDecodeError:
                value = raw
        vec = decode_embedding(value)
        try:
            categories = json.loads(dec(cats)) if cats else []
        except ValueError:
            categories = []
        out.append(
            {
                "id": dec(mem_id),
                "memory": dec(text),
                "categories": categories if isinstance(categories, list) else [],
                "updated_at": dec(updated),
                "_vec": vec,
            }
        )
    con.close()
    return out


def kendall_tau(a: list[str], b: list[str]) -> float:
    """Tau over the union of two ranked lists; unranked items sit just past the end."""
    union = list(dict.fromkeys(a + b))
    ra = {m: i for i, m in enumerate(a)}
    rb = {m: i for i, m in enumerate(b)}
    miss = max(len(a), len(b)) + 1
    con = dis = 0
    for i in range(len(union)):
        for j in range(i + 1, len(union)):
            x, y = union[i], union[j]
            da = ra.get(x, miss) - ra.get(y, miss)
            db = rb.get(x, miss) - rb.get(y, miss)
            if da * db > 0:
                con += 1
            elif da * db < 0:
                dis += 1
    total = con + dis
    return (con - dis) / total if total else 1.0


def main() -> None:
    n_probes = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    rows = load()
    pool = [r for r in rows if len(r["_vec"]) == 384 and len(r["memory"]) >= 80]
    print(f"db     : {DB}")
    print(f"pool   : {len(pool)} rows (dim-384, text >= 80 chars) of {len(rows)} live")

    matrix = np.asarray([r["_vec"] for r in pool], dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0.0] = 1.0

    rng = random.Random(SEED)
    probes = rng.sample(range(len(pool)), min(n_probes, len(pool)))

    top1_changed = 0
    taus: list[float] = []
    rank_moves: list[int] = []

    for pi in probes:
        probe = pool[pi]
        query = probe["memory"][:QUERY_CHARS]
        qv = np.asarray(probe["_vec"], dtype=np.float64)
        qn = float(np.linalg.norm(qv)) or 1.0
        cos = (matrix @ qv) / (norms * qn)
        vector = np.clip(np.round((cos + 1.0) / 2.0, 4), 0.0, 1.0)

        rule = np.asarray([score_memory(query, r) for r in pool], dtype=np.float64)

        keep = np.ones(len(pool), dtype=bool)
        keep[pi] = False  # leave-one-out

        legacy = LEGACY[0] * rule + LEGACY[1] * vector
        semantic = SEMANTIC[0] * rule + SEMANTIC[1] * vector
        legacy[~keep] = -1.0
        semantic[~keep] = -1.0

        top_a = [pool[i]["id"] for i in np.argsort(-legacy)[:TOP_K]]
        top_b = [pool[i]["id"] for i in np.argsort(-semantic)[:TOP_K]]
        if top_a[0] != top_b[0]:
            top1_changed += 1
        taus.append(kendall_tau(top_a, top_b))
        rank_b = {m: i for i, m in enumerate(top_b)}
        for i, m in enumerate(top_a):
            if m in rank_b:
                rank_moves.append(abs(i - rank_b[m]))

    overlap = statistics.mean(taus)
    print(f"probes : {len(probes)} (seed {SEED}, leave-one-out, query = own text[:{QUERY_CHARS}])")
    print(f"\n== legacy {LEGACY} vs semantic {SEMANTIC}, top-{TOP_K} ==")
    print(f"  top-1 changed      : {top1_changed}/{len(probes)} ({100.0 * top1_changed / len(probes):.0f}%)")
    print(f"  mean Kendall tau   : {overlap:.4f}  (1.0 = identical order)")
    print(f"  tau < 1.0 (reordered): {sum(1 for t in taus if t < 1.0)}/{len(taus)}")
    if rank_moves:
        print(f"  mean |rank shift|  : {statistics.mean(rank_moves):.2f} positions")


if __name__ == "__main__":
    main()
