#!/usr/bin/env python3
"""M1 회상 평가 — LongMemEval V1 골드로 recall@k를 리더 없이 채점.

인프로세스(서버·HTTP 없음): forget.store를 직접 불러 제품 코드 경로 그대로
잰다. 문항별로 격리 스코프(user_id=question_id)에 건초 세션을 적재하고,
질문으로 검색해 top-k에 정답 세션 출신 기억이 있는지 본다.

  적재 단위: 세션당 유저 발화 연결체를 800자 청크로 (verbatim, infer=off —
  V1/V2 '검색' 비교가 목적이므로 저장은 상수로 고정)

사용:
  .venv/bin/python research/recall-eval/recall_eval.py ingest [n_questions]
  .venv/bin/python research/recall-eval/recall_eval.py measure [--k 6]
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = Path(os.environ.get("RECALL_EVAL_DB", "/tmp/recall-eval.sqlite3"))
DATA = ROOT / "research" / "longmemeval-data" / "longmemeval_s_cleaned.json"
N_DEFAULT = 100
CHUNK_CHARS = 800

os.environ["MEM1_DB_PATH"] = str(DB)


def _store():
    from forget import db as app_db
    from forget.db import init_db

    app_db.DB_PATH = DB
    init_db()
    from forget import store

    return store


def questions(n: int):
    """층화 표본: 6유형 균등 (계측기 교정 2026-08-03 — 앞슬라이스는
    쉬운 2유형만 담겨 포화·판별불능이었음). 유형 내 순서 고정(원본 순),
    n은 유형당 n//6."""
    all_q = json.load(open(DATA))
    from collections import defaultdict
    by_type = defaultdict(list)
    for q in all_q:
        by_type[q["question_type"]].append(q)
    per = max(1, n // len(by_type))
    picked = []
    for t in sorted(by_type):
        picked.extend(by_type[t][:per])
    return picked


def session_chunks(session) -> list[str]:
    text = "\n".join(
        f"{t.get('role')}: {t.get('content', '')}" for t in session if t.get("content")
    )
    return [text[i : i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]


def cmd_ingest(n: int) -> None:
    store = _store()
    qs = questions(n)
    t0 = time.time()
    docs = 0
    for qi, q in enumerate(qs):
        scope = q["question_id"]
        for sid, session in zip(q["haystack_session_ids"], q["haystack_sessions"]):
            for ci, chunk in enumerate(session_chunks(session)):
                store.add_memories(
                    {
                        "messages": [{"role": "user", "content": chunk}],
                        "user_id": scope,
                        "infer": False,
                        "metadata": {"session_id": sid, "chunk": ci},
                    }
                )
                docs += 1
        if (qi + 1) % 10 == 0:
            print(f"  {qi+1}/{len(qs)} 문항, {docs}청크, {time.time()-t0:.0f}s", flush=True)
    print(f"ingest 완료: {len(qs)}문항 {docs}청크 {time.time()-t0:.0f}s → {DB}")


def cmd_measure(k: int, variant: str, n: int = N_DEFAULT) -> None:
    store = _store()
    if variant != "v1":
        os.environ["MEM1_RECALL_V2"] = variant  # M1 구현이 읽는 스위치
    qs = questions(n)
    hits = 0
    mrr = 0.0
    latencies = []
    for q in qs:
        gold = set(q["answer_session_ids"])
        t0 = time.time()
        result = store.search_memories(
            {"query": q["question"], "filters": {"user_id": q["question_id"]}, "top_k": k}
        )
        latencies.append(time.time() - t0)
        rank_hit = None
        covered = set()
        for rank, m in enumerate(result.get("results") or [], 1):
            sid = str((m.get("metadata") or {}).get("session_id"))
            if sid in gold:
                covered.add(sid)
                if rank_hit is None:
                    rank_hit = rank
        if rank_hit:
            hits += 1
            mrr += 1.0 / rank_hit
        coverage_sum = getattr(cmd_measure, "_cov", 0.0) + len(covered) / max(len(gold), 1)
        cmd_measure._cov = coverage_sum
    n = len(qs)
    import statistics

    coverage = getattr(cmd_measure, "_cov", 0.0) / n
    cmd_measure._cov = 0.0
    print(
        f"[{variant}] recall@{k}: {hits}/{n} = {hits/n:.3f} | MRR {mrr/n:.3f} | "
        f"골드커버리지 {coverage:.3f} | 지연 중앙값 {statistics.median(latencies)*1000:.0f}ms"
    )


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "measure"
    if cmd == "ingest":
        cmd_ingest(int(sys.argv[2]) if len(sys.argv) > 2 else N_DEFAULT)
    else:
        k = 6
        variant = "v1"
        n = N_DEFAULT
        for arg in sys.argv[2:]:
            if arg.startswith("--k="):
                k = int(arg.split("=")[1])
            elif arg.startswith("--n="):
                n = int(arg.split("=")[1])
            else:
                variant = arg
        cmd_measure(k, variant, n)
