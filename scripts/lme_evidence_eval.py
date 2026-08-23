"""LME 증거-회수 평가 — 외부 gold로 재는 조립기 성적. (평가셋 v2-ext, 2026-08-24)

정훈의 제안: "1~2주 라벨 축적을 기다리는 게 답답하다 — LME-V2로 측정하자."
맞는 방향이고, 핵심 관찰은 이것이다: LongMemEval 500문항에는 문항마다
answer_session_ids(증거 세션 주석)가 달려 있다. 이것이 곧 **즉석 외부 gold**다 —
우리 시스템이 만든 라벨이 아니므로 순환이 없고(평가셋 v1의 사인이 순환이었다),
지금 당장 500문항 분량이 있다.

3층 측정 설계 (비용 오름차순):
  L1 (이 스크립트, $0·무LLM): 증거 회수 — 질의로 검색·조립했을 때 증거 세션산
      기억이 후보(천장)와 선택에 드는가. 검색·선택 병을 외부 자로 분해.
  L2 ($0, 4090 Qwen 리더·판정): QA 정확도 A/B 반복용 (판정 편향은 팔 간 상쇄).
  L3 (게이트, $15-40: GPT-4o 리더·판정): 공표 숫자. 팔이 로컬에서 이긴 뒤에만.

하네스(research/longmemeval/harness.py)는 공표 숫자의 재현 지도이므로 불변.
이 러너는 인게스트에 metadata.lme_session을 얹어 기억→세션 역추적을 가능케 한다.

사용: MEM1_DB_PATH=<벤치DB> .venv/bin/python scripts/lme_evidence_eval.py [--n 3] [--top-k 84]
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "research/longmemeval-data/longmemeval_s_cleaned.json"

_DATE_RE = re.compile(r"(\d{4})[/-](\d{2})[/-](\d{2}).*?(\d{2}):(\d{2})")


def normalize_date(date: str) -> str:
    m = _DATE_RE.search(str(date).strip())
    if m:
        y, mo, d, hh, mm = m.groups()
        return f"{y}-{mo}-{d}T{hh}:{mm}:00"
    dm = re.search(r"(\d{4})[/-](\d{2})[/-](\d{2})", str(date))
    if dm:
        return f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}T12:00:00"
    return str(date)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--top-k", type=int, default=84)
    ap.add_argument("--granularity", default="session", choices=["session", "turn"])
    ap.add_argument("--seed", type=int, default=20260824)
    args = ap.parse_args()

    if "forget.sqlite3" in os.environ.get("MEM1_DB_PATH", ""):
        sys.exit("실원장 금지 — 벤치 DB를 MEM1_DB_PATH로 지정하라")

    from forget.db import get_db, init_db
    from forget.store import add_memories, search_memories
    init_db()

    data = json.load(open(DATA))
    rng = random.Random(args.seed)
    # 층화 표집: 유형 비율 유지 (abstention 문항은 _abs 접미 id — 증거가 없으므로 제외)
    pool = [q for q in data if not str(q["question_id"]).endswith("_abs")]
    by_type: dict[str, list] = {}
    for q in pool:
        by_type.setdefault(q["question_type"], []).append(q)
    sample = []
    for qtype, items in sorted(by_type.items()):
        k = max(1, round(args.n * len(items) / len(pool)))
        sample.extend(rng.sample(items, min(k, len(items))))
    sample = sample[: args.n] if len(sample) > args.n else sample

    stats = {"ceiling": [], "selected": [], "per_type": {}}
    t0 = time.time()
    for qi, inst in enumerate(sample):
        scope = f"lme-{inst['question_id']}"
        dates = inst.get("haystack_dates") or []
        session_ids = inst.get("haystack_session_ids") or []
        n_mem = 0
        for si, session in enumerate(inst["haystack_sessions"]):
            created = normalize_date(dates[si] if si < len(dates) else inst.get("question_date", ""))
            sid = str(session_ids[si]) if si < len(session_ids) else f"s{si}"
            if args.granularity == "session":
                body = "\n".join(f"{t['role']}: {t['content']}" for t in session
                                 if "role" in t and "content" in t)
                if not body:
                    continue
                add_memories({"messages": [{"role": "user", "content": body[:4000]}], "infer": False, "user_id": scope,
                              "app_id": "lme", "created_at": created,
                              "metadata": {"lme_session": sid}, "hebbian": False})
                n_mem += 1
            else:
                for turn in session:
                    add_memories({"messages": [{"role": "user", "content": f"{turn['role']}: {turn['content']}"[:2000]}],
                                  "infer": False, "user_id": scope, "app_id": "lme", "created_at": created,
                                  "metadata": {"lme_session": sid}, "hebbian": False})
                    n_mem += 1

        evidence = {str(s) for s in inst.get("answer_session_ids") or []}
        with get_db() as conn:
            gold_ids = {str(r[0]) for r in conn.execute(
                "SELECT id, metadata FROM memories WHERE user_id = ? AND deleted = 0", (scope,))
                if json.loads(r[1] or "{}").get("lme_session") in evidence}
        if not gold_ids:
            print(f"  [{qi}] {inst['question_id']} 증거 기억 0 — 건너뜀 (주석 세션 미인게스트?)")
            continue

        res = search_memories({"query": inst["question"], "filters": {"user_id": scope},
                               "top_k": args.top_k, "trace": False})
        ranked = [str(m.get("id")) for m in res.get("results") or []]
        sel = set(ranked[: args.top_k])
        ceiling_hit = len(gold_ids & sel) / len(gold_ids)   # 검색이 top_k 안에 데려온 비율
        top10_hit = len(gold_ids & set(ranked[:10])) / len(gold_ids)
        stats["ceiling"].append(ceiling_hit)
        stats["selected"].append(top10_hit)
        stats["per_type"].setdefault(inst["question_type"], []).append((ceiling_hit, top10_hit))
        print(f"  [{qi}] {inst['question_type'][:20]:20s} 기억 {n_mem:4d} · 증거 {len(gold_ids)} "
              f"· top-{args.top_k} 회수 {ceiling_hit:.2f} · top-10 {top10_hit:.2f}")

    n = len(stats["ceiling"])
    if n:
        print(f"\n{n}문항 · {time.time()-t0:.0f}s · 세분성 {args.granularity}")
        print(f"증거 회수: top-{args.top_k} {sum(stats['ceiling'])/n:.3f} · top-10 {sum(stats['selected'])/n:.3f}")
        for qtype, vals in sorted(stats["per_type"].items()):
            c = sum(v[0] for v in vals) / len(vals)
            s = sum(v[1] for v in vals) / len(vals)
            print(f"  {qtype:26s} n={len(vals):3d}  top-k {c:.2f} · top-10 {s:.2f}")


if __name__ == "__main__":
    main()
