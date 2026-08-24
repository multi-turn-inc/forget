"""P-W-1 데이터 준비 — 게이트 모방 어댑터의 교재 분할 (2026-08-24).

## P-W-1 등록 (숫자 보기 전 고정)

과제: 게이트 모방 — (원발화) → (이 사람이 남길 사실들). "무엇을 기억할
사람인가"의 취향 델타. 사실 저장이 아니라 편집 정책의 학습 (CLS v2 교정
준수: 사실은 컨텍스트로, 습관은 가중치로).

분할: **시간 홀드아웃** — ts 정렬 후 최후 15%. 무작위 분할 금지(근사중복
누수). few-shot 예시 5개는 훈련부 꼬리에서.
베이스: Qwen3-4B (첫 방법 검증용 소형 — 방법이 서면 8B/27B 승급, 공시).
대조: 같은 베이스 + 5-shot 프롬프트 (무어댑터) vs 어댑터 + 0-shot.
계기: 사실 수준 그리디 매칭 F1 — 예측/골드 사실을 정규화 유사도 ≥0.55로
그리디 짝짓기, 예시별 P/R/F1의 매크로 평균. 홀드아웃 중 200표본(시드
20260824)만 생성 평가 (비용 공시).
판정: 채택 어댑터 F1 ≥ 베이스+10pp / 기각 ≤ 베이스+3pp / 사이 회색.
비용: 로컬 $0. 훈련 중 llama-server 정지 필요 — 정지 시간을 병기한다.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "research/eval/wm_sft_v0.jsonl"
OUT_DIR = REPO / "research/eval"

SYSTEM = ("You are the memory gate of a personal AI memory system. Given a raw "
          "utterance from the user's work sessions, output ONLY the durable facts "
          "worth remembering long-term, one per line prefixed with '- '. Keep each "
          "fact short and self-contained. Match the owner's taste for what matters.")


def main() -> None:
    rows = [json.loads(l) for l in open(SRC) if json.loads(l).get("kind") == "gate_pair"]
    rows.sort(key=lambda r: r["ts"])
    cut = int(len(rows) * 0.85)
    train, holdout = rows[:cut], rows[cut:]

    def clean_input(raw: str) -> str:
        # 계기 수리 (P-W-1 1차 런 부검): input 필드는 서버가 ensure_ascii로
        # 저장한 JSON 문자열 — 그대로 쓰면 모델이 \uXXXX 이스케이프를 보고
        # 흉내 낸다 (베이스 0.000의 뿌리, 어댑터 승리의 오염원: 형식 해독 학습).
        # JSON 파싱해 정상 한글 대화문으로 복원한다.
        try:
            msgs = json.loads(raw)
            if isinstance(msgs, list):
                return "\n".join(
                    f"{m.get('role', '?')}: {m.get('content', '')}" for m in msgs
                    if isinstance(m, dict))
        except (ValueError, TypeError):
            pass
        return raw

    def fmt(r):
        return {"system": SYSTEM, "user": clean_input(r["input"])[:1500],
                "assistant": "\n".join(f"- {f}" for f in r["facts"])}

    with open(OUT_DIR / "w1_train.jsonl", "w") as f:
        for r in train:
            f.write(json.dumps(fmt(r), ensure_ascii=False) + "\n")
    with open(OUT_DIR / "w1_holdout.jsonl", "w") as f:
        for r in holdout:
            f.write(json.dumps({**fmt(r), "gold_facts": r["facts"]}, ensure_ascii=False) + "\n")
    fewshot = [fmt(r) for r in train[-5:]]
    json.dump(fewshot, open(OUT_DIR / "w1_fewshot.json", "w"), ensure_ascii=False)
    eval_idx = sorted(random.Random(20260824).sample(range(len(holdout)),
                                                     min(200, len(holdout))))
    json.dump(eval_idx, open(OUT_DIR / "w1_eval_idx.json", "w"))
    print(f"훈련 {len(train)} · 홀드아웃 {len(holdout)} (시간 분할 경계 ts={holdout[0]['ts'][:19]}) "
          f"· 평가 표본 {len(eval_idx)}")


if __name__ == "__main__":
    main()

# ── P-W-1c 등록 (2026-08-25 새벽 — 대장 #14 처방 집행: "교재 늘리면 되지"의
#    유혹 앞에 학습 곡선 먼저. P-W-2(GRPO) 착수의 전제 작업) ──────────────
# 과제: 데이터 절제 곡선 — 같은 조리법(P-W-1b: r16/a32, 2ep, bs2×ga8, lr1e-4,
#   clean_input, 홀드아웃·평가 200표본 동일)으로 훈련 표본만 {1k, 2k} 중첩
#   무작위 부분집합(시드 20260825, 2k ⊃ 1k). 시간 접두가 아니라 무작위 중첩 —
#   홀드아웃 누수는 시간 분할이 이미 막았고, 곡선은 동분포 표본이 정직하다.
#   생성: rng(20260825)로 전체에서 2000개 표집 후 그중 1000개 재표집.
# 참조점: F1(3.15k) = 0.653 (P-W-1b) · base+5shot = 0.620.
# 판정 (숫자 보기 전 고정):
#   포화: F1(3.15k) − F1(1k) < +2pp → 대장 #14에 "우리 도메인 실측: 1k 조기
#     포화" 갱신, P-W-2는 현 교재 그대로(확대 논외).
#   미포화: 곡선 단조 증가 그리고 F1(3.15k) − F1(1k) ≥ +4pp → 교재 확대가
#     레버 — P-W-2 전에 게이트 쌍 추가 채굴을 선행 후보로 승격.
#   사이/비단조: 회색 — 곡선 형태 공시 후 P-W-2 진행(확대 논외).
# 비용: 로컬 $0. llama-server 정지 필요 — 정지·재개 시각 병기 의무.
#
# ── P-W-1c 판정 (2026-08-25 03:52 실측, llama-server 정지 02:47~재개 03:54 KST) ──
# F1: 1k 0.662 (P 0.772) · 2k 0.659 (P 0.769) · 3.15k 0.653 (P 0.758, P-W-1b)
# → F1(3.15k) − F1(1k) = −0.9pp < +2pp = **포화 확정** (곡선 평평~미하강).
# 해석: 게이트 취향은 저복잡도 정책 — 1k 쌍에서 이미 완성 (Word2World 2만
# 궤적 대비 20배 이른 포화; 선별성 이득도 1k에서 완성형 0.772). 무릎의
# 하한은 미측정 — 1k가 최소 측정점. 집행: 대장 #14 "우리 도메인 1k 조기
# 포화"로 갱신, P-W-2는 현 교재 그대로(확대 논외), 롤아웃 반복 비용 함의는
# 긍정적(소수 정예 교재로 충분).

# ── P-W-2 정식 등록 (2026-08-24 밤, 정훈 우려 "SFT를 쓰면 의미없는 게 될 수도"를
#    구속으로 전환. 타산지석 #1 인용) ─────────────────────────────────────
# 지위: P-W-1b는 결과 무관 **계기 전용** — SFT 어댑터는 어디에도 배포하지
#   않는다. 취향 델타의 정본 경로 = P-W-2.
# 방법: 사실-집합 정렬 GRPO — 롤아웃 어댑터가 사실 목록을 생성하면 원장
#   정답과의 그리디 매칭 F1(결정론, LLM 심판 불요)을 보상으로. HumanLM의
#   상태-정렬 원리 × RLVR-World의 검증가능 보상의 결혼.
# 판정(숫자 보기 전): P-W-2 F1 ≥ P-W-1b F1 + 8pp → GRPO 경로 채택.
#   ≤ +2pp → SFT로 충분(선별 과제엔 모방 병리 미전이로 판정, 대장 #1 갱신).
#   부기: 형식/내용 분리 해부를 두 팔 모두에 의무 적용.
