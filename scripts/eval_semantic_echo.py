"""의미 메아리 v2 판정기 — 6그램 문면 일치 vs 임베딩 유사도 사용판정. (본선 2)

## 사전 등록 (숫자를 보기 전에 고정, 2026-08-23)

자료: 실기억 60건 → Qwen3.8-27B가 "이 기억을 근거로 답하라"로 생성한 사용 문장
(인용/의역 자연 혼합 — 의역 강제는 6그램에게 불공정하므로 하지 않았다).
  양성 = (기억 i, 사용문 i) / 음성 = (기억 i, 사용문 j≠i) 무작위 3배.

탐지기:
  v1 = 현행 6그램: 정규화 후 probe(80자)의 부분문자열 포함 (forget_capture._echoed)
  v2 = 서버 임베딩(effective_embedding_stack 그대로 — 지금은 bge-small-en) 코사인
  v2+ = v1 OR (v2 ≥ θ)   ← 실배선 후보 (문면 적중은 그대로 살린다)

판정 (등록):
  기준점 = 음성 오탐률(FPR) ≤ 5%가 되는 문턱에서의 양성 재현율(recall).
  채택: v2+의 recall이 v1의 recall보다 ≥ +15pp 높으면 v2+ 배선.
  기각: +5pp 미만이면 현행 유지 — 영어 전용 인코더가 한국어 의역을 못 잡는다는
        뜻이므로, 이 항목은 다국어 임베딩 게이트(백필) 뒤로 이월.
  회색(+5~15pp): 배선하되 라벨 metadata에 v1/v2 근거를 병기해 실사용 검증.

위험 등록: 서버 임베딩이 영어 전용이라 v2가 질 수 있다 — 그 부정 결과도 산출이다
(다국어 전환 게이트의 근거가 된다).

사용: .venv/bin/python scripts/eval_semantic_echo.py <echo_pairs.jsonl>
"""
from __future__ import annotations

import json
import random
import re
import sys
import unicodedata

PROBE_MAX_LEN = 80      # 현행 훅과 동일 조건
PROBE_MIN_LEN = 12
NEG_RATIO = 3


def normalize(text: str) -> str:
    # forget_capture._normalize와 동일 규칙 (독립 구현 — 훅은 이 저장소 밖이다)
    text = unicodedata.normalize("NFKC", str(text)).lower()
    return re.sub(r"[\s\W_]+", "", text)


def v1_hit(memory: str, usage: str) -> bool:
    probe = normalize(memory)[:PROBE_MAX_LEN]
    return len(probe) >= PROBE_MIN_LEN and probe in normalize(usage)


def main() -> None:
    pairs = [json.loads(l) for l in open(sys.argv[1])]
    rng = random.Random(20260823)
    positives = [(p["memory"], p["usage"]) for p in pairs]
    negatives = []
    for p in pairs:
        others = [q for q in pairs if q["i"] != p["i"]]
        for q in rng.sample(others, min(NEG_RATIO, len(others))):
            negatives.append((p["memory"], q["usage"]))

    from forget.providers import embed_text
    from forget.memory_engine import cosine_similarity

    def v2_sim(memory: str, usage: str) -> float:
        return cosine_similarity(embed_text(memory), embed_text(usage))

    pos_sims = [v2_sim(m, u) for m, u in positives]
    neg_sims = [v2_sim(m, u) for m, u in negatives]
    pos_v1 = [v1_hit(m, u) for m, u in positives]
    neg_v1 = [v1_hit(m, u) for m, u in negatives]

    # 문턱: 음성 오탐 ≤5%가 되는 최소 유사도 (등록된 기준점)
    neg_sorted = sorted(neg_sims, reverse=True)
    theta = neg_sorted[max(0, int(len(neg_sorted) * 0.05) - 1)] + 1e-6 if neg_sorted else 1.0

    v1_recall = sum(pos_v1) / len(pos_v1)
    v1_fpr = sum(neg_v1) / len(neg_v1)
    v2_recall = sum(s >= theta for s in pos_sims) / len(pos_sims)
    v2p_recall = sum(h or s >= theta for h, s in zip(pos_v1, pos_sims)) / len(pos_sims)
    v2p_fpr = sum(h or s >= theta for h, s in zip(neg_v1, neg_sims)) / len(neg_sims)

    print(f"양성 {len(positives)} · 음성 {len(negatives)} · 임베딩 문턱 θ={theta:.3f} (음성 FPR 5% 기준)")
    print(f"{'탐지기':8s} {'재현율':>7s} {'오탐률':>7s}")
    print(f"{'v1 6그램':8s} {v1_recall:7.2f} {v1_fpr:7.2f}")
    print(f"{'v2 임베딩':8s} {v2_recall:7.2f} {'0.05':>7s}")
    print(f"{'v2+ (OR)':8s} {v2p_recall:7.2f} {v2p_fpr:7.2f}")
    delta = (v2p_recall - v1_recall) * 100
    print(f"\nΔ재현율(v2+ − v1) = {delta:+.0f}pp → ", end="")
    if delta >= 15:
        print("채택 (등록선 ≥ +15pp)")
    elif delta < 5:
        print("기각 — 현행 유지, 다국어 임베딩 게이트 뒤로 이월 (등록선 < +5pp)")
    else:
        print("회색지대 — 배선하되 근거 병기 (등록선 +5~15pp)")
    import statistics
    print(f"양성 유사도 중위 {statistics.median(pos_sims):.3f} · 음성 중위 {statistics.median(neg_sims):.3f}")


if __name__ == "__main__":
    main()
