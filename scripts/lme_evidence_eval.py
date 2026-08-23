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
        with get_db() as conn:
            already = conn.execute(
                "SELECT count(*) FROM memories WHERE user_id = ? AND deleted = 0", (scope,)
            ).fetchone()[0]
        dates = inst.get("haystack_dates") or []
        session_ids = inst.get("haystack_session_ids") or []
        n_mem = already
        for si, session in enumerate(inst["haystack_sessions"] if not already else []):
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

        # 계기 교정 (2026-08-24, [96] 해부에서): 주석은 세션 단위인데 턴 단위 회수로
        # 채점하면 분모가 무관 턴(키보드 잡담)으로 부풀어 정상 검색이 0.12로 찍힌다 —
        # 실제로는 결정적 턴이 rank 2였다. 1차 지표를 주석 결에 맞춘다:
        #   needle    = 최고 순위 gold 턴 (바늘을 표면화했는가)
        #   coverage  = 증거 세션마다 ≥1턴이 창 안 (세션 단위 주석 그대로)
        # 턴 회수는 부차로 유지·병기한다.
        with get_db() as conn:
            session_of = {str(r[0]): json.loads(r[1] or "{}").get("lme_session")
                          for r in conn.execute(
                              "SELECT id, metadata FROM memories WHERE user_id = ? AND deleted = 0",
                              (scope,))}
        res = search_memories({"query": inst["question"], "filters": {"user_id": scope},
                               "top_k": 500})
        ranked = [str(m.get("id")) for m in res.get("results") or []]
        rank_of = {mid: i for i, mid in enumerate(ranked)}
        gold_ranks = sorted(rank_of.get(g, 10**9) for g in gold_ids)
        needle = gold_ranks[0]
        sess_min: dict[str, int] = {}
        for g in gold_ids:
            sess = str(session_of.get(g))
            sess_min[sess] = min(sess_min.get(sess, 10**9), rank_of.get(g, 10**9))
        cov84 = sum(1 for v in sess_min.values() if v < args.top_k) / len(sess_min)
        cov10 = sum(1 for v in sess_min.values() if v < 10) / len(sess_min)
        turn84 = sum(1 for r in gold_ranks if r < args.top_k) / len(gold_ranks)
        row = {"qid": inst["question_id"], "type": inst["question_type"], "n_mem": n_mem,
               "needle": needle, "cov84": cov84, "cov10": cov10, "turn84": turn84,
               "sess_min": sess_min}
        stats.setdefault("rows", []).append(row)
        stats["per_type"].setdefault(inst["question_type"], []).append(row)
        print(f"  [{qi}] {inst['question_type'][:20]:20s} needle {needle if needle<10**9 else '∞':>4} "
              f"· 세션커버@{args.top_k} {cov84:.2f} @10 {cov10:.2f} · 턴회수 {turn84:.2f}", flush=True)

    rows = stats.get("rows") or []
    n = len(rows)
    if n:
        import statistics
        out_path = os.environ.get("LME_EVAL_DUMP", "")
        if out_path:
            with open(out_path, "w") as f:
                for row in rows:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        def agg(vals):
            needle10 = sum(1 for v in vals if v["needle"] < 10) / len(vals)
            needle84 = sum(1 for v in vals if v["needle"] < args.top_k) / len(vals)
            mrr = sum(1.0 / (1 + v["needle"]) for v in vals) / len(vals)
            c84 = sum(v["cov84"] for v in vals) / len(vals)
            c10 = sum(v["cov10"] for v in vals) / len(vals)
            t84 = sum(v["turn84"] for v in vals) / len(vals)
            return needle10, needle84, mrr, c84, c10, t84
        print(f"\n{n}문항 · {time.time()-t0:.0f}s · 세분성 {args.granularity}")
        print(f"{'유형':26s} {'n':>3s} {'바늘@10':>7s} {'바늘@84':>7s} {'MRR':>6s} {'커버@84':>7s} {'커버@10':>7s} {'턴@84':>6s}")
        for qtype, vals in sorted(stats["per_type"].items()):
            a = agg(vals)
            print(f"{qtype:26s} {len(vals):3d} {a[0]:7.2f} {a[1]:7.2f} {a[2]:6.3f} {a[3]:7.2f} {a[4]:7.2f} {a[5]:6.2f}")
        a = agg(rows)
        print(f"{'전체':26s} {n:3d} {a[0]:7.2f} {a[1]:7.2f} {a[2]:6.3f} {a[3]:7.2f} {a[4]:7.2f} {a[5]:6.2f}")


if __name__ == "__main__":
    main()
