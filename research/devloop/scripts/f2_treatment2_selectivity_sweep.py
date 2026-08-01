#!/usr/bin/env python3
"""F2 처치 2 선택성 스윕 (사이클 22, 읽기 전용).

사이클 21(notes/cycle-21-f2-treatment2-projection.md)은 처치 2(phrase 매칭 자격
len>=2 & non-numeric + 상한 0.10)를 두 쿼리에만 투영했다: 퇴화한 devloop 고정
프롬프트(n=1)와 정상 주제 쿼리(n=1, 미국 이주). 결론("devloop 프롬프트에서 비선택적,
정상 쿼리엔 near-no-op")은 side당 n=1 + 손수 관련성 라벨(사이클9·18=관련, pash·Quant=노이즈)에
의존했다.

사이클 22는 그 결론을 **게임내성 지표**로 다양한 현실 쿼리에 재검한다. 손수 라벨 대신:

  (1) 랭크 보존 — 처치 2 투영 후 히트 순서가 바뀌는가? 현재 점수 순서 대 투영 점수
      순서의 pairwise 역전 수(Kendall tau). 0 역전이면 처치 2는 순서를 절대 안 바꾼다
      → 관련성 재순위기가 아니라 전역 임계 노브(비선택적). top-1 보존도 함께 본다.
  (2) junk 기여 CoV — 히트별 junk(자격 미달 토큰 기여)가 균일한가(단순 시프트,
      비선택적) 편중인가(특정 히트만 강등, 선택적). std/mean.

변환 대수: proj = cur - junk - max(0, qual - CAP). full-query bonus(0.25)는 상쇄.
per-hit 감소량이 히트마다 다르므로(junk·qual 편차) 랭크 역전은 실제로 가능 —
결과는 예단 불가.

score_memory 권위·phrase 분해는 사이클 21 f2_treatment2_projection.py와 동일(직접 비교
가능성 유지). 라이브 :8000 재생은 후보 검색 집합 확보용이며 점수는 현재 repo score_memory로
재계산(라이브는 구코드, /ready commit=null).

실행: .venv/bin/python research/devloop/scripts/f2_treatment2_selectivity_sweep.py
     (--fixture 로 저장된 히트 재사용, 재생 없이 재계산)"""
import json
import os
import statistics
import sys
import urllib.request

sys.path.insert(0, ".")
from forget.memory_engine import expanded_tokens, score_memory

THRESHOLD = 0.45          # hooks/forget_turnrecall.py SCORE_THRESHOLD 기본값
PHRASE_CAP = 0.10         # 처치 2 후보 상한
TOP_K = 8
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures_cycle22")

# 고정 devloop 프롬프트 (퇴화 앵커, 사이클 18·21과 동일 재생 — 직접 비교용).
DEVLOOP_PROMPT = (
    "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소(/Users/junghunkim/orca/"
    "<repo>, 브랜치 main-work)의 LOOP.md(헌장)와 "
    "research/devloop/cycle-prompt.md(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 "
    "따른다. 0단계 회상은 forget의 get_task_state(task_id='devloop')로 시작하고, "
    "너는 이 작업의 기억 없이 태어났으므로 복원 품질을 metrics.jsonl에 정직하게 채점해 남겨라"
)[:300]

# 현실 도그푸드 쿼리 셋 — 전부 canonical 스토어에 온토픽 기억이 있고 pash·heartbeat·Quant는
# 노이즈여야 하는 비퇴화 쿼리(주제가 서로 다름 → 재순위기라면 쿼리마다 다르게 재순위해야).
REALISTIC = {
    "us-relocation": (
        "정훈의 미국 이주 전략과 법인 설립 타이밍은 어떻게 잡아야 하나. "
        "YC 제출 전후로 델라웨어 법인을 세울지 보류할지, 비자·거주 계획과 함께 결정하고 싶다."),
    "e2ee-pivot": (
        "forget의 E2EE 피봇 전략은 무엇이었나. VC 스케일과 풀타임 솔로, 개발자 웻지, "
        "90일 검증 게이트를 어떻게 잡았는지 다시 확인하고 싶다."),
    "dogfood-setup": (
        "forget 도그푸딩 셋업은 어떻게 되어 있나. 사용자 메모리 레이어가 로컬 forget으로 "
        "전환된 launchd 구성과 ~/.forget 경로, 롤백 방법을 알려달라."),
    "researcher-identity": (
        "정훈의 연구자 정체성과 GTM을 실험 언어로 프레이밍하는 접근은 무엇인가. "
        "시장 진입을 가설·실험으로 다시 쓰는 방식을 정리해달라."),
    "b2b-pitch": (
        "창업원 B2B 발표 피드백은 무엇이었나. 강제성이 구매 조건이라는 점, 고객 먼저, "
        "DLP 인접 포지셔닝에 대한 조언을 다시 보고 싶다."),
    "compression-metrics": (
        "forget의 압축률 측정 3종은 무엇인가. 원시 압축비, rate-distortion 한 장, "
        "용량 곡선의 기준선과 목표 수치를 확인하고 싶다."),
    "codex-dual-write": (
        "Codex 이중 기억 쓰기 경로 함정은 무엇이었나. 데모·격리 세팅이 실제 스코프로 "
        "새는 문제와 ChatGPT 앱이 config.toml을 되돌리는 현상을 정리해달라."),
}


def rpc(name, arguments):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(
        "http://127.0.0.1:8000/mcp",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    body = json.loads(urllib.request.urlopen(req, timeout=15).read())
    return json.loads(body["result"]["content"][0]["text"])


def qualified(token: str) -> bool:
    """처치 2 매칭 자격: 길이 2+ 이며 순수 숫자가 아님."""
    return len(token) >= 2 and not token.isdigit()


def phrase_decompose(query: str, text: str):
    """score_memory phrase 항을 현행 규칙대로 재현·분해 (사이클 21과 동일).
    반환: (junk, qual, full_query_bonus)."""
    q_tokens = expanded_tokens(query)
    lowered = text.lower()
    junk = qual = 0.0
    for tok in q_tokens:
        if tok in lowered:
            if qualified(tok):
                qual += 0.02
            else:
                junk += 0.02
    fqb = 0.25 if query.lower() and query.lower() in lowered else 0.0
    return round(junk, 4), round(qual, 4), fqb


def project(cur, junk, qual):
    """처치 2 투영 총점 (완본: 자격 필터 + 상한 0.10). proj = cur - junk - max(0, qual-CAP)."""
    reduction = junk + max(0.0, qual - PHRASE_CAP)
    return max(0.0, min(1.0, round(cur - reduction, 4)))


def project_b(cur, junk, qual):
    """처치 2b (자격 필터만, 상한 없음): junk만 제거. proj = cur - junk.
    상한 성분을 분리해 무엇이 재순위를 유발하는지 가른다."""
    return max(0.0, min(1.0, round(cur - junk, 4)))


def rank_inversions(cur_list, proj_list):
    """cur 순서 대 proj 순서의 pairwise 불일치(역전) 수 + Kendall tau + top-1 보존.
    동점은 불일치로 세지 않음(strict sign 비교)."""
    n = len(cur_list)
    if n < 2:
        return 0, 1.0, True
    inv = 0
    for i in range(n):
        for j in range(i + 1, n):
            dc = cur_list[i] - cur_list[j]
            dp = proj_list[i] - proj_list[j]
            if (dc > 0 and dp < 0) or (dc < 0 and dp > 0):
                inv += 1
    pairs = n * (n - 1) / 2
    tau = round(1 - 2 * inv / pairs, 4)
    top1_cur = max(range(n), key=lambda k: cur_list[k])
    top1_proj = max(range(n), key=lambda k: proj_list[k])
    return inv, tau, top1_cur == top1_proj


def analyze(label, query):
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    fixture = os.path.join(FIXTURE_DIR, f"{label}.json")
    if "--fixture" not in sys.argv:
        res = rpc("search_memories", {"query": query, "top_k": TOP_K})
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

    rows = []
    for h in slim:
        cur = score_memory(query, h)
        junk, qual, fqb = phrase_decompose(query, h["memory"])
        rows.append({"cur": cur, "proj": project(cur, junk, qual),
                     "proj_b": project_b(cur, junk, qual), "junk": junk, "qual": qual,
                     "kind": (h.get("metadata") or {}).get("assertion_kind") or "memory",
                     "text": h["memory"][:38].replace("\n", " ")})

    cur_list = [r["cur"] for r in rows]
    inv, tau, top1_kept = rank_inversions(cur_list, [r["proj"] for r in rows])
    inv_b, tau_b, top1_kept_b = rank_inversions(cur_list, [r["proj_b"] for r in rows])
    junks = [r["junk"] for r in rows]
    junk_mean = round(statistics.mean(junks), 4) if junks else 0.0
    junk_cov = round(statistics.pstdev(junks) / junk_mean, 3) if junk_mean else 0.0
    drops = sum(1 for r in rows if r["cur"] >= THRESHOLD > r["proj"])
    above = sum(1 for r in rows if r["cur"] >= THRESHOLD)
    # 상한이 top-1 훼손을 유발하는가: 완본이 top1을 깨지만 2b는 지키면 = 상한 탓.
    cap_breaks_top1 = (not top1_kept) and top1_kept_b

    print(f"\n=== [{label}]  q_tokens={len(expanded_tokens(query))}  "
          f"n_hits={len(rows)}  above_thr={above}")
    print(f"    T2(자격+상한): inv={inv} tau={tau} top1_kept={top1_kept} DROP={drops}/{above}")
    print(f"    T2b(자격만):   inv={inv_b} tau={tau_b} top1_kept={top1_kept_b}   "
          f"junk_mean={junk_mean} junk_CoV={junk_cov}  cap_breaks_top1={cap_breaks_top1}")
    for r in sorted(rows, key=lambda x: -x["cur"]):
        mark = "DROP" if (r["cur"] >= THRESHOLD > r["proj"]) else ("·" if r["cur"] >= THRESHOLD else "")
        print(f"    {r['cur']:6.3f} ->T2 {r['proj']:6.3f} ->T2b {r['proj_b']:6.3f}  "
              f"junk={r['junk']:.3f} qual={r['qual']:.3f}  {mark:>4}  "
              f"[{r['kind'][:10]:>10}] {r['text']}")
    return {"label": label, "inversions": inv, "tau": tau, "top1_kept": top1_kept,
            "tau_b": tau_b, "top1_kept_b": top1_kept_b, "cap_breaks_top1": cap_breaks_top1,
            "junk_mean": junk_mean, "junk_cov": junk_cov, "drops": drops, "above": above,
            "n_hits": len(rows)}


def main():
    print(f"THRESHOLD={THRESHOLD}  CAP={PHRASE_CAP}  TOP_K={TOP_K}")
    print("selectivity = 처치2가 히트 순서를 바꾸는가(재순위기) vs 전역 시프트(임계 노브).")
    summ = [analyze("devloop-meta(퇴화앵커)", DEVLOOP_PROMPT)]
    for label, q in REALISTIC.items():
        summ.append(analyze(label, q))

    print("\n\n===== 요약 (게임내성 지표) =====")
    print(f"{'query':>22} {'abv':>3} | {'T2_tau':>6} {'T2_top1':>7} | "
          f"{'T2b_tau':>7} {'T2b_top1':>8} | {'cap_brk':>7}")
    for s in summ:
        rr = (s["tau"] < 1.0) or (not s["top1_kept"])
        flag = "  <-T2 RERANK" if rr else ""
        print(f"{s['label']:>22} {s['above']:3d} | {s['tau']:6.3f} {str(s['top1_kept']):>7} | "
              f"{s['tau_b']:7.3f} {str(s['top1_kept_b']):>8} | "
              f"{str(s['cap_breaks_top1']):>7}{flag}")
    realistic = [s for s in summ if s["label"] != "devloop-meta(퇴화앵커)"]
    rr2 = sum(1 for s in realistic if s["tau"] < 1.0 or not s["top1_kept"])
    rr2b = sum(1 for s in realistic if s["tau_b"] < 1.0 or not s["top1_kept_b"])
    t1_break2 = sum(1 for s in realistic if not s["top1_kept"])
    t1_break2b = sum(1 for s in realistic if not s["top1_kept_b"])
    cap_driven = sum(1 for s in realistic if s["cap_breaks_top1"])
    print(f"\n현실 쿼리 {len(realistic)}개:")
    print(f"  T2 (자격+상한): 재순위 {rr2}개, top-1 훼손 {t1_break2}개")
    print(f"  T2b(자격만):    재순위 {rr2b}개, top-1 훼손 {t1_break2b}개")
    print(f"  top-1 훼손이 상한 성분 탓(T2 깨고 T2b 지킴): {cap_driven}개")
    print("H1(사전등록): 현실 쿼리 전부 순서보존 → 비선택적. 하나라도 재순위면 반증.")


if __name__ == "__main__":
    main()
