#!/usr/bin/env python3
"""Recall-reachable store vs stored-total: the honest compression numerator
(devloop cycle 33, 2026-08-03).

Cycle 28 (fresh_raw_ratio.py) measured the compression headline on TWO numerator
layers — total(3030) and distilled(538) — and found the "≈2% / ~47:1" headline
survives only on total×msg_only, but that total is 82% SessionEnd auto-capture.
Cycle 32 (autocapture_recall_relevance.py) then found that 99.4% (2516/2531) of the
auto-capture layer are recall DEAD-LETTERS: never a recall candidate, only 6 ever
selected. next_actions[1] candidate (b): quantify the compression-headline effect of
those dead-letters — "store total vs recall reach".

This cycle adds a THIRD numerator layer between distilled and total:

  recall-reachable : memories whose id EVER appears as a recall CANDIDATE in the
                     observed post-flood context_traces (task_state role excluded).
  recall-selected  : the stricter subset ever actually SELECTED into a payload.

and decomposes reachability BY LAYER (distilled vs auto_capture), so we distinguish
two very different stories:
  - flood is pure dead weight  (distilled highly reachable, auto_capture ~all dead)
  - recall barely touches store (distilled ALSO mostly dead)

Primary honest number = what FRACTION OF STORED BYTES is recall-reachable (the
"dead-weight fraction"). Secondary = compression ratios for the reachable numerator
against a FRESHLY re-measured denominator (comparable to cycle 28's 49.6:1).

CONTROLS: cycle 28 rows (total×msg_only 49.6:1/2.02%, distilled×msg_only 426.7:1/
0.234%) and cycle 32 footprint (auto reachable 15 cand / 6 sel of 2531 by COUNT).

CAVEATS (honest, stated in the note too):
  - "reachable" = observed as a candidate in the LOGGED traces only. It is an
    empirical LOWER BOUND on reachability; an unqueried memory is not proven dead,
    only never-yet-surfaced under the observed query stream.
  - the trace query stream is devloop-startup-dominated (cycle 32: 2325/2406) — so
    reachability is measured under a self-loop-heavy query distribution, not general.
  - post-flood single reembed regime (inherited from cycle 29/32).

$0, local, STRICTLY read-only (mode=ro). Deps: tiktoken only (denominator).
"""
import json
import os
import sqlite3
import sys

import tiktoken

DB = os.path.expanduser("~/.forget/forget.sqlite3")
PROJECTS = os.path.expanduser("~/.claude/projects")
FLOOD_BOUNDARY = "2026-07-31T00:00:00Z"
WINDOW_DAYS = 17

# ---- controls (cycle 28 fresh_raw_ratio + cycle 32 footprint) ----
CYC28_TOTAL_MO = 49.6      # total x msg_only
CYC28_DISTILLED_MO = 426.7  # distilled x msg_only
CYC32_AUTO_CAND = 15       # auto_capture ever-candidate, by COUNT, of 2531
CYC32_AUTO_SEL = 6         # auto_capture ever-selected, by COUNT


def classify(memory, metadata):
    try:
        md = json.loads(metadata) if metadata else {}
    except Exception:
        md = {}
    if md.get("hook") in ("SessionEnd", "PreCompact"):
        return "auto_capture"
    if isinstance(memory, str) and memory.startswith("세션 캡처"):
        return "auto_capture"
    return "distilled"


def load_store(enc):
    """id -> (layer, chars, tokens); scope = cycle-28 numerator (junghunkim x forget,
    not deleted). Returns dict + per-layer aggregate."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    info = {}
    agg = {"distilled": {"n": 0, "chars": 0, "tokens": 0},
           "auto_capture": {"n": 0, "chars": 0, "tokens": 0}}
    for mid, memory, metadata in con.execute(
            "SELECT id, memory, metadata FROM memories "
            "WHERE user_id='junghunkim' AND app_id='forget' "
            "AND (deleted IS NULL OR deleted IN ('0',0))"):
        memory = memory or ""
        lay = classify(memory, metadata)
        tok = len(enc.encode(memory))
        info[mid] = (lay, len(memory), tok)
        agg[lay]["n"] += 1
        agg[lay]["chars"] += len(memory)
        agg[lay]["tokens"] += tok
    con.close()
    return info, agg


def scan_reach(info):
    """Post-flood context_traces: distinct in-scope memory ids ever a CANDIDATE
    (task_state role excluded) and ever SELECTED."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT candidate_ids, selected_ids, roles FROM context_traces "
        "WHERE created_at>=?", (FLOOD_BOUNDARY,)).fetchall()
    con.close()
    cand, sel = set(), set()
    n_traces = 0
    for c_ids, s_ids, ro in rows:
        n_traces += 1
        try:
            cids = json.loads(c_ids) if c_ids else []
            sids = set(json.loads(s_ids) if s_ids else [])
            roles = json.loads(ro) if ro else {}
        except Exception:
            continue
        for mid in cids:
            if roles.get(mid) == "task_state":
                continue
            if mid in info:              # in-scope (junghunkim x forget) only
                cand.add(mid)
                if mid in sids:
                    sel.add(mid)
    return cand, sel, n_traces


def collect_files():
    import time
    cutoff = time.time() - WINDOW_DAYS * 86400
    out = []
    for root, dirs, files in os.walk(PROJECTS):
        if "/subagents" in root or "/_backup" in root:
            continue
        for fn in files:
            if fn.endswith(".jsonl"):
                p = os.path.join(root, fn)
                try:
                    if os.path.getmtime(p) >= cutoff:
                        out.append(p)
                except OSError:
                    pass
    return out


def extract(line):
    try:
        obj = json.loads(line)
    except Exception:
        return "", ""
    msg = obj.get("message")
    if not isinstance(msg, dict):
        return "", ""
    content = msg.get("content")
    msg_parts, tool_parts = [], []
    if isinstance(content, str):
        msg_parts.append(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                msg_parts.append(part)
            elif isinstance(part, dict):
                t = part.get("type")
                if t == "text":
                    msg_parts.append(part.get("text", ""))
                elif t == "thinking":
                    msg_parts.append(part.get("thinking", ""))
                elif t == "tool_result":
                    c = part.get("content")
                    if isinstance(c, str):
                        tool_parts.append(c)
                    elif isinstance(c, list):
                        for sub in c:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                tool_parts.append(sub.get("text", ""))
                            elif isinstance(sub, str):
                                tool_parts.append(sub)
    return "\n".join(msg_parts), "\n".join(tool_parts)


def measure_denominator(enc):
    import hashlib
    files = collect_files()
    relpaths = sorted(os.path.relpath(p, PROJECTS) for p in files)
    manifest = hashlib.sha256("\n".join(relpaths).encode("utf-8")).hexdigest()
    agg = {"msg_only": 0, "with_tools": 0}
    for p in files:
        m_tok = t_tok = 0
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    mo, tr = extract(line)
                    if mo:
                        m_tok += len(enc.encode(mo))
                    if tr:
                        t_tok += len(enc.encode(tr))
        except OSError:
            continue
        agg["msg_only"] += m_tok
        agg["with_tools"] += m_tok + t_tok
    return len(files), manifest, agg


def main():
    do_denom = "--no-denom" not in sys.argv
    enc = tiktoken.get_encoding("o200k_base")

    info, store = load_store(enc)
    cand, sel, n_traces = scan_reach(info)

    total_n = store["distilled"]["n"] + store["auto_capture"]["n"]
    total_t = store["distilled"]["tokens"] + store["auto_capture"]["tokens"]
    distilled_t = store["distilled"]["tokens"]

    # reachable / selected aggregates, split by layer
    def layer_agg(idset):
        a = {"distilled": {"n": 0, "tokens": 0}, "auto_capture": {"n": 0, "tokens": 0}}
        for mid in idset:
            lay, _c, tok = info[mid]
            a[lay]["n"] += 1
            a[lay]["tokens"] += tok
        return a

    reach = layer_agg(cand)
    seld = layer_agg(sel)
    reach_t = reach["distilled"]["tokens"] + reach["auto_capture"]["tokens"]
    sel_t = seld["distilled"]["tokens"] + seld["auto_capture"]["tokens"]
    reach_n = reach["distilled"]["n"] + reach["auto_capture"]["n"]
    sel_n = seld["distilled"]["n"] + seld["auto_capture"]["n"]

    print(f"=== STORE (junghunkim x forget, not deleted, o200k_base) — {n_traces} post-flood traces ===")
    print(f"  {'layer':13s} {'n':>6s} {'tokens':>9s}")
    for k in ("distilled", "auto_capture"):
        print(f"  {k:13s} {store[k]['n']:6d} {store[k]['tokens']:9d}")
    print(f"  {'TOTAL':13s} {total_n:6d} {total_t:9d}")

    print("\n=== RECALL-REACHABLE (ever a candidate in logged traces, in-scope) ===")
    print(f"  {'layer':13s} {'reach_n':>8s} {'/store':>8s} {'reach_tok':>10s} {'/store_tok':>11s}")
    for k in ("distilled", "auto_capture"):
        sn, stk = store[k]["n"], store[k]["tokens"]
        rn, rtk = reach[k]["n"], reach[k]["tokens"]
        print(f"  {k:13s} {rn:8d} {rn/sn*100:7.2f}% {rtk:10d} {rtk/stk*100:10.2f}%")
    print(f"  {'TOTAL':13s} {reach_n:8d} {reach_n/total_n*100:7.2f}% {reach_t:10d} {reach_t/total_t*100:10.2f}%")
    print(f"  control (cycle32, by COUNT): auto_capture ever-candidate = {CYC32_AUTO_CAND} of 2531")

    print("\n=== RECALL-SELECTED (ever selected into a payload, in-scope) ===")
    print(f"  {'layer':13s} {'sel_n':>8s} {'/store':>8s} {'sel_tok':>10s} {'/store_tok':>11s}")
    for k in ("distilled", "auto_capture"):
        sn, stk = store[k]["n"], store[k]["tokens"]
        xn, xtk = seld[k]["n"], seld[k]["tokens"]
        print(f"  {k:13s} {xn:8d} {xn/sn*100:7.2f}% {xtk:10d} {xtk/stk*100:10.2f}%")
    print(f"  {'TOTAL':13s} {sel_n:8d} {sel_n/total_n*100:7.2f}% {sel_t:10d} {sel_t/total_t*100:10.2f}%")
    print(f"  control (cycle32, by COUNT): auto_capture ever-selected = {CYC32_AUTO_SEL} of 2531")

    dead_tok = total_t - reach_t
    print("\n=== DEAD-WEIGHT (stored but never recall-reachable in observed traces) ===")
    print(f"  stored tokens:           {total_t:9d}")
    print(f"  recall-reachable tokens: {reach_t:9d}  ({reach_t/total_t*100:.2f}% of store)")
    print(f"  DEAD-WEIGHT tokens:      {dead_tok:9d}  ({dead_tok/total_t*100:.2f}% of store)")
    auto_stk = store["auto_capture"]["tokens"]
    auto_dead = auto_stk - reach["auto_capture"]["tokens"]
    print(f"  of which auto_capture dead: {auto_dead:9d}  ({auto_dead/dead_tok*100:.2f}% of dead-weight)")

    if not do_denom:
        print("\n(--no-denom: skipping denominator; ratios omitted)")
        return

    print(f"\n=== DENOMINATOR (all-projects, {WINDOW_DAYS}d, o200k_base direct, fresh) ===")
    nfiles, manifest, dtok = measure_denominator(enc)
    print(f"  corpus: {nfiles} files   manifest sha256={manifest[:16]}...")
    print(f"  msg_only tokens={dtok['msg_only']:,}   with_tools tokens={dtok['with_tools']:,}")

    print("\n=== COMPRESSION RATIOS (denom_tok / num_tok) — reachable layer is NEW ===")
    print(f"  {'denom':11s} {'num_layer':16s} {'num_tok':>9s} {'ratio':>10s} {'retention%':>11s}")
    for v in ("msg_only", "with_tools"):
        d = dtok[v]
        for nlabel, ntok in (("total", total_t), ("recall-reachable", reach_t),
                             ("recall-selected", sel_t), ("distilled", distilled_t)):
            if not ntok:
                continue
            print(f"  {v:11s} {nlabel:16s} {ntok:9d} {d/ntok:9.1f}:1 {ntok/d*100:10.3f}%")
    print("\n=== CONTROLS (cycle 28 msg_only) ===")
    print(f"  total×msg_only={CYC28_TOTAL_MO}:1   distilled×msg_only={CYC28_DISTILLED_MO}:1")


if __name__ == "__main__":
    main()
