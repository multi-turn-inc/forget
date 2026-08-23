"""어텐션 실험 판정기 — 사전 등록(docs/attention-retrieval-strength.md)대로 채점한다.

입력: attn-lab 출력 JSONL 1~2개 (permute 팔이 둘이면 P-B까지 판정)
판정:
  P-A  질의 내 gold 좌석의 정규화 질량 서열 — AUC > 0.65 지지 / < 0.55 반증
  P-B  두 셔플 팔 간 좌석 서열 스피어만 상관 > 0.6 지지
  P-C  무관 좌석(distractor)이 하위 사분위 — 지지율 보고
사용: .venv/bin/python scripts/analyze_attn_lab.py out_p1.jsonl [out_p2.jsonl]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

CONTEXTS = Path(__file__).resolve().parent.parent / "research/eval/attn_contexts_v0.jsonl"


def load(path: str) -> dict[str, dict]:
    rows = {}
    for line in Path(path).open():
        r = json.loads(line)
        for s in r["seats"]:
            s["density"] = s["mass"] / max(1, s["tokens"])   # 좌석 길이 보정
        rows[r["qid"]] = r
    return rows


def auc(pos: list[float], neg: list[float]) -> float:
    """맨-휘트니 AUC — gold가 비-gold보다 높은 쌍의 비율."""
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def spearman(a: list[float], b: list[float]) -> float:
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos_, i in enumerate(order):
            r[i] = pos_
        return r
    ra, rb = rank(a), rank(b)
    n = len(a)
    if n < 3:
        return float("nan")
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra) ** 0.5
    vb = sum((y - mb) ** 2 for y in rb) ** 0.5
    return cov / (va * vb) if va and vb else float("nan")


def main() -> None:
    arm1 = load(sys.argv[1])
    arm2 = load(sys.argv[2]) if len(sys.argv) > 2 else None
    distractors = {}
    if CONTEXTS.exists():
        for line in CONTEXTS.open():
            c = json.loads(line)
            distractors[c["qid"]] = {s["id"] for s in c["seats"] if s.get("distractor")}

    # ── P-A: 질의 내 AUC ────────────────────────────────────────────────
    aucs, per_q = [], []
    for qid, r in arm1.items():
        pos = [s["density"] for s in r["seats"] if s["gold"]]
        neg = [s["density"] for s in r["seats"] if not s["gold"]]
        a = auc(pos, neg)
        if a == a:
            aucs.append(a)
            per_q.append((qid, a, len(pos), len(neg)))
    mean_auc = sum(aucs) / len(aucs) if aucs else float("nan")
    verdict_a = "지지" if mean_auc > 0.65 else ("반증" if mean_auc < 0.55 else "회색지대")
    print(f"P-A  질의 {len(aucs)}건 · 평균 AUC {mean_auc:.3f} → {verdict_a}  (지지>0.65 / 반증<0.55)")
    lo = sorted(per_q, key=lambda x: x[1])[:3]
    hi = sorted(per_q, key=lambda x: -x[1])[:3]
    print("     최고:", " ".join(f"{q}:{a:.2f}" for q, a, *_ in hi))
    print("     최저:", " ".join(f"{q}:{a:.2f}" for q, a, *_ in lo))

    # ── P-B: 셔플 팔 간 서열 안정성 ─────────────────────────────────────
    if arm2:
        rhos = []
        for qid, r1 in arm1.items():
            r2 = arm2.get(qid)
            if not r2:
                continue
            d1 = {s["id"]: s["density"] for s in r1["seats"]}
            d2 = {s["id"]: s["density"] for s in r2["seats"]}
            common = sorted(set(d1) & set(d2))
            if len(common) >= 4:
                rhos.append(spearman([d1[i] for i in common], [d2[i] for i in common]))
        rhos = [r for r in rhos if r == r]
        mean_rho = sum(rhos) / len(rhos) if rhos else float("nan")
        verdict_b = "지지 — 어텐션은 위치가 아니라 정체를 따른다" if mean_rho > 0.6 else "반증 — 위치 편향이 지배한다"
        print(f"P-B  질의 {len(rhos)}건 · 평균 스피어만 ρ {mean_rho:.3f} → {verdict_b}  (지지>0.6)")

    # ── P-C: 무관 좌석 하위 사분위 ──────────────────────────────────────
    if distractors:
        hits = total = 0
        for qid, r in arm1.items():
            dset = distractors.get(qid) or set()
            dens = sorted(s["density"] for s in r["seats"])
            cut = dens[max(0, len(dens) // 4 - 1)]
            for s in r["seats"]:
                if s["id"] in dset:
                    total += 1
                    hits += s["density"] <= cut
        if total:
            print(f"P-C  무관 좌석 {total}석 중 하위 사분위 {hits}석 = {100 * hits / total:.0f}%")


if __name__ == "__main__":
    main()
