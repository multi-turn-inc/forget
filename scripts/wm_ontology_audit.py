"""P-WM-1 — 상태 온톨로지 커버리지 감사 (2026-08-24, 탑다운 헌장 L3).

등록 (숫자 보기 전 고정, docs/personal-world-model-design.md):
  실수요 표본(도그푸드 턴리콜 질의 50 + LME 100문항)을 "어느 상태 유형이
  답했겠는가"로 분류한다.
  - 채택: 5유형이 표본의 ≥90%를 덮고, 각 유형 점유 ≥2%.
  - 부분: 커버 80~90% → 미커버 군집에서 6번째 유형 후보 도출.
  - 기각: <80% → 온톨로지 재설계.
  - 어떤 유형 점유 <2% → 그 유형은 v0에서 제거(사변적 지방).

원장 접근은 SELECT만 (context_traces에서 질의 표본). 분류기 = 로컬 Qwen
(터널 18812, temp 0, json_schema 강제) — $0.

## P-WM-1 판정 (2026-08-24 1차 런): 기각 — 커버 66% (<80%) → 재설계 발동.
해부: 도그푸드 82%(none 9는 대부분 원천 소음 — 비회상 턴) · LME 58%,
none이 temporal 20/27·multi-session 13/26에 집중 = 날짜 붙은 사건들의
세기·정렬·집계 수요. v0의 구조적 실수 = 현재(상태)만 있고 과거-구조
(시간축 사건)가 없음. disposition 1.3%·relation 0.7% → <2% 규칙으로 제거
(relation은 entity 속성으로 흡수, disposition은 기억층 잔류).

## P-WM-1b (v1 재감사, 숫자 보기 전 등록): 유형 = entity·event·open_loop·
routine. 문턱 동일 (≥90% & 유형별 ≥2% 채택 / 80~90 부분 / <80 재재설계).
예측: event가 none 군집 대부분을 흡수, 원천 소음 잔존으로 커버 ~90% 부근.
(v1로 본문 갱신 — v0 결과는 git 이력 + wm_ontology_audit.jsonl에 보존.
 용어 주석: 정훈 지적으로 대외 표면에서는 '온톨로지' 대신 '상태 유형'을 쓴다.)
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "research/longmemeval-data/longmemeval_s_cleaned.json"
LLM = os.environ.get("LME_LLM_URL", "http://127.0.0.1:18812/v1/chat/completions")
LEDGER = os.path.expanduser("~/.forget/forget.sqlite3")
OUT = os.environ.get("WM_AUDIT_OUT", str(REPO / "research/eval/wm_ontology_audit_v1_1.jsonl"))

# v1.1 (계기 수리 2건, 실행 로그에 공시): ① 요약의 TYPES[:5]가 none을 커버로
# 오계상해 100%로 인쇄되던 버그 → 상태 유형만 명시 집계. ② none이 "수요인데
# 미커버"와 "기억 수요 아님"을 섞던 설계 결함 → not_a_demand 분리. 분모는
# 진성 수요만: 커버리지 = 상태유형 / (전체 − not_a_demand − error).
TYPES = ["entity", "event", "open_loop", "routine", "none", "not_a_demand"]
STATE_TYPES = ["entity", "event", "open_loop", "routine"]
SCHEMA = {"type": "object", "properties": {"type": {"enum": TYPES}},
          "required": ["type"], "additionalProperties": False}

PROMPT = """개인 AI 기억 시스템의 상태 유형 감사. 아래 질의/질문에 답하려면
어떤 상태 유형이 1차로 필요한지 하나만 고르라.

- entity: 사람·프로젝트·장소·도구의 현재 상태/속성 ("X가 뭐였지", "그 설정은")
- event: 과거에 일어난 일의 시간축 기록 — 날짜·순서·횟수·간격·값의 집계
  ("언제였지", "몇 번", "순서대로", "얼마나 차이", "지난번 ~때")
- open_loop: 진행 중 과제·약속·마감·미결 질문 ("어디까지 했지", "하기로 한 것")
- routine: 반복 구조·주기 ("매주 하던", "보통 언제", 빈도·습관)
- none: 기억에 대한 수요이긴 하나 위 넷으로는 답할 수 없음
- not_a_demand: 애초에 기억 수요가 아닌 발화 (지시·내레이션·감탄·텔레메트리)

질의: {q}"""


def classify(q: str) -> str:
    body = {"model": "qwen", "temperature": 0.0, "max_tokens": 24,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "t", "schema": SCHEMA, "strict": True}},
            "messages": [{"role": "user", "content": PROMPT.format(q=q[:400])}]}
    req = urllib.request.Request(LLM, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                out = json.loads(resp.read())["choices"][0]["message"]["content"]
            return json.loads(out)["type"]
        except Exception:
            if attempt == 2:
                return "error"
            time.sleep(3)
    return "error"


def sample_dogfood(n: int, rng: random.Random) -> list[str]:
    conn = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)
    try:
        rows = [r[0] for r in conn.execute(
            "SELECT DISTINCT query FROM context_traces WHERE length(query) > 10")]
    finally:
        conn.close()
    return rng.sample(rows, min(n, len(rows)))


def sample_lme(n: int, rng: random.Random) -> list[dict]:
    data = json.load(open(DATA))
    pool = [q for q in data if not str(q["question_id"]).endswith("_abs")]
    by_type: dict[str, list] = {}
    for q in pool:
        by_type.setdefault(q["question_type"], []).append(q)
    sample = []
    for qtype, items in sorted(by_type.items()):
        k = max(1, round(n * len(items) / len(pool)))
        sample.extend(rng.sample(items, min(k, len(items))))
    return sample[:n]


def main() -> None:
    rng = random.Random(20260824)
    items = ([{"src": "dogfood", "q": q} for q in sample_dogfood(50, rng)]
             + [{"src": f"lme:{i['question_type']}", "q": i["question"]}
                for i in sample_lme(100, rng)])
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["q"] for l in open(OUT)}
    with open(OUT, "a") as fout:
        for idx, item in enumerate(items):
            if item["q"] in done:
                continue
            item["type"] = classify(item["q"])
            fout.write(json.dumps(item, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"  [{idx}] {item['type']:12s} ← {item['q'][:60]}", flush=True)

    rows = [json.loads(l) for l in open(OUT)]
    counts = Counter(r["type"] for r in rows)
    total = len(rows)
    demand = [r for r in rows if r["type"] not in ("not_a_demand", "error")]
    cov = (sum(1 for r in demand if r["type"] in STATE_TYPES) / len(demand)) if demand else 0.0
    print(f"\nP-WM-1b 판정 재료 — 표본 {total} · 진성 수요 {len(demand)} "
          f"(도그푸드 {sum(1 for r in rows if r['src']=='dogfood')} · LME {sum(1 for r in rows if r['src'].startswith('lme'))})")
    for t in TYPES + ["error"]:
        if counts.get(t):
            share = counts[t] / len(demand) if (demand and t in STATE_TYPES + ["none"]) else counts[t] / total
            print(f"  {t:12s} {counts[t]:4d} (수요 내 {share:5.1%})" if t in STATE_TYPES + ["none"]
                  else f"  {t:12s} {counts[t]:4d} (표본 내 {share:5.1%})")
    print(f"  커버리지(진성 수요 분모): {cov:.1%}")
    verdict = ("채택" if cov >= 0.9 and all(sum(1 for r in demand if r["type"] == t)/max(len(demand),1) >= 0.02 for t in STATE_TYPES)
               else "부분 — 추가 유형 후보 도출" if cov >= 0.8
               else "기각 — 상태 유형 재설계")
    thin = [t for t in STATE_TYPES if sum(1 for r in demand if r["type"] == t)/max(len(demand),1) < 0.02]
    print(f"  등록 판정: {verdict}" + (f" · 제거 후보(<2%): {thin}" if thin else ""))
    print("AUDIT_DONE", flush=True)


if __name__ == "__main__":
    main()
