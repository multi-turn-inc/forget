#!/usr/bin/env python3
"""Auto-capture layer's impact on real recall selection (devloop cycle 29, 2026-08-02).

Cycle 28 found the dogfood store grew 536 -> ~3030 and 82% of that (2492) is
SessionEnd/PreCompact AUTO-CAPTURE that landed 07-31/08-01. It logged an
UNVERIFIED hypothesis (frictions.md, F2-adjacent): those low-signal session
summaries, added to the recall candidate pool, could WORSEN F2 relevance by
crowding out distilled memories. This cycle tests that hypothesis against the
REAL recall pipeline output, not a projection.

DATA = context_traces (selector-policy-v1.1). Each row is one real recall/
assemble call with candidate_ids / selected_ids / rejected_ids / scores(dict) /
roles(dict). filters pin scope to user_id=junghunkim, app_id=forget. This is
strictly stronger evidence than cycle 21's degenerate-replay projection: it is
what the selector ACTUALLY surfaced and chose.

METHOD ($0, local, read-only mode=ro):
  1. Load all memories -> id: layer (auto_capture | distilled), created_at.
     Same classify() as cycle 28 (metadata.hook in {SessionEnd,PreCompact} or
     text startswith "세션 캡처").
  2. For each trace, classify every candidate by role:
       role==task_state       -> 'task_state'   (lives in claims, not memories)
       role general + in mem   -> auto_capture | distilled
       else                    -> 'unknown'
  3. Segment traces by the auto-capture flood boundary (2026-07-31T00:00Z):
     pre-flood candidates cannot contain the flood; post-flood can.
  4. Report per-layer: candidate share, selected share, selection rate
     P(selected|candidate), score distribution. Crowd-out test: within each
     post-flood trace, count (auto SELECTED, distilled REJECTED) pairs with
     score[auto] > score[distilled] vs the reverse.

Hypothesis is SUPPORTED if auto_capture, once present, occupies a large share of
SELECTED recall AND scores comparably/higher than distilled (wins slots despite
low signal). It is NOT SUPPORTED if the selector systematically scores/ranks
auto_capture below distilled (flood never reaches recall output).
"""
import json
import os
import sqlite3
import statistics
from collections import defaultdict

DB = os.path.expanduser("~/.forget/forget.sqlite3")
FLOOD_BOUNDARY = "2026-07-31T00:00:00Z"  # auto-capture landed 07-31/08-01


def classify(memory, metadata):
    """Identical layer rule to cycle 28 fresh_raw_ratio.py."""
    try:
        md = json.loads(metadata) if metadata else {}
    except Exception:
        md = {}
    if md.get("hook") in ("SessionEnd", "PreCompact"):
        return "auto_capture"
    if isinstance(memory, str) and memory.startswith("세션 캡처"):
        return "auto_capture"
    return "distilled"


def load_memories(con):
    """id -> (layer, created_at). All rows (a candidate may reference a since-
    deleted memory; we only need its metadata for classification)."""
    out = {}
    for mid, memory, metadata, created_at in con.execute(
        "SELECT id, memory, metadata, created_at FROM memories"
    ):
        out[mid] = (classify(memory or "", metadata), created_at)
    return out


def jload(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def layer_of(mid, role, mem):
    if role == "task_state":
        return "task_state"
    hit = mem.get(mid)
    if hit is None:
        return "unknown"
    return hit[0]  # auto_capture | distilled


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    mem = load_memories(con)
    n_auto = sum(1 for v in mem.values() if v[0] == "auto_capture")
    n_dist = sum(1 for v in mem.values() if v[0] == "distilled")
    print(f"=== STORE (all scopes in memories table) ===")
    print(f"  memories loaded: {len(mem)}  (auto_capture={n_auto}, distilled={n_dist})")

    rows = list(con.execute(
        "SELECT created_at, candidate_ids, selected_ids, rejected_ids, scores, roles "
        "FROM context_traces ORDER BY created_at"))
    con.close()

    segments = {"all": [], "pre_flood": [], "post_flood": []}
    for r in rows:
        segments["all"].append(r)
        (segments["post_flood"] if r[0] and r[0] >= FLOOD_BOUNDARY
         else segments["pre_flood"]).append(r)

    print(f"\n=== TRACES (selector-policy-v1.1, junghunkim x forget) ===")
    print(f"  total={len(rows)}  pre-flood(<{FLOOD_BOUNDARY})={len(segments['pre_flood'])}  "
          f"post-flood={len(segments['post_flood'])}")

    for seg_name in ("all", "pre_flood", "post_flood"):
        seg = segments[seg_name]
        cand = defaultdict(int)          # layer -> candidate count
        sel = defaultdict(int)           # layer -> selected count
        cand_scores = defaultdict(list)  # layer -> [scores of candidates]
        sel_scores = defaultdict(list)   # layer -> [scores of selected]
        auto_in_pool_traces = 0          # traces whose candidate pool has >=1 auto
        auto_selected_traces = 0         # traces that selected >=1 auto
        crowd_win = 0                    # (auto selected) beat (distilled rejected) on score
        crowd_lose = 0                   # (distilled selected) beat (auto rejected)
        cap_bound = 0                    # traces where selected < candidates (real pressure)

        for created_at, c_ids, s_ids, r_ids, sc, ro in seg:
            cids = jload(c_ids, [])
            sids = set(jload(s_ids, []))
            rids = set(jload(r_ids, []))
            scores = jload(sc, {})
            roles = jload(ro, {})
            if sids and len(sids) < len(cids):
                cap_bound += 1
            has_auto = has_auto_sel = False
            sel_auto_scores, rej_dist_scores = [], []
            sel_dist_scores, rej_auto_scores = [], []
            for mid in cids:
                lay = layer_of(mid, roles.get(mid), mem)
                cand[lay] += 1
                s = scores.get(mid)
                if s is not None:
                    cand_scores[lay].append(s)
                if mid in sids:
                    sel[lay] += 1
                    if s is not None:
                        sel_scores[lay].append(s)
                if lay == "auto_capture":
                    has_auto = True
                    if mid in sids:
                        has_auto_sel = True
                        if s is not None:
                            sel_auto_scores.append(s)
                    if mid in rids and s is not None:
                        rej_auto_scores.append(s)
                elif lay == "distilled":
                    if mid in sids and s is not None:
                        sel_dist_scores.append(s)
                    if mid in rids and s is not None:
                        rej_dist_scores.append(s)
            if has_auto:
                auto_in_pool_traces += 1
            if has_auto_sel:
                auto_selected_traces += 1
            for a in sel_auto_scores:
                for d in rej_dist_scores:
                    if a > d:
                        crowd_win += 1
            for d in sel_dist_scores:
                for a in rej_auto_scores:
                    if d > a:
                        crowd_lose += 1

        print(f"\n--- segment: {seg_name}  (traces={len(seg)}, capacity-bound={cap_bound}) ---")
        tot_c = sum(cand.values()) or 1
        tot_s = sum(sel.values()) or 1
        print(f"  {'layer':13s} {'cand':>7s} {'cand%':>7s} {'sel':>7s} {'sel%':>7s} "
              f"{'sel_rate':>9s} {'cand_med':>9s} {'sel_med':>9s}")
        for lay in ("auto_capture", "distilled", "task_state", "unknown"):
            c = cand.get(lay, 0)
            s = sel.get(lay, 0)
            rate = (s / c * 100) if c else 0.0
            cmed = statistics.median(cand_scores[lay]) if cand_scores[lay] else float("nan")
            smed = statistics.median(sel_scores[lay]) if sel_scores[lay] else float("nan")
            print(f"  {lay:13s} {c:7d} {c/tot_c*100:6.1f}% {s:7d} {s/tot_s*100:6.1f}% "
                  f"{rate:8.1f}% {cmed:9.4f} {smed:9.4f}")
        print(f"  auto_capture present in candidate pool: {auto_in_pool_traces}/{len(seg)} traces; "
              f"selected in: {auto_selected_traces}/{len(seg)} traces")
        print(f"  crowd-out pairs (auto SELECTED score > distilled REJECTED score): {crowd_win}")
        print(f"  reverse pairs (distilled SELECTED score > auto REJECTED score): {crowd_lose}")


if __name__ == "__main__":
    main()
