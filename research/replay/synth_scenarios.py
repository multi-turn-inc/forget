#!/usr/bin/env python3
"""원칙-증류 시나리오 합성 v0 (골격) — run1 표면-암기 실패의 처방.

Constitutional AI/context distillation 계보: 행동 원칙을 훈련 예시에 직접
넣지 않고, 원칙을 지시로 걸어 **다양한 작업 상황**에 응답을 생성시킨 뒤
(상황 → 원칙-준수 응답)을 SFT/선호 데이터로 쓴다. 모델이 암기하는 것이
단일 틀이 아니라 원칙 자체가 되게.

생성 엔진 = Spark 27B (품질 배치).

run2 스펙 확정 (2026-08-12 조사 a7ef994 근거):
- N = 원칙당 고유 시나리오 25+ (총 100+; 2507.04889: 100건이 임계, 이후 체감)
- 도메인 혼합 필수 + 생성 후 임베딩 cos>0.8 중복 제거 (Only-IF 2402.10891)
- 주 기법 = 원칙-증류: SFT 정답 축자가 아니라 "원칙을 시스템으로 건 자기
  분포"에 KL (Prompt Baking 2409.13697 / OPCD 2602.12275) — 여기선 근사로
  시스템-조건 생성 응답을 SFT 타깃으로 (완전 KL 증류는 run3)
- 안정화 기본값: EOS/pad 분리(1순위!) · NEFTune · 1에폭 · 일반지시 5% 혼합
- 선호: DPO 1epoch lr5e-7 β0.1, 단 고유 프롬프트 수 ≥ 쌍 수 (2603.20100 붕괴 회피)
"""
from __future__ import annotations

import json
from pathlib import Path

R = Path(__file__).resolve().parent

# 4대 행동 원칙 — run1의 A급 교정에서 귀납. 각 원칙에 A급 정본이 시드로 붙는다.
PRINCIPLES = [
    {"key": "unverified_claim",
     "principle": "코드나 설정을 바꾼 뒤 실물(화면·출력)을 확인하지 않았으면 '됐다/완료'라고 보고하지 말 것. 바꾼 것과 확인한 것을 구분하고, 판정은 사용자에게 위임하라.",
     "gold_srcs": ["beb0a628-3c3d-4470-a20c-d68a9b8ced2f.jsonl:4952",
                   "15eb2d38-134b-4ac1-a98d-dd652743fb28.jsonl:1149"]},
    {"key": "early_stop",
     "principle": "사용자 승인 대기가 생겨도 멈추지 말 것. 대기 항목을 명시하되, 기다리는 동안 진행 가능한 일을 이어서 하라.",
     "gold_srcs": ["c3da929c-c92d-4034-9abd-13b1ab90d722.jsonl:1602",
                   "c3da929c-c92d-4034-9abd-13b1ab90d722.jsonl:669"]},
    {"key": "failure_framing",
     "principle": "실패를 '더 좋은 발견'으로 포장하지 말 것. 첫 문장에서 실패를 실패라 명명하고, 부산물은 부산물이라 표기하라.",
     "gold_srcs": ["532b5d8a-9990-47ae-985b-926dbdd9a544.jsonl:4934"]},
    {"key": "overclaim",
     "principle": "방어 못 할 주장(과장된 해자·천장 근접 등)을 하지 말 것. 약점을 스스로 먼저 말하고, 방어 가능한 것만 주장하라.",
     "gold_srcs": ["532b5d8a-9990-47ae-985b-926dbdd9a544.jsonl:4460",
                   "fa8de18c-403e-4bff-a411-acb03bd320d2.jsonl:1292"]},
]

# 시나리오 생성 프롬프트 — 원칙 하나에서 서로 다른 작업 표면 N개를 뽑는다.
# (핵심: 표면 다양성이 목표. 같은 상황 재진술이 아니라 다른 도메인·다른 작업.)
SCENARIO_GEN = """다음은 AI 어시스턴트가 지켜야 할 행동 원칙이다:

「{principle}」

이 원칙이 시험되는 서로 다른 작업 상황을 {n}개 만들어라. 각 상황은
도메인(코딩·글쓰기·조사·배포·분석 등)과 구체 과제가 서로 달라야 하고,
원칙을 어기기 쉬운 유혹이 자연스럽게 깔려 있어야 한다. 상황만, 한 줄씩,
번호 없이."""

# 각 시나리오에서 원칙-준수 응답 생성 — 원칙을 시스템으로 걸고 응답.
RESPONSE_GEN_SYSTEM = "너는 다음 원칙을 체화한 어시스턴트다: 「{principle}」 이 원칙을 자연스럽게 따르되, 원칙을 명시적으로 인용하지는 말고 행동으로만 드러내라."


def load_gold() -> dict:
    return {json.loads(l)["src"]: json.loads(l)["gold"]
            for l in (R / "dpo_gold_v0.jsonl").open()}


N_PER_PRINCIPLE = 30  # 고유 시나리오 (총 120 > 임계 100)


def build_seed_manifest() -> list:
    gold = load_gold()
    manifest = []
    for p in PRINCIPLES:
        seeds = [gold[s] for s in p["gold_srcs"] if s in gold]
        manifest.append({"key": p["key"], "principle": p["principle"],
                         "seed_count": len(seeds), "seeds": seeds})
    (R / "principle_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


# --- Spark 생성 (이 함수는 Spark에서 실행; 로컬은 매니페스트만) ---
def generate_on_spark(manifest: list, gen_fn) -> None:
    """gen_fn(system, user, temp) → str. 각 원칙 → N 시나리오 → 시나리오별 응답."""
    sft_rows, seen_scen = [], set()
    for m in manifest:
        raw = gen_fn("", SCENARIO_GEN.format(principle=m["principle"], n=N_PER_PRINCIPLE), 0.9)
        scenarios = [s.strip(" -*\t") for s in raw.splitlines() if len(s.strip()) > 15]
        for scen in scenarios:
            if scen in seen_scen:
                continue
            seen_scen.add(scen)
            resp = gen_fn(RESPONSE_GEN_SYSTEM.format(principle=m["principle"]), scen, 0.5)
            sft_rows.append({"key": m["key"], "messages": [
                {"role": "user", "content": scen},
                {"role": "assistant", "content": resp}]})
    with (R / "train_sft_v1.jsonl").open("w") as fh:
        for r in sft_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"원칙-증류 SFT: {len(sft_rows)}건 (고유 시나리오)")


if __name__ == "__main__":
    m = build_seed_manifest()
    print(f"원칙 {len(m)}개 · 시드 {sum(x['seed_count'] for x in m)}개 · 목표 시나리오 {len(m)*N_PER_PRINCIPLE}")
    print("Spark 생성은 spark_synth.py로 (27B), 중복 필터는 임베딩 단계에서")
