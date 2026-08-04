"""Embedding-space audit of the dogfood store (read-only, $0, no model load).

Cycle 43. Answers the question LOOP.md 원칙 3 demands and P7's caveat ② left open:
*what body is this instance actually running, and is the store in one space?*

Method — primary evidence only, no self-report:
  1. Decode every live embedding with the PRODUCT's own `decode_embedding`
     (not a reimplementation) and cross-tab format x dimension x creation date.
  2. Locate the exact write at which the stored dimension flips.
  3. Measure what the product does when a query meets a stored vector of a
     different dimension, using the PRODUCT's own `cosine_similarity`. Real
     stored 384-d vectors stand in as queries, so no embedder is loaded and
     the comparison happens in the true bge-small space.

Read-only: opens sqlite with mode=ro. Never writes, never touches the server.

Usage:  .venv/bin/python research/devloop/scripts/embedding_space_audit.py
"""

from __future__ import annotations

import collections
import os
import random
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from forget.memory_engine import cosine_similarity  # noqa: E402
from forget.utils import decode_embedding  # noqa: E402

DB = os.environ.get("FORGET_DB", os.path.expanduser("~/.forget/forget.sqlite3"))
# The recall gate the turn hook applies (forget_turnrecall.py) — the line a
# score has to cross to be injected into a prompt.
RECALL_GATE = 0.45
SEED = 43


def load_rows(db_path: str) -> list[tuple[str, str, list[float], bytes | str]]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.text_factory = bytes
    cur = con.cursor()
    cur.execute("select id, created_at, embedding from memories where deleted=0")
    rows = []
    for mem_id, created_at, raw in cur:
        mem_id = mem_id.decode() if isinstance(mem_id, bytes) else mem_id
        created_at = created_at.decode() if isinstance(created_at, bytes) else created_at
        # decode_embedding sniffs MEB1-blob vs legacy JSON text, so feed it the
        # bytes for blobs and the decoded str for JSON rows.
        value: bytes | str = raw
        if isinstance(raw, bytes) and raw[:4] != b"MEB1":
            try:
                value = raw.decode()
            except UnicodeDecodeError:
                value = raw
        rows.append((mem_id, created_at or "", decode_embedding(value), raw))
    con.close()
    return rows


def fmt_of(raw: bytes | str) -> str:
    if raw is None or raw == b"" or raw == "":
        return "EMPTY"
    return "MEB1" if isinstance(raw, bytes) and raw[:4] == b"MEB1" else "JSON"


def main() -> None:
    rows = load_rows(DB)
    print(f"db            : {DB}")
    print(f"live rows     : {len(rows)}")

    combo = collections.Counter()
    by_date = collections.defaultdict(collections.Counter)
    for _, created_at, vec, raw in rows:
        key = (fmt_of(raw), len(vec))
        combo[key] += 1
        by_date[created_at[:10]][key] += 1

    print("\n== format x dimension ==")
    for (fmt, dim), n in sorted(combo.items(), key=lambda kv: -kv[1]):
        print(f"  {fmt:5s} dim={dim:<4d} {n:6d}  ({100.0 * n / len(rows):.2f}%)")

    print("\n== by creation date ==")
    for day in sorted(by_date):
        cells = ", ".join(f"{f}-{d}:{n}" for (f, d), n in sorted(by_date[day].items()))
        print(f"  {day}  {cells}")

    dims = sorted({len(v) for _, _, v, _ in rows if v})
    if len(dims) > 1:
        print("\n== dimension transition (UTC) ==")
        for dim in dims:
            stamps = sorted(c for _, c, v, _ in rows if len(v) == dim)
            print(f"  dim={dim:<4d} n={len(stamps):<5d} first={stamps[0]}  last={stamps[-1]}")

    # --- what does a cross-space comparison actually score? ---
    majority = max(dims, key=lambda d: sum(1 for _, _, v, _ in rows if len(v) == d))
    minority = [d for d in dims if d != majority]
    if not minority:
        print("\nstore is single-space; no cross-space comparison to make.")
        return

    rng = random.Random(SEED)
    queries = [v for _, _, v, _ in rows if len(v) == majority]
    rng.shuffle(queries)
    queries = queries[:200]

    print(f"\n== cross-space scoring (product cosine_similarity, gate {RECALL_GATE}) ==")
    print(f"   {len(queries)} real dim-{majority} stored vectors used as queries (seed {SEED})")

    for dim in minority:
        odd = [(i, v) for i, _, v, _ in rows if len(v) == dim]
        scores = [cosine_similarity(q, v) for q in queries for _, v in odd]
        over = sum(1 for s in scores if s >= RECALL_GATE)
        print(
            f"\n  dim={dim} rows={len(odd)} pairs={len(scores)}\n"
            f"    mean={statistics.mean(scores):.4f}  median={statistics.median(scores):.4f}"
            f"  min={min(scores):.4f}  max={max(scores):.4f}\n"
            f"    >= gate {RECALL_GATE}: {over}/{len(scores)} ({100.0 * over / len(scores):.1f}%)"
        )
        for mem_id, v in odd:
            s = [cosine_similarity(q, v) for q in queries]
            print(
                f"    {mem_id[:8]}  mean={statistics.mean(s):.4f}"
                f"  >=gate {sum(1 for x in s if x >= RECALL_GATE)}/{len(s)}"
            )

    # Control: same-space pairs, so the cross-space number has something to
    # be compared against (원칙 1 — no number without a control).
    others = [v for _, _, v, _ in rows if len(v) == majority]
    rng.shuffle(others)
    ctrl = [cosine_similarity(q, o) for q, o in zip(queries, others[: len(queries)]) if q is not o]
    print(
        f"\n  CONTROL same-space dim={majority} pairs={len(ctrl)}\n"
        f"    mean={statistics.mean(ctrl):.4f}  median={statistics.median(ctrl):.4f}"
        f"  min={min(ctrl):.4f}  max={max(ctrl):.4f}\n"
        f"    >= gate {RECALL_GATE}: {sum(1 for s in ctrl if s >= RECALL_GATE)}/{len(ctrl)}"
        f" ({100.0 * sum(1 for s in ctrl if s >= RECALL_GATE) / len(ctrl):.1f}%)"
    )


if __name__ == "__main__":
    main()
