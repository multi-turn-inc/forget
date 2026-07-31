#!/usr/bin/env python3
"""LongMemEval-V2 배선 파일럿 — forget vs BM25 대조군 (12문항, small 하이스택).

목적은 점수가 아니라 배선 검증이다 (MemoryArena 교훈: "0점은 성능이 아니라
배선 실패일 수 있다"). 격리 인스턴스(포트 43917, 전용 DB) 전용 — 도그푸드 :8000 금지.

어댑터 결정 (정직성 기록):
- 궤적→청크: 상태별 [환경/목표/URL/행동/생각] + 접근성 트리 앞 1200자.
  트리 전문은 수십만 자라 파일럿에선 절단 — 절단이 회상에 불리하게 작용할 수 있음(양쪽 동일 조건).
- 리더: claude -p (고정, 두 시스템 동일). 근거는 top-k 검색 결과만.
- 채점: mc/phrase는 규칙, *-abs와 서술형은 LLM 판정(claude -p, 정답 대조).

사용: .venv/bin/python research/lmev2/pilot.py ingest|ask|score
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

TMP = "/Users/junghunkim/.claude/jobs/f6b439e4/tmp"
BASE = os.environ.get("LMEV2_BASE", "http://127.0.0.1:43917")
USER, APP = "lmev2-pilot", "lmev2"
TOP_K = 8
TREE_CHARS = 1200
OUT = os.path.join(TMP, "pilot_results.json")


def _post(path: str, payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def load_chunks() -> list[str]:
    """하이스택 100궤적 → 상태별 텍스트 청크 (forget과 BM25가 같은 입력을 본다)."""
    ids = set(json.load(open(f"{TMP}/pilot_traj_ids.json")))
    chunks = []
    with open(f"{TMP}/trajectories.jsonl") as fh:
        for line in fh:
            t = json.loads(line)
            if t["id"] not in ids:
                continue
            head = f"[trajectory {t['id']} env={t['environment']} outcome={t['outcome']}] goal: {t['goal']}"
            for s in t["states"]:
                action = s.get("action") or "(initial)"
                thought = (s.get("thought") or "")[:300]
                tree = (s.get("accessibility_tree") or "")[:TREE_CHARS]
                chunks.append(
                    f"{head}\nstep {s['state_index']} url={s.get('url','')}\n"
                    f"action: {action}\nthought: {thought}\nobservation: {tree}"
                )
    return chunks


def cmd_ingest() -> None:
    chunks = load_chunks()
    print(f"chunks: {len(chunks)}")
    t0 = time.time()
    for i, c in enumerate(chunks):
        _post("/v1/memories/", {"text": c, "user_id": USER, "app_id": APP})
        if i % 200 == 0:
            print(f"  {i}/{len(chunks)} ({time.time()-t0:.0f}s)", flush=True)
    print(f"ingest done in {time.time()-t0:.0f}s")


# ---- BM25 (의존성 없는 대조군) ----------------------------------------------

def bm25_index(chunks: list[str]):
    import math
    import re
    docs = [re.findall(r"[a-z0-9]+", c.lower()) for c in chunks]
    df: dict[str, int] = {}
    for d in docs:
        for w in set(d):
            df[w] = df.get(w, 0) + 1
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / max(1, n)
    idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def search(q: str, k: int) -> list[str]:
        import collections
        qw = re.findall(r"[a-z0-9]+", q.lower())
        scores = []
        for i, d in enumerate(docs):
            tf = collections.Counter(d)
            s = sum(idf.get(w, 0) * tf[w] * 2.5 / (tf[w] + 1.5 * (0.25 + 0.75 * len(d) / avgdl))
                    for w in qw if w in tf)
            scores.append((s, i))
        return [chunks[i] for _, i in sorted(scores, reverse=True)[:k]]
    return search


def reader(question: str, contexts: list[str]) -> str:
    ctx = "\n\n---\n\n".join(contexts)[:60_000]
    prompt = (
        "You are answering from an agent's memory of past web-navigation sessions.\n"
        f"<memory>\n{ctx}\n</memory>\n\nQuestion: {question}\n\n"
        "Answer concisely from memory only. If memory does not contain the answer "
        "or the question's premise is wrong, say so explicitly."
    )
    r = subprocess.run(["claude", "-p", prompt, "--max-turns", "1"],
                       capture_output=True, text=True, timeout=300)
    return r.stdout.strip()


def cmd_ask() -> None:
    qs = json.load(open(f"{TMP}/pilot_questions.json"))
    chunks = load_chunks()
    bm25 = bm25_index(chunks)
    results = []
    for q in qs:
        f_ctx = [r["memory"] for r in _post(
            "/v1/memories/search/",
            {"query": q["question"][:800], "user_id": USER, "app_id": APP, "top_k": TOP_K},
        ).get("results", [])]
        b_ctx = bm25(q["question"], TOP_K)
        row = {"id": q["id"], "type": q["question_type"], "question": q["question"],
               "answer": q["answer"], "eval": q["eval_function"],
               "forget_answer": reader(q["question"], f_ctx) if f_ctx else "(no recall)",
               "bm25_answer": reader(q["question"], b_ctx)}
        results.append(row)
        print(f"[{len(results)}/{len(qs)}] {q['question_type']}", flush=True)
        json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"wrote {OUT}")


def judge(question: str, gold: str, answer: str) -> bool:
    prompt = (
        f"Question: {question}\nReference answer: {gold}\nModel answer: {answer}\n\n"
        "Does the model answer convey the same conclusion as the reference "
        "(including correctly abstaining/rejecting a false premise when the "
        "reference does)? Reply with exactly one word: yes or no."
    )
    r = subprocess.run(["claude", "-p", prompt, "--max-turns", "1"],
                       capture_output=True, text=True, timeout=120)
    return r.stdout.strip().lower().startswith("y")


def cmd_score() -> None:
    rows = json.load(open(OUT))
    f_ok = b_ok = 0
    for row in rows:
        fj = judge(row["question"], str(row["answer"]), row["forget_answer"])
        bj = judge(row["question"], str(row["answer"]), row["bm25_answer"])
        row["forget_correct"], row["bm25_correct"] = fj, bj
        f_ok += fj; b_ok += bj
        print(f"{row['type']:28} forget={'O' if fj else 'X'} bm25={'O' if bj else 'X'}")
    json.dump(rows, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"\nforget {f_ok}/{len(rows)}  ·  BM25 {b_ok}/{len(rows)}")


if __name__ == "__main__":
    {"ingest": cmd_ingest, "ask": cmd_ask, "score": cmd_score}[sys.argv[1]]()
