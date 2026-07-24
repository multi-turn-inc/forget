# forget — design system

The visual identity converged across the 2026-07-24 redesign (site, og, 404).
This file is the contract: any new surface — page, image, CLI output, slide —
should be derivable from it without asking.

## The one idea

**The brand performs the product.** forget's core mechanic is the
strikethrough (supersede: retire a fact, keep its history), and so is the
logo — f̶orget. Every surface should enact this at least once: the wordmark
draws its own strike, a superseded fact renders struck-through, the 404 page
retires dead URLs as ledger rows. The logo is not a joke about the product;
it is the product.

## Principles

1. **Paper, not screen.** Warm paper white, hairline rules, serif display —
   a research journal, not a SaaS template. Restraint reads as confidence;
   we sell trust, not urgency.
2. **The product is the only dark object.** Terminal windows are the sole
   dark elements on any surface, so the product owns the eye. Never add a
   second dark mass competing with it.
3. **Red is the editor's pen, not an alarm.** Strikethroughs, italic
   emphasis, section numbers, one benchmark bar, small marks. Never floods,
   glows, or gradients.
4. **Data is the ornament.** Where decoration is wanted, render real data
   (benchmark bars, ledger rows, dated trajectory) instead of abstract
   shapes. Specificity is the aesthetic.
5. **Craft the unseen.** View-source comments, console messages, 404 pages,
   tabular numerals — obsession signals live where only the curious look.

## Tokens

```
paper      #faf9f7      page background
paper-2    #f4f2ee      recessed fills (code chips, bar tracks)
ink        #1a1c20      primary text
body       #4e5359      body text
muted      #71767d      secondary
faint      #9b9fa6      tertiary / captions
hair       #e5e2dc      hairline rules
hair-2     #d7d3cb      stronger hairline (borders)
red        #d31126      the editor's pen (site) / #e5122e (favicon legacy)
red-soft   #f8e9e7      red tint fills
term       #14161c      terminal background — the one dark object
```

Terminal syntax (GitHub-dark-adjacent, calm):
```
text #d6dae2 · dim #5b626e · label #8a92a0
green #6fdd8b · yellow #e3b341 · red #ff7b72 · cyan #79c0ff
```

## Type

- **Display**: Instrument Serif 400 (+ italic). Headlines, quotes, section
  titles, the closer. Italic + red marks the emphasized clause — one per
  headline, never more.
- **Body**: Inter 400/500/600/700.
- **Data**: mono (SF Mono stack). All numbers, dates, labels, terminal
  content. `font-variant-numeric: tabular-nums` wherever digits align.
- Editorial numbering: sections carry mono eyebrows — `01 · PROOF`.

## Voice

Specific over superlative ("81.8%", never "blazing fast"). First person
honest ("We couldn't read it if we tried", "What we won't pretend").
One quotable, slightly dangerous line per surface. Korean surfaces keep
the same register — 단정하고, 구체적이고, 한 문장은 위험하게.

## Surface inventory & status (2026-07-24 audit)

| Surface | Status |
|---|---|
| forget.sh desktop | ✅ redesigned; hero right void at ≥1440px is a known P2 |
| forget.sh mobile (390px) | 🔴 P0 — eyebrow/cmd-pill/nav overflow (fix in flight) |
| og.png | ✅ v2 — asymmetric, terminal bleed, benchmark bars |
| 404 | ✅ superseded-ledger |
| GitHub README | 🟡 text-only; add badges + og hero (renders on PyPI too) |
| npm README | 🔴 links to wrong org (junghunkim → multi-turn-inc) |
| CLI output (connect/doctor) | ✅ ✓/✗ ledger style, matches system |
| Hook output (capsule/recall) | ✅ product surface, colors match |
| GitHub social preview | ⬜ manual: upload og.png in repo settings |
| Release notes | ✅ template established with v0.2.1 |

## Reproduction

og.png pipeline: edit the HTML source, render headless, downscale.
```
chrome --headless --screenshot=og-2x.png --window-size=1200,630 \
  --force-device-scale-factor=2 --virtual-time-budget=6000 og.html
sips -z 630 1200 og-2x.png --out site/og.png
```
