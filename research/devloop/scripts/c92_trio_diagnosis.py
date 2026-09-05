#!/usr/bin/env python3
"""사이클 92 계기 — 얼어붙은 훅 트리오(c43·c42·c45)의 1차 증거 진단 (읽기 전용).

집행 대상: audit-90 **R3** — "얼어붙은 훅 3건에 처치 사이클 1개를 배정한다.
최소 단위는 수리가 아니라 1차 증거 진단 1사이클(왜 같은 3건이 회전하는가 —
**점수·스코프·쓰기 시각** 중 무엇인가)."

무엇을 재는가.
  c46~c91 원장 28행이 같은 세 기억(c42 결정+발견 · c43 발견 · c45 발견)의 주입을
  miss로 계상했다. audit-90 N4: c46 이후 recall_misses 123 중 81(65.9%)이 이 트리오.
  처치 배정 0회. 이 계기는 고치지 않는다 — **원인 축을 가른다.**

방법 (게임 내성).
  자기보고(metrics)나 기억을 근거로 쓰지 않는다. `hooks/forget_turnrecall.py`를
  import해 훅과 **같은 함수·같은 파라미터**로 라이브 스토어(:8000)를 재생하고,
  랭킹·점수 성분·메타데이터·created_at을 그대로 인쇄한다. `main()`은 호출하지
  않는다(원장·세션 상태 무기록). 유일한 의도적 이탈: `trace`를 넘기지 않는다
  (추적행 쓰기 회피 — 랭킹에는 무영향, §A 헤더에 명시).

축의 조작화.
  (S) 점수  — 트리오가 고정 질의에서 최상위이고 신규 devloop 기억이 그 아래인가.
  (C) 스코프 — 신규 devloop 기억이 layered_filter에서 탈락하는가.
  (W) 쓰기   — 스토어에 애초에 신규 devloop **기억행**이 없는가(= 회상이 아니라
              쓰기 문제. 루프가 사이클 발견을 add_memory 대신 record_task_state로만
              남겼다면 훅은 원리적으로 최신 발견을 못 본다 — task_state 하드 배제).

출력은 판정을 인쇄하되 근거 수치를 함께 인쇄한다 — 판정만 남기면 다음 손이 재검할 수 없다.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "hooks"))

import forget_turnrecall as hook  # noqa: E402
from forget_project import layered_filter, project_key_for_path  # noqa: E402

# 이 사이클의 실제 프롬프트(축자). c27 마찰("코퍼스 선정법 미기록")에 따라
# 질의를 코드에 고정한다 — 훅은 prompt[:300]을 질의로 쓰므로 이 문자열이 곧 질의다.
CYCLE_PROMPT = (
    "devloop 사이클을 정확히 한 바퀴 실행하라. 이 저장소(/Users/junghunkim/orca/workspaces/forget/"
    "내-프롬프트를-공유하기-싫어, 브랜치 main-work)의 LOOP.md(헌장)와 research/devloop/cycle-prompt.md"
    "(지시서)를 먼저 읽고 지시서의 절차 0~5를 그대로 따른다. 0단계 회상은 forget의 "
    "get_task_state(task_id='devloop')로 시작하고, 너는 이 작업의 기억 없이 태어났으므로 복원 품질을 "
    "metrics.jsonl에 정직하게 채점해 남겨라 — 그 채점이 제품의 자연실험이다. 금지: 릴리스 태그, "
    "배포(vercel/npm/pypi), 외부 발신, ~/.forget 실DB 파괴적 조작. 게이트가 필요한 산출물은 만들어두고 "
    "'게이트 대기'로 보고만 한다. 커밋과 push는 허용된다."
)

# 트리오 식별은 id가 아니라 **본문 지문**으로 한다(원장이 id를 남기지 않았다).
TRIO_FINGERPRINTS = {
    "c43": "사이클 43 발견",
    "c42": "사이클 42 결정+발견",
    "c45": "사이클 45 발견",
}


def short(text: str, n: int = 72) -> str:
    return str(text or "").replace("\n", " ")[:n]


def trio_tag(text: str) -> str:
    for tag, needle in TRIO_FINGERPRINTS.items():
        if needle in str(text or ""):
            return tag
    return ""


def meta_of(item: dict) -> dict:
    return item.get("metadata") or {}


def describe(item: dict, rank: int) -> str:
    md = meta_of(item)
    bd = item.get("score_breakdown") or {}
    flags = []
    if md.get("hook"):
        flags.append("hook")
    if md.get("assertion_kind") == "task_state":
        flags.append("task_state")
    if hook._conflict_pair(item):
        flags.append("conflict")
    elig = "Y" if hook._injection_eligible(item) else "N"
    tag = trio_tag(item.get("memory"))
    return (
        f"  #{rank:<2} score={float(item.get('score') or 0):.4f} "
        f"rule={bd.get('rule')} vec={bd.get('vector')} elig={elig} "
        f"{'TRIO:' + tag if tag else ''}\n"
        f"      id={item.get('id')} created={item.get('created_at')} "
        f"len={len(str(item.get('memory') or ''))} proj={md.get('project')!r} "
        f"layer={md.get('scope_layer')!r} flags={flags or '-'}\n"
        f"      {short(item.get('memory'), 110)}"
    )


def part_a(project):
    """훅과 동일 파라미터 재생 — 무엇이 실제로 창에 들어오는가."""
    print("[A. 훅 재생 — 같은 함수·같은 파라미터, main() 미호출]")
    print(f"    query = prompt[:300] (len={len(CYCLE_PROMPT[:300])}), "
          f"top_k={hook.CANDIDATE_TOP_K}, recall=low, score_breakdown=True")
    print(f"    project={project!r}  gate={hook.SCORE_THRESHOLD} "
          f"semantic_floor={hook.SEMANTIC_FLOOR} margin={hook.FLATNESS_MARGIN} "
          f"PICK_POOL={hook.PICK_POOL} MAX_RECALLS={hook.MAX_RECALLS}")
    print("    ※ 의도적 이탈 1: trace 미전달(추적행 쓰기 회피). 랭킹 무영향.")
    args = {
        "query": CYCLE_PROMPT[:300],
        "top_k": hook.CANDIDATE_TOP_K,
        "recall": "low",
        "score_breakdown": True,
    }
    flt = layered_filter(project)
    if flt:
        args["filters"] = flt
    result = hook._rpc("search_memories", args)
    results = result.get("results") or []
    print(f"    후보 {len(results)}건")
    for i, item in enumerate(results, 1):
        print(describe(item, i))
    # 훅의 실제 선택 재현 (seen 원장은 이 세션 것을 쓰지 않는다 — 순수 점수 경로)
    eligible = [x for x in results if hook._injection_eligible(x)]
    scores = sorted((float(x.get("score") or 0) for x in eligible), reverse=True)[:hook.FLATNESS_WINDOW]
    measurable = len(scores) >= hook.FLATNESS_MIN_SAMPLES
    flat = measurable and (scores[0] - scores[len(scores) // 2]) < hook.FLATNESS_MARGIN
    print(f"\n    [평탄도] 자격후보={len(eligible)} 창점수={[round(s, 4) for s in scores]} "
          f"measurable={measurable} flat={flat}")
    picks = [x for x in results[:hook.PICK_POOL]
             if hook._injection_eligible(x) and float(x.get("score") or 0) >= hook.SCORE_THRESHOLD]
    print(f"    [선택] PICK_POOL 내 자격·게이트 통과 = {len(picks)}건: "
          f"{[trio_tag(p.get('memory')) or short(p.get('memory'), 24) for p in picks]}")
    return results


def part_b(project):
    """스토어의 devloop 기억행 전수 — 쓰기 축(W)."""
    print("\n[B. 스토어의 '[devloop]' 기억행 전수 — 쓰기 시각 축]")
    flt = {"AND": [layered_filter(project), {"memory": {"icontains": "[devloop]"}}]} if project \
        else {"memory": {"icontains": "[devloop]"}}
    args = {"query": "devloop 사이클 발견 결정", "top_k": 200, "recall": "low", "filters": flt}
    try:
        result = hook._rpc("search_memories", args, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"    조회 실패: {exc}")
        return []
    rows = result.get("results") or []
    print(f"    '[devloop]' 포함 기억행 {len(rows)}건 (top_k=200 상한)")
    dated = sorted(rows, key=lambda r: str(r.get("created_at") or ""))
    for item in dated:
        md = meta_of(item)
        kind = "task_state" if md.get("assertion_kind") == "task_state" else (
            "hook" if md.get("hook") else "memory")
        print(f"    {str(item.get('created_at'))[:19]}  {kind:<10} "
              f"len={len(str(item.get('memory') or '')):<5} "
              f"proj={md.get('project')!r} id={item.get('id')}  {short(item.get('memory'), 60)}")
    if dated:
        print(f"    → 가장 오래된 {str(dated[0].get('created_at'))[:19]} / "
              f"가장 최근 {str(dated[-1].get('created_at'))[:19]}")
    return rows


def part_c(project, deep_k=120):
    """같은 고정 질의로 깊게 인출 — 신규 devloop 기억은 몇 위인가 (점수 축 S)."""
    print(f"\n[C. 같은 질의·깊은 인출(top_k={deep_k}) — 트리오와 신규 devloop 기억의 순위 대조]")
    args = {
        "query": CYCLE_PROMPT[:300],
        "top_k": deep_k,
        "recall": "low",
        "score_breakdown": True,
    }
    flt = layered_filter(project)
    if flt:
        args["filters"] = flt
    try:
        result = hook._rpc("search_memories", args, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"    조회 실패: {exc}")
        return []
    rows = result.get("results") or []
    print(f"    후보 {len(rows)}건 · 게이트 {hook.SCORE_THRESHOLD} 이상 "
          f"{sum(1 for r in rows if float(r.get('score') or 0) >= hook.SCORE_THRESHOLD)}건")
    print("    -- '[devloop]' 기억행만 발췌 (순위/점수/자격/작성시각) --")
    for i, item in enumerate(rows, 1):
        text = str(item.get("memory") or "")
        if "[devloop]" not in text:
            continue
        md = meta_of(item)
        elig = "Y" if hook._injection_eligible(item) else "N"
        tag = trio_tag(text)
        gate = "PASS" if float(item.get("score") or 0) >= hook.SCORE_THRESHOLD else "----"
        print(f"    #{i:<3} {float(item.get('score') or 0):.4f} {gate} elig={elig} "
              f"{'TRIO:' + tag if tag else '      '} "
              f"created={str(item.get('created_at'))[:19]} len={len(text):<5} {short(text, 54)}")
    print("    -- PICK_POOL(상위 5) 밖에서 자격 있는 '[devloop]' 행이 있으면 창 고갈(P10 계열) --")
    return rows


def part_d(project):
    """스코프 축(C) — layered_filter가 무엇을 떨어뜨리는가, 필터 없이 재생해 대조."""
    print("\n[D. 스코프 축 — 같은 질의, layered_filter 없이 재생(대조군)]")
    args = {
        "query": CYCLE_PROMPT[:300],
        "top_k": hook.CANDIDATE_TOP_K,
        "recall": "low",
        "score_breakdown": True,
    }
    try:
        result = hook._rpc("search_memories", args, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"    조회 실패: {exc}")
        return
    rows = result.get("results") or []
    print(f"    필터 없는 상위 {len(rows)}건:")
    for i, item in enumerate(rows, 1):
        md = meta_of(item)
        tag = trio_tag(item.get("memory"))
        print(f"    #{i:<2} {float(item.get('score') or 0):.4f} "
              f"proj={md.get('project')!r} layer={md.get('scope_layer')!r} "
              f"{'TRIO:' + tag if tag else ''} {short(item.get('memory'), 60)}")
    print("    → 필터 유/무의 상위 집합이 같으면 스코프 축은 원인이 아니다.")


def part_f(deep_rows):
    """반사실 — 배제 후 백필(PICK_POOL 확장)이 얼어붙음을 푸는가. 읽기 전용 투영."""
    print("\n[F. 반사실 투영 — '배제 후 백필'만으로 얼어붙음이 풀리는가]")
    print("    현행 훅: results[:PICK_POOL=5]만 훑는다 → 무자격 claim 2건이 슬롯 2개를 먹고")
    print("    남은 3칸이 곧 주입 3건. 만약 백필(자격 후보만 세어 3건 채우기)로 바꾼다면?")
    for depth in (5, 10, 20, 40):
        pool = deep_rows[:depth]
        picks = [x for x in pool
                 if hook._injection_eligible(x) and float(x.get("score") or 0) >= hook.SCORE_THRESHOLD][:hook.MAX_RECALLS]
        labels = []
        for p in picks:
            tag = trio_tag(p.get("memory"))
            labels.append(f"TRIO:{tag}" if tag else short(p.get("memory"), 34))
        print(f"    depth={depth:<3} 주입 3건 = {labels}")
    print("    → 깊이를 늘려도 들어오는 것은 '최근 기억'이 아니라 '그 다음으로 긴 옛 기억'이면,")
    print("      백필(하네스측 값싼 수리)은 얼어붙음의 레버가 아니다.")


def part_g(deep_rows):
    """축 분리 — 점수는 길이를 재는가, 최근성을 재는가 (순위상관, 게임 내성)."""
    print("\n[G. 축 분리 — 순위상관(스피어만). 손수 라벨 없음, 값은 스토어에서만 나온다]")
    rows = [r for r in deep_rows if "[devloop]" in str(r.get("memory") or "")
            and hook._injection_eligible(r)]
    if len(rows) < 8:
        print(f"    표본 부족({len(rows)}) — 생략")
        return
    scores = [float(r.get("score") or 0) for r in rows]
    lengths = [len(str(r.get("memory") or "")) for r in rows]
    stamps = [str(r.get("created_at") or "") for r in rows]

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1
            for k in range(i, j + 1):
                out[order[k]] = avg
            i = j + 1
        return out

    def spearman(a, b):
        ra, rb = rank(a), rank(b)
        n = len(a)
        ma, mb = sum(ra) / n, sum(rb) / n
        num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
        den = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
        return num / den if den else float("nan")

    print(f"    표본 n={len(rows)} ('[devloop]' 자격 기억행, 같은 고정 질의)")
    print(f"    spearman(len,   score) = {spearman(lengths, scores):+.3f}")
    print(f"    spearman(recency, score) = {spearman(stamps, scores):+.3f}   "
          f"(created_at 문자열 순 = 시간 순)")
    top = sorted(zip(scores, lengths, stamps), reverse=True)[:3]
    bot = sorted(zip(scores, lengths, stamps))[:3]
    print(f"    상위 3: {[(round(s, 4), l, t[:10]) for s, l, t in top]}")
    print(f"    하위 3: {[(round(s, 4), l, t[:10]) for s, l, t in bot]}")
    print("    → len 상관이 높고 recency 상관이 0 근처면, 점수축은 길이이지 최근성이 아니다.")


def part_h(deep_rows):
    """점수 성분 전수 — 어느 성분이 판별하는가 (rule/vector만 인쇄하면 합성을 못 본다)."""
    print("\n[H. score_breakdown 전 키 — 판별 성분의 소재]")
    keys = set()
    for r in deep_rows[:40]:
        keys |= set((r.get("score_breakdown") or {}).keys())
    print(f"    관측된 breakdown 키: {sorted(keys) or '없음'}")
    for i, r in enumerate(deep_rows[:8], 1):
        bd = r.get("score_breakdown") or {}
        tag = trio_tag(r.get("memory"))
        print(f"    #{i} score={float(r.get('score') or 0):.4f} "
              f"len={len(str(r.get('memory') or '')):<5} {'TRIO:' + tag if tag else '':<9} "
              f"{ {k: bd[k] for k in sorted(bd)} }")
    print("    ※ vector가 좁은 띠에 포화하면 판별은 rule 쪽에 있다(훅 docstring의 실측과 대조).")


def part_i(deep_rows):
    """판별력의 소재 — 가중치가 큰 채널이 판별하는 채널인가 (동적 범위 × 가중치).

    합성식은 소스 확인분이다 (forget/store.py:4790·4807·4811):
        score = 0.45*rule + 0.55*vector (+ min(0.14, 0.06*|entity_overlap|))
    가중치는 vector 쪽이 크지만, 그 채널이 좁은 띠에 포화하면 **순위를 정하는 것은
    가중치가 작은 rule 쪽**이다. 여기서 그 두 기여의 실제 범위를 잰다.
    """
    print("\n[I. 판별력의 소재 — 기여도 범위 (합성식은 store.py:4807 확인분)]")
    RULE_W, VEC_W = 0.45, 0.55
    rows = [r for r in deep_rows if "[devloop]" in str(r.get("memory") or "")
            and hook._injection_eligible(r) and (r.get("score_breakdown") or {}).get("rule") is not None]
    if len(rows) < 8:
        print(f"    표본 부족({len(rows)}) — 생략")
        return
    rule = [float((r.get("score_breakdown") or {})["rule"]) for r in rows]
    vec = [float((r.get("score_breakdown") or {})["vector"]) for r in rows]
    print(f"    표본 n={len(rows)}  (가중치 rule={RULE_W} vector={VEC_W})")
    print(f"    rule   원범위 [{min(rule):.4f}, {max(rule):.4f}] 폭 {max(rule) - min(rule):.4f} "
          f"→ 가중 기여 폭 {RULE_W * (max(rule) - min(rule)):.4f}")
    print(f"    vector 원범위 [{min(vec):.4f}, {max(vec):.4f}] 폭 {max(vec) - min(vec):.4f} "
          f"→ 가중 기여 폭 {VEC_W * (max(vec) - min(vec)):.4f}")
    ent = sum(1 for r in rows if (r.get("score_breakdown") or {}).get("entity_boost"))
    print(f"    entity_boost 보유 {ent}/{len(rows)}건 (각 +0.06, 이산) — 한계 좌석의 결정자")
    print("    → 가중 기여 폭이 큰 쪽이 순위를 정한다. vector가 포화면 큰 가중치가 무력하다.")

    # 한계 좌석 산술: 3번째 주입 슬롯이 entity_boost로 갈리는가
    ranked = sorted(rows, key=lambda r: -float(r.get("score") or 0))
    print("    -- 한계 좌석 검산 (entity_boost 제거 시 순위) --")
    for r in ranked[:6]:
        bd = r.get("score_breakdown") or {}
        boost = float(bd.get("entity_boost") or 0.0)
        base = float(r.get("score") or 0) - boost
        tag = trio_tag(r.get("memory"))
        print(f"      {float(r.get('score') or 0):.4f} (boost {boost:.2f} 제거 시 {base:.4f}) "
              f"len={len(str(r.get('memory') or '')):<5} {'TRIO:' + tag if tag else short(r.get('memory'), 30)}")


def main():
    project = project_key_for_path(REPO)
    print("=" * 100)
    print("c92 얼어붙은 훅 트리오 진단 — audit-90 R3 집행 (읽기 전용, main() 미호출)")
    print("=" * 100)
    results = part_a(project)
    part_b(project)
    deep_rows = part_c(project)
    part_d(project)
    part_f(deep_rows)
    part_g(deep_rows)
    part_h(deep_rows)
    part_i(deep_rows)
    print("\n[E. 판정 재료 요약]")
    trio_in_window = [trio_tag(r.get("memory")) for r in results if trio_tag(r.get("memory"))]
    print(f"    훅 창(top_k={hook.CANDIDATE_TOP_K}) 안의 트리오: {trio_in_window or '없음'}")
    print("    축 판정은 노트(notes/cycle-92-*.md)에 기재한다 — 이 스크립트는 수치만 낳는다.")


if __name__ == "__main__":
    main()
