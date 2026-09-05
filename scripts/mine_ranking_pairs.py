"""랭킹 쌍 채굴기 — 장부를 리트리버의 훈련 신호로 바꾼다. (2026-08-23)

"사실은 컨텍스트로 · 습관은 가중치로 · 장부는 훈련 신호로"(2026-08-12)의 세 번째
항의 실체. 읽기 전용: 실원장에 아무것도 쓰지 않는다.

라벨 원천 (강한 것부터):
  S1  context_outcomes.used_memory_ids      — 이 기억이 실제로 첫 행동을 만들었다
  S2  failure_stage='none'의 selected_ids   — 주입이 도움됐다 (트레이스 단위 약한 양성)
  N1  harmful_memory_ids                    — 실제로 해로웠다
  N2  failure_stage='selection_failure'의 selected_ids — 소음이었다
  IB  candidate_ids − selected_ids          — 배치 내 음성 (검색은 봤지만 안 뽑힘)
reasoning_failure(2,911건)는 제외한다: 회상이 아니라 추론이 실패한 턴이라
리트리버에겐 라벨이 아니다.

출력: JSONL {query, positives, negatives, weight, source}
사용: .venv/bin/python scripts/mine_ranking_pairs.py [출력경로]
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

DB = os.environ.get("MEM1_DB_PATH", str(Path.home() / ".forget/forget.sqlite3"))
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".forget/datasets/ranking_pairs_v0.jsonl"

MIN_QUERY_CHARS = 6      # 너무 짧은 질의는 신호가 아니라 잡음
MAX_INBATCH_NEG = 4      # 트레이스당 배치 내 음성 상한
MAX_TEXT_CHARS = 500


def loads(value, default):
    try:
        parsed = json.loads(value) if value else default
        return parsed if isinstance(parsed, type(default)) else default
    except Exception:
        return default


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    texts: dict[str, str] = {
        str(row[0]): str(row[1] or "")[:MAX_TEXT_CHARS]
        for row in con.execute("SELECT id, memory FROM memories WHERE deleted = 0")
    }

    rows = con.execute(
        """
        SELECT t.query, t.candidate_ids, t.selected_ids,
               o.used_memory_ids, o.harmful_memory_ids, o.failure_stage
        FROM context_outcomes o
        JOIN context_traces t ON o.trace_id = t.trace_id
        WHERE t.query IS NOT NULL AND t.query != ''
        """
    ).fetchall()

    examples: list[dict] = []
    stats = {"s1_used": 0, "s2_helped": 0, "n1_harmful": 0, "n2_noise": 0, "skipped": 0}

    for query, cand_raw, sel_raw, used_raw, harm_raw, stage in rows:
        query = str(query).strip()
        if len(query) < MIN_QUERY_CHARS:
            stats["skipped"] += 1
            continue
        candidates = [str(x) for x in loads(cand_raw, [])]
        selected = [str(x) for x in loads(sel_raw, [])]
        used = [str(x) for x in loads(used_raw, [])]
        harmful = [str(x) for x in loads(harm_raw, [])]
        resolve = lambda ids: [texts[i] for i in ids if texts.get(i)]  # noqa: E731

        inbatch = resolve([c for c in candidates if c not in set(selected)][:MAX_INBATCH_NEG])

        if used:  # S1: 가장 강한 라벨 — 답을 실제로 만든 기억
            pos = resolve(used)
            if pos:
                examples.append({"query": query, "positives": pos,
                                 "negatives": resolve(harmful) + inbatch,
                                 "weight": 1.0, "source": "used"})
                stats["s1_used"] += 1
                continue
        if harmful:  # N1 단독 (양성 없이 해로움만 관측된 턴)
            neg = resolve(harmful)
            if neg:
                examples.append({"query": query, "positives": [],
                                 "negatives": neg, "weight": 1.0, "source": "harmful"})
                stats["n1_harmful"] += 1
                continue
        if stage == "none" and selected:  # S2: 트레이스 단위 약한 양성
            pos = resolve(selected)
            if pos:
                examples.append({"query": query, "positives": pos, "negatives": inbatch,
                                 "weight": 0.4, "source": "helped"})
                stats["s2_helped"] += 1
                continue
        if stage == "selection_failure" and selected:  # N2: 뽑혔지만 소음이었다
            neg = resolve(selected)
            if neg:
                examples.append({"query": query, "positives": [], "negatives": neg,
                                 "weight": 0.6, "source": "noise"})
                stats["n2_noise"] += 1
                continue
        stats["skipped"] += 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    n_pos = sum(len(e["positives"]) for e in examples)
    n_neg = sum(len(e["negatives"]) for e in examples)
    print(f"트레이스 {len(rows)}건 → 예제 {len(examples)}건 (양성 {n_pos} · 음성 {n_neg})")
    print(f"  내역: {stats}")
    print(f"  출력: {OUT}")


if __name__ == "__main__":
    main()
