#!/usr/bin/env python3
"""P25 판정 계기 (사이클 81, 읽기 전용, $0, 결정적).

처치: score_memory phrase_bonus의 per-token +0.02를 자격 토큰(len>=2 &
not isdigit)으로 제한 (상한 없음 — c22가 상한의 회귀성을 실측).

판정 두 팔 (predictions.md P25 (a)(b), 코드 변경 전 선등록):
  (a) 대수 동치 — fixtures_cycle22 8쿼리 x 히트 전수에서
      new_score == clamp(round(old_raw - junk, 4)). old_raw는 커밋 3db1681
      시점 score_memory의 동결 재현(아래 old_rule_raw — 토크나이저·temporal은
      이 사이클에서 불변이므로 본체에서 임포트). 1건 불일치 = 반증.
  (b) c22 T2b 랭크 재현 — 앵커 2026-08-02T12:00+09:00 고정, 쿼리별
      tau(구규칙 순서 vs 신규칙 순서)를 notes/cycle-22 표의 T2b 열과 대조.
      랭크 산술은 c22 f2_treatment2_selectivity_sweep.py rank_inversions와
      동일(strict sign, 동점 무시). recency 앵커 시간차 캐비앗은 P25 (b)에
      선언 — 불일치 시 per-쌍 점수차를 인쇄해 recency 귀속을 판별한다.

실행: .venv/bin/python research/devloop/scripts/c81_phrase_qual_regression.py
(fixtures_cycle22/*.json만 읽음. 라이브 :8000 무접촉, 종료코드 0=전수 통과.)
"""
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
from forget.memory_engine import expanded_tokens, score_memory, temporal_bonus
from forget.utils import parse_datetime

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures_cycle22")
ANCHOR = "2026-08-02T12:00:00+09:00"  # c22 실측일 정오 (P25 (b) 캐비앗 참조)

# c22 실측 (notes/cycle-22-f2-treatment2-selectivity.md 표, T2b 열).
EXPECTED_T2B = {
    "devloop-meta(퇴화앵커)": (0.857, True),
    "us-relocation": (1.000, True),
    "e2ee-pivot": (0.643, True),
    "dogfood-setup": (1.000, True),
    "researcher-identity": (1.000, True),
    "b2b-pitch": (1.000, True),
    "compression-metrics": (0.929, False),
    "codex-dual-write": (0.857, True),
}


def old_rule_raw(query: str, memory: dict, reference_date=None):
    """커밋 3db1681 시점 score_memory의 동결 재현 — 클램프/반올림 전 원값과
    무자격 토큰 기여(junk)를 함께 반환."""
    q_tokens = expanded_tokens(query)
    m_tokens = expanded_tokens(str(memory.get("memory", "")))
    if not q_tokens:
        return 1.0, 0.0
    overlap = len(q_tokens.intersection(m_tokens))
    union = len(q_tokens.union(m_tokens)) or 1
    jaccard = overlap / union
    coverage = overlap / len(q_tokens)
    phrase_bonus = junk = 0.0
    lowered_memory = str(memory.get("memory", "")).lower()
    lowered_query = query.lower()
    for token in q_tokens:
        if token in lowered_memory:
            phrase_bonus += 0.02
            if not (len(token) >= 2 and not token.isdigit()):
                junk += 0.02
    if lowered_query and lowered_query in lowered_memory:
        phrase_bonus += 0.25
    categories = {str(c).lower() for c in memory.get("categories", [])}
    category_bonus = 0.12 if q_tokens.intersection(categories) else 0.0
    recency_bonus = 0.0
    anchor = parse_datetime(reference_date) or datetime.now(timezone.utc)
    updated = parse_datetime(memory.get("updated_at"))
    if updated:
        age_days = max((anchor - updated).total_seconds() / 86400, 0)
        recency_bonus = 0.08 * math.exp(-age_days / 60)
    raw = (0.45 * coverage) + (0.35 * jaccard) + phrase_bonus + category_bonus + recency_bonus
    raw += temporal_bonus(query, memory, reference_date)
    return raw, junk


def rank_inversions(cur_list, proj_list):
    """c22 계기와 동일 산술 (strict sign, 동점 무시)."""
    n = len(cur_list)
    if n < 2:
        return 1.0, True
    inv = 0
    for i in range(n):
        for j in range(i + 1, n):
            dc = cur_list[i] - cur_list[j]
            dp = proj_list[i] - proj_list[j]
            if (dc > 0 and dp < 0) or (dc < 0 and dp > 0):
                inv += 1
    tau = round(1 - 2 * inv / (n * (n - 1) / 2), 4)
    top1 = max(range(n), key=lambda k: cur_list[k]) == max(range(n), key=lambda k: proj_list[k])
    return tau, top1


def main():
    fixtures = sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.json")))
    assert len(fixtures) == 8, f"fixtures_cycle22 8개 기대, {len(fixtures)}개 발견"
    eq_fail = rank_fail = hits_total = 0
    print(f"anchor={ANCHOR}  (a) 대수 동치  (b) c22 T2b 랭크 재현")
    for path in fixtures:
        label = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            data = json.load(f)
        query, hits = data["query"], data["hits"]
        old_scores, new_scores = [], []
        for h in hits:
            hits_total += 1
            raw, junk = old_rule_raw(query, h, ANCHOR)
            predicted = max(0.0, min(1.0, round(raw - junk, 4)))
            new = score_memory(query, h, ANCHOR)
            old_scores.append(max(0.0, min(1.0, round(raw, 4))))
            new_scores.append(new)
            if abs(new - predicted) > 5e-5:
                eq_fail += 1
                print(f"  [a-FAIL] {label}: new={new} predicted={predicted} "
                      f"junk={junk:.3f} | {h['memory'][:40]!r}")
        tau, top1 = rank_inversions(old_scores, new_scores)
        exp_tau, exp_top1 = EXPECTED_T2B[label]
        ok = abs(tau - exp_tau) <= 0.001 and top1 == exp_top1
        if not ok:
            rank_fail += 1
            print(f"  [b-FAIL] {label}: tau={tau} (기대 {exp_tau}) "
                  f"top1_kept={top1} (기대 {exp_top1})")
            for o, n_, h in sorted(zip(old_scores, new_scores, hits), key=lambda x: -x[0]):
                print(f"      old={o:6.4f} new={n_:6.4f}  {h['memory'][:38]!r}")
        else:
            print(f"  [ok] {label:>24}  n={len(hits)}  tau={tau} top1_kept={top1}")
    print(f"\n(a) 대수 동치: {hits_total - eq_fail}/{hits_total} 히트 통과"
          f"{' — 반증' if eq_fail else ''}")
    print(f"(b) 랭크 재현: {8 - rank_fail}/8 쿼리 일치{' — 불일치 있음' if rank_fail else ''}")
    sys.exit(1 if (eq_fail or rank_fail) else 0)


if __name__ == "__main__":
    main()
