#!/usr/bin/env python3
"""LongMemEval-V2 풀런 — forget vs BM25, medium 하이스택 (텍스트 422문항).

설계 결정 (정직성 기록):
- 하이스택이 문항별(433개 고유)이므로 도메인 합집합(web 599 + enterprise 874
  궤적)을 도메인별 스코프로 1회 적재하고, 질의 시 검색 결과를 그 문항의
  하이스택 궤적 id로 필터 → 문항별 허용 기억 제약을 보존.
- 이미지 문항 29개 제외 (리더가 텍스트 전용) — 커버리지 422/451로 보고.
- 접근성 트리 절단 1200→3000자 (파일럿의 -abs 실패 원인 완화. 여전히 절단이며
  풀트리 대비 부재 증명에 불리할 수 있음 — 양 시스템 동일 조건).
- 채점: mc_choice_match·norm_phrase_set_match는 규칙, 나머지는 LLM 심판.
- 인증 가드: 리더/심판 출력에 "Failed to authenticate" 포함 시 실패로 간주,
  90초 대기 후 재시도(최대 3회), 그래도 실패면 미완료로 남겨 재개 가능.
- 체크포인트: 문항 단위 저장 — 중단 후 같은 명령으로 재개.

사용: .venv/bin/python research/lmev2/fullrun.py ingest|run|score|report
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

TMP = "/Users/junghunkim/.claude/jobs/f6b439e4/tmp"
BASE = os.environ.get("LMEV2_BASE", "http://127.0.0.1:43917")
APP = os.environ.get("LMEV2_APP", "lmev2full")
TOP_K = 8
SEARCH_K = 40  # 필터 전 여유
TREE_CHARS = 3000
WORKERS = 4
STATE = os.path.join(TMP, f"fullrun_state_{APP}.json")


def _post(path: str, payload: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def load_questions() -> list[dict]:
    qs = [json.loads(l) for l in open(f"{TMP}/questions.jsonl")]
    return [q for q in qs if q["image"] is None]


def load_haystacks() -> dict:
    return json.load(open(f"{TMP}/haystack_medium.json"))


def domain_traj_ids() -> dict[str, set]:
    qs = {q["id"]: q for q in (json.loads(l) for l in open(f"{TMP}/questions.jsonl"))}
    out: dict[str, set] = {"web": set(), "enterprise": set()}
    for qid, tids in load_haystacks().items():
        out[qs[qid]["domain"]].update(tids)
    return out


def iter_chunks(wanted: set):
    """(trajectory_id, chunk_text) 스트림 — 궤적 id가 텍스트 머리에 박힌다."""
    with open(f"{TMP}/trajectories.jsonl") as fh:
        for line in fh:
            t = json.loads(line)
            if t["id"] not in wanted:
                continue
            head = (f"[trajectory {t['id']} env={t['environment']} "
                    f"outcome={t['outcome']}] goal: {t['goal']}")
            for s in t["states"]:
                yield t["id"], (
                    f"{head}\nstep {s['state_index']} url={s.get('url','')}\n"
                    f"action: {s.get('action') or '(initial)'}\n"
                    f"thought: {(s.get('thought') or '')[:300]}\n"
                    f"observation: {(s.get('accessibility_tree') or '')[:TREE_CHARS]}"
                )


TRAJ_RE = re.compile(r"^\[trajectory ([0-9a-f-]+)")


def chunk_traj_id(text: str) -> str:
    m = TRAJ_RE.match(text)
    return m.group(1) if m else ""


def cmd_ingest() -> None:
    doms = domain_traj_ids()
    for dom, tids in doms.items():
        user = f"lmev2-{dom}"
        n = 0
        t0 = time.time()
        for _tid, chunk in iter_chunks(tids):
            _post("/v1/memories/", {"text": chunk, "user_id": user, "app_id": APP})
            n += 1
            if n % 2000 == 0:
                print(f"[{dom}] {n} chunks ({time.time()-t0:.0f}s)", flush=True)
        print(f"[{dom}] done: {n} chunks, {time.time()-t0:.0f}s", flush=True)


def _claude(prompt: str, retries: int = 3, timeout: int = 300) -> str:
    for attempt in range(retries):
        try:
            r = subprocess.run(["claude", "-p", prompt, "--max-turns", "1"],
                               capture_output=True, text=True, timeout=timeout)
            out = r.stdout.strip()
            if "Failed to authenticate" in out or (not out and attempt < retries - 1):
                time.sleep(90)
                continue
            return out
        except subprocess.TimeoutExpired:
            if attempt == retries - 1:
                return "(reader timeout)"
            time.sleep(30)
    return "(auth failure — rerun after /login)"


def reader(question: str, contexts: list[str]) -> str:
    ctx = "\n\n---\n\n".join(contexts)[:60_000]
    return _claude(
        "You are answering from an agent's memory of past sessions in this "
        f"environment.\n<memory>\n{ctx}\n</memory>\n\nQuestion: {question}\n\n"
        "Answer concisely from memory only. If memory does not contain the "
        "answer or the question's premise is wrong, say so explicitly.".replace(
            "{question}", question)
    )


# ---- BM25 도메인 인덱스 -------------------------------------------------------

class BM25:
    def __init__(self, pairs: list[tuple[str, str]]):
        import collections
        import math
        self.ids = [p[0] for p in pairs]
        self.texts = [p[1] for p in pairs]
        self.docs = [re.findall(r"[a-z0-9]+", t.lower()) for t in self.texts]
        df: dict[str, int] = collections.Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(1, n)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.tfs = [collections.Counter(d) for d in self.docs]

    def search(self, q: str, k: int, allowed: set) -> list[str]:
        qw = re.findall(r"[a-z0-9]+", q.lower())
        scored = []
        for i, tf in enumerate(self.tfs):
            if self.ids[i] not in allowed:
                continue
            s = sum(self.idf.get(w, 0) * tf[w] * 2.5 /
                    (tf[w] + 1.5 * (0.25 + 0.75 * len(self.docs[i]) / self.avgdl))
                    for w in qw if w in tf)
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [self.texts[i] for _, i in scored[:k]]


def _load_state() -> dict:
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def _save_state(state: dict) -> None:
    json.dump(state, open(STATE, "w"), ensure_ascii=False)


def cmd_run() -> None:
    qs = load_questions()
    hs = load_haystacks()
    state = _load_state()
    doms = domain_traj_ids()
    bm25 = {dom: BM25(list(iter_chunks(tids))) for dom, tids in doms.items()}
    print("BM25 indexes built", flush=True)

    def work(q: dict):
        if q["id"] in state and "auth failure" not in str(state[q["id"]]):
            return
        allowed = set(hs[q["id"]])
        raw = _post("/v1/memories/search/",
                    {"query": q["question"][:800], "user_id": f"lmev2-{q['domain']}",
                     "app_id": APP, "top_k": SEARCH_K}).get("results", [])
        f_ctx = [r["memory"] for r in raw
                 if chunk_traj_id(r["memory"]) in allowed][:TOP_K]
        b_ctx = bm25[q["domain"]].search(q["question"], TOP_K, allowed)
        state[q["id"]] = {
            "type": q["question_type"], "domain": q["domain"],
            "answer": q["answer"], "eval": q["eval_function"],
            "question": q["question"],
            "forget_answer": reader(q["question"], f_ctx) if f_ctx else "(no recall)",
            "bm25_answer": reader(q["question"], b_ctx) if b_ctx else "(no recall)",
        }
        _save_state(state)
        done = len([k for k in state if "forget_answer" in state.get(k, {})])
        print(f"[{done}/{len(qs)}] {q['question_type']}", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(work, qs))
    print("run complete", flush=True)


# ---- 채점 --------------------------------------------------------------------

def _norm(s: str, spec: str) -> str:
    s = s.strip()
    if "lower=true" in spec:
        s = s.lower()
    if "normalize_hyphen=true" in spec:
        s = s.replace("-", " ")
    return re.sub(r"\s+", " ", s)


def rule_score(row: dict) -> bool | None:
    spec = row["eval"]
    gold, ans = str(row["answer"]), row["forget_answer"]  # caller가 필드 지정
    if spec.startswith("mc_choice_match"):
        return _norm(gold, spec) in _norm(ans, spec)
    if spec.startswith("norm_phrase_set_match"):
        golds = [g.strip() for g in gold.split("|")]
        return any(_norm(g, spec) in _norm(ans, spec) for g in golds)
    return None  # LLM 심판 필요


def llm_judge(question: str, gold: str, answer: str) -> bool:
    out = _claude(
        f"Question: {question}\nReference answer: {gold}\nModel answer: {answer}\n\n"
        "Does the model answer convey the same conclusion as the reference "
        "(including correctly abstaining or rejecting a false premise when the "
        "reference does)? Reply with exactly one word: yes or no.", timeout=120)
    return out.strip().lower().startswith("y")


def cmd_score() -> None:
    state = _load_state()
    for qid, row in state.items():
        for side in ("forget", "bm25"):
            key = f"{side}_correct"
            if key in row:
                continue
            probe = dict(row, forget_answer=row[f"{side}_answer"])
            verdict = rule_score(probe)
            if verdict is None:
                verdict = llm_judge(row["question"], str(row["answer"]),
                                    row[f"{side}_answer"])
            row[key] = bool(verdict)
        _save_state(state)
        done = len([r for r in state.values() if "forget_correct" in r])
        if done % 25 == 0:
            print(f"scored {done}", flush=True)
    print("score complete", flush=True)


def cmd_report() -> None:
    from collections import defaultdict
    state = _load_state()
    rows = [r for r in state.values() if "forget_correct" in r]
    by = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        b = by[r["type"]]
        b[0] += r["forget_correct"]; b[1] += r["bm25_correct"]; b[2] += 1
    print(f"{'유형':30} {'forget':>8} {'BM25':>8} {'n':>4}")
    for t, (f, b, n) in sorted(by.items()):
        print(f"{t:30} {f:>8} {b:>8} {n:>4}")
    tf = sum(r['forget_correct'] for r in rows)
    tb = sum(r['bm25_correct'] for r in rows)
    print(f"\n합계: forget {tf}/{len(rows)} ({tf/len(rows)*100:.1f}%)  ·  "
          f"BM25 {tb}/{len(rows)} ({tb/len(rows)*100:.1f}%)")


if __name__ == "__main__":
    {"ingest": cmd_ingest, "run": cmd_run,
     "score": cmd_score, "report": cmd_report}[sys.argv[1]]()
