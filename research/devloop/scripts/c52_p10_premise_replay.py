#!/usr/bin/env python3
"""c52 — P10 전제 재평가 (read-only, 2026-08-05).

P10(등록 c42): "배제 필터 이후에 후보 예산을 채우면(백필) 회상이 되살아난다."
전제: 훅이 top_k=MAX_RECALLS+2=5를 배제 필터 이전에 확정하고 백필하지 않아,
task_state·캡슐 중복이 상위 5칸을 소진하면 주입 0(침묵)이 된다 — c41·c42 실측.

재평가 이유: c49~c51 훅 주입 만석(3) 3연속. 전제의 결과부(침묵)가 현 스토어에서
재현되지 않을 가능성. 방법은 c42와 동일한 read-only 재생: 설치본 훅의 검색 경로를
main() 미호출로 재실행(원장 쓰기 없음), top_k=5(현행) vs 15(처치 대리)를 대조.

판정 질문:
  Q1. top_k=5에서 훅 필터 통과 건수는? (c42: 0건 — 침묵)
  Q2. top_k=15 확장 창에서 pash류 오프토픽이 게이트(0.45) 위에 있는가?
      (c42: rank 7 · 0.7423 — 예측 (b)의 근거)
  Q3. 백필 처치가 현 조건에서 실제로 발화하는가?
      (top_k=5 통과 ≥ MAX_RECALLS이면 백필은 no-op)

주의(c51 교훈 — 검증자의 니들을 의심하라): 이 스크립트는 라이브 :8000에 실검색을
보내는 것이지 트랜스크립트 니들 매칭이 아니므로 채널 맹점 계열과는 다른 채널이다.
단 세션 ledger(seen/캡슐 중복)는 재현하지 않는다 — 아래 CAVEAT 참조.
"""
import importlib.util
import json
import os
import sys

HOOK_DIR = os.path.expanduser("~/.forget/hooks")
sys.path.insert(0, HOOK_DIR)

spec = importlib.util.spec_from_file_location(
    "forget_turnrecall", os.path.join(HOOK_DIR, "forget_turnrecall.py"))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

# 이 사이클 데몬 프롬프트 원문(세션 실측과 동일 질의) — 훅과 동일하게 [:300] 절단.
PROMPT = (
    "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소(/Users/junghunkim/orca/workspaces/"
    "forget/내-프롬프트를-공유하기-싫어, 브랜치 main-work)의 LOOP.md(헌장)와 "
    "research/devloop/cycle-prompt.md(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 "
    "따른다. 0단계 회상은 forget의 get_task_state(task_id='devloop')로 시작하고, "
    "너는 이 작업의 기억 없이 태어났으므로 복원 품질을 metrics.jsonl에 정직하게 채점해 "
    "남겨라 — 그 채점이 제품의 자연실험이다."
)[:300]

CWD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

OFFTOPIC_NEEDLES = ("pash", "트윗", "tweet", "information asymmetry", "tenting")


def classify(item):
    """훅 main()의 필터 순서를 그대로 재현(세션 ledger 제외). 반환: (판정, 이유)."""
    md = item.get("metadata") or {}
    score = float(item.get("score") or 0.0)
    if md.get("hook"):
        return "drop", "hook-pointer"
    if md.get("assertion_kind") == "task_state":
        return "drop", "task_state"
    if md.get("superseded_by") or (isinstance(md.get("supersedes"), list) and md.get("supersedes")):
        return "conflict", f"conflict-pair(gate {hook.CONFLICT_THRESHOLD})"
    if score < hook.SCORE_THRESHOLD:
        return "drop", f"below-gate({hook.SCORE_THRESHOLD})"
    return "pass", "-"


def replay(top_k):
    project = None if scope_disabled() else project_key_for_path(CWD)
    args = {"query": PROMPT, "top_k": top_k, "recall": "low"}
    if project:
        args["filters"] = layered_filter(project)
    res = hook._rpc("search_memories", args)
    rows = []
    passes = 0
    for rank, item in enumerate(res.get("results") or [], 1):
        verdict, why = classify(item)
        text = (item.get("memory") or "").replace("\n", " ")
        offtopic = any(n in text.lower() for n in OFFTOPIC_NEEDLES)
        if verdict == "pass":
            passes += 1
        injected = verdict == "pass" and passes <= hook.MAX_RECALLS
        rows.append({
            "rank": rank,
            "score": round(float(item.get("score") or 0.0), 4),
            "verdict": verdict,
            "why": why,
            "would_inject": injected,
            "offtopic_needle": offtopic,
            "text90": text[:90],
        })
    return rows


def main():
    print(f"query[:60]: {PROMPT[:60]}")
    print(f"hook constants: MAX_RECALLS={hook.MAX_RECALLS} top_k(현행)={hook.MAX_RECALLS + 2} "
          f"gate={hook.SCORE_THRESHOLD}")
    for top_k in (5, 15):
        rows = replay(top_k)
        inject = [r for r in rows if r["would_inject"]]
        off_in_window = [r for r in rows if r["offtopic_needle"] and r["score"] >= hook.SCORE_THRESHOLD]
        print(f"\n=== top_k={top_k} ===")
        for r in rows:
            mark = "INJ" if r["would_inject"] else ("off" if r["offtopic_needle"] else "   ")
            print(f"{r['rank']:>3}. {r['score']:.4f}  {r['verdict']:<8} {r['why']:<22} {mark}  {r['text90']}")
        print(f"→ 주입 {len(inject)}건 / 게이트 위 오프토픽(니들) {len(off_in_window)}건")
    print("\nCAVEAT: 세션 ledger(seen·캡슐 중복 억제)는 재현하지 않음 — 실세션에서는 캡슐이"
          " 이미 보여준 기억이 추가로 떨어질 수 있으므로 여기 '주입'은 상한이다."
          " (c42 재생도 동일 조건이므로 대조는 유효.)")


if __name__ == "__main__":
    main()
