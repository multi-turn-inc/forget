#!/usr/bin/env python3
"""Fully-fresh raw compression ratio (devloop cycle 28, 2026-08-02).

Cycle 27 calibrated only the DENOMINATOR coefficient (chars/token) and explicitly
deferred the fresh numerator: "완전한 fresh 비율(분자·분모 둘 다 현재 데이터 재측정)은
백로그 ③/원시비 재실행 몫." This script closes that: BOTH sides are measured now,
BOTH directly tokenized with o200k_base (no coefficient), and BOTH from a committed,
deterministic selection — discharging the "측정 재현성" friction (cycle 27).

DENOMINATOR = main-session transcripts under ~/.claude/projects (exclude
/subagents/, /_backup/), files modified within WINDOW_DAYS. Same corpus as cycle 27.
A manifest sha256 of the sorted relpaths pins exactly what was counted (the window
slides + files grow, so exact reproduction needs the same ~/.claude snapshot; the
hash records the file set this run measured — strictly more than the baseline, which
recorded nothing about its 148-session corpus).

NUMERATOR = forget dogfood scope (user_id=junghunkim, app_id=forget), not-deleted,
read STRICTLY read-only from the live store. It is decomposed by capture layer,
because the store grew 536 (baseline 2026-07-31) -> ~3024 and 82% of that is
SessionEnd auto-capture that appeared 07-31/08-01 — so "저장 기억" is now ambiguous:
  - auto_capture : metadata.hook in {SessionEnd, PreCompact} or text startswith 세션 캡처
  - distilled    : the rest (deliberate add_memory + [devloop] notes) == baseline-comparable

Controls: baseline 47:1 / 2.12% (non-reproducible corpus) and cycle-27 coefficient-
corrected 43.5-46.4:1. $0, local, read-only. Deps: tiktoken only.
"""
import hashlib
import json
import os
import sqlite3
import statistics
import sys
import time

import tiktoken

PROJECTS = os.path.expanduser("~/.claude/projects")
DB = os.path.expanduser("~/.forget/forget.sqlite3")
WINDOW_DAYS = 17

# ---- controls (from compression-baseline.md / cycle 27) ----
BASELINE_DENOM_CHARS = 10_622_729
BASELINE_DENOM_TOK = 3_319_602      # chars/3.2 (assumed)
BASELINE_NUM_MEM = 536
BASELINE_NUM_TOK = 70_386           # o200k_base actual
BASELINE_RATIO = BASELINE_DENOM_TOK / BASELINE_NUM_TOK      # 47.2:1
CYC27_CORR_WT = 46.4                # with_tools corrected (baseline chars / K)
CYC27_CORR_MO = 43.5                # msg_only corrected


# ======================= DENOMINATOR =======================
def collect_files():
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
    files = collect_files()
    relpaths = sorted(os.path.relpath(p, PROJECTS) for p in files)
    manifest = hashlib.sha256("\n".join(relpaths).encode("utf-8")).hexdigest()
    agg = {"msg_only": {"chars": 0, "tokens": 0},
           "with_tools": {"chars": 0, "tokens": 0}}
    for p in files:
        m_chars = m_tok = t_chars = t_tok = 0
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    mo, tr = extract(line)
                    if mo:
                        m_chars += len(mo)
                        m_tok += len(enc.encode(mo))
                    if tr:
                        t_chars += len(tr)
                        t_tok += len(enc.encode(tr))
        except OSError:
            continue
        agg["msg_only"]["chars"] += m_chars
        agg["msg_only"]["tokens"] += m_tok
        agg["with_tools"]["chars"] += m_chars + t_chars
        agg["with_tools"]["tokens"] += m_tok + t_tok
    return files, relpaths, manifest, agg


# ======================= NUMERATOR =======================
def classify(memory, metadata):
    try:
        md = json.loads(metadata) if metadata else {}
    except Exception:
        md = {}
    hook = md.get("hook")
    if hook in ("SessionEnd", "PreCompact"):
        return "auto_capture"
    if isinstance(memory, str) and memory.startswith("세션 캡처"):
        return "auto_capture"
    return "distilled"


def measure_numerator(enc):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "SELECT memory, metadata FROM memories "
        "WHERE user_id='junghunkim' AND app_id='forget' "
        "AND (deleted IS NULL OR deleted IN ('0',0))")
    layers = {"auto_capture": {"n": 0, "chars": 0, "tokens": 0},
              "distilled": {"n": 0, "chars": 0, "tokens": 0}}
    for memory, metadata in cur.fetchall():
        memory = memory or ""
        lay = classify(memory, metadata)
        layers[lay]["n"] += 1
        layers[lay]["chars"] += len(memory)
        layers[lay]["tokens"] += len(enc.encode(memory))
    con.close()
    return layers


def main():
    enc = tiktoken.get_encoding("o200k_base")

    # numerator first (cheap), snapshot the store point-in-time
    lay = measure_numerator(enc)
    total_n = sum(lay[k]["n"] for k in lay)
    total_c = sum(lay[k]["chars"] for k in lay)
    total_t = sum(lay[k]["tokens"] for k in lay)
    distilled_t = lay["distilled"]["tokens"]

    print("=== NUMERATOR (junghunkim x forget, not deleted, o200k_base direct) ===")
    for k in ("distilled", "auto_capture"):
        d = lay[k]
        print(f"  {k:13s} n={d['n']:5d}  chars={d['chars']:8d}  tokens={d['tokens']:8d}")
    print(f"  {'TOTAL':13s} n={total_n:5d}  chars={total_c:8d}  tokens={total_t:8d}")
    print(f"  baseline control: {BASELINE_NUM_MEM} mem = {BASELINE_NUM_TOK:,} tok")
    print(f"  -> distilled layer ({lay['distilled']['n']}) ~ baseline ({BASELINE_NUM_MEM}); "
          f"growth is {lay['auto_capture']['n']} auto-capture (SessionEnd/PreCompact)")

    # denominator
    print("\n=== DENOMINATOR (all-projects, exclude subagents/_backup, "
          f"{WINDOW_DAYS}d window, o200k_base direct) ===")
    files, relpaths, manifest, agg = measure_denominator(enc)
    print(f"  corpus: {len(files)} files   manifest sha256={manifest[:16]}...")
    for v in ("msg_only", "with_tools"):
        a = agg[v]
        K = a["chars"] / a["tokens"] if a["tokens"] else float("nan")
        print(f"  {v:11s} chars={a['chars']:11,}  tokens={a['tokens']:10,}  (K={K:.3f})")

    # ratios matrix
    print("\n=== FRESH RATIOS (denom_tok / num_tok) ===")
    print(f"  {'denom_variant':12s} {'num_layer':11s} {'ratio':>9s} {'retention%':>11s}")
    for v in ("msg_only", "with_tools"):
        dtok = agg[v]["tokens"]
        for nlabel, ntok in (("total", total_t), ("distilled", distilled_t)):
            if not ntok:
                continue
            print(f"  {v:12s} {nlabel:11s} {dtok/ntok:8.1f}:1 {ntok/dtok*100:10.3f}%")

    print("\n=== CONTROLS ===")
    print(f"  baseline (non-reproducible corpus): {BASELINE_RATIO:.1f}:1, "
          f"retention {BASELINE_NUM_TOK/BASELINE_DENOM_TOK*100:.2f}%")
    print(f"  cycle-27 coeff-corrected (baseline chars/K, frozen num): "
          f"{CYC27_CORR_MO}:1 (msg_only) ~ {CYC27_CORR_WT}:1 (with_tools)")

    # emit manifest artifact path hint
    print(f"\n(manifest of {len(relpaths)} relpaths available; sha256={manifest})")
    return manifest, relpaths


if __name__ == "__main__":
    main()
