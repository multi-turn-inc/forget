#!/usr/bin/env python3
"""Why does 80% of the curated (distilled) brain never reach recall? — decompose
distilled recall-reach by TOPIC, RECENCY, and LENGTH (devloop cycle 34, 2026-08-03).

Cycle 33 (recall_reachable_compression.py) found that under the observed post-flood
trace stream only 13.43% of distilled memories (20.37% of distilled bytes) EVER become
a recall candidate — "recall barely touches the store" (verdict B). Its central,
self-flagged CAVEAT: dead-weight != useless, because the trace query stream is
devloop-startup-dominated, so off-topic memories (US relocation, quant) would be
"insurance inventory" correctly NOT surfaced by devloop queries. That caveat PREDICTS
that reach should be explained by topic-match: loop-topic memories reach, off-topic
substrate does not.

This cycle TESTS that prediction by splitting the 581 distilled memories three ways:

  TOPIC   loop-topic (field notes / cycle decisions relevant to the devloop query
          stream) vs substrate (durable user/strategy/quant/audit knowledge).
          Game-resistant classifier: metadata devloop_cycle|cycle|friction, or
          track in {devloop,self-loop,loop}, or category 'devloop', or '[devloop]'
          prefix in the memory text. (Signal is independent of the recall score.)
  RECENCY reach rate by created_at month.
  LENGTH  reach rate binned by o200k token length (tests the F2 C1 mechanism:
          cycle 18 established unbounded phrase_bonus x long Korean memories gives
          length a floor score — so reach may be a LENGTH artifact, not relevance).

CONTROLS: reproduces cycle 33's distilled reach (78 of 581 = 13.43%) exactly (same
load_store + scan_reach). Reach split (loop vs substrate) and length bins are new.

CAVEATS (honest, carried in the note):
  - "reach" = ever a candidate in the LOGGED post-flood traces = empirical LOWER
    bound under a devloop-startup-dominated query distribution (cycle 33 caveat).
  - loop-topic vs substrate differ in more than topic: loop-topic includes many
    fragmentary micro-memories (split add_memory calls), so a within-topic reach gap
    is confounded with fragmentation. Length bins partly separate this.
  - a memory not reaching recall is NOT lost: it still enters context via disk
    channels (frictions.md, notes/, task_state) — the measurement-cycle pattern.

$0, local, STRICTLY read-only (mode=ro). Deps: tiktoken only.
"""
import json
import os
import sqlite3
import statistics

import tiktoken

DB = os.path.expanduser("~/.forget/forget.sqlite3")
FLOOD_BOUNDARY = "2026-07-31T00:00:00Z"

# ---- controls (cycle 33 recall_reachable_compression) ----
CYC33_DISTILLED_N = 581
CYC33_DISTILLED_REACH_N = 78          # 13.43%
CYC33_DISTILLED_REACH_PCT = 13.43


def parse(s):
    try:
        return json.loads(s) if s else {}
    except Exception:
        return {}


def classify_layer(memory, metadata):
    md = parse(metadata)
    if md.get("hook") in ("SessionEnd", "PreCompact"):
        return "auto_capture"
    if isinstance(memory, str) and memory.startswith("세션 캡처"):
        return "auto_capture"
    return "distilled"


def is_loop_topic(memory, metadata, categories):
    """Relevant to the devloop-startup query stream that dominates the traces.
    Score-independent (metadata/category/text-prefix only)."""
    md = parse(metadata)
    cats = categories if isinstance(categories, list) else []
    if any(k in md for k in ("devloop_cycle", "cycle", "friction")):
        return True
    if md.get("track") in ("devloop", "self-loop", "loop"):
        return True
    if "devloop" in cats:
        return True
    if isinstance(memory, str) and "[devloop]" in memory[:60]:
        return True
    return False


def load(enc):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    info = {}
    for mid, mem, md, ca, cats in con.execute(
            "SELECT id, memory, metadata, created_at, categories FROM memories "
            "WHERE user_id='junghunkim' AND app_id='forget' "
            "AND (deleted IS NULL OR deleted IN ('0',0))"):
        mem = mem or ""
        info[mid] = dict(
            mem=mem,
            lay=classify_layer(mem, md),
            loop=is_loop_topic(mem, md, parse(cats) if cats else []),
            ca=ca or "",
            tok=len(enc.encode(mem)),
        )
    con.close()
    return info


def scan_reach(info):
    """Post-flood context_traces: distinct in-scope memory ids ever a CANDIDATE
    (task_state role excluded). Same rule as cycle 33."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cand = set()
    n_traces = 0
    for c_ids, ro in con.execute(
            "SELECT candidate_ids, roles FROM context_traces WHERE created_at>=?",
            (FLOOD_BOUNDARY,)):
        n_traces += 1
        cids = parse(c_ids)
        roles = parse(ro)
        if not isinstance(cids, list):
            continue
        for mid in cids:
            if roles.get(mid) == "task_state":
                continue
            if mid in info:
                cand.add(mid)
    con.close()
    return cand, n_traces


def rate(ids, cand):
    n = len(ids)
    r = sum(1 for m in ids if m in cand)
    return n, r, (r / n * 100 if n else 0.0)


def main():
    enc = tiktoken.get_encoding("o200k_base")
    info = load(enc)
    cand, n_traces = scan_reach(info)

    dist = [m for m in info if info[m]["lay"] == "distilled"]
    n, r, pct = rate(dist, cand)
    print(f"=== distilled reach (control: cycle 33 = "
          f"{CYC33_DISTILLED_REACH_N}/{CYC33_DISTILLED_N} = {CYC33_DISTILLED_REACH_PCT}%) ===")
    print(f"  distilled: store={n}  reach={r}  ({pct:.2f}%)   [{n_traces} post-flood traces]")

    loop = [m for m in dist if info[m]["loop"]]
    sub = [m for m in dist if not info[m]["loop"]]
    print("\n=== TOPIC (tests cycle-33 'insurance inventory' caveat) ===")
    for lab, ids in (("loop-topic", loop), ("substrate", sub)):
        n, r, pct = rate(ids, cand)
        print(f"  {lab:11s}: store={n:3d}  reach={r:3d}  ({pct:5.1f}%)")

    print("\n=== RECENCY (created month) ===")
    months = sorted({info[m]["ca"][:7] for m in dist if info[m]["ca"]})
    for mth in months:
        ids = [m for m in dist if info[m]["ca"][:7] == mth]
        n, r, pct = rate(ids, cand)
        print(f"  {mth}: store={n:3d}  reach={r:3d}  ({pct:5.1f}%)")

    print("\n=== LENGTH (o200k tokens) — tests F2 C1 length mechanism ===")
    bins = [(0, 20), (20, 50), (50, 120), (120, 300), (300, 10**9)]
    for lo, hi in bins:
        ids = [m for m in dist if lo <= info[m]["tok"] < hi]
        if not ids:
            continue
        n, r, pct = rate(ids, cand)
        loopshare = sum(1 for m in ids if info[m]["loop"]) / n * 100
        hi_s = "inf" if hi == 10**9 else str(hi)
        print(f"  [{lo:4d},{hi_s:>5s}) tok: store={n:3d} reach={r:3d} ({pct:5.1f}%)  loop-share={loopshare:4.0f}%")

    print("\n=== length x topic (separate length from topic) ===")
    for band, (lo, hi) in (("<50tok", (0, 50)), (">=50tok", (50, 10**9))):
        for lab, ids0 in (("loop", loop), ("substrate", sub)):
            ids = [m for m in ids0 if lo <= info[m]["tok"] < hi]
            n, r, pct = rate(ids, cand)
            print(f"  {band:8s} {lab:9s}: store={n:3d} reach={r:3d} ({pct:5.1f}%)")

    print("\n=== silent-miss candidates (loop-topic distilled NOT reaching) ===")
    nr_loop = [m for m in loop if m not in cand]
    frag = [m for m in nr_loop if info[m]["tok"] < 40]
    durable = sorted([m for m in nr_loop if info[m]["tok"] >= 120],
                     key=lambda m: info[m]["tok"], reverse=True)
    print(f"  total non-reaching loop-topic: {len(nr_loop)}")
    print(f"  of which <40tok per-cycle fragments (low value): {len(frag)} "
          f"({len(frag)/len(nr_loop)*100:.0f}%)")
    print(f"  substantive (>=120tok) durable loop notes NOT reaching: {len(durable)}")
    for m in durable[:6]:
        print(f"    [{info[m]['tok']:3d}tok] {info[m]['mem'][:88]!r}")

    med_loop = statistics.median([info[m]["tok"] for m in loop])
    med_sub = statistics.median([info[m]["tok"] for m in sub])
    print(f"\n  (median tok: loop-topic={med_loop:.0f}  substrate={med_sub:.0f})")


if __name__ == "__main__":
    main()
