#!/usr/bin/env python3
"""F2 처치 2 투영 (사이클 21, 읽기 전용) — 코드 쓰기 전 반증가능 예측 선등록용.

사이클 18(notes/cycle-18-f2-root-cause.md)이 지배 원인 C1을 특정했다: score_memory의
phrase_bonus가 쿼리 토큰마다 부분 문자열 매칭 시 +0.02를 상한 없이 합산하는데, CJK
bigram 토크나이저가 길이 1 런(단문자 조사 '로'·'를'·'이'·'의')과 숫자('0'·'5')를 토큰으로
내보내므로, 장문 한국어 기억이 주제 무관하게 +0.3 안팎을 확보하고 임계 0.45가 비구속이 된다.

P8 처치 2 후보(frictions.md·predictions.md 등록): phrase_bonus 매칭 자격 강화
(len(token) >= 2 AND not token.isdigit()) + 합산 상한(0.10). 이 스크립트는 그 변환을
라이브 :8000 재생 히트에 read-only로 투영해, 처치 2가 배선되기 전에 정량 예측을 만든다.

- current: 현재 repo score_memory (권위) + phrase 성분 분해(junk 토큰 vs 자격 토큰 기여)
- projected: phrase per-token 합을 자격 필터+상한으로 대체했을 때의 총점
- 판정: F2 상습 노이즈(pash·heartbeat·stance)가 임계 아래로 떨어지는가(비구속→구속),
  그리고 주제 일치 기억이 과억제되지 않는가(양방향 반증).

repo 루트에서 실행: .venv/bin/python research/devloop/scripts/f2_treatment2_projection.py
히트 텍스트/점수는 f2_treatment2_hits.json으로 저장(재현: --replay 없이 재계산)."""
import json
import os
import sys
import urllib.request

sys.path.insert(0, ".")
from forget.memory_engine import expanded_tokens, score_memory

# 사이클 18 f2_replay/f2_components와 동일한 고정 재생 쿼리 (직접 비교 가능성 유지).
PROMPT = (
    "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소(/Users/junghunkim/orca/"
    "<repo>, 브랜치 main-work)의 LOOP.md(헌장)와 "
    "research/devloop/cycle-prompt.md(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 "
    "따른다. 0단계 회상은 forget의 get_task_state(task_id='devloop')로 시작하고, "
    "너는 이 작업의 기억 없이 태어났으므로 복원 품질을 metrics.jsonl에 정직하게 채점해 남겨라"
)[:300]

# 선택성 프로브: 특정 주제(미국 이주·법인 타이밍) 쿼리 — 온토픽 canonical 기억
# (junghun-us-relocation-goal)이 존재하고 pash·heartbeat류는 노이즈여야 하는 비퇴화 쿼리.
# 고정 devloop 프롬프트는 전부 devloop-메타라 coverage/jaccard가 노이즈/관련을 못 가른다.
SELECTIVITY_QUERY = (
    "정훈의 미국 이주 전략과 법인 설립 타이밍은 어떻게 잡아야 하나. "
    "YC 제출 전후로 델라웨어 법인을 세울지 보류할지, 비자·거주 계획과 함께 결정하고 싶다."
)

THRESHOLD = 0.45          # hooks/forget_turnrecall.py SCORE_THRESHOLD 기본값
PHRASE_CAP = 0.10         # 처치 2 후보 상한 (cycle-18 처치 후보 1)
HITS_FIXTURE = os.path.join(os.path.dirname(__file__), "f2_treatment2_hits.json")


def rpc(name, arguments):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(
        "http://127.0.0.1:8000/mcp",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=10).read())
    return json.loads(body["result"]["content"][0]["text"])


def qualified(token: str) -> bool:
    """처치 2 매칭 자격: 길이 2+ 이며 순수 숫자가 아님."""
    return len(token) >= 2 and not token.isdigit()


def phrase_decompose(query: str, text: str):
    """score_memory의 phrase 항을 현행 규칙대로 재현하고 junk/자격 기여로 분해한다.
    반환: (raw_per_token, junk_contrib, qualified_contrib, full_query_bonus)."""
    q_tokens = expanded_tokens(query)
    lowered = text.lower()
    junk = qual = 0.0
    for tok in q_tokens:
        if tok in lowered:
            if qualified(tok):
                qual += 0.02
            else:
                junk += 0.02
    full_query_bonus = 0.25 if query.lower() and query.lower() in lowered else 0.0
    return round(junk + qual, 4), round(junk, 4), round(qual, 4), full_query_bonus


def analyze(label, query, fixture):
    replay = "--fixture" not in sys.argv
    if replay:
        res = rpc("search_memories", {"query": query, "top_k": 8})
        hits = res.get("results") or []
        slim = [{"id": str(h.get("id", "")), "memory": str(h.get("memory") or ""),
                 "score": float(h.get("score") or 0), "categories": h.get("categories") or [],
                 "updated_at": h.get("updated_at"),
                 "metadata": {"assertion_kind": (h.get("metadata") or {}).get("assertion_kind")}}
                for h in hits]
        with open(fixture, "w") as f:
            json.dump({"query": query, "hits": slim}, f, ensure_ascii=False, indent=2)
    else:
        with open(fixture) as f:
            slim = json.load(f)["hits"]

    q_tokens = expanded_tokens(query)
    print(f"\n=== [{label}] query[:56]={query[:56]!r}")
    print(f"    q_tokens n={len(q_tokens)}  THRESHOLD={THRESHOLD}  CAP={PHRASE_CAP}")
    print(f"{'cur':>6} {'proj':>6} {'phr_cur':>7} {'junk':>6} {'qual':>6} {'phr_proj':>8} "
          f"{'cross':>5} {'kind':>10}  memory[:42]")
    for h in slim:
        cur = score_memory(query, h)
        raw, junk, qual, fqb = phrase_decompose(query, h["memory"])
        cur_phrase = raw + fqb
        proj_phrase = min(qual, PHRASE_CAP) + fqb            # 자격 토큰만 + 상한
        proj = max(0.0, min(1.0, round(cur - cur_phrase + proj_phrase, 4)))
        crosses = cur >= THRESHOLD > proj
        kind = h.get("metadata", {}).get("assertion_kind") or "memory"
        text = h["memory"][:42].replace("\n", " ")
        print(f"{cur:6.3f} {proj:6.3f} {cur_phrase:7.3f} {junk:6.3f} {qual:6.3f} "
              f"{proj_phrase:8.3f} {'DROP' if crosses else '-':>5} {kind:>10}  {text}")


def main():
    analyze("devloop-replay(고정 메타)", PROMPT, HITS_FIXTURE)
    analyze("selectivity(미국 이주 주제)", SELECTIVITY_QUERY,
            HITS_FIXTURE.replace(".json", "_sel.json"))
    print("\n요약: 'DROP' = 현재 임계 통과했으나 처치 2 투영에서 임계 아래로 (회상 침묵).")
    print("선택성 판정은 selectivity 쿼리에서: 온토픽 기억 생존 & pash·heartbeat류 DROP이면 성립.")


if __name__ == "__main__":
    main()
