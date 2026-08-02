#!/usr/bin/env python3
"""Content-relevance of MARGINAL auto-capture recall selections (devloop cycle 32, 2026-08-03).

Cycle 29 (autocapture_recall_impact.py) refuted the crowd-out hypothesis but left
an explicit RESIDUAL (잔여 관측 2): ~24.3% of post-flood recall OUTPUT is
auto_capture, clustered right at the selection threshold (sel_median 0.4462). Whether
those marginal picks are TOPICALLY RELEVANT "점수만으로 판별 불가 — 내용 읽기 필요
(향후 측정)". This cycle performs that content read.

KEY DATA FACT (this cycle): the recall queries are not topical — they are session-
startup/resume queries of the form "session startup in <cwd> — active tasks ...".
And every auto_capture memory is a SESSION SUMMARY that embeds its SOURCE PROJECT
(metadata.transcript_path / the "전문: /Users/..." tail). Claude encodes the source
project into the transcript dir name:
  -Users-junghunkim-orca-workspaces-forget----------------  = the devloop workspace
  -Users-junghunkim--PARA-0-Inbox-DILABv2                    = DILAB hardware project
So topic-relevance of a marginal auto_capture pick is OPERATIONALIZED, game-resistantly
(source parse is independent of the numeric score), as:

  same_context : the captured session's source project == the query's cwd project
  off_context  : cross-project scope leak (a session from a DIFFERENT project
                 surfaced in this cwd's restore query)

This is a proxy, validated by direct reading of a sample (see notes/cycle-32-*.md).
It is NOT a claim that same-context == useful; it is the sharpest content signal for a
"restore working context in cwd X" query. $0, local, read-only mode=ro.
"""
import json
import os
import re
import sqlite3
import statistics
from collections import defaultdict

DB = os.path.expanduser("~/.forget/forget.sqlite3")
FLOOD_BOUNDARY = "2026-07-31T00:00:00Z"


def is_auto(memory, md):
    if md.get("hook") in ("SessionEnd", "PreCompact"):
        return True
    if isinstance(memory, str) and memory.startswith("세션 캡처"):
        return True
    return False


def project_label(path):
    """Collapse a filesystem/transcript path to a coarse working-context label.
    Handles both real cwds ('/Users/.../orca/workspaces/forget/내-...') and Claude
    transcript-dir encodings ('-Users-...-orca-workspaces-forget-----')."""
    p = path or ""
    # normalize the encoding separators so both real and encoded paths match
    norm = p.replace("/", "-")
    if "orca-workspaces-forget-" in norm or "orca/workspaces/forget/" in p:
        return "forget-devloop"
    if "PARA-0-Inbox-DILABv2" in norm or "DILABv2" in norm:
        return "DILAB"
    if "orca-projects-SCC" in norm or "SCC_0714" in norm:
        return "SCC"
    if "Documents-Quant" in norm or "Documents/Quant" in p:
        return "Quant"
    if "Documents-forget" in norm or "Documents/forget" in p:
        return "forget-docs"
    if "dev-offreco" in norm or "dev/offreco" in p:
        return "offreco"
    if "rate-limit-pty" in norm:
        return "orca-internal"
    if norm.endswith("-Users-junghunkim") or "-Users-junghunkim-" not in norm.rstrip("-"):
        return "home"
    # fall back to the leaf project segment
    seg = [s for s in norm.split("-") if s]
    return "other:" + "-".join(seg[2:5]) if len(seg) > 4 else "other"


def source_path(md, text):
    tp = md.get("transcript_path") or ""
    if tp:
        return tp
    m = re.search(r"전문:\s*(/\S+)", text or "")
    return m.group(1) if m else ""


def query_label(query):
    """Extract the cwd from 'session <verb> in <cwd> — ...' and label it."""
    m = re.search(r"session \w+ in (.+?) —", query or "")
    if m:
        return project_label(m.group(1))
    return "non-cwd-query"


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    # memory id -> (is_auto, source_label)
    meminfo = {}
    for mid, memory, metadata in con.execute("SELECT id, memory, metadata FROM memories"):
        try:
            md = json.loads(metadata) if metadata else {}
        except Exception:
            md = {}
        auto = is_auto(memory or "", md)
        lbl = project_label(source_path(md, memory or "")) if auto else None
        meminfo[mid] = (auto, lbl)

    rows = list(con.execute(
        "SELECT created_at, query, candidate_ids, selected_ids, scores, roles "
        "FROM context_traces WHERE created_at>=? ORDER BY created_at", (FLOOD_BOUNDARY,)))
    con.close()

    # marginal band: near the empirical selection threshold. cycle 29 sel_median=0.4462.
    LOW, HIGH = 0.40, 0.50

    # store-level footprint: of all auto_capture memories, how many ever reach
    # recall candidacy / selection at all (post-flood)?
    n_auto_store = sum(1 for v in meminfo.values() if v[0])
    auto_cand_ids, auto_sel_ids = set(), set()
    sel_freq = defaultdict(int)
    for created_at, query, c_ids, s_ids, sc, ro in rows:
        try:
            cids = json.loads(c_ids) if c_ids else []
            sids = set(json.loads(s_ids) if s_ids else [])
            roles = json.loads(ro) if ro else {}
        except Exception:
            continue
        for mid in cids:
            if roles.get(mid) == "task_state":
                continue
            info = meminfo.get(mid)
            if info and info[0]:
                auto_cand_ids.add(mid)
                if mid in sids:
                    auto_sel_ids.add(mid)
                    sel_freq[mid] += 1
    print("=== auto_capture recall FOOTPRINT (post-flood) ===")
    print(f"  auto_capture memories in store: {n_auto_store}")
    print(f"  ever a recall candidate: {len(auto_cand_ids)}  "
          f"({len(auto_cand_ids)/n_auto_store*100:.1f}% of store)")
    print(f"  ever selected:           {len(auto_sel_ids)}  "
          f"({len(auto_sel_ids)/n_auto_store*100:.2f}% of store)")
    top = sorted(sel_freq.values(), reverse=True)
    tot_sel = sum(top) or 1
    if len(top) >= 3:
        print(f"  top-3 selected memories = {sum(top[:3])}/{tot_sel} = "
              f"{sum(top[:3])/tot_sel*100:.1f}% of all auto selections (concentration)")
    print()

    # counters over SELECTED auto_capture instances (post-flood)
    sel_auto = 0
    sel_auto_same = 0
    sel_auto_off = 0
    sel_auto_query_noncwd = 0          # query itself has no cwd (can't judge)
    marg_auto = 0                       # selected auto in [LOW,HIGH)
    marg_same = 0
    marg_off = 0
    marg_noncwd = 0
    off_by_srclabel = defaultdict(int)  # off-context: which source project leaked
    same_scores, off_scores = [], []
    # for the sample-read: (score, query_label, src_label, mid)
    examples_off, examples_same = [], []

    for created_at, query, c_ids, s_ids, sc, ro in rows:
        try:
            sids = set(json.loads(s_ids) if s_ids else [])
            scores = json.loads(sc) if sc else {}
            roles = json.loads(ro) if ro else {}
        except Exception:
            continue
        qlbl = query_label(query)
        for mid in sids:
            if roles.get(mid) == "task_state":
                continue
            info = meminfo.get(mid)
            if not info or not info[0]:
                continue  # not auto_capture
            src = info[1]
            s = scores.get(mid)
            sel_auto += 1
            if qlbl in ("non-cwd-query",):
                sel_auto_query_noncwd += 1
                relation = "noncwd"
            elif src == qlbl:
                sel_auto_same += 1
                relation = "same"
                if s is not None:
                    same_scores.append(s)
            else:
                sel_auto_off += 1
                off_by_srclabel[f"{src}->{qlbl}"] += 1
                relation = "off"
                if s is not None:
                    off_scores.append(s)
            if s is not None and LOW <= s < HIGH:
                marg_auto += 1
                if relation == "same":
                    marg_same += 1
                    if len(examples_same) < 12:
                        examples_same.append((round(s, 4), qlbl, src, mid))
                elif relation == "off":
                    marg_off += 1
                    if len(examples_off) < 12:
                        examples_off.append((round(s, 4), qlbl, src, mid))
                else:
                    marg_noncwd += 1

    def pct(a, b):
        return f"{a/b*100:.1f}%" if b else "n/a"

    print("=== SELECTED auto_capture instances (post-flood traces) ===")
    print(f"  total selected auto_capture: {sel_auto}")
    print(f"  same-context (src project == query cwd): {sel_auto_same}  ({pct(sel_auto_same, sel_auto)})")
    print(f"  off-context  (cross-project leak):       {sel_auto_off}  ({pct(sel_auto_off, sel_auto)})")
    print(f"  query has no cwd (unjudgeable):          {sel_auto_query_noncwd}  ({pct(sel_auto_query_noncwd, sel_auto)})")
    judgeable = sel_auto_same + sel_auto_off
    print(f"  --> among JUDGEABLE (cwd query) selections: off-context = {pct(sel_auto_off, judgeable)}")
    if same_scores and off_scores:
        print(f"  score median: same-context={statistics.median(same_scores):.4f}  off-context={statistics.median(off_scores):.4f}")

    print(f"\n=== MARGINAL band [{LOW},{HIGH}) selected auto_capture ===")
    print(f"  marginal auto selected: {marg_auto}")
    print(f"  same-context: {marg_same}  ({pct(marg_same, marg_auto)})")
    print(f"  off-context:  {marg_off}  ({pct(marg_off, marg_auto)})")
    print(f"  non-cwd query: {marg_noncwd}  ({pct(marg_noncwd, marg_auto)})")
    marg_judge = marg_same + marg_off
    print(f"  --> among JUDGEABLE marginal: off-context = {pct(marg_off, marg_judge)}")

    print(f"\n=== off-context leaks by source->query (top 15) ===")
    for k, v in sorted(off_by_srclabel.items(), key=lambda x: -x[1])[:15]:
        print(f"  {v:5d}  {k}")

    print(f"\n=== sample marginal OFF-context (score, query_cwd, src, mid) ===")
    for e in examples_off:
        print("  ", e)
    print(f"\n=== sample marginal SAME-context (score, query_cwd, src, mid) ===")
    for e in examples_same:
        print("  ", e)


if __name__ == "__main__":
    main()
