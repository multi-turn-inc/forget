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

## 추기 (2026-08-24 새벽 — 계기 고장 4호 공시와 교정 등록, 숫자 보기 전 고정)

  P-L2-C(예산 무릎 스윕)는 설계 그대로 **불활성**이었다: assemble_context 내부
  검색이 top_k 기본 10이라 후보 풀이 수도꼭지에서 이미 좁혀져(문항당 ~7건 ·
  1.1k tok), 예산 2k/4k/8k는 하류 노브였다. 두 스윕 런이 바이트 동일 — 부산물로
  파이프라인 결정론(temp 0)은 검증됐다. 원장 정정: B의 −23pp는 "예산 2k의 조립"이
  아니라 "**후보 10건**의 조립"의 성적이다.

  P-L2-C′ (교정 스윕): LME_B_TOPK=84로 A와 동일한 후보 풀을 주고 예산 {2k,4k,8k}.
      무릎 규칙 동일 — B84(b) ≥ A−2pp인 최소 b* = "조립 등가점", 절감비(17.3k/b*)
      병기. 8k에서도 A−5pp 미달이면 이 리더·이 세분성에서 단발 조립 열세 확정.
  P-L2-D (더듬기 — 정훈 발의 "기억을 한 턴만에 끝내야 되는 건가. 사람은 부족한
      기억을 더듬어가며 길게 끄집어낸다"): D = 실제 캡슐(top_k 10 · 예산 2k, B와
      같은 출발선) + SEARCH 루프 ≤5회(회당 top_k 10, 기수번 기억 중복 제거).
      리더가 "SEARCH: <검색어>" 한 줄을 내면 추가 회수해 이어붙이고 다시 읽는다.
      채택: D ≥ A−5pp 그리고 평균 누적 토큰 ≤ 6k → "작은 캡슐 + 더듬기" 제품 경로.
      부분 지지: D ≥ B+10pp → 더듬기 유효, 상한은 리더 역량.
      기각: D < B+5pp → 이 리더에서 더듬기 무효 (도구 규약·리더 교체로 이월).

## 추기 2 (2026-08-24 오후 — D2 절제 등록, 정훈 발의 "메타인지를 단순히
   명시화한다고 해결이 될까?" — 그 회의 자체를 절제 실험으로)

  팔 E (D2a, 언어화 단독): 더듬기 앞에 리더가 증거 체크리스트를 먼저 쓰고
      (계획 호출 1회) 그 목록을 시스템에 얹은 뒤 D와 동일 루프.
  팔 G (D2b, 외부화 게이트): 체크리스트 없음. 발판이 잰 신호를 주입 —
      ①증거 스팬 계수(컨텍스트의 서로 다른 날짜 수) ②직전 회수 강도
      (검색 최고 점수, 약함 표시) ③다중증거 휴리스틱(how many/compare/
      total/order 등 — gold 유형 아님, 질문 문면만) 해당 시 0라운드
      즉답을 1회 반려하고 최소 1회 탐침 강제.
  판정 (숫자 보기 전 고정, D0=0.660 · n=100 동일 표본):
      E − D < +3pp 그리고 G − E ≥ +5pp → "메타인지는 언어화가 아니라
      외부화" 테제 채택 (정훈 회의의 실증).
      E − D ≥ +5pp → 언어화도 유효 — 테제 기각, 회의가 틀림으로 판정.
      G − D < +3pp → 외부화도 무효 — 0층 신호로는 부족, 1층(세계모델
      기대)으로 병소 이월.

사용: MEM1_DB_PATH=<벤치DB> .venv/bin/python scripts/lme_l2_ab.py [--n 100] [--arms ABCDEG]
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


MULTI_EVIDENCE_RE = re.compile(
    r"how many|how much (more|less)|total|compare|first|last|order|difference|"
    r"between|each time|every time|all the|몇 |비교|순서|총 |차이", re.I)


def evidence_checklist(question: str, qdate: str) -> str:
    """팔 E(D2a)의 계획 호출 — 언어화 메타인지 단독의 효과를 절제한다."""
    return llm("You plan evidence retrieval for a memory system. List the distinct "
               "pieces of evidence (facts, dates, sessions) needed to answer the "
               "question. 3-6 short bullet lines. Do NOT answer the question.",
               f"Question (asked on {qdate}): {question}", max_tokens=180).strip()[:600]


def read_groping(question: str, qdate: str, context: str, searcher, max_rounds: int = 5,
                 checklist: str | None = None, external_gates: bool = False):
    """팔 D/E/G — 더듬기(strategic recall). 사람의 인출은 한 턴이 아니다: 단서를
    만들고(생성), 맞는지 보고(재인), 다시 더듬는다. 그 최소 기계화 — 도구 호출
    규약이 없는 로컬 리더로도 돌게, SEARCH: 한 줄 규약으로 루프를 돈다.

    checklist(팔 E): 리더가 스스로 쓴 증거 목록을 시스템에 얹음 — 언어화 단독.
    external_gates(팔 G): 발판이 잰 신호를 주입 — 증거 스팬 계수·직전 회수
    강도, 그리고 다중증거 휴리스틱 문항의 0-탐침 즉답을 1회 반려(강제 최소
    탐침 — 외과 체크리스트 원리: 내성이 아니라 의무라서 작동한다).

    반환 (답, 누적 컨텍스트 토큰, 검색 횟수, 최종 컨텍스트 토큰).
    """
    shown = context
    total_tok = 0
    n_search = 0
    last_strength: float | None = None
    forced_used = False
    for round_i in range(max_rounds + 1):
        last = round_i == max_rounds
        system = ("You answer questions about the user based ONLY on the provided memory excerpts. "
                  f"The question is asked on {qdate}. Use the memory dates to resolve any relative "
                  "time references. "
                  + ("You may not search again. Answer concisely from the excerpts; if the needed "
                     "information is not there, say you don't know."
                     if last else
                     "If the excerpts fully answer the question, answer concisely. If anything "
                     "needed is missing, do NOT guess: reply with exactly one line in the form\n"
                     "SEARCH: <3-8 search keywords, include absolute dates if relevant>"))
        if checklist:
            system += "\n\nEvidence you determined you need:\n" + checklist
        instrument = ""
        if external_gates:
            dates = set(re.findall(r"\[(\d{4}-\d{2}-\d{2})\]", shown))
            instrument = f"\n[instrument] evidence span in context: {len(dates)} distinct dates"
            if last_strength is not None:
                instrument += (f"\n[instrument] last retrieval strength: {last_strength:.2f}"
                               + (" (weak — evidence may be missing)" if last_strength < 0.5 else ""))
        user = f"<memories>\n{shown}\n</memories>{instrument}\n\nQuestion: {question}\nAnswer concisely."
        total_tok += token_est(user)
        out = llm(system, user)
        m = re.match(r"^\s*SEARCH:\s*(.+)$", out, re.IGNORECASE)
        if (m is None and external_gates and not forced_used and n_search == 0
                and not last and MULTI_EVIDENCE_RE.search(question)):
            forced_used = True
            shown += ("\n[instrument] This question likely needs multiple evidence pieces "
                      "(comparison/counting/ordering). You must SEARCH at least once before answering.")
            continue
        if not m or last:
            # 누적(스테이트리스 지불)과 최종 컨텍스트(캐시 리더 지불) 둘 다 —
            # 프리픽스 캐시가 있으면 재독 라운드는 거의 공짜라 후자가 실효 비용.
            return out, total_tok, n_search, token_est(shown)
        n_search += 1
        extra, strength = searcher(m.group(1).strip()[:300])
        last_strength = strength
        shown = shown + "\n" + (extra or "(추가 회수 결과 없음 — 같은 검색을 반복하지 말 것)")
    return out, total_tok, n_search, token_est(shown)


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
    # 표본은 항상 n=100 정본 목록에서 앞 N개 — L1과 같은 문항·같은 벤치 스코프를
    # 보장한다 (스모크가 --n에 따라 다른 문항을 뽑아 빈 스코프를 때리던 결함 수리).
    N_CANON = 100
    sample = []
    for qtype, items in sorted(by_type.items()):
        k = max(1, round(N_CANON * len(items) / len(pool)))
        sample.extend(rng.sample(items, min(k, len(items))))
    sample = (sample[:N_CANON] if len(sample) > N_CANON else sample)[: args.n]

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

            probe = search_memories({"query": question, "filters": {"user_id": scope}, "top_k": 84})
            if not probe.get("results"):
                print(f"  [{qi}] {inst['question_id']} 스코프 비어 있음 — 건너뜀", flush=True)
                continue
            if "A" in args.arms:
                lines = [f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}"
                         for m in probe.get("results") or []]
                # 공개 상한 (1차 실행 후 정정 기록): 일부 multi-session 덤프가 24k
                # 서버 창을 초과해 400 — 덤프도 리더 창에서 잘리는 것이 실무이므로
                # A = "top-84, 추정 18k 토큰까지, 순위 보존·꼬리 탈락"으로 명시한다.
                # 바늘은 거의 항상 상위권(MRR 0.914)이라 증거 탈락은 드물다.
                while lines and sum(len(l) for l in lines) // 4 > 18000:
                    lines.pop()
                ctx = "\n".join(lines)
                hyp = read_answer(question, qdate, ctx)
                row["A"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["A_tok"] = token_est(ctx)
                row["A_hyp"] = hyp[:200]

            if any(a in args.arms for a in "BCDEG"):
                def assembled(query: str):
                    r = assemble_context({"query": query, "filters": {"user_id": scope},
                                          "top_k": int(os.environ.get("LME_B_TOPK", "10")),
                                          "budget_tokens": int(os.environ.get("LME_B_BUDGET", "2000")), "record_trace": False,
                                          "disable_resume_workspace": True})
                    memories = r.get("memories") or []
                    lines = [f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}"
                             for m in memories]
                    return "\n".join(lines), {str(m.get("id")) for m in memories}

            if "B" in args.arms:
                ctx, _ = assembled(question)
                hyp = read_answer(question, qdate, ctx)
                row["B"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["B_tok"] = token_est(ctx)
                row["B_hyp"] = hyp[:200]

            if "C" in args.arms:
                try:
                    expansion = expand_query(question, qdate)
                except Exception:
                    expansion = ""
                ctx, _ = assembled(f"{question} {expansion}".strip())
                hyp = read_answer(question, qdate, ctx)
                row["C"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["C_tok"] = token_est(ctx)
                row["C_exp"] = expansion[:150]
                row["C_hyp"] = hyp[:200]

            def make_groper():
                ctx0, seen = assembled(question)
                def searcher(q: str):
                    res = search_memories({"query": q, "filters": {"user_id": scope}, "top_k": 10})
                    results = res.get("results") or []
                    top = max((float(m.get("score") or 0) for m in results), default=0.0)
                    lines = []
                    for m in results:
                        mid = str(m.get("id"))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        lines.append(f"- [{str(m.get('created_at'))[:10]}] {str(m.get('memory'))}")
                    return "\n".join(lines), top
                return ctx0, searcher

            if "D" in args.arms:
                ctx0, searcher = make_groper()
                hyp, dtok, nsrch, dctx = read_groping(question, qdate, ctx0, searcher)
                row["D"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["D_tok"] = dtok
                row["D_srch"] = nsrch
                row["D_ctx"] = dctx
                row["D_hyp"] = hyp[:200]

            if "E" in args.arms:
                ctx0, searcher = make_groper()
                chk = evidence_checklist(question, qdate)
                hyp, etok, nsrch, ectx = read_groping(question, qdate, ctx0, searcher,
                                                      checklist=chk)
                row["E"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["E_tok"] = etok + token_est(chk)
                row["E_srch"] = nsrch
                row["E_ctx"] = ectx
                row["E_chk"] = chk[:200]
                row["E_hyp"] = hyp[:200]

            if "G" in args.arms:
                ctx0, searcher = make_groper()
                hyp, gtok, nsrch, gctx = read_groping(question, qdate, ctx0, searcher,
                                                      external_gates=True)
                row["G"] = judge(inst["question_type"], question, str(inst["answer"]), hyp)
                row["G_tok"] = gtok
                row["G_srch"] = nsrch
                row["G_ctx"] = gctx
                row["G_hyp"] = hyp[:200]

            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            marks = " ".join(f"{a}={'O' if row.get(a) else 'X'}" for a in args.arms if a in row)
            print(f"  [{qi}] {inst['question_type'][:18]:18s} {marks} "
                  f"(tok A:{row.get('A_tok','-')} B:{row.get('B_tok','-')} C:{row.get('C_tok','-')}"
                  f" D:{row.get('D_tok','-')}/{row.get('D_srch','-')}회)",
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
    if "D" in args.arms:
        srch = [r.get("D_srch", 0) for r in rows if "D" in r]
        if srch:
            print(f"P-L2-D 부기: 평균 검색 {sum(srch)/len(srch):.1f}회 · "
                  f"검색 0회 {sum(1 for s in srch if s == 0)}건 · "
                  f"5회 소진 {sum(1 for s in srch if s >= 5)}건 (판정은 A·B 참조점 대조로 원장에서)")
    for qtype in sorted({r['type'] for r in rows}):
        line = f"  {qtype:26s}"
        for arm in args.arms:
            a, n = acc(arm, {qtype})
            line += f" {arm}:{a:.2f}(n={n})"
        print(line)


if __name__ == "__main__":
    main()
