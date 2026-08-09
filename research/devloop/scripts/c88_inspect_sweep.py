"""c88 산출물 검시 — 정합성 재검산(계기 자체 flags를 믿지 않고 원자료에서 다시 센다)."""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
d = json.loads((ROOT / "research/devloop/notes/c88_payload_sweep.json").read_text(encoding="utf-8"))
meta, rows, K = d["meta"], d["rows"], d["meta"]["k_list"]

print("== meta ==")
for k, v in meta.items():
    if k != "body":
        print(f"  {k}: {v}")
print("== body (원칙 3 스택 선언) ==")
for k, v in meta["body"].items():
    print(f"  {k}: {v}")

print(f"\n== 정합성 재검산 (n={len(rows)}) ==")
mono_bad = ratio_bad = 0
for r in rows:
    prev = -1
    for k in K:
        c = r["by_k"][str(k)]
        if c["payload_tokens"] < prev:
            mono_bad += 1
        prev = c["payload_tokens"]
        if c["n_retrieved"] != min(k, r["stored"]):
            ratio_bad += 1
print(f"  단조성 위반 셀: {mono_bad}")
print(f"  n_retrieved != min(k, stored) 셀: {ratio_bad}")
print(f"  계기 자체 flagged_questions: {d['flagged_questions']}")
st = [r["stored"] for r in rows]
print(f"  stored(턴 수) min/median/max: {min(st)} / {statistics.median(st)} / {max(st)}  총 {sum(st)}")

print("\n== 페이로드 토큰 (o200k_base), 42문항 ==")
print(f"{'k':>4} {'median':>9} {'mean':>9} {'p10':>7} {'p90':>8} {'min':>7} {'max':>7} {'tok/기억':>9}")
for k in K:
    a = meta and d["aggregate_by_k"][str(k)]
    print(f"{k:>4} {a['payload_median']:>9.1f} {a['payload_mean']:>9.1f} {a['payload_p10']:>7.0f} "
          f"{a['payload_p90']:>8.0f} {a['payload_min']:>7} {a['payload_max']:>7} "
          f"{a['payload_median'] / k:>9.1f}")

print("\n== c14 문서화 추정(1.2–2k tok)이 대응하는 k 구간 ==")
for k in K:
    med = d["aggregate_by_k"][str(k)]["payload_median"]
    mark = "  <-- 1.2–2k 구간" if 1200 <= med <= 2000 else ""
    print(f"  k={k:<3} median={med:>9.1f}{mark}")
