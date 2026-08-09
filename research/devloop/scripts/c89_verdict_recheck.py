#!/usr/bin/env python3
"""c89 판정 재검산 — 무기억 4세션의 독립 검시 (읽기 전용).

3세션이 남긴 notes/c89_dual_payload.json의 `verdicts` 블록과 노트 본문의 수치를
**믿지 않고** 원자료 rows에서 다시 계산한다. 계기가 자기 verdict를 자기가 채점한
순환을 끊는 유일한 방법은 다른 세션이 rows로 되짚는 것이다(LOOP.md 검증 구조 ①).

검산 항목
  A. J1  dual 중앙값 · p10 · p90 · c14 구간 이탈 배수
  B. J2  obs층 항목당 토큰
  C. J3  raw42 중앙값이 c88 by_k["42"] 중앙값과 일치하는가 + **문항별 전수 대조**
  D. 가산성  payload_dual == payload_obs + payload_raw (전 문항)
  E. 앵커 항등식  n_obs=60 · n_raw=42 · n_total=102 이탈 문항 수
  F. 정정 사이트  살아 있는 주장 파일에 옛 숫자(1.2-2k · 57배 · 2%)가 남았는가

출력은 판정별 PASS/FAIL과 근거 수치뿐. 파일을 쓰지 않는다.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

DEVLOOP = Path(__file__).resolve().parent.parent
C89 = DEVLOOP / "notes" / "c89_dual_payload.json"
C88 = DEVLOOP / "notes" / "c88_payload_sweep.json"

# 살아 있는 주장 사이트 — 옛 숫자가 남아 있으면 정정 미완 (노트 §4 표의 7곳)
CLAIM_SITES = [
    DEVLOOP / "compression-baseline.md",
    DEVLOOP / "token-overhead.md",
    DEVLOOP / "scripts" / "rate_distortion_chart.py",
    DEVLOOP / "rate-distortion.svg",
]
STALE_PATTERNS = [
    (r"1[.,]2\s*[-–~]\s*2\s*k", "1.2–2k 추정"),
    (r"1/57", "1/57 서사"),
    (r"tok_lo[\"']?\s*:\s*1[_,]?200", "차트 tok_lo=1200"),
]


def pct_nearest(vals: list[float], q: float) -> float:
    """nearest-rank 분위수 — 계기가 쓴 것과 **다른** 관례(민감도 대조용)."""
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def pct_instrument(vals: list[float]) -> tuple[float, float]:
    """계기 정본 관례 — statistics.quantiles(n=10) 기본값(method='exclusive').
    c89_dual_payload.py:301 과 동일. 공표 수염은 이 값이다."""
    qs = statistics.quantiles(vals, n=10)
    return qs[0], qs[8]


def main() -> int:
    d = json.loads(C89.read_text())
    rows = d["rows"] if "rows" in d else d["questions"]
    claimed = d["verdicts"]

    dual = [r["payload_dual_tokens"] for r in rows]
    obs = [r["payload_obs_tokens"] for r in rows]
    raw = [r["payload_raw_tokens"] for r in rows]

    ok = True
    print(f"[rows] n={len(rows)}  (기대 42)")
    ok &= len(rows) == 42

    # ---- A. J1 ----------------------------------------------------------
    med = statistics.median(dual)
    ratio = round(med / 2000, 2)
    c = claimed["J1_dual_median_in_c14_range"]
    a_ok = (med == c["measured_median"]) and (not c["in_range"]) and med > 2000
    print(f"[A/J1] median={med:.1f} (주장 {c['measured_median']}) "
          f"min={min(dual)} max={max(dual)} mean={statistics.mean(dual):.1f} · "
          f"상한대비 {ratio}배 (주장 {c['ratio_vs_hi']}) -> {'PASS' if a_ok else 'FAIL'}")
    ok &= a_ok

    # ---- A'. 수염의 관례 민감도 (관측 45) --------------------------------
    # 중앙값은 관례 무관하지만 p10/p90은 아니다. 공표 수염이 어느 정의인지
    # 밝히지 않으면 독자가 재계산해도 같은 수를 얻지 못한다.
    i10, i90 = pct_instrument(dual)
    n10, n90 = pct_nearest(dual, 0.10), pct_nearest(dual, 0.90)
    stats_blk = d.get("aggregate", {}).get("payload_dual_tokens", {})
    j10, j90 = stats_blk.get("p10"), stats_blk.get("p90")
    a2_ok = (j10 is not None and abs(i10 - j10) < 0.01 and abs(i90 - j90) < 0.01)
    print(f"[A'] 수염 관례 민감도 — 계기 정본(exclusive) p10={i10:.1f} p90={i90:.1f} "
          f"(산출물 {j10} / {j90}) vs nearest-rank p10={n10} p90={n90} · "
          f"차이 {abs(i10 - n10):.1f} / {abs(i90 - n90):.1f} tok "
          f"-> {'PASS(정본 일치)' if a2_ok else 'FAIL'}")
    print("     ※ 공표 수염 9,687 / 14,988 = exclusive 관례. 관례를 밝히지 않으면 "
          "재계산이 어긋난다(관측 45).")
    ok &= a2_ok

    # ---- B. J2 ----------------------------------------------------------
    per_item = [o / r["n_obs"] for o, r in zip(obs, rows)]
    b_med = round(statistics.median(per_item), 2)
    c2 = claimed["J2_obs_layer_tok_per_item"]
    b_ok = abs(b_med - c2["measured_median"]) < 0.01 and not c2["in_range"]
    print(f"[B/J2] obs층 항목당 median={b_med} tok (주장 {c2['measured_median']}) "
          f"구간 {c2['range']} -> {'PASS' if b_ok else 'FAIL'}")
    ok &= b_ok

    # ---- C. J3 (전수 대조) ----------------------------------------------
    c88 = json.loads(C88.read_text())
    c88_rows = c88["rows"] if "rows" in c88 else c88["questions"]
    c88_k42 = {}
    for r in c88_rows:
        by_k = r.get("by_k") or {}
        cell = by_k.get("42") or by_k.get(42)
        if cell:
            c88_k42[r["question_id"]] = cell["payload_tokens"]
    mism = [(r["question_id"], c88_k42.get(r["question_id"]), r["payload_raw_tokens"])
            for r in rows if c88_k42.get(r["question_id"]) != r["payload_raw_tokens"]]
    raw_med = statistics.median(raw)
    c88_med = statistics.median(list(c88_k42.values()))
    c_ok = not mism and raw_med == c88_med == 9960.5
    print(f"[C/J3] raw42 median={raw_med} vs c88 k=42 median={c88_med} · "
          f"문항 대조 {len(rows) - len(mism)}/{len(rows)} 일치, 불일치 {len(mism)} "
          f"-> {'PASS' if c_ok else 'FAIL'}")
    if mism:
        for q, a, b in mism[:5]:
            print(f"        mismatch {q}: c88={a} c89={b}")
    ok &= c_ok

    # ---- D. 가산성 -------------------------------------------------------
    add_bad = [r["question_id"] for r in rows
               if r["payload_dual_tokens"] != r["payload_obs_tokens"] + r["payload_raw_tokens"]]
    print(f"[D] 가산성 위반 {len(add_bad)}/{len(rows)} -> {'PASS' if not add_bad else 'FAIL'}")
    ok &= not add_bad

    # ---- E. 앵커 항등식 --------------------------------------------------
    ident_bad = [r["question_id"] for r in rows
                 if not (r["n_obs"] == 60 and r["n_raw"] == 42 and r.get("n_total", 102) == 102)]
    print(f"[E] 앵커 항등식(60+42=102) 이탈 {len(ident_bad)}/{len(rows)} "
          f"-> {'PASS' if not ident_bad else 'FAIL'}")
    ok &= not ident_bad

    # ---- F. 정정 사이트 잔존 --------------------------------------------
    stale = []
    for p in CLAIM_SITES:
        if not p.exists():
            continue
        text = p.read_text()
        # 정정 각주/도입부에서 옛 숫자를 '폐기됨'으로 인용하는 줄은 잔존이 아니다.
        for ln, line in enumerate(text.splitlines(), 1):
            if any(w in line for w in ("Correction", "정정", "폐기", "retired", "previously")):
                continue
            for pat, name in STALE_PATTERNS:
                if re.search(pat, line, re.I):
                    stale.append(f"{p.relative_to(DEVLOOP)}:{ln} [{name}]")
    print(f"[F] 살아 있는 주장 사이트의 옛 숫자 잔존 {len(stale)}건 "
          f"-> {'PASS' if not stale else 'FAIL'}")
    for s in stale:
        print(f"        {s}")
    ok &= not stale

    print(f"\n== 종합: {'ALL PASS — 3세션 판정을 4세션이 원자료로 재확인' if ok else 'FAIL 있음 — 수확 보류'} ==")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
