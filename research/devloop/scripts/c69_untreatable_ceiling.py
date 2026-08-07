#!/usr/bin/env python3
"""c69 — 처치 불가 천장: 실제로 이기는 행은 **P22 축 위에 있지 않다** (read-only, $0).

발견 경로(정직 기재): 이것을 찾으려고 한 것이 아니다. F1 사슬 재현의 **잔여 3행**을
'미미하다'로 접지 않고 들여다본 결과다. 그 3행은 `rule=0.0000 · vector=0.0000`인데
`score`가 0.5389 · 0.6931 · 0.7112다 — 즉 **rule/vector 합성 사슬을 통과하지 않은 행**이고,
본문은 전부 `Task <id> is <status>. …` 형태의 **task_state 클레임**이다.

측정: 질의별로 (가) 처치 가능 행의 최고점 (나) 처치 불가 행(rule=vector=0)의 최고점을
나란히 낸다. (나) > (가)인 질의 수가 '처치의 천장'이 구속하는 빈도다.

★★ 실측 결과 (2026-08-07, 이 문단은 **측정 후에 쓰였다**) — 내가 측정 전에 이 자리에 적어
   둔 극적인 판정은 **데이터가 거부했다.** 정직 기재로 경과를 남긴다:

   측정 전 초안(**틀렸다**): "그 점수(0.6931·0.7112)는 ON-real 최저 top-1(0.6346)보다 높다
   → 처치가 완벽히 성공해도 top-1 자리는 처치 불가 행이 가져간다. **처치의 상한이 처치
   밖에서 정해져 있다**." — ON-real 팔의 *최저*와 처치 불가 행의 *최고*를 비교한 것이
   오류다. 두 수는 서로 다른 질의에서 나오므로 그 부등식은 아무것도 함의하지 않는다.

   실측: 천장이 구속하는 질의 = **0/23**. 처치 불가 행은 전 풀에서 **3개**뿐이고(모두
   `Task … is …`), 등장한 두 질의(on-1 절차0·on-4 벤치)에서도 각각 0.6931<0.7711,
   0.7112<0.8037로 **처치 가능 행에 진다**. 즉 "처치의 상한이 처치 밖에 있다"는 주장은
   **이 표본에서 지지되지 않는다.**

   남는 참값(범위를 좁혀 서술): ① 합성 사슬을 우회하는 행이 **실재한다**(rule=vector=0인데
   score 0.5389~0.7112) ② 그 3행은 **전원 게이트 0.45를 넘는다**(3/3) — 즉 주입 자격은
   갖는다 ③ 어떤 vector 축 처치도 이 행들을 움직이지 못하므로 P22의 수용 기준은 구조적으로
   **처치 가능 행만의 성질**을 재고 있다(범위 한정이며, 천장 주장은 아니다) ④ 이 기전은
   **P10의 기전**이다(c62: "주입 0/3은 top1 task_state claim의 점수 포화가 정한다"). P10은
   c63~c68 **6사이클 이월** 중이고 c68이 선행 조건을 '점수의 상수항 구조 위에서 재서술'로
   재정의했다 — 이 계측은 그 재서술에 필요한 사실(우회 행의 존재·점수대·게이트 통과)을
   주지만, **P10을 여기서 판정하지는 않는다.**

read-only: search_memories만. 쓰기 0 · LLM 0 · $0.

    .venv/bin/python research/devloop/scripts/c69_untreatable_ceiling.py
"""
from __future__ import annotations

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


c69 = _load("c69_centering_prototype")
c68 = c69.c68
GATE = c68.GATE_NOW


def is_untreatable(row: dict) -> bool:
    """rule과 vector가 둘 다 0 — 합성 사슬을 통과하지 않았다는 표지."""
    return row["rule"] == 0.0 and row["vector"] == 0.0 and row["score"] > 0.0


def main() -> None:
    print("c69 — 처치 불가 천장 (task_state 클레임)")
    print(f"현행 게이트={GATE}  ON-real 팔 최저 top-1(c69 baseline)=0.6346")
    arms = ([("ON-real", label, q) for label, q in c68.ON_REAL]
            + [("OFF", label, q) for label, q in c69.FRESH_OFF]
            + [("OFF-c68", label, q) for label, q in c68.OFF])

    print(f"\n  {'팔':<9}{'질의':<13}{'처치가능최고':>11}{'처치불가최고':>11}{'천장구속':>9}"
          f"  처치 불가 행 본문")
    bound = 0
    untreatable_scores = []
    treatable_tops = []
    for arm, label, q in arms:
        rows = c69.probe_pool(q, c69.POOL_TOP_K)
        un = [r for r in rows if is_untreatable(r)]
        tr = [r for r in rows if not is_untreatable(r)]
        un_top = max((r["score"] for r in un), default=0.0)
        tr_top = max((r["score"] for r in tr), default=0.0)
        untreatable_scores.extend(r["score"] for r in un)
        treatable_tops.append(tr_top)
        binds = un_top > tr_top
        bound += int(binds)
        best_un = max(un, key=lambda r: r["score"], default=None)
        print(f"  {arm:<9}{label:<13}{tr_top:>11.4f}{un_top:>11.4f}"
              f"{'★ 예' if binds else '아니오':>9}  "
              f"{(best_un['text'][:44] if best_un else 'n/a')}")

    print(f"\n  천장이 구속하는 질의 = {bound}/{len(arms)}")
    if untreatable_scores:
        print(f"  처치 불가 행 점수: n={len(untreatable_scores)} "
              f"최저={min(untreatable_scores):.4f} 최고={max(untreatable_scores):.4f}")
        over = sum(1 for s in untreatable_scores if s >= GATE)
        print(f"  그중 게이트 {GATE} 이상 = {over}/{len(untreatable_scores)} "
              f"({100.0 * over / len(untreatable_scores):.0f}%)")
    print(f"  처치 가능 행 top-1 범위: {min(treatable_tops):.4f}~{max(treatable_tops):.4f}")

    print("\n=== 함의 ===")
    if bound:
        print(f"  · 처치 불가 행이 {bound}개 질의의 top-1을 차지한다. 그 질의들에서는 "
              "vector 성분에 대한 어떤 처치도 top-1을 바꾸지 못한다.")
    print("  · 따라서 P22 (b)의 수용 기준('허용 구간 폭')은 **처치 가능 행만의 성질**을 재고 "
          "있었다. c69의 처치 스윕 표도 같은 한계를 가진다(F1 불일치 행을 제외했으므로 "
          "정확히 이 행들을 뺀 상태로 계산됐다) — 표의 숫자는 유효하지만 **범위가 좁다.**")
    print("  · P10 재서술의 근거: 상수항 구조의 최상위 항은 아핀 상수(0.275)도 비등방성"
          "(‖μ‖=0.9071)도 아니라 **합성 사슬을 우회하는 행의 존재**다. 앞의 둘은 처치 대상이고 "
          "이것은 **설계 결정**이다 — 우회가 의도라면 게이트가 그 행에 어떤 뜻인지 따로 정해야 한다.")

    print("\nCAVEAT: ① `rule=vector=0`은 '사슬 우회'의 **대리 표지**다. 우연히 둘 다 0인 "
          "합성 행이 있다면 오분류된다(관측 표본에서는 전부 `Task … is …` 형태였다). "
          "② 훅은 top_k=5·MAX_RECALLS=3으로 자르므로 실제 주입에서 이 행들이 차지하는 자리는 "
          "여기서 잰 것보다 **더 치명적**일 수 있다(창이 좁을수록 천장이 더 구속한다). "
          "③ 단일 시점·현 스택. ④ 제품을 바꾸지 않는다.")


if __name__ == "__main__":
    main()
