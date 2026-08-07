#!/usr/bin/env python3
"""c69 진단 — 두 개의 유효 전제 미충족을 규명한다 (read-only, $0).

c69_centering_prototype.py의 첫 런이 **자기 대조에서 두 번 걸렸다**. 처치 판정을 내기 전에
둘 다 원인을 확정한다 (c67 자기규율 (나): 새 계측기의 첫 런을 baseline 대조로 받으면
계측기 자신의 결함이 같은 턴에 드러난다 — 드러났으니 여기서 멈추고 규명한다).

  결함 ① **T0가 c68을 재현하지 못한다.** c68은 OFF top-1 최고를 `0.6037`로 쟀고
    (top_k=HOOK_TOP_K=5), c69는 같은 질의·같은 몸에서 `0.6925`를 쟀다(top_k=200).
    top-1은 깊이와 무관해야 한다 — 서버가 점수 내림차순으로 잘라 준다면. 이 불일치는
    둘 중 하나를 뜻한다:
      (가) 서버의 top_k 절단이 점수 순이 아니다 → **c68의 OFF 최고가 과소추정**이었고,
           c68 헤드라인의 "구간 [0.6100, 0.6346]이 존재하나 잡음 안"은 실제로는
           **구간이 아예 없다(분리 불가)**로 정정돼야 한다. c68은 그 경우 결론의 방향은
           같지만(상수 경로 폐쇄) **근거가 더 강해진다.**
      (나) 내 채취가 훅과 다른 무언가를 본다 → c69 쪽 결함.
    가설을 가르는 실험: 같은 질의를 깊이만 바꿔 여러 번 채취하고 최고점의 추이를 본다.
    깊이가 늘 때 최고점이 **증가**하면 (가)다 — 얕은 창은 상위 행을 놓친다.

  결함 ② **F1 사슬 재현 95.78% (135/3200 불일치).** 내가 모르는 보정이 하나 더 있다.
    breakdown의 **원본 키 전체**를 덤프해 어떤 키가 불일치 행에만 나타나는지 본다
    (c69 프로토타입의 probe는 알려진 키만 뽑아 보관했다 — 그 축약이 원인을 숨긴다).

read-only: search_memories만. 쓰기 0 · LLM 0 · $0.

    .venv/bin/python research/devloop/scripts/c69_depth_and_chain_diagnosis.py
"""
from __future__ import annotations

import collections
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


c68 = _load("c68_gate_recalibration")
c69 = _load("c69_centering_prototype")
c59 = c68.c59

DEPTHS = (5, 10, 15, 30, 60, 120, 200, 400)


def raw_probe(query: str, top_k: int) -> list[dict]:
    """breakdown을 축약하지 않고 원본 그대로 보존한다."""
    from forget_project import layered_filter, project_key_for_path, scope_disabled
    args = {"query": query, "top_k": top_k, "recall": "low", "score_breakdown": True}
    if not scope_disabled():
        project = project_key_for_path(c59.CWD)
        if project:
            args["filters"] = layered_filter(project)
    rows = c59.hook._rpc("search_memories", args).get("results") or []
    return [{"id": r.get("id") or "", "score": float(r.get("score") or 0.0),
             "bd": dict(r.get("score_breakdown") or {}),
             "text": " ".join((r.get("memory") or "").split())} for r in rows]


def main() -> None:
    print("c69 진단 — ① 깊이 의존 ② 사슬 재현 불일치")
    print("=" * 78)
    print("[① 깊이 의존] 같은 질의를 깊이만 바꿔 채취한다. top-1이 깊이에 따라 오르면")
    print("    서버의 top_k 절단이 점수 순이 아니라는 뜻이고, c68의 OFF 최고는 과소추정이다.")
    print(f"\n  {'질의':<14}" + "".join(f"{d:>9}" for d in DEPTHS))
    verdict_rows = []
    for arm, pairs in (("OFF", c68.OFF), ("ON-real", c68.ON_REAL)):
        for label, q in pairs:
            tops = []
            for d in DEPTHS:
                rows = raw_probe(q, d)
                tops.append(max((r["score"] for r in rows), default=0.0))
            monotone_up = tops[-1] > tops[0] + 1e-9
            verdict_rows.append((arm, label, tops, monotone_up))
            print(f"  {label:<14}" + "".join(f"{t:>9.4f}" for t in tops)
                  + ("   ↑깊이의존" if monotone_up else ""))
    n_dep = sum(1 for *_x, up in verdict_rows if up)
    print(f"\n  깊이 의존 질의 {n_dep}/{len(verdict_rows)}")
    if n_dep:
        print("  → **가설 (가) 확정**: 서버의 top_k 절단은 점수 내림차순이 아니다. 얕은 창으로 "
              "잰 최고점은 하한이며, c68의 OFF 최고 0.6037은 과소추정이었다.")
        print("     함의: c68이 '존재한다'고 보고한 허용 구간 [0.6100, 0.6346]은 **실재하지 "
              "않는다**(OFF가 ON-real 최저를 넘는다) → 판정은 '잡음 안'이 아니라 '분리 불가'로 "
              "강화된다. c68의 결론 방향(상수 경로 폐쇄)은 유지되고 근거는 더 강해진다.")
        print("     그리고 P22 (a)의 시계에 영향: 폭이 '넓어질 수 없다'는 연역은 유지되지만 "
              "기준값 0.0246 자체가 얕은 창의 산물이므로 **기준값을 정정해야 한다**.")
    else:
        print("  → 깊이 무관. c68 재현 실패의 원인은 다른 곳이다(내 채취 쪽을 의심해야 한다).")

    # 얕은 창이 무엇을 놓쳤는지 한 예로 보여준다 — 지표가 아니라 증거로.
    label, q = c68.OFF[0]
    shallow = raw_probe(q, 5)
    deep = raw_probe(q, 200)
    shallow_ids = {r["id"] for r in shallow}
    missed = [r for r in sorted(deep, key=lambda r: -r["score"])[:5]
              if r["id"] not in shallow_ids]
    print(f"\n  [증거] '{label}' — 깊이 5의 최고 {max(r['score'] for r in shallow):.4f} vs "
          f"깊이 200의 최고 {max(r['score'] for r in deep):.4f}")
    for r in missed[:3]:
        print(f"    깊이 5가 놓친 상위 행: {r['score']:.4f}  {r['text'][:78]}")

    # ---------------- ② 사슬 재현 불일치 ----------------
    print("\n" + "=" * 78)
    print("[② 사슬 재현 불일치] breakdown 원본 키로 원인을 가른다")
    key_counter_bad: collections.Counter = collections.Counter()
    key_counter_ok: collections.Counter = collections.Counter()
    samples = []
    total = bad = 0
    for _label, q in list(c68.OFF) + list(c68.ON_REAL):
        for r in raw_probe(q, 200):
            bd = r["bd"]
            total += 1
            recon = None
            for fb in (False, True):
                cand = c69.compose_score(
                    float(bd.get("rule") or 0.0), float(bd.get("vector") or 0.0),
                    entity_boost=float(bd.get("entity_boost") or 0.0),
                    keyword=float(bd.get("keyword") or 0.0),
                    superseded=bool(bd.get("superseded")),
                    session_capture=bool(bd.get("session_capture")),
                    scope_fallback=fb)
                if abs(cand - r["score"]) <= 0.0002:
                    recon = cand
                    break
            if recon is None:
                bad += 1
                key_counter_bad.update(bd.keys())
                if len(samples) < 8:
                    base = (float(bd.get("rule") or 0.0) * c69.RULE_W
                            + float(bd.get("vector") or 0.0) * c69.VECTOR_W)
                    samples.append((r, base))
            else:
                key_counter_ok.update(bd.keys())
    print(f"  총 {total}행 중 불일치 {bad} ({100.0 * bad / total:.2f}%)")
    print(f"\n  {'breakdown 키':<20}{'불일치행':>10}{'일치행':>10}   비고")
    for key in sorted(set(key_counter_bad) | set(key_counter_ok)):
        nb, no = key_counter_bad[key], key_counter_ok[key]
        flag = ""
        if nb and not no:
            flag = "★ 불일치 행에만 나타난다 — 원인 후보"
        elif nb and no and bad and (nb / bad) > 0.9 > (no / max(1, total - bad)):
            flag = "★ 불일치 행에 집중"
        print(f"  {key:<20}{nb:>10}{no:>10}   {flag}")
    print("\n  [표본] 불일치 행의 관측 score vs 내 재조립 (base = rule×0.45 + vector×0.55)")
    for r, base in samples:
        ratio = r["score"] / base if base else 0.0
        print(f"    관측={r['score']:.4f}  base={base:.4f}  관측/base={ratio:.4f}  "
              f"keys={sorted(r['bd'].keys())}")
        print(f"      {r['text'][:76]}")
    print("\n  (관측/base가 특정 상수에 몰리면 그 상수가 내가 모르는 곱셈 보정이다.)")
    ratios = collections.Counter()
    for r, base in samples:
        if base:
            ratios[round(r["score"] / base, 3)] += 1
    if ratios:
        print(f"  표본 비율 분포: {dict(ratios)}")


if __name__ == "__main__":
    main()
