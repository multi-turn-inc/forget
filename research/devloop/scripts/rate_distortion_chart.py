#!/usr/bin/env python3
"""rate–distortion chart (측정 ②) — LongMemEval accuracy vs context tokens read.

Dependency-free SVG generator so the artifact is reproducible from a bare venv.
Every plotted number is a documented measurement; nothing is interpolated:

- GPT-4o full-context: ~115k tok/question -> 60.6%  (LongMemEval paper, ICLR 2025)
- forget:              12,363 tok/question (median) -> 78.4% +-0.4  (3 seeds, exp №0003;
                       x is a MEASUREMENT as of cycle 89, not an estimate: the dual
                       pipeline's recall payload was measured directly on dev-42 with
                       the anchor config (obs_k 60 + raw 42 = 102 items). Whiskers are
                       the p10-p90 spread across questions, not seed error; the quantile
                       convention is statistics.quantiles(n=10) default ("exclusive") --
                       naming it matters, a nearest-rank recompute shifts p90 by ~62 tok.)

CORRECTION (cycle 89, 2026-08-10): x was previously plotted as a "1.2-2k estimate".
Direct measurement puts the median at 12,363 tok -- 6.2x above the old upper bound.
The old estimate was never measured; it is retired here. See
research/devloop/notes/cycle-89-dual-payload.md for the measurement and its caveats.
- GPT-4o oracle ceiling 87.0% drawn as a reference line (paper).

Deliberately excluded: the published 81.8% best-config run — its retrieval payload
tokens were never measured (run files record n_ctx = item count, not tokens), and
this chart does not plot estimated x for measured y without saying so.

Usage: python research/devloop/scripts/rate_distortion_chart.py
Writes: research/devloop/rate-distortion.svg
"""

import math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "rate-distortion.svg"

# ---- data (sources in module docstring) ------------------------------------
FULL_CTX = {"tokens": 115_000, "acc": 60.6, "label": "GPT-4o, full context"}
FORGET = {"tok_med": 12_363, "tok_lo": 9_687, "tok_hi": 14_988,
          "acc": 78.4, "err": 0.4, "label": "forget"}
ORACLE = 87.0

# ---- geometry ---------------------------------------------------------------
W, H = 760, 520
ML, MR, MT, MB = 64, 28, 64, 146  # margins; bottom holds source notes (6 lines since c89)
PW, PH = W - ML - MR, H - MT - MB
X_MIN, X_MAX = 1_000, 200_000    # log scale
Y_MIN, Y_MAX = 50, 95

# palette: neutral ink + one accent, AA-contrast on white
INK = "#1f2430"      # text/axes
MUTED = "#6b7280"    # secondary text, baseline point
GRID = "#e5e7eb"
ACCENT = "#2563eb"   # forget point
REF = "#9ca3af"      # oracle reference line


def xp(tokens: float) -> float:
    t = (math.log10(tokens) - math.log10(X_MIN)) / (math.log10(X_MAX) - math.log10(X_MIN))
    return ML + t * PW


def yp(acc: float) -> float:
    return MT + (1 - (acc - Y_MIN) / (Y_MAX - Y_MIN)) * PH


def fmt_tok(n: int) -> str:
    return f"{n // 1000}k" if n >= 1000 else str(n)


def build() -> str:
    e = []
    e.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
             f'font-family="-apple-system, Helvetica, Arial, sans-serif" font-size="13">')
    e.append(f'<rect width="{W}" height="{H}" fill="white"/>')

    # title + subtitle
    e.append(f'<text x="{ML}" y="28" font-size="17" font-weight="600" fill="{INK}">'
             'Memory as compression: fewer tokens, better answers</text>')
    e.append(f'<text x="{ML}" y="48" fill="{MUTED}">LongMemEval accuracy vs context tokens '
             'read per question (log scale)</text>')

    # gridlines + y ticks
    for acc in range(Y_MIN, Y_MAX + 1, 10):
        y = yp(acc)
        e.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML + PW}" y2="{y:.1f}" stroke="{GRID}"/>')
        e.append(f'<text x="{ML - 8}" y="{y + 4:.1f}" text-anchor="end" fill="{MUTED}">{acc}%</text>')

    # x ticks
    for t in (1_000, 2_000, 5_000, 10_000, 20_000, 50_000, 100_000, 200_000):
        x = xp(t)
        e.append(f'<line x1="{x:.1f}" y1="{MT + PH}" x2="{x:.1f}" y2="{MT + PH + 5}" stroke="{MUTED}"/>')
        e.append(f'<text x="{x:.1f}" y="{MT + PH + 20}" text-anchor="middle" fill="{MUTED}">{fmt_tok(t)}</text>')
    e.append(f'<text x="{ML + PW / 2:.1f}" y="{MT + PH + 40}" text-anchor="middle" fill="{INK}">'
             'context tokens per question (log)</text>')

    # axes
    e.append(f'<line x1="{ML}" y1="{MT}" x2="{ML}" y2="{MT + PH}" stroke="{INK}" stroke-width="1"/>')
    e.append(f'<line x1="{ML}" y1="{MT + PH}" x2="{ML + PW}" y2="{MT + PH}" stroke="{INK}" stroke-width="1"/>')

    # oracle ceiling reference
    yo = yp(ORACLE)
    e.append(f'<line x1="{ML}" y1="{yo:.1f}" x2="{ML + PW}" y2="{yo:.1f}" '
             f'stroke="{REF}" stroke-dasharray="5 4"/>')
    e.append(f'<text x="{ML + PW}" y="{yo - 6:.1f}" text-anchor="end" fill="{MUTED}">'
             'GPT-4o oracle ceiling 87.0% (paper)</text>')

    # full-context point
    xf, yf = xp(FULL_CTX["tokens"]), yp(FULL_CTX["acc"])
    e.append(f'<circle cx="{xf:.1f}" cy="{yf:.1f}" r="6" fill="{MUTED}"/>')
    e.append(f'<text x="{xf:.1f}" y="{yf + 24:.1f}" text-anchor="end" fill="{INK}">'
             f'{FULL_CTX["label"]}</text>')
    e.append(f'<text x="{xf:.1f}" y="{yf + 40:.1f}" text-anchor="end" fill="{MUTED}">'
             '~115k tok → 60.6%</text>')

    # forget point: x p10-p90 whisker (measured spread) + y error bar (3 seeds)
    xlo, xhi = xp(FORGET["tok_lo"]), xp(FORGET["tok_hi"])
    xm = xp(FORGET["tok_med"])
    ym = yp(FORGET["acc"])
    ylo, yhi = yp(FORGET["acc"] - FORGET["err"]), yp(FORGET["acc"] + FORGET["err"])
    e.append(f'<line x1="{xlo:.1f}" y1="{ym:.1f}" x2="{xhi:.1f}" y2="{ym:.1f}" '
             f'stroke="{ACCENT}" stroke-width="2"/>')
    for xcap in (xlo, xhi):
        e.append(f'<line x1="{xcap:.1f}" y1="{ym - 5:.1f}" x2="{xcap:.1f}" y2="{ym + 5:.1f}" '
                 f'stroke="{ACCENT}" stroke-width="2"/>')
    e.append(f'<line x1="{xm:.1f}" y1="{ylo:.1f}" x2="{xm:.1f}" y2="{yhi:.1f}" '
             f'stroke="{ACCENT}" stroke-width="2"/>')
    e.append(f'<circle cx="{xm:.1f}" cy="{ym:.1f}" r="6" fill="{ACCENT}"/>')
    e.append(f'<text x="{xm:.1f}" y="{ym - 30:.1f}" text-anchor="start" font-weight="600" fill="{ACCENT}">'
             f'{FORGET["label"]}</text>')
    e.append(f'<text x="{xm:.1f}" y="{ym - 14:.1f}" text-anchor="start" fill="{INK}">'
             '12.4k tok (median) → 78.4% ± 0.4</text>')

    # delta annotation between the two points
    e.append(f'<text x="{(xm + xf) / 2:.1f}" y="{(ym + yf) / 2 - 8:.1f}" text-anchor="middle" '
             f'fill="{INK}">+17.8pp with ~1/9 of the tokens</text>')

    # source / honesty notes
    notes = [
        "Sources: GPT-4o full-context 60.6% and oracle 87.0% — LongMemEval paper (ICLR 2025, arXiv:2410.10813).",
        "forget 78.4% ± 0.4 — 3 seeds (exp №0003). x measured cycle 89 on dev-42, anchor config (obs 60 + raw 42 = 102 items);",
        "whiskers are p10–p90 across questions (quantile convention: statistics.quantiles n=10, exclusive).",
        "Correction: x was previously a 1.2–2k estimate, 6.2× below measurement.",
        "Caveat: y is from the July run (old arithmetic); x was measured on the current body. Same config, different body.",
        "Excluded: forget best-config 81.8% (runs/full-v3-500) — its payload tokens were never measured, so it has no honest x.",
    ]
    for i, n in enumerate(notes):
        e.append(f'<text x="{ML}" y="{H - 86 + i * 15}" font-size="11" fill="{MUTED}">{n}</text>')

    e.append('</svg>')
    return "\n".join(e)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT}")
