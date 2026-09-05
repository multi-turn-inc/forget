#!/usr/bin/env python3
"""c68 — 회상 게이트 상수(SCORE_THRESHOLD=0.45) 재교정: 문턱 스윕 + 양측 괄호 (read-only, $0).

계기: c66이 게이트의 판별력 0(선택도 +0%p)을 실측하고 재교정을 원장 1순위로 올렸다.
c67이 "독립 대조군 2개 확보"로 넘겼다. 이 사이클의 일은 **새 상수를 정하는 것**이다.

■ 물려받은 귀속의 정정 (c64 자기규율: 앞선 손이 배제하지 못한 대안 설명을 먼저 찾아라)
  c67 원장은 대조군 ②를 "관련 있는 것끼리의 점수 상한"이라고 넘겼다. 1차 증거
  (embedding_space_audit.py:131-140)를 읽으면 그 CONTROL은 **같은 공간의 무작위 쌍**이다
  (queries·others 모두 셔플된 전체 풀에서 zip). 즉 0.9040은 관련 쌍의 상한이 아니라
  **무관 쌍의 기준선**이다. 방향이 반대이므로 재교정의 함의도 반대다: "좋은 매치에 비해
  0.45가 낮다"가 아니라 "**무관한 쌍조차 0.90을 받는다**"(임베딩 비등방성). 이 스크립트는
  그 정정을 읽기가 아니라 **실측**으로 대체한다 — OFF 군이 무관 질의의 실제 점수를 낸다.

■ 재교정이 답해야 하는 것은 "0.45를 얼마로 올리나"가 아니라 먼저 "**어떤 상수든 되나**"다.
  두 개의 한쪽만 유효한(one-sided) 계측기로 양측 괄호를 만든다:

  ON-self 팔 — 자기질의 천장(mechanical, 판단 개입 0):
    무작위 K개 저장 기억을 골라 **그 기억 자신의 텍스트**를 질의로 쓴다. 표적은 id로
    확정되므로 라벨링에 내 어휘 판단이 들어가지 않는다. 자기질의는 회상의 **최선의 경우**
    이므로 여기서 얻는 TPR은 **상한**이다 → 이 팔이 탈락시키는 문턱은 확실히 너무 높다.
    (한쪽만 유효: TPR=1.0은 실전 TPR을 보장하지 않는다. 반대 방향으로만 읽어라.)

    ★ 1차 런의 계측기 결함과 원인 확정 (귀속 전 배제 수행):
      1차 런은 12개 중 10개 표적이 top_15에 아예 없었다. 가설 A(스코프 밖)를 **기각**한다 —
      c68_on_arm_diagnosis.py로 확인: 미반환 10건 전원이 layered_filter를 통과하는 스코프
      안에 있었다(metadata.project='forget' 또는 None). 실제 원인은 **표본이 세션 캡처였다**:
      10건 전원이 metadata.hook='SessionEnd'이고, 제품은 이 행을 설계상 ×0.5로 강등하며
      (store.py:4823-4830) 텍스트가 "세션 캡처 (SessionEnd/other): 세션 <uuid>…" 상투구라
      수백 개의 자기 복제와 거의 동일 점수로 경합한다 → 표적이 창 밖으로 밀린다.
      따라서 ON-self 팔은 **사실 기억만** 표본으로 쓴다(hook 행 제외). 이 제외는 제품이
      이미 하는 강등을 계측기가 따라가는 것이며, 제외 사실과 스토어 구성비를 함께 출력한다.

  ON-real 팔 — 실전 온토픽 질의(이것이 진짜 t_max를 정한다):
    자기질의 천장은 1.0이라 상한을 거의 구속하지 않는다 — 그것만으로 상수를 올리면
    "무관 질의를 막았다"만 보고 "실제 회상도 막았다"를 못 본다. 스토어에 관련 기억이
    있는 온토픽 질의의 **top-1 점수**가 상수의 실질 상한이다. 관련성 판정은 이 손의
    어휘 판단이므로 top-1 원문을 함께 출력해 감사 가능하게 만든다.

  OFF 팔 — 무관 질의 오탐(clean, 행 라벨링 불요):
    스토어에 관련 기억이 존재하지 않는 주제를 묻는다. 통과한 행은 **전부** 오탐이므로
    행 단위 관련성 판정 없이 FPR이 측정된다. (c66 caveat ①: 질의는 이 손이 골랐다.
    무관함은 어휘 판단에 의존한다 — 8개로 확장했으나 소표본은 그대로다.)

  판정: t_max = ON 표적 전원이 통과하는 최대 문턱, t_min = OFF 질의 주입이 0이 되는 최소
  문턱. **t_min > t_max 이면 어떤 상수도 분리하지 못한다** → 고장난 것은 상수가 아니라
  점수다(재교정은 극장이 되고, 처치는 상수 변경이 아니어야 한다).

■ 측정 대상은 훅이 실제로 비교하는 값 = `score` 필드(rule*0.45 + vector*0.55 + 보정).
  raw cosine이 아니다 (c66 자기규율 (다): 실제 필터 사슬을 재현하고 나서 문장을 쓴다).

read-only: search_memories만 호출한다. 쓰기 0, LLM 0(recall=low) → 외부 비용 $0.

    .venv/bin/python research/devloop/scripts/c68_gate_recalibration.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import random
import sqlite3
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "c59_oracle_replay", os.path.join(HERE, "c59_oracle_replay.py"))
c59 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c59)

GATE_NOW = c59.hook.SCORE_THRESHOLD          # 현행 상수 = 재교정 대상
MAX_RECALLS = c59.hook.MAX_RECALLS
HOOK_TOP_K = MAX_RECALLS + 2                 # 훅이 실제로 쓰는 깊이
WIDE_TOP_K = 15                              # 분포 모양 관측용
DB = os.environ.get("FORGET_DB", os.path.expanduser("~/.forget/forget.sqlite3"))
SEED = 68
N_SELF = 12                                  # ON 팔 표본 수
SELF_QUERY_CHARS = 160                        # 자기질의로 쓸 앞부분 길이

# OFF 군 — 스토어(devloop·forget·정훈의 일)와 무관한 주제. 8개로 확장(c66은 4개).
OFF = [
    ("off-1 음식", "김치찌개에 넣을 돼지고기 부위와 신김치 숙성 정도"),
    ("off-2 물리", "lattice QCD 격자 간격과 윌슨 루프 재규격화"),
    ("off-3 행정", "자동차 종합보험 갱신 만기일과 특약 변경 절차"),
    ("off-4 원예", "몬스테라 잎이 노랗게 변할 때 물주기 간격 조정"),
    ("off-5 조류", "북극 제비갈매기의 연간 이동 경로와 번식지 위도"),
    ("off-6 건축", "철근 콘크리트 보의 처짐 한계와 피복 두께 기준"),
    ("off-7 음악", "바로크 통주저음에서 6화음 숫자 표기 읽는 법"),
    ("off-8 의류", "울 니트 세탁 후 늘어난 소매 원래 길이로 줄이기"),
]

# ON-real 군 — 스토어에 관련 기억이 존재하는 온토픽 질의. c66의 ON 3개를 승계하고 확장.
# 어휘를 저장 텍스트에서 그대로 베끼지 않는다(자기질의로 퇴화하지 않게).
ON_REAL = [
    ("on-1 절차0", "devloop 사이클 절차 0 회상 restore_turns 채점"),
    ("on-2 오라클", "oracle replay silent_miss 게이트 분모 판정"),
    ("on-3 스택", "임베딩 차원 재임베딩 프로바이더 스택 선언"),
    ("on-4 벤치", "LME-V2 하네스에서 forget과 RAG 대조 점수"),
    ("on-5 이주", "미국 이주 목표와 법인 설립 시점 판단"),
    ("on-6 피봇", "E2EE 피봇 전략과 개발자 웻지 검증 게이트"),
    ("on-7 발표", "B2B 발표 피드백에서 강제성과 구매 조건"),
    ("on-8 마찰", "캡슐 신선도 마찰과 유동층 stale 마커"),
]

GRID = [round(0.30 + 0.01 * i, 2) for i in range(70)]   # 0.30 ~ 0.99


def verdict_band(
    on_real_top1: list[float],
    off_top1: list[float],
    grid: list[float] | None = None,
) -> dict:
    """허용 상수 구간과 그 신뢰성 판정 — 순수 함수 (테스트가 고정한다).

    관측 32의 수용 기준 ①을 코드로 못 박는다: **자기질의(상한) 팔은 인자가 아니다.**
    분리·최적성 주장은 실전 표본(on_real)과 대조군(off)만으로 계산되며, 상한 팔로는
    이 함수를 호출할 수 없다. 빈 팔은 '판정 불가'이며 '이상 없음'으로 접지 않는다.

    반환: t_min(오탐 0 최소) · t_max(ON-real 전원 통과 상한) · band(폭) ·
          off_scale(OFF 최고점 산포) · verdict in {"판정 불가", "분리 불가", "잡음 안", "분리"}
    """
    if not on_real_top1 or not off_top1:
        return {"verdict": "판정 불가", "t_min": None, "t_max": None,
                "band": None, "off_scale": None}
    grid = grid if grid is not None else GRID
    t_max = min(on_real_top1)
    off_max = max(off_top1)
    t_min = next((t for t in grid if all(s < t for s in off_top1)), None)
    off_scale = off_max - min(off_top1)
    if t_min is None or t_min > t_max:
        verdict = "분리 불가"
        band = None if t_min is None else t_max - t_min
    else:
        band = t_max - t_min
        # 구간이 대조군 산포보다 좁으면 상수는 잡음 안에 앉는다. 그리고 표본을 늘리면
        # t_min↑·t_max↓만 가능하므로 이 구간은 넓어질 수 없다(P22 연역).
        verdict = "잡음 안" if band < off_scale else "분리"
    return {"verdict": verdict, "t_min": t_min, "t_max": t_max,
            "band": band, "off_scale": off_scale}


def probe(query: str, top_k: int) -> list[dict]:
    """훅과 같은 스코프·같은 recall로 검색하고 게이트가 보는 값을 그대로 돌려준다."""
    from forget_project import layered_filter, project_key_for_path, scope_disabled
    args = {"query": query, "top_k": top_k, "recall": "low", "score_breakdown": True}
    if not scope_disabled():
        project = project_key_for_path(c59.CWD)
        if project:
            args["filters"] = layered_filter(project)
    rows = c59.hook._rpc("search_memories", args).get("results") or []
    out = []
    for r in rows:
        bd = r.get("score_breakdown") or {}
        out.append({
            "id": r.get("id") or "",
            "score": float(r.get("score") or 0.0),
            "vector": bd.get("vector"),
            "rule": bd.get("rule"),
            "text": " ".join((r.get("memory") or "").split()),
        })
    return out


def store_composition() -> tuple[int, int]:
    """(사실 기억 수, 세션 캡처 수) — ON-self 표본에서 무엇을 제외했는지 병기하기 위해."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("select metadata from memories where deleted=0")
    fact = hook = 0
    for (md,) in cur.fetchall():
        try:
            is_hook = bool((json.loads(md) if md else {}).get("hook"))
        except (ValueError, TypeError):
            is_hook = False
        if is_hook:
            hook += 1
        else:
            fact += 1
    con.close()
    return fact, hook


def sample_self_queries() -> list[tuple[str, str]]:
    """(memory_id, 자기 텍스트 앞부분) — 표적이 id로 확정되는 ON-self 팔 표본.

    metadata.hook 행(세션 캡처)은 제외한다: 제품이 설계상 ×0.5 강등하고 상투구 복제가
    수백 개라 자기질의조차 창 밖으로 밀린다(1차 런 10/12 미반환의 확정된 원인).
    """
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute(
        "select id, memory, metadata from memories "
        "where deleted=0 and length(memory) >= 80")
    rows = []
    for mid, mem, md in cur.fetchall():
        try:
            if bool((json.loads(md) if md else {}).get("hook")):
                continue
        except (ValueError, TypeError):
            pass
        rows.append((str(mid), str(mem)))
    con.close()
    rng = random.Random(SEED)
    rng.shuffle(rows)
    picked = rows[:N_SELF]
    return [(mid, " ".join(text.split())[:SELF_QUERY_CHARS]) for mid, text in picked]


def main() -> None:
    print("c68 — 게이트 상수 재교정: 문턱 스윕 + 양측 괄호")
    print(f"현행 상수 GATE_NOW={GATE_NOW}  MAX_RECALLS={MAX_RECALLS}  "
          f"hook_top_k={HOOK_TOP_K}  wide_top_k={WIDE_TOP_K}  seed={SEED}")
    print("몸 선언: step 0 [Body] 지문이 정본 (effective 스택을 쓸 것, checks 아님)")

    fact_n, hook_n = store_composition()
    print(f"스토어 구성: 사실 기억 {fact_n} / 세션 캡처(metadata.hook) {hook_n} "
          f"= 전체 {fact_n + hook_n} 중 캡처 {100.0 * hook_n / (fact_n + hook_n):.1f}%")

    # ---------------- ON-self 팔: 자기질의 천장 ----------------
    print("\n" + "=" * 78)
    print("[ON-self 팔] 자기질의(사실 기억만) — 표적은 id로 확정. TPR은 **상한**이다.")
    on_target_scores: list[float] = []
    on_missing = 0
    nontarget_scores: list[float] = []
    for mid, qtext in sample_self_queries():
        rows = probe(qtext, WIDE_TOP_K)
        hit = next((r for r in rows if r["id"] == mid), None)
        if hit is None:
            on_missing += 1
            print(f"  {mid[:8]}  표적 미반환 (top_{WIDE_TOP_K} 밖) — TPR 분자에서 제외")
            continue
        on_target_scores.append(hit["score"])
        nontarget_scores.extend(r["score"] for r in rows if r["id"] != mid)
        rank = next(i for i, r in enumerate(rows) if r["id"] == mid) + 1
        print(f"  {mid[:8]}  표적점수={hit['score']:.4f} rank={rank}/{len(rows)}  "
              f"vector={hit['vector']}  rule={hit['rule']}")
    if not on_target_scores:
        print("  ON 팔 표본 0 — 판정 불가로 종료한다 (미채취를 '이상 없음'으로 접지 않는다).")
        return
    t_self = min(on_target_scores)
    print(f"\n  표적 점수 n={len(on_target_scores)} 미반환={on_missing}  "
          f"min={t_self:.4f} median={statistics.median(on_target_scores):.4f} "
          f"max={max(on_target_scores):.4f}")
    print(f"  → t_self = {t_self:.4f}  (이보다 높은 상수는 **최선의 경우조차** 탈락시킨다)")

    # ---------------- ON-real 팔: 실전 온토픽 상한 ----------------
    print("\n" + "=" * 78)
    print("[ON-real 팔] 온토픽 질의 top-1 — 상수의 **실질** 상한. top-1 원문 병기(감사용).")
    on_real_top1: list[float] = []
    for label, q in ON_REAL:
        rows = probe(q, HOOK_TOP_K)
        if not rows:
            print(f"  {label:<12} 결과 0건 — 상한 계산에서 제외")
            continue
        top = max(rows, key=lambda r: r["score"])
        on_real_top1.append(top["score"])
        print(f"  {label:<12} top1={top['score']:.4f} vec={top['vector']} "
              f"rule={top['rule']}\n       {top['text'][:96]}")
    if not on_real_top1:
        print("  ON-real 표본 0 — 판정 불가로 종료 (미채취를 '이상 없음'으로 접지 않는다).")
        return
    t_max = min(on_real_top1)
    print(f"\n  ON-real top-1 n={len(on_real_top1)} min={t_max:.4f} "
          f"median={statistics.median(on_real_top1):.4f} max={max(on_real_top1):.4f}")
    print(f"  → t_max = {t_max:.4f}  (이보다 높은 상수는 온토픽 질의의 주입을 0으로 만든다)")

    # ---------------- OFF 팔: 무관 질의 오탐 ----------------
    print("\n" + "=" * 78)
    print("[OFF 팔] 무관 질의 — 통과 행은 전부 오탐. 행 라벨링 불요.")
    off_rows_hook: list[list[float]] = []   # 질의별 훅 깊이 점수
    off_rows_wide: list[float] = []
    for label, q in OFF:
        rows_h = probe(q, HOOK_TOP_K)
        rows_w = probe(q, WIDE_TOP_K)
        sh = sorted((r["score"] for r in rows_h), reverse=True)
        off_rows_hook.append(sh)
        off_rows_wide.extend(r["score"] for r in rows_w)
        top = f"{sh[0]:.4f}" if sh else "n/a"
        n_pass_now = sum(1 for s in sh if s >= GATE_NOW)
        print(f"  {label:<12} 결과 {len(rows_h)}건  최고={top}  "
              f"현행 게이트 통과 {n_pass_now}/{len(sh)}")
        for r in rows_h[:2]:
            print(f"       {r['score']:.4f} vec={r['vector']} {r['text'][:70]}")
    off_max = max((s[0] for s in off_rows_hook if s), default=0.0)
    print(f"\n  OFF 최고 점수(훅 깊이) = {off_max:.4f}   "
          f"wide 팔 n={len(off_rows_wide)} "
          f"mean={statistics.mean(off_rows_wide):.4f}" if off_rows_wide else "")

    # ---------------- 스윕 ----------------
    def off_query_fpr(t: float) -> float:
        """주입이 발생하는 OFF 질의의 비율 — 제품 영향의 단위는 질의다."""
        bad = sum(1 for scores in off_rows_hook if any(s >= t for s in scores))
        return bad / len(off_rows_hook)

    def on_tpr(t: float) -> float:
        """온토픽 질의가 여전히 top-1을 주입하는 비율 — 제품 영향의 단위는 질의다."""
        return sum(1 for s in on_real_top1 if s >= t) / len(on_real_top1)

    def self_tpr(t: float) -> float:
        return sum(1 for s in on_target_scores if s >= t) / len(on_target_scores)

    t_min = next((t for t in GRID if off_query_fpr(t) == 0.0), None)

    print("\n" + "=" * 78)
    print("[스윕] 문턱 t → ON-real TPR / OFF 질의 오탐율 / ON-self TPR(상한)")
    print(f"  {'t':>6}  {'TPR(real)':>10}  {'FPR(off)':>10}  {'TPR-FPR':>8}  {'TPR(self)':>10}")
    shown = [t for t in GRID if abs(t * 100 % 5) < 1e-6]        # 0.05 간격
    for t in shown:
        tp, fp = on_tpr(t), off_query_fpr(t)
        mark = "  <- 현행" if abs(t - GATE_NOW) < 1e-9 else ""
        print(f"  {t:6.2f}  {tp:10.2f}  {fp:10.2f}  {tp - fp:+8.2f}  {self_tpr(t):10.2f}{mark}")

    best_t, best_j = max(((t, on_tpr(t) - off_query_fpr(t)) for t in GRID), key=lambda kv: kv[1])

    print("\n" + "=" * 78)
    print("=== 판정 재료 ===")
    print(f"  현행 t={GATE_NOW}:  TPR(real)={on_tpr(GATE_NOW):.2f}  "
          f"FPR(off)={off_query_fpr(GATE_NOW):.2f}  "
          f"선택도={on_tpr(GATE_NOW) - off_query_fpr(GATE_NOW):+.2f}")
    print(f"  t_self (자기질의 천장, 거의 비구속) = {t_self:.4f}")
    print(f"  t_max  (ON-real 전원 주입 상한)     = {t_max:.4f}")
    print(f"  t_min  (OFF 오탐 0 최소)            = "
          f"{'없음(그리드 상한까지 오탐 존재)' if t_min is None else f'{t_min:.4f}'}")
    print(f"  OFF 최고={off_max:.4f}  ON-real 최저={t_max:.4f}  "
          f"분리 여백 = {t_max - off_max:+.4f}")
    print(f"  최대 선택도 = {best_j:+.2f} @ t={best_t:.2f}")
    if t_min is None:
        print("  → 판정: 그리드 내에 오탐 0인 상수가 없다. **상수로는 분리 불가**.")
    elif t_min > t_max:
        print(f"  → 판정: t_min({t_min:.4f}) > t_max({t_max:.4f}) — **어떤 상수도 분리하지 "
              "못한다.** 고장난 것은 상수가 아니라 점수다(비등방성). 상수 변경은 극장이다.")
    else:
        band = t_max - t_min
        print(f"  → 판정: [{t_min:.4f}, {t_max:.4f}] 구간이 존재한다(폭 {band:.4f}). "
              f"권고 상수 = {t_min:.2f} (오탐 0을 사는 최소값).")
        # 폭이 OFF 분포의 잡음 규모보다 좁으면 상수는 잡음 안에 앉는다 — 그 경우
        # "권고값이 있다"는 사실만으로 상수 처치를 정당화하지 않는다.
        off_spread_scale = max(s[0] for s in off_rows_hook if s) - min(
            s[0] for s in off_rows_hook if s)
        print(f"     OFF top1 분포 폭 = {off_spread_scale:.4f} "
              f"(질의 {len(off_rows_hook)}개의 최고점 산포). 허용 구간 폭 {band:.4f}이 이보다 "
              f"{'좁다 — 상수는 잡음 안에 앉는다.' if band < off_spread_scale else '넓다 — 상수 처치가 표본 내에서는 견딘다.'}")
        # 표본 확대는 이 구간을 구제할 수 없다: t_min은 OFF 최고점의 함수라 질의를 더하면
        # 약단조 증가하고, t_max는 ON-real 최저 top-1이라 약단조 감소한다. 구간은 넓어질 수
        # 없고 좁아지거나 소멸한다 → "표본을 늘려 상수를 정당화한다"는 경로는 원리상 닫혔다.
        print("     ★ 구간 단조 축소: 질의를 더하면 t_min↑·t_max↓만 가능하다. 표본 확대는 "
              "상수를 정당화하는 경로가 아니라 **탈락시키는** 경로다 — 상수 처치가 살아남는 "
              "유일한 조건은 표본을 작게 유지하는 것이고 그것은 측정 회피다.")

    # ---------------- 진단(처치 아님): 상대 문턱 ----------------
    # "고장난 것이 상수인가"에 답하려면 상수가 아닌 규칙이 분리하는지 봐야 한다.
    # 상대 규칙 = 질의별 top1 대비 낙폭. 이것은 이 사이클의 처치가 아니라 진단 1줄이다.
    print("\n[진단 — 처치 아님] 질의 내 상대 낙폭이 분리하는가")
    print("  ★ ON 측은 **ON-real**로 잰다. 자기질의 낙폭은 top1=1.0이 만드는 퇴화값이라")
    print("    상대 규칙의 분리력을 과대평가한다(1차 진단의 결함 — 정정본).")
    off_spreads = [s[0] - s[len(s) // 2] for s in off_rows_hook if len(s) >= 4]
    on_spreads = []
    on_flat_suppressed = []
    for label, q in ON_REAL:
        s = sorted((r["score"] for r in probe(q, HOOK_TOP_K)), reverse=True)
        if len(s) >= 4:
            sp = s[0] - s[len(s) // 2]
            on_spreads.append(sp)
            if sp < c59.hook.FLATNESS_MARGIN:
                on_flat_suppressed.append((label, sp))
    self_spreads = []
    for mid, qtext in sample_self_queries():
        s = sorted((r["score"] for r in probe(qtext, HOOK_TOP_K)), reverse=True)
        if len(s) >= 4:
            self_spreads.append(s[0] - s[len(s) // 2])
    if on_spreads and off_spreads:
        for name, vals in (("ON-real", on_spreads), ("OFF    ", off_spreads),
                           ("ON-self", self_spreads)):
            if vals:
                print(f"  {name} spread(top-중앙) n={len(vals)} min={min(vals):.4f} "
                      f"median={statistics.median(vals):.4f} max={max(vals):.4f}")
        overlap = not (min(on_spreads) > max(off_spreads) or min(off_spreads) > max(on_spreads))
        print(f"  ON-real 최저={min(on_spreads):.4f}  OFF 최고={max(off_spreads):.4f}  "
              f"겹침={overlap}")
        margin = c59.hook.FLATNESS_MARGIN
        print(f"  훅의 현행 FLATNESS_MARGIN={margin} — 이 값이 두 분포 사이 간격 "
              f"[{max(off_spreads):.4f}, {min(on_spreads):.4f}]에 "
              f"{'들어앉아 있다(아래 여유 %+.4f / 위 여유 %+.4f)' % (margin - max(off_spreads), min(on_spreads) - margin) if max(off_spreads) < margin < min(on_spreads) else '들어앉아 있지 않다'}")
        if not overlap:
            print("  → 상대 규칙은 이 표본에서 분리한다. 절대 상수가 못 한 일을 이미 하고 있다.")
        else:
            print("  → 상대 규칙도 단독으로는 분리하지 못한다.")
        # 제품 영향의 실수치: 평탄도 게이트가 **온토픽** 질의를 전량 억제하는 횟수.
        # OFF를 전부 막는 대가로 무엇을 함께 막는지가 이 계측의 요점이다.
        off_suppressed = sum(1 for sp in off_spreads if sp < c59.hook.FLATNESS_MARGIN)
        print(f"  평탄도 게이트(margin={c59.hook.FLATNESS_MARGIN}) 실효: "
              f"OFF 억제 {off_suppressed}/{len(off_spreads)} (원하는 동작) · "
              f"ON-real 억제 {len(on_flat_suppressed)}/{len(on_spreads)} (부수 피해)")
        for label, sp in on_flat_suppressed:
            print(f"       [온토픽인데 전량 억제] {label} spread={sp:.4f}")
    else:
        print("  표본 부족 — 판정 불가")

    print("\nCAVEAT: ① ON 팔은 자기질의이므로 TPR은 **상한**이다. TPR=1.0을 실전 재현율로 "
          "읽지 마라 — 이 팔은 '너무 높은 문턱'만 반증한다. ② OFF 8개의 무관함은 이 손의 "
          "어휘 판단이다(c66 caveat ① 승계, 4→8 확장). ③ 단일 시점·현 스택 측정이며 구 "
          "스택 대조는 없다(설치본 교체됨). ④ 훅의 세션 ledger·중복 억제·평탄도 게이트는 "
          "재현하지 않았다 — 여기서 '통과'는 게이트 단독 통과이며 실주입의 상한이다.")


if __name__ == "__main__":
    main()
