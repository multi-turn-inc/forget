"""LME L2 구성 A/B — 덤프 vs 조립 vs 조립+접지. (2026-08-24, 정훈 승인 "등록하고 걸자")

L1 교정판이 밝힌 것: 바늘@84 = 1.00 — 검색 도달은 이 벤치마크에서 만점이다.
공표 81.8%와의 ~18pp 격차는 하류(구성·독해)에 산다. 그러므로 이 실험은 검색이
아니라 **리더가 읽는 것**을 팔로 가른다 — 우리 제품 명제("조립이 곧 제품",
"2천 토큰이 11.5만을 이긴다")의 84턴 스케일 외부 실측이다.

팔 (문항마다 동일 인게스트, 동일 리더·판정 — 다른 것은 컨텍스트뿐):
  A 덤프   top-84 검색 턴을 날짜와 함께 나열 (Tier-0 재현 · ~9천 토큰대)
  B 조립   assemble_context 예산 2,000 토큰 (신뢰 랭킹·중복 제거·기아 방지·앵커 렌더)
  C 접지   B + 질의 확장 — 로컬 LLM이 질문을 검색어로 재작성하며 상대 날짜를
           절대 날짜로 해소 ("two months ago Wednesday" → 2023-02-01). 시뮬레이션
           밴드의 최소형이며 1차 표적은 temporal·multi-session.

리더·판정: Qwen3.8-27B @ 4090 (터널 18812), temp 0. 판정 프롬프트는 하네스
JUDGE_TEMPLATES 문면 그대로 — 판정자 편향은 팔 간 상쇄된다 (공표 숫자와의
절대 비교는 불가하며 주장하지 않는다. 그것은 L3 게이트의 몫).

## 사전 등록 판정 (숫자를 보기 전에 고정)

  P-L2-A (조립 대 덤프): B − A ≥ +3pp → 조립 우위 실증.
      |B − A| < 3pp → 동급 — 토큰 1/4~1/5로 같은 정확도면 실질 승리로 기록하되
      "우위"라 부르지 않는다. B − A ≤ −3pp → 조립이 정보를 잃는다: 문항별
      덤프-정답·조립-오답 사례를 해부해 병소(선별/예산/렌더)를 특정한다.
  P-L2-B (접지): temporal+multi-session 부분집합에서 C − B ≥ +5pp → 접지 채택.
      +2pp 미만 → 기각. 타 유형에서 C − B ≤ −3pp면 부작용으로 채택 불가.
  부기: 팔별 평균 컨텍스트 토큰을 반드시 병기한다 — 효율 축이 주장의 절반이다.

사용: MEM1_DB_PATH=<벤치DB> .venv/bin/python scripts/lme_l2_ab.py [--n 100] [--arms ABC]
      (이어달리기: 출력 JSONL의 완료 문항은 건너뛴다)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "research/longmemeval-data/longmemeval_s_cleaned.json"
LLM = os.environ.get("LME_LLM_URL", "http://127.0.0.1:18812/v1/chat/completions")
OUT = os.environ.get("LME_L2_OUT", str(REPO / "research/eval/lme_L2_ab_rows.jsonl"))

JUDGE = {
    "default": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "temporal-reasoning": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. \n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {q}\n\nCorrect Answer: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {q}\n\nRubric: {a}\n\nModel Response: {r}\n\nIs the model response correct? Answer yes or no only.",
}


def llm(system: str, user: str, max_tokens: int = 256) -> str:
    body = {"model": "qwen", "temperature": 0.0, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request(LLM, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(4 * (attempt + 1))
    return ""


def token_est(text: str) -> int:
    return max(1, len(text) // 4)


def read_answer(question: str, qdate: str, context: str) -> str:
    system = ("You answer questions about the user based ONLY on the provided memory excerpts. "
              f"The question is asked on {qdate}. Use the memory dates to resolve any relative "
              "time references. If the needed information is not in the excerpts, say you don't know.")
    user = f"<memories>\n{context}\n</memories>\n\nQuestion: {question}\nAnswer concisely."
    return llm(system, user)


def judge(qtype: str, question: str, answer: str, hyp: str) -> bool:
    template = JUDGE.get(qtype, JUDGE["default"])
    out = llm("You are a strict grader.",
              template.format(q=question, a=answer, r=hyp), max_tokens=8)
    return out.strip().lower().startswith("yes")


def expand_query(question: str, qdate: str) -> str:
    out = llm("You rewrite questions into search keywords for a memory database. "
              "Resolve every relative date reference into absolute dates (YYYY-MM-DD) "
              f"using the question date {qdate}. Output ONLY comma-separated keywords, "
              "phrases and absolute dates. No explanations.",
              question, max_tokens=80)
    return re.sub(r"\s+", " ", out)[:300]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--arms", default="ABC")
    ap.add_argument("--seed", type=int, default=20260824)
    args = ap.parse_args()
    if "forget.sqlite3" in os.environ.get("MEM1_DB_PATH", ""):
        sys.exit("실원장 금지 — 벤치 DB를 지정하라")

    from forget.store import assemble_context, search_memories

    data = json.load(open(DATA))
    rng = random.Random(args.seed)
    pool = [q for q in data if not str(q["question_id"]).endswith("_abs")]
    by_type: dict[str, list] = {}
    for q in pool:
        by_type.setdefault(q["question_type"], []).append(q)
    sample = []
    for qtype, items in sorted(by_type.items()):
        k = max(1, round(args.n * len(items) / len(pool)))
        sample.extend(rng.sample(items, min(k, len(items))))
    sample = sample[: args.n] if len(sample) > args.n else sample

    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            try:
                done.add(json.loads(line)["qid"])
            except Exception:
                pass
    t0 = time.time()
    with open(OUT, "a") as fout:
        for qi, inst in enumerate(sample):
            if inst["question_id"] in done:
                continue
            scope = f"lme-{inst['question_id']}"
            question, qdate = inst["question"], inst.get("question_date", "")
            row = {"qid": inst["question_id"], "type": inst["question_type"]}

            if "A" in args.arms:
                res = search_memories({"query": question, "filters": {"user_id": scope}, "top_k": 84})
                lines = [f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}"
                         for m in res.get("results") or []]
                ctx = "\n".join(lines)
                hyp = read_answer(question, qdate, ctx)
                row["A"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["A_tok"] = token_est(ctx)
                row["A_hyp"] = hyp[:200]

            if "B" in args.arms or "C" in args.arms:
                def assembled(query: str):
                    r = assemble_context({"query": query, "filters": {"user_id": scope},
                                          "budget_tokens": 2000, "record_trace": False,
                                          "disable_resume_workspace": True})
                    memories = r.get("memories") or []
                    lines = [f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}"
                             for m in memories]
                    return "\n".join(lines)

            if "B" in args.arms:
                ctx = assembled(question)
                hyp = read_answer(question, qdate, ctx)
                row["B"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["B_tok"] = token_est(ctx)
                row["B_hyp"] = hyp[:200]

            if "C" in args.arms:
                try:
                    expansion = expand_query(question, qdate)
                except Exception:
                    expansion = ""
                ctx = assembled(f"{question} {expansion}".strip())
                hyp = read_answer(question, qdate, ctx)
                row["C"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["C_tok"] = token_est(ctx)
                row["C_exp"] = expansion[:150]
                row["C_hyp"] = hyp[:200]

            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            marks = " ".join(f"{a}={'O' if row.get(a) else 'X'}" for a in args.arms if a in row)
            print(f"  [{qi}] {inst['question_type'][:18]:18s} {marks} "
                  f"(tok A:{row.get('A_tok','-')} B:{row.get('B_tok','-')} C:{row.get('C_tok','-')})",
                  flush=True)

    rows = [json.loads(l) for l in open(OUT)]
    seen = {}
    for r in rows:
        seen[r["qid"]] = r
    rows = list(seen.values())
    print(f"\n{len(rows)}문항 · {time.time()-t0:.0f}s")

    def acc(arm, subset=None):
        vals = [r for r in rows if arm in r and (subset is None or r["type"] in subset)]
        return (sum(1 for r in vals if r[arm]) / len(vals), len(vals)) if vals else (float("nan"), 0)

    def tok(arm):
        vals = [r[f"{arm}_tok"] for r in rows if f"{arm}_tok" in r]
        return sum(vals) / len(vals) if vals else 0

    print(f"{'팔':4s} {'정확도':>7s} {'n':>4s} {'평균 토큰':>9s}")
    for arm in args.arms:
        a, n = acc(arm)
        print(f"{arm:4s} {a:7.3f} {n:4d} {tok(arm):9.0f}")
    if "A" in args.arms and "B" in args.arms:
        d = (acc("B")[0] - acc("A")[0]) * 100
        print(f"\nP-L2-A: B−A = {d:+.1f}pp → "
              + ("조립 우위" if d >= 3 else ("동급 (토큰 효율로 실질 승리)" if d > -3 else "조립 손실 — 해부 필요")))
    if "B" in args.arms and "C" in args.arms:
        target = {"temporal-reasoning", "multi-session"}
        d = (acc("C", target)[0] - acc("B", target)[0]) * 100
        side = (acc("C", None)[0] - acc("B", None)[0]) * 100
        print(f"P-L2-B: (temporal+multi) C−B = {d:+.1f}pp → "
              + ("접지 채택" if d >= 5 else ("기각" if d < 2 else "회색")) + f" · 전체 부작용 {side:+.1f}pp")
    for qtype in sorted({r['type'] for r in rows}):
        line = f"  {qtype:26s}"
        for arm in args.arms:
            a, n = acc(arm, {qtype})
            line += f" {arm}:{a:.2f}(n={n})"
        print(line)


if __name__ == "__main__":
    main()
