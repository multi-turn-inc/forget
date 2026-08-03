#!/usr/bin/env python3
"""compression coefficient calibration (devloop cycle 27, 2026-08-02).

compression-baseline.md computed the raw-compression denominator in *tokens*
as chars/3.2 (a conservative estimate) and named the follow-up explicitly:
"정밀화하려면 표본 파일 토크나이즈로 계수 보정 — 루프의 후속 측정 과제."

This script closes that honesty gap: it tokenizes real Claude Code session
transcripts with the SAME tokenizer the numerator used (o200k_base) and reports
the empirical chars/token coefficient K, with the assumed 3.2 as the control.

Corpus = main-session transcripts under ~/.claude/projects, EXCLUDING
/subagents/ and /_backup/ paths (mirrors the baseline's "148 sessions" type).
Window = files modified within the last 17 days (mirrors the baseline window
"최근 17일" as re-anchored to today). $0, local, read-only.

Two extraction variants are computed because "실제 대화 텍스트, JSON 봉투 제외"
is ambiguous about tool I/O:
  - msg_only : user/assistant text + assistant thinking (no tool_use/tool_result)
  - with_tools: msg_only + tool_result text (file/command output the model reads)
The variant whose avg chars/file matches the baseline's 71.8k chars/session is
the method-matched one (empirical parity check on the extraction definition).
"""
import json
import os
import statistics
import sys
import time

import tiktoken

PROJECTS = os.path.expanduser("~/.claude/projects")
WINDOW_DAYS = 17
BASELINE_CHARS = 10_622_729          # baseline denominator, chars (fixed constant)
BASELINE_SESSIONS = 148
BASELINE_COEFF = 3.2                 # assumed chars/token (control)
BASELINE_DENOM_TOK = 3_319_602      # baseline denominator tokens (= chars/3.2)
NUMERATOR_TOK = 70_386              # baseline numerator, o200k_base actual (unchanged)
NUMERATOR_MEM = 536


def collect_files():
    cutoff = time.time() - WINDOW_DAYS * 86400
    out = []
    for root, dirs, files in os.walk(PROJECTS):
        if "/subagents" in root or "/_backup" in root:
            continue
        for fn in files:
            if not fn.endswith(".jsonl"):
                continue
            p = os.path.join(root, fn)
            try:
                if os.path.getmtime(p) >= cutoff:
                    out.append(p)
            except OSError:
                pass
    return out


def extract(line):
    """Return (msg_only_text, tool_result_text) for one JSONL line."""
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
                # tool_use input intentionally excluded (structural JSON)
    return "\n".join(msg_parts), "\n".join(tool_parts)


def main():
    enc = tiktoken.get_encoding("o200k_base")
    files = collect_files()
    print(f"corpus: {len(files)} main-session files "
          f"(subagents/_backup excluded), window={WINDOW_DAYS}d")
    if not files:
        print("no files in window", file=sys.stderr)
        return

    agg = {
        "msg_only": {"chars": 0, "tokens": 0, "per_file_k": []},
        "with_tools": {"chars": 0, "tokens": 0, "per_file_k": []},
    }
    per_file_chars_wt = []
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
        # msg_only
        agg["msg_only"]["chars"] += m_chars
        agg["msg_only"]["tokens"] += m_tok
        if m_tok:
            agg["msg_only"]["per_file_k"].append(m_chars / m_tok)
        # with_tools
        wt_chars, wt_tok = m_chars + t_chars, m_tok + t_tok
        agg["with_tools"]["chars"] += wt_chars
        agg["with_tools"]["tokens"] += wt_tok
        if wt_tok:
            agg["with_tools"]["per_file_k"].append(wt_chars / wt_tok)
        per_file_chars_wt.append(wt_chars)

    n = len(files)
    print(f"\nbaseline control: {BASELINE_SESSIONS} sessions, "
          f"{BASELINE_CHARS:,} chars, ~{BASELINE_CHARS/BASELINE_SESSIONS:,.0f} chars/session, "
          f"assumed K={BASELINE_COEFF} -> {BASELINE_DENOM_TOK:,} tok, ratio "
          f"{BASELINE_DENOM_TOK/NUMERATOR_TOK:.1f}:1, retention "
          f"{NUMERATOR_TOK/BASELINE_DENOM_TOK*100:.2f}%")

    for variant in ("msg_only", "with_tools"):
        a = agg[variant]
        if not a["tokens"]:
            continue
        K = a["chars"] / a["tokens"]
        cpf = a["chars"] / n
        med_k = statistics.median(a["per_file_k"]) if a["per_file_k"] else float("nan")
        print(f"\n=== variant: {variant} ===")
        print(f"  chars={a['chars']:,}  tokens={a['tokens']:,}")
        print(f"  aggregate K (chars/token) = {K:.3f}   (control 3.2)")
        print(f"  per-file K median = {med_k:.3f}")
        print(f"  avg chars/file = {cpf:,.0f}   (baseline 71.8k/session)")
        # Result B: apply calibrated K to the baseline's FIXED char count,
        # holding numerator constant -> corrected ratio (isolates the coefficient).
        corr_denom = BASELINE_CHARS / K
        corr_ratio = corr_denom / NUMERATOR_TOK
        corr_ret = NUMERATOR_TOK / corr_denom * 100
        print(f"  corrected denom tok (baseline chars/K) = {corr_denom:,.0f}")
        print(f"  corrected ratio = {corr_ratio:.1f}:1  (control 47:1)")
        print(f"  corrected retention = {corr_ret:.2f}%  (control 2.12%)")

    print(f"\nper-file chars (with_tools): min={min(per_file_chars_wt):,} "
          f"median={statistics.median(per_file_chars_wt):,.0f} "
          f"max={max(per_file_chars_wt):,}")


if __name__ == "__main__":
    main()
