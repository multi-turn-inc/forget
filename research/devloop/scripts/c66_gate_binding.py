#!/usr/bin/env python3
"""c66 — 회상 게이트(0.45)가 아직 구속력이 있는가: 대조군 동반 실측 (read-only, 2026-08-07).

계기: c59 oracle replay 비재현 추적 결과 :8000의 몸이 08-06 16:45에 교체됐고
(forget_ai 0.4.0, 저장소본과 22/22 바이트 동일), 비-devloop 커밋 fd30a68이
"임베딩 경로 수리"를 포함한다. 신 스택에서 주제-정렬 질의의 vector 성분이
0.84~0.95로 올라 regime C 25행 **전원**이 게이트 0.45를 통과했다.

질문: 게이트가 판별력을 잃은 것이 (가) 온토픽 질의에 국한된 정상 동작인가,
(나) 질의 무관하게 전역적으로 비구속인가. (나)이면 훅은 게이트가 아니라
MAX_RECALLS(=3) 랭킹만으로 주입하며, 그것은 필드노트 #2(회상 관련성)의 회귀다.

원칙 1 준수 — 대조군 설계:
  ON  : 스토어에 실제 관련 기억이 있는 질의 (devloop·forget 주제)
  OFF : 스토어와 무관한 질의 (음식·물리·행정) — 이 질의에서 게이트 통과가
        많이 나오면 게이트는 관련성 판별에 실패하고 있다는 직접 증거
  판정값은 예단하지 않는다. OFF의 통과가 0이면 (가)가 지지된다.

    .venv/bin/python research/devloop/scripts/c66_gate_binding.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "c59_oracle_replay", os.path.join(HERE, "c59_oracle_replay.py"))
c59 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c59)

GATE = c59.hook.SCORE_THRESHOLD
MAX_RECALLS = c59.hook.MAX_RECALLS
TOP_K = 15

ON = [
    ("on-1 devloop 절차", "devloop 사이클 절차 0 회상 restore_turns 채점"),
    ("on-2 오라클 재생", "oracle replay silent_miss 게이트 분모 판정"),
    ("on-3 임베딩 스택", "임베딩 차원 재임베딩 프로바이더 스택 선언"),
]
OFF = [
    ("off-1 음식", "김치찌개에 넣을 돼지고기 부위와 신김치 숙성 정도"),
    ("off-2 물리", "lattice QCD 격자 간격과 윌슨 루프 재규격화"),
    ("off-3 행정", "자동차 종합보험 갱신 만기일과 특약 변경 절차"),
    ("off-4 원예", "몬스테라 잎이 노랗게 변할 때 물주기 간격 조정"),
]


def probe_k(query, top_k):
    from forget_project import layered_filter, project_key_for_path, scope_disabled
    project = None if scope_disabled() else project_key_for_path(c59.CWD)
    args = {"query": query, "top_k": top_k, "recall": "low", "score_breakdown": True}
    if project:
        args["filters"] = layered_filter(project)
    rows = c59.hook._rpc("search_memories", args).get("results") or []
    out = []
    for r in rows:
        bd = r.get("score_breakdown") or {}
        out.append({
            "score": float(r.get("score") or 0.0),
            "rule": bd.get("rule"), "vector": bd.get("vector"),
            "text": " ".join((r.get("memory") or "").split()),
        })
    return out


def summarize(label, query):
    rows = probe_k(query, TOP_K)
    passes = [r for r in rows if r["score"] >= GATE]
    vecs = [r["vector"] for r in rows if isinstance(r["vector"], (int, float))]
    injected = passes[:MAX_RECALLS]
    print(f"\n--- {label} ---")
    print(f"  질의: {query}")
    print(f"  결과 {len(rows)}건 | 게이트 통과 {len(passes)}/{len(rows)} "
          f"({len(passes) / len(rows) * 100:.0f}%)" if rows else "  결과 0건")
    if vecs:
        print(f"  vector 성분: {min(vecs):.3f}~{max(vecs):.3f} (중앙 근사 "
              f"{sorted(vecs)[len(vecs) // 2]:.3f})")
    if rows:
        print(f"  최고 {rows[0]['score']:.4f} / 최저 {rows[-1]['score']:.4f}")
    for r in injected:
        print(f"    [주입될 것] {r['score']:.4f} {r['text'][:95]}")
    return len(passes), len(rows)


def main():
    print("c66 — 회상 게이트 구속력 실측 (대조군 동반)")
    print(f"gate={GATE} MAX_RECALLS={MAX_RECALLS} top_k={TOP_K} | "
          f"몸: forget_ai 0.4.0, :8000 pid 기동 08-06 16:45:56")

    print("\n" + "=" * 74 + "\n[ON 군 — 스토어에 관련 기억 있음]")
    on_stats = [summarize(l, q) for l, q in ON]
    print("\n" + "=" * 74 + "\n[OFF 군 — 대조군, 스토어와 무관]")
    off_stats = [summarize(l, q) for l, q in OFF]

    def rate(stats):
        p = sum(a for a, _ in stats)
        t = sum(b for _, b in stats)
        return p, t, (p / t * 100 if t else 0.0)

    op, ot, orate = rate(on_stats)
    fp, ft, frate = rate(off_stats)
    print("\n" + "=" * 74)
    print("=== 판정 재료 ===")
    print(f"  ON  게이트 통과 {op}/{ot} = {orate:.0f}%")
    print(f"  OFF 게이트 통과 {fp}/{ft} = {frate:.0f}%   <-- 대조군")
    print(f"  선택도(ON−OFF) = {orate - frate:+.0f}%p")
    if frate >= 80:
        print("  → 게이트는 **전역 비구속**. 무관 질의도 통과하므로 관련성 판별은 "
              "사실상 MAX_RECALLS 랭킹이 전담한다 (필드노트 #2 회귀 후보).")
    elif frate <= 20:
        print("  → 게이트는 여전히 구속적. regime C 전원 통과는 온토픽 질의의 "
              "정상 동작으로 읽힌다 (가설 (가) 지지).")
    else:
        print("  → 중간대. 단일 표본으로 단정 금지 — 질의 수를 늘려 재측정.")

    # --- 2단: 훅 충실 재현 -------------------------------------------------
    # 게이트 0.45가 전역 비구속이어도 훅은 2차 방어를 갖는다. fd30a68이 도입한
    # 평탄도 게이트(FLATNESS_MARGIN)와 SEMANTIC_FLOOR가 실제 주입을 막는지가
    # 제품 영향의 진짜 판정이다. 훅은 top_k=MAX_RECALLS+2=5로 검색한다 —
    # 1단의 top_k=15와 다르므로 평탄도 판정도 5행 기준으로 재현해야 한다.
    import re as _re
    _ht = open(os.path.expanduser("~/.forget/hooks/forget_turnrecall.py"),
               encoding="utf-8").read()

    def _const(name, default):
        m = _re.search(name + r'\s*=\s*float\(os\.environ\.get\([^,]+,\s*"([\d.]+)"', _ht)
        return float(m.group(1)) if m else default

    margin = _const("FLATNESS_MARGIN", 0.03)
    floor = _const("SEMANTIC_FLOOR", 0.30)
    hook_top_k = MAX_RECALLS + 2

    print("\n" + "=" * 74)
    print(f"=== 2단: 훅 충실 재현 (top_k={hook_top_k}, flatness margin={margin}, "
          f"semantic floor={floor}) ===")
    print("  훅 순서: task_state/hook 제외 → 게이트 0.45 → **평탄도** → semantic floor")
    suppressed = injected_any = 0
    for label, query in ON + OFF:
        rows = probe_k(query, hook_top_k)
        scores = sorted((r["score"] for r in rows), reverse=True)
        flat = len(scores) >= 4 and (scores[0] - scores[len(scores) // 2]) < margin
        gated = [r for r in rows if r["score"] >= GATE]
        after_floor = [r for r in gated
                       if not (isinstance(r["vector"], (int, float)) and r["vector"] < floor)]
        final = [] if flat else after_floor[:MAX_RECALLS]
        spread = (scores[0] - scores[len(scores) // 2]) if len(scores) >= 4 else float("nan")
        tag = "**평탄→전량 억제**" if flat else f"주입 {len(final)}건"
        print(f"  {label:<16} spread(top−중앙)={spread:.4f}  "
              f"게이트통과={len(gated)}/{len(rows)}  {tag}")
        if flat:
            suppressed += 1
        elif final:
            injected_any += 1
            for r in final:
                print(f"       [실주입] {r['score']:.4f} {r['text'][:80]}")
    print(f"\n  평탄도 게이트가 억제한 질의: {suppressed}/{len(ON + OFF)}  "
          f"| 실제 주입이 발생한 질의: {injected_any}/{len(ON + OFF)}")
    print("  → 이 2단 결과가 제품 영향의 판정이다. 1단(게이트 비구속)은 "
          "**오라클 계기**의 문제이고, 2단이 통과를 막으면 회상 품질 회귀는 아니다.")

    print("\nCAVEAT: ① 질의 7개는 소표본이고 이 손이 골랐다 — OFF 군이 스토어와 "
          "정말 무관한지는 어휘 판단에 의존한다 ② 현재 스토어·현재 스택 단일 시점 "
          "측정이며 구 스택 대조가 없다(설치본이 이미 교체됨 — 구 스택 재현에는 "
          "0.3.x 롤백이 필요하고 그것은 실DB 위험이라 하지 않았다) ③ '주입될 것'은 "
          "훅의 세션 ledger·중복 억제를 재현하지 않은 상한 추정.")


if __name__ == "__main__":
    main()
