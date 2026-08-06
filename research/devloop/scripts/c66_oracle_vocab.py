#!/usr/bin/env python3
"""c66 — audit-60 R3 집행: 적대-어휘 재실행 (read-only, 2026-08-07).

R3 문면: "c57~c59 커밋된 C 질의를 **선언문 작성자가 아닌 손이 다른 어휘로 재구성**해
분모 안정성을 판정하라. 결과값은 예단하지 않는다."

설계 — 하나만 흔든다:
  c59_oracle_replay.py를 **모듈로 임포트**해 replay/classify/seen/created_at_of와
  SAMPLE(선언문·birth 컷오프·seen_prefixes)을 그대로 재사용한다. 게이트 상수·필터
  순서·SEEN 판정·시간여행 컷오프는 커밋본과 바이트 동일이며, **변하는 입력은 regime C의
  질의 문자열 하나뿐**이다. 따라서 분모 변동은 전부 어휘에 귀속된다.

측정 3종:
  ① 분모 = regime C UNSEEN-PASS 건수 (silent_miss 후보 모집단) — 변이별
  ② pass 집합 안정성 = 변이 쌍 Jaccard + 전 변이 교집합/합집합 (동일성 = 정규화 전문 sha1)
  ③ near-miss 대역 [gate-0.05, gate) 멤버십 churn — c58 발견(A10 캐비앗이 어휘에 따라
     분모 안·밖을 넘나든 것)이 어휘 변이에서 재현되는지

변이 7종 (V0만 커밋본, V1~V6은 이 손이 작성):
  V0 orig     c59 커밋본 topical_query — 재현 기준선
  V1 syn      한국어 동의어 치환 (같은 개념, 다른 낱말)
  V2 abstract 전문어 0 — 현상만 평문으로 서술
  V3 en       영어 — 언어 자체를 바꾼 어휘 충격
  V4 minimal  핵심 2어절
  V5 method   방법론 어휘만 (사이클 고유 발견축 제거)
  V6 derived  기계적 파생 — 선언문에서 장르 접두만 제거, 사람의 어휘 선택 0

캐비앗(정직 고지): 이 손은 c58 선언문의 작성자가 아니고 c59 질의의 작성자도 아니지만,
변이 작성 **전에** V0 원문을 읽었다. 따라서 V1~V6은 V0과 독립 추출이 아니다 — "다른
어휘"라는 R3 요건은 충족하나 "독립 표본"은 아니다. V6은 이 오염이 없는 유일한 변이다
(기계적 파생, 사람 선택 없음).

    .venv/bin/python research/devloop/scripts/c66_oracle_vocab.py
"""
import hashlib
import importlib.util
import itertools
import os

HERE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location(
    "c59_oracle_replay", os.path.join(HERE, "c59_oracle_replay.py"))
c59 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c59)

SAMPLE = c59.SAMPLE
GATE = c59.hook.SCORE_THRESHOLD
NEAR_MISS_BAND = c59.NEAR_MISS_BAND
TOP_K_C = 25  # c59 regime C와 동일 — pass 분모는 top_k=15와 동일 집합(랭킹 접두)


def _derived_query():
    """V6 — 선언문에서 장르 접두만 기계적으로 제거. 사람의 어휘 선택 0.

    c59 주석이 명시한 접두 우회 목적을 문자열 조작만으로 달성한다:
    '[devloop] 사이클 58 선택+결정 (...):' 머리를 잘라 본문만 남기고 300자 절단
    (regime A/B와 같은 절단 폭이라 어휘만 다른 비교가 된다).
    """
    d = SAMPLE["declaration"]
    body = d.split("):", 1)[1] if "):" in d else d
    return " ".join(body.split())[:300]


VARIANTS = [
    ("V0 orig", SAMPLE["topical_query"]),
    ("V1 syn", (
        "오라클 사후 재생 대조 질의 어휘 치환 표본 판박이 교체 장르 부풀림 "
        "점수 문턱 미달 누락 조용한 실패 계상 모집단 판정"
    )),
    ("V2 abstract", (
        "관련된 기억이 저장소에 있었는데도 표면에 떠오르지 않아 작업이 그것을 "
        "모르고 지나간 실패를 나중에 되짚어 찾아내는 방법과 그 방법의 한계"
    )),
    ("V3 en", (
        "oracle replay of a work declaration, silent recall failure detection, "
        "score gate false negatives near the threshold, denominator stability, "
        "genre prefix matching inflation, sample parameterization"
    )),
    ("V4 minimal", "조용한 실패 오라클 재생"),
    ("V5 method", (
        "재생 스크립트 SAMPLE 교체 top_k 확대 게이트 임계 near-miss 대역 병기 "
        "시간여행 컷오프 SEEN 판정"
    )),
    ("V6 derived", _derived_query()),
]


def ident(row):
    """동일성 = 정규화 전문의 sha1 (c59 dedup의 text[:60]보다 강한 키)."""
    return hashlib.sha1(row["text"].encode("utf-8")).hexdigest()[:12]


def measure(query):
    rows = c59.replay(TOP_K_C, query)
    live = [r for r in rows if not r["post"]]  # POST-c58 행은 규약상 분모 밖
    passes = [r for r in live if r["verdict"] == "pass"]
    unseen_pass = [r for r in passes if not r["seen"]]
    lo = GATE - NEAR_MISS_BAND
    near = [r for r in live if lo <= r["score"] < GATE]
    return {
        "rows": len(rows), "post": len(rows) - len(live),
        "pass": passes, "unseen_pass": unseen_pass, "near": near,
        "top_score": max((r["score"] for r in rows), default=0.0),
    }


def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def main():
    n = SAMPLE["cycle"]
    print("c66 — audit-60 R3 적대-어휘 재실행 (분모 안정성)")
    print(f"표본: c{n} (c59 커밋본 SAMPLE 그대로) | gate={GATE} | "
          f"top_k(C)={TOP_K_C} | near-miss band={NEAR_MISS_BAND}")
    print(f"시간여행 컷오프: {SAMPLE['birth']} | SEEN 접두 {len(SAMPLE['seen_prefixes'])}건")
    print("고정: replay/classify/seen/created_at_of/SAMPLE = c59 커밋본 임포트. "
          "변하는 입력 = regime C 질의 1개.\n")

    results = {}
    pass_sets = {}
    for label, q in VARIANTS:
        m = measure(q)
        results[label] = m
        pass_sets[label] = {ident(r) for r in m["pass"]}
        print(f"--- {label} ---")
        print(f"  query[:100]: {q[:100]}")
        print(f"  rows={m['rows']} POST제외={m['post']} pass={len(m['pass'])} "
              f"UNSEEN-PASS(분모)={len(m['unseen_pass'])} near-miss={len(m['near'])} "
              f"top_score={m['top_score']:.4f}")
        for r in m["unseen_pass"]:
            print(f"    [분모] score={r['score']:.4f} created={r['created']} "
                  f"{r['text'][:120]}")

    print("\n=== ① 분모(UNSEEN-PASS) 변이별 ===")
    denoms = {k: len(v["unseen_pass"]) for k, v in results.items()}
    for k, v in denoms.items():
        print(f"  {k:<12} {v}")
    lo, hi = min(denoms.values()), max(denoms.values())
    print(f"  범위: {lo}~{hi}  (스윙 {hi - lo})  "
          f"{'변동 없음' if lo == hi else '**어휘에 따라 변동**'}")

    print("\n=== ② pass 집합 안정성 (동일성 = 전문 sha1) ===")
    sizes = {k: len(v) for k, v in pass_sets.items()}
    print(f"  pass 크기: " + "  ".join(f"{k}={v}" for k, v in sizes.items()))
    inter = set.intersection(*pass_sets.values()) if pass_sets else set()
    union = set.union(*pass_sets.values()) if pass_sets else set()
    print(f"  전 변이 교집합={len(inter)}  합집합={len(union)}  "
          f"핵심 비율={len(inter) / len(union):.2f}" if union else "  합집합 0")
    print("  쌍별 Jaccard:")
    for a, b in itertools.combinations(pass_sets, 2):
        print(f"    {a:<12} × {b:<12} = {jaccard(pass_sets[a], pass_sets[b]):.2f}")
    only = {k: pass_sets[k] - inter for k in pass_sets}
    print("  변이 고유분(교집합 밖) 건수: " +
          "  ".join(f"{k}={len(v)}" for k, v in only.items()))

    print("\n=== ③ near-miss 대역 churn ===")
    near_sets = {k: {ident(r) for r in v["near"]} for k, v in results.items()}
    n_union = set.union(*near_sets.values()) if near_sets else set()
    print(f"  대역 합집합={len(n_union)}건. 변이별: " +
          "  ".join(f"{k}={len(v)}" for k, v in near_sets.items()))
    all_pass = union
    crossers = n_union & all_pass
    print(f"  **경계 교차자**(어떤 변이에선 pass, 다른 변이에선 near-miss)={len(crossers)}건")
    for h in crossers:
        for k in results:
            for r in results[k]["pass"] + results[k]["near"]:
                if ident(r) == h:
                    where = "pass" if r["verdict"] == "pass" and r["score"] >= GATE else "near"
                    print(f"    {h} {k:<12} score={r['score']:.4f} {where:<5} "
                          f"{r['text'][:90]}")
                    break

    print("\nCAVEAT: ① c59 캐비앗 전부 승계(현재-스토어 재생·게이트가 '관련'의 오라클·"
          "판정은 노트에서) ② V1~V6은 V0 원문을 읽은 뒤 작성 — '다른 어휘' 충족, "
          "'독립 표본' 아님. V6만 오염 없음(기계적 파생) ③ near-miss는 top_k=25 창으로 "
          "절단된 하한 관측 ④ 이 스크립트는 분모의 **어휘 민감도**만 잰다. 분모가 "
          "안정이어도 게이트 자체의 위음성(c58 발견)은 별개로 남는다.")


if __name__ == "__main__":
    main()
