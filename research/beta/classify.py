"""β W1 — organic contamination taxonomy over the production dump.

Input: corpus/dump-raw.json (PRIVATE, gitignored — 3,130 items of real
agent-session exhaust, 2026-06-24..07-17, multi-project).
Output: corpus/classified.json (private) + stdout stats (shareable).

Taxonomy (agent-exhaust flavored — this is the paper's Table 1):
  ephemeral-state   session-state that expires (deadlines, "next step is…")
  near-duplicate    same fact re-written within a short window (similarity)
  doc-chunk         CLAUDE.md / project-profile spam split into chunks
  newsbot           content-feed residue with source markers
  probe             test/diagnostic writes
  fragment          <25 chars, no standalone meaning
  durable           what a curator would keep (complement — not junk)

Rule-based first pass; a stratified 100-item sample goes to manual review
(design §3.2 anonymization protocol applies before any public artifact).
"""
from __future__ import annotations

import collections
import json
import random
import re
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
ITEMS = json.loads((HERE / "corpus" / "dump-raw.json").read_text())
if isinstance(ITEMS, dict):
    ITEMS = ITEMS.get("results") or []

EPHEMERAL = re.compile(
    r"(다음 핵심은|다음 단계는|다음 우선순위|까지 진행|예정이다|하기로 했다$|남았다$|"
    r"진행 중이다|대기 중|오늘 (밤|중으로)|내일|이번 주)")
PROBE = re.compile(r"(테스트|probe|프로브|점검용|연동 점검|스모크|smoke)", re.I)
NEWSBOT = re.compile(r"(\(출처:|\[[가-힣]{3,6}\].{0,40}다뤘다|포인트를 받았)")
DOCCHUNK = re.compile(r"^(## |# |\d+\. )|CLAUDE\.md|Project Profile", re.M)


def base_label(text: str) -> str:
    t = text.strip()
    if len(t) < 25:
        return "fragment"
    if NEWSBOT.search(t):
        return "newsbot"
    if DOCCHUNK.search(t[:80]):
        return "doc-chunk"
    if PROBE.search(t[:50]):
        return "probe"
    if EPHEMERAL.search(t):
        return "ephemeral-state"
    return "durable"


def mark_near_duplicates(rows: list[dict]) -> int:
    """Same-day near-identical rewrites (agent hooks fire repeatedly)."""
    by_day = collections.defaultdict(list)
    for r in rows:
        by_day[r["created_at"][:10]].append(r)
    n = 0
    for day_rows in by_day.values():
        day_rows.sort(key=lambda r: r["created_at"])
        for i, r in enumerate(day_rows):
            if r["label"] == "fragment":
                continue
            for prev in day_rows[max(0, i - 20):i]:
                if abs(len(prev["memory"]) - len(r["memory"])) > 40:
                    continue
                if SequenceMatcher(None, prev["memory"], r["memory"]).ratio() > 0.82:
                    r["label"] = "near-duplicate"
                    n += 1
                    break
    return n


def main() -> None:
    rows = [{"id": m["id"], "memory": m["memory"], "created_at": m.get("created_at", ""),
             "label": base_label(m["memory"])} for m in ITEMS]
    n_dup = mark_near_duplicates(rows)
    counts = collections.Counter(r["label"] for r in rows)
    total = len(rows)
    print(f"N={total} · 기간 {min(r['created_at'] for r in rows)[:10]}"
          f" → {max(r['created_at'] for r in rows)[:10]}")
    for label, n in counts.most_common():
        print(f"  {label:<16} {n:>5}  ({n/total:.0%})")
    junk = total - counts["durable"]
    print(f"정크율(초벌): {junk/total:.1%}  (durable 제외 전부)")
    (HERE / "corpus" / "classified.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1))

    # stratified manual-review sample: 15 per label (or all if fewer)
    rng = random.Random(42)
    sample = []
    for label in counts:
        pool = [r for r in rows if r["label"] == label]
        rng.shuffle(pool)
        sample.extend(pool[:15])
    (HERE / "corpus" / "review-sample.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=1))
    print(f"수동 검수 표본 {len(sample)}건 → corpus/review-sample.json")


if __name__ == "__main__":
    main()
