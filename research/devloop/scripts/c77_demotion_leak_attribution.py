#!/usr/bin/env python3
"""c77 — 관측 33 부수 관측(a9402b0c 강등 누출)의 기전 귀속 (read-only, $0).

c69는 이 행을 "사용자 발언을 그대로 인용하면서 `metadata.hook`이 없어 세션 캡처
×0.5 강등을 빠져나간다 — 강등이 성질이 아니라 대리 표지에 걸려 있다"로 등재했다
(frictions.md 관측 33 부수 관측). 이 사이클은 그 프레임을 **믿지 않고 판별한다**:
처치(강등 확대)가 유효하려면 강등 누락이 관측된 해악(무관 질의 top-5 침입)의
**구속 기전**이어야 한다. 행 자체는 trust.kind=fact인 실제 선호 기억이므로,
잘못 넓힌 강등은 trust 계약(source=user 녹색 사실은 1급 기억)을 역전시킨다.

경합 가설 (선선언 — 판정 규칙을 실행 전에 고정한다, c64 자기규율):
  H_A  강등 누락이 구속적: 반사실 ×0.5(캡처 강등)만으로 이 행이 재현 질의의
       **과반**에서 훅 창(top-5) 밖 & 게이트(0.45) 아래로 떨어진다.
  H_C1 rule 바닥이 구속적(F2/C1): 저장소 몸 rule 분해에서 junk 토큰(c22 자격
       기준의 부정: len<2 또는 숫자)의 기여를 빼면 게이트 통과가 무너지거나,
       junk가 rule 기여의 과반이다.
  H_V  임베딩 어트랙터: rule 기여가 미미한데 vector 항(0.55×v, 구척도)만으로
       게이트를 넘는다 (rule=0 통과선 cos ≥ 0.6364, c72 아핀 연역).
  부수: 클래스 강등(무hook·trust.source=user 전체 ×0.5)의 온토픽 부수 피해 —
       이 행이 자기 주제 질의에서 순위를 잃으면 강등 확대 처치의 반대 증거.

몸 선언 (원칙 3 — 두 산술 혼용 금지, 병기만 한다):
  · 순위·반사실 재조립 = **살아 있는 몸**(:8000 설치본 forget_ai 0.4.0, 구척도
    vector=(cos+1)/2, 게이트 0.45). c69의 11/15 관측과 같은 몸.
  · rule 성분 분해 = **저장소 몸**(forget/memory_engine.score_memory) — 처치가
    내려앉을 몸. 저장소/서버 rule 값을 병기해 이전 가능성을 보고한다.

대조군 규약 (관측 34): 무관 질의는 **이 사이클에서 새로 뽑았고**(c68 OFF·c69
nf 계열 재사용 금지), 어절(len≥3) 스토어 전문 미등장 ≥2를 SQL로 검사해 통과분만
쓴다. 질의 원문은 이 계기 파일에만 있다 — 보고·기억에는 라벨로만 지칭한다(관측 36).

반사실 산술의 근거: 합성 사슬(store.py:4807-4851)에서 캡처 강등 이후의 연산은
스코프 폴백 ×0.88 곱셈뿐이고 클램프가 없으므로, 반사실 점수 = 서빙 점수 × 0.5가
정확하다. 재조립 자체는 c69의 F1 검증된 compose_score로 전 풀 행에서 재확인한다.

read-only: 서버는 search_memories만(계기 검색은 recall 계상 제외 — c68 선언),
DB는 sqlite mode=ro. 쓰기 0 · LLM 0(recall=low) · 외부 비용 $0.

    .venv/bin/python research/devloop/scripts/c77_demotion_leak_attribution.py
"""
from __future__ import annotations

import collections
import importlib.util
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone

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
c59 = c68.c59
DB = c68.DB
GATE = c68.GATE_NOW
LEAK = "a9402b0c-9b84-4489-b65d-c70ecc050249"
HOOK_WINDOW = 5            # 훅 top_k=5 — c69의 "11/15 top-5" 관측 창 승계
POOL = 200
TOL = 0.0002

# 신선 무관 질의 — c77에서 새로 뽑음(재사용 금지, 관측 34 ①). 적격 검사 통과분만 쓴다.
FRESH_OFF = [
    ("nf77-1 양봉", "월동 봉군의 사양액 급이와 응애 방제 시점 조절"),
    ("nf77-2 천문", "세페이드 변광성의 광도곡선 주기와 거리지수 보정"),
    ("nf77-3 염색", "쪽물 발효 염액의 환원 상태와 매염제 농도 관리"),
    ("nf77-4 철도", "곡선부 궤도의 캔트 부족량과 완화곡선 체감 설정"),
    ("nf77-5 수의", "반추위 산증의 조사료 배합비와 반추 자극 관리"),
    ("nf77-6 기상", "뇌우 셀의 발달 단계와 하강돌풍 탐지 지표"),
    ("nf77-7 판금", "박판 용접의 열변형 억제와 구속지그 배치 설계"),
    ("nf77-8 유가공", "응유효소 첨가량과 커드가름 시점의 산도 기준"),
    ("nf77-9 악기", "파이프오르간 송풍압 조정과 리드관 정음 작업"),
    ("nf77-10 잠수", "감압 정지의 수심 산정과 잔류질소 배출 계획"),
]

# 온토픽 질의 — 누출 행 자신의 주제(부수 피해 반사실용). OFF 라벨이 아니므로
# 소모(관측 34) 대상이 아니다. 원문은 이 파일에만 둔다.
ON_TOPIC = [
    ("ot-1 자율승인", "Quant 자율 실행의 승인 요건과 자격증명 재요청 정책"),
    ("ot-2 주문승인", "브로커 주문 제출 취소의 명시적 승인 요건"),
]


def eligible(queries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """c69 적격 검사 승계: 어절(len≥3) 중 스토어 전문 미등장이 2개 이상."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    keep = []
    for label, q in queries:
        tokens = [t for t in q.split() if len(t) >= 3]
        clean = 0
        for t in tokens:
            cur.execute("select count(*) from memories where deleted=0 and memory like ?",
                        (f"%{t}%",))
            if cur.fetchone()[0] == 0:
                clean += 1
        ok = clean >= 2
        print(f"  {label:<14} 어절(≥3자) {len(tokens)}개 중 미등장 {clean}개  "
              f"{'적격' if ok else '★ 부적격'}")
        if ok:
            keep.append((label, q))
    con.close()
    return keep


def probe_full(query: str, top_k: int) -> list[dict]:
    """c69 probe_pool 확장 — 스코프 폴백 플래그·생성시각까지 보존한다."""
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
            "rule": float(bd.get("rule") or 0.0),
            "vector": float(bd.get("vector") or 0.0),
            "entity_boost": float(bd.get("entity_boost") or 0.0),
            "keyword": float(bd.get("keyword") or 0.0),
            "superseded": bool(bd.get("superseded")),
            "session_capture": bool(bd.get("session_capture")),
            "fallback": (r.get("scope") == "fallback"),
            "created_at": str(r.get("created_at") or ""),
        })
    return sorted(out, key=lambda x: -x["score"])


def f1_check(pool: list[dict], fb: dict[str, float]) -> tuple[int, int, int]:
    """서빙 점수를 compose_score로 재조립 — 반사실 조작의 유효성 전제."""
    ok = bad = bypass = 0
    for r in pool:
        if r["rule"] == 0.0 and r["vector"] == 0.0 and r["score"] > 0:
            bypass += 1          # task_state 우회 행(라이브 몸엔 c76 표지 없음)
            continue
        cand = c69.compose_score(
            r["rule"], r["vector"], entity_boost=r["entity_boost"], keyword=r["keyword"],
            feedback_adjust=fb.get(r["id"], 0.0), superseded=r["superseded"],
            session_capture=r["session_capture"], scope_fallback=r["fallback"])
        if abs(cand - r["score"]) <= TOL:
            ok += 1
        else:
            bad += 1
    return ok, bad, bypass


def leak_class_ids() -> tuple[set[str], dict[str, int]]:
    """강등 누출 클래스: trust.source=user 이면서 metadata.hook 부재 (deleted=0)."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("select id, agent_id, metadata from memories where deleted=0")
    ids: set[str] = set()
    stats = {"class": 0, "codex": 0, "with_interpretation": 0, "hooked_user": 0}
    for mid, agent, meta_raw in cur.fetchall():
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except (TypeError, ValueError):
            meta = {}
        trust = meta.get("trust") or {}
        if trust.get("source") != "user":
            continue
        if meta.get("hook"):
            stats["hooked_user"] += 1
            continue
        ids.add(str(mid))
        stats["class"] += 1
        if agent == "codex":
            stats["codex"] += 1
        if "interpretation" in meta:
            stats["with_interpretation"] += 1
    con.close()
    return ids, stats


def load_leak_row() -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    row = con.execute("select * from memories where id=?", (LEAK,)).fetchone()
    con.close()
    if row is None:
        raise SystemExit(f"누출 행 {LEAK[:8]}이 스토어에 없다 — 전제 붕괴, 판정 불가")
    d = dict(row)
    try:
        cats = json.loads(d.get("categories") or "[]")
    except (TypeError, ValueError):
        cats = []
    return {"memory": d.get("memory") or "", "categories": cats,
            "updated_at": d.get("updated_at")}


def rule_decompose(query: str, mem: dict) -> dict:
    """저장소 몸 score_memory(memory_engine.py:672-702)의 성분 분해 + junk 귀속.

    자기 검증: 성분 합이 같은 몸의 score_memory 출력과 일치해야 한다(불일치면
    분해를 신뢰하지 않는다 — c66 '실제 사슬을 재현하고 나서 문장을 써라').
    junk 기준은 c22 자격 필터의 부정: len<2 또는 숫자 토큰.
    """
    from forget.memory_engine import expanded_tokens, score_memory, temporal_bonus, parse_datetime
    q_tokens = expanded_tokens(query)
    m_tokens = expanded_tokens(str(mem.get("memory", "")))
    if not q_tokens:
        return {}
    overlap = q_tokens.intersection(m_tokens)
    coverage = len(overlap) / len(q_tokens)
    jaccard = len(overlap) / (len(q_tokens.union(m_tokens)) or 1)
    lowered_memory = str(mem.get("memory", "")).lower()
    phrase_hits = [t for t in q_tokens if t in lowered_memory]
    phrase = 0.02 * len(phrase_hits) + (0.25 if query.lower() in lowered_memory else 0.0)
    categories = {str(c).lower() for c in mem.get("categories", [])}
    category = 0.12 if q_tokens.intersection(categories) else 0.0
    anchor = datetime.now(timezone.utc)
    updated = parse_datetime(mem.get("updated_at"))
    recency = 0.0
    if updated:
        age_days = max((anchor - updated).total_seconds() / 86400, 0)
        recency = 0.08 * math.exp(-age_days / 60)
    temporal = temporal_bonus(query, mem, None)
    total = max(0.0, min(1.0, round(0.45 * coverage + 0.35 * jaccard + phrase
                                    + category + recency + temporal, 4)))
    ref = score_memory(query, mem)
    is_junk = lambda t: len(t) < 2 or t.isdigit()   # noqa: E731
    junk_phrase_hits = [t for t in phrase_hits if is_junk(t)]
    junk_overlap = {t for t in overlap if is_junk(t)}
    # junk 제거 반사실: junk 토큰이 애초에 질의에 없었다면의 rule 값
    q_clean = frozenset(t for t in q_tokens if not is_junk(t))
    if q_clean:
        ov_c = q_clean.intersection(m_tokens)
        cov_c = len(ov_c) / len(q_clean)
        jac_c = len(ov_c) / (len(q_clean.union(m_tokens)) or 1)
        phr_c = 0.02 * sum(1 for t in q_clean if t in lowered_memory) \
            + (0.25 if query.lower() in lowered_memory else 0.0)
        no_junk = max(0.0, min(1.0, round(0.45 * cov_c + 0.35 * jac_c + phr_c
                                          + category + recency + temporal, 4)))
    else:
        no_junk = None
    return {
        "coverage": coverage, "jaccard": jaccard, "phrase": phrase,
        "category": category, "recency": recency, "temporal": temporal,
        "total": total, "ref": ref, "self_ok": abs(total - ref) <= TOL,
        "q_n": len(q_tokens), "overlap_n": len(overlap),
        "junk_overlap_n": len(junk_overlap), "phrase_n": len(phrase_hits),
        "junk_phrase_n": len(junk_phrase_hits), "rule_no_junk": no_junk,
    }


def rank_of(pool: list[dict], scores: dict[str, float], target: str) -> tuple[int | None, float | None]:
    if target not in scores:
        return None, None
    s = scores[target]
    rank = 1 + sum(1 for r in pool if r["id"] != target and scores[r["id"]] > s)
    return rank, s


def main() -> None:
    print("c77 — a9402b0c 강등 누출의 기전 귀속")
    print("=" * 78)
    print(f"몸 선언: 순위·반사실 = 살아 있는 몸(:8000 구척도, 게이트 {GATE}) / "
          "rule 분해 = 저장소 몸(병기, 혼용 금지)")
    print(f"누출 행: {LEAK[:8]}  훅 창 top-{HOOK_WINDOW}  풀 깊이 {POOL}")

    print("\n[0. 클래스 크기 — 강등 누출 클래스(trust.source=user · hook 부재)]")
    cls_ids, stats = leak_class_ids()
    print(f"  클래스 {stats['class']}행 (그중 codex {stats['codex']} · "
          f"interpretation 동반 {stats['with_interpretation']}) / "
          f"hook 있는 user행 {stats['hooked_user']}")
    print(f"  누출 행 클래스 소속: {LEAK in cls_ids}")

    print("\n[1. 신선 무관 질의 적격 검사 (관측 34 — 어휘는 새로, 미등장 기계 확인)]")
    off = eligible(FRESH_OFF)
    print(f"  적격 {len(off)}/{len(FRESH_OFF)}")

    fb = c69.load_feedback_adjust()
    leak_fb = fb.get(LEAK, 0.0)
    print(f"\n[2. 반사실 전제 — F1 재조립 검증]  누출 행 피드백 보정: {leak_fb:+.2f}")
    mem = load_leak_row()

    per_q = []
    f1_tot = [0, 0, 0]
    print(f"\n  {'질의':<14}{'서빙점수':>9}{'순위':>5}{'게이트':>7}"
          f"{'×0.5점수':>9}{'×0.5순위':>8}{'×0.5게이트':>9}   rule(서버)  vec(서빙)")
    for label, q in off:
        pool = probe_full(q, POOL)
        ok, bad, byp = f1_check(pool, fb)
        f1_tot = [f1_tot[0] + ok, f1_tot[1] + bad, f1_tot[2] + byp]
        served = {r["id"]: r["score"] for r in pool}
        base_rank, base_score = rank_of(pool, served, LEAK)
        if base_rank is None:
            per_q.append({"label": label, "q": q, "in_pool": False})
            print(f"  {label:<14}{'풀 밖':>9}")
            continue
        leak_row = next(r for r in pool if r["id"] == LEAK)
        cf = dict(served)
        cf[LEAK] = round(served[LEAK] * 0.5, 4)
        cf_rank, cf_score = rank_of(pool, cf, LEAK)
        pool_pass = sum(1 for r in pool if r["score"] >= GATE)
        per_q.append({
            "label": label, "q": q, "in_pool": True,
            "rank": base_rank, "score": base_score,
            "gate": base_score >= GATE, "top5": base_rank <= HOOK_WINDOW,
            "cf_rank": cf_rank, "cf_score": cf_score,
            "cf_gate": cf_score >= GATE, "cf_top5": cf_rank <= HOOK_WINDOW,
            "rule_server": leak_row["rule"], "vector": leak_row["vector"],
            "fallback": leak_row["fallback"], "pool_pass": pool_pass,
            "pool_n": len(pool),
        })
        print(f"  {label:<14}{base_score:>9.4f}{base_rank:>5}"
              f"{'통과' if base_score >= GATE else '아래':>7}"
              f"{cf[LEAK]:>9.4f}{cf_rank:>8}"
              f"{'통과' if cf_score >= GATE else '아래':>9}   "
              f"{leak_row['rule']:>8.4f}  {leak_row['vector']:>8.4f}"
              f"  [풀 게이트 통과 {pool_pass}/{len(pool)}]")
    print(f"  F1 재조립: 일치 {f1_tot[0]} / 불일치 {f1_tot[1]} / task_state 우회 {f1_tot[2]}"
          f"  (불일치>0이면 반사실 산술을 신뢰하지 않는다)")

    hits = [p for p in per_q if p.get("top5") and p.get("gate")]
    print(f"\n  재현: 훅 창 침입(top-5·게이트 통과) {len(hits)}/{len(off)}  "
          f"[c69 관측은 11/15 — 다른 질의 표본, 직접 비교 아님(라벨 만료)]")

    print("\n[3. rule 분해 — 저장소 몸 (junk = len<2 또는 숫자, c22 자격 기준의 부정)]")
    print(f"  {'질의':<14}{'rule(repo)':>10}{'자기검증':>8}{'junk覆':>7}{'junk句':>7}"
          f"{'rule(무junk)':>12}{'phrase':>8}{'recency':>8}")
    for p in per_q:
        if not p.get("in_pool"):
            continue
        d = rule_decompose(p["q"], mem)
        p["rule_repo"] = d["total"]
        p["rule_no_junk"] = d["rule_no_junk"]
        p["decompose"] = d
        print(f"  {p['label']:<14}{d['total']:>10.4f}"
              f"{'일치' if d['self_ok'] else '★불일치':>8}"
              f"{d['junk_overlap_n']:>5}/{d['overlap_n']}"
              f"{d['junk_phrase_n']:>5}/{d['phrase_n']}"
              f"{(d['rule_no_junk'] if d['rule_no_junk'] is not None else float('nan')):>12.4f}"
              f"{d['phrase']:>8.4f}{d['recency']:>8.4f}")

    print("\n[4. 온토픽 부수 피해 반사실 — 클래스 강등(무hook user행 전체 ×0.5)이 "
          "이 행의 자기 주제 순위를 깨는가]")
    for label, q in ON_TOPIC:
        pool = probe_full(q, POOL)
        served = {r["id"]: r["score"] for r in pool}
        base_rank, base_score = rank_of(pool, served, LEAK)
        if base_rank is None:
            print(f"  {label:<14} 풀 밖 — 온토픽인데 표면화되지 않음(그 자체가 관측)")
            continue
        cf = {r["id"]: (round(r["score"] * 0.5, 4) if r["id"] in cls_ids and not r["session_capture"]
                        else r["score"]) for r in pool}
        cf_rank, cf_score = rank_of(pool, cf, LEAK)
        winner = max(pool, key=lambda r: cf[r["id"]])
        print(f"  {label:<14} 현재 rank {base_rank}({base_score:.4f}) → 클래스 강등 후 "
              f"rank {cf_rank}({cf_score:.4f}, 게이트 {'통과' if cf_score >= GATE else '아래'})"
              f"  강등 후 1위: {winner['id'][:8]}"
              f"{' (클래스 밖)' if winner['id'] not in cls_ids else ' (같은 클래스)'}")

    print("\n[5. 판정 — 선선언 규칙 적용]")
    if hits:
        h_a = sum(1 for p in hits if not p["cf_top5"] and not p["cf_gate"])
        vec_only = [round(0.55 * p["vector"], 4) for p in hits]
        h_v = sum(1 for v in vec_only if v >= GATE)
        h_c1 = 0
        for p in hits:
            nj = p.get("rule_no_junk")
            if nj is None:
                continue
            # junk 제거 반사실 rule로 서빙 사슬을 다시 합성(구척도, 저장소 rule을 대입한
            # 교차 계산이므로 '병기'로만 읽는다): junk가 게이트 통과의 결정 요인인가
            with_j = c69.compose_score(p["rule_repo"], p["vector"],
                                       feedback_adjust=leak_fb,
                                       scope_fallback=p["fallback"])
            without_j = c69.compose_score(nj, p["vector"],
                                          feedback_adjust=leak_fb,
                                          scope_fallback=p["fallback"])
            if with_j >= GATE > without_j:
                h_c1 += 1
        n = len(hits)
        print(f"  H_A (강등 누락 구속): 반사실 ×0.5로 창 밖+게이트 아래 {h_a}/{n} → "
              f"{'지지' if h_a * 2 > n else '기각(과반 미달)'}")
        print(f"  H_V (벡터 단독 통과): 0.55×vec ≥ {GATE} 인 침입 {h_v}/{n}")
        print(f"  H_C1 (junk가 통과 결정): junk 제거 시 게이트 붕괴 {h_c1}/{n} "
              f"(저장소 rule 대입 교차 계산 — 병기)")
    else:
        print("  침입 재현 0 — 신선 표본에서 해악이 재현되지 않았다. 귀속 판정을 내지 않고")
        print("  c69 표본과의 차이(질의·시점)를 기록한다. '재현 안 됨'은 '해소'가 아니다.")

    if hits:
        print("\n[6. 사후 분석 — 선선언 규칙 H_A의 결함 (실행 후 발견, 사후임을 명기)]")
        print("  H_A는 '이 행이 창 밖으로 떨어지는가'를 재는데, OFF 질의의 top-5는 정의상")
        print("  전부 무관하다(적격 검사가 스토어 미등장을 보장) — 행 하나를 강등해도 다른")
        print("  무관 행이 그 자리를 채운다. 해악(무관 침입) 수준에서 강등은 회전이지 감소가")
        print("  아니다. 회전의 물증 = 위 [풀 게이트 통과 n/200] (c68 FPR=1.00의 재확인).")
        avg_pass = sum(p["pool_pass"] for p in hits) / len(hits)
        print(f"  침입 질의의 풀 내 게이트 통과 평균: {avg_pass:.1f}/200")

        print("\n[7. 저장소 몸 투영 — ⑮ 배포(vector=max(0,cos), c72 아핀 제거)가 이 표본을 고치는가]")
        print("  병기용 투영: 0.45×rule(repo) + 0.55×max(0,2v−1) + fb. 순위는 계산하지")
        print("  않는다(풀 전체의 repo 재채점이 필요 — 이 투영은 게이트 통과 여부만 본다).")
        for p in hits:
            cos = 2 * p["vector"] - 1
            repo_v = max(0.0, cos)
            proj = round(0.45 * p.get("rule_repo", 0.0) + 0.55 * repo_v, 4)
            if leak_fb:
                proj = max(0.0, min(1.0, round(proj + leak_fb, 4)))
            if p["fallback"]:
                proj = round(proj * 0.88, 4)
            print(f"  {p['label']:<14} cos={cos:.4f}  repo 투영={proj:.4f}  "
                  f"게이트 {'통과 — 배포로 안 죽는다' if proj >= GATE else '아래 — 배포가 죽인다'}")

    print("\nCAVEAT: ① 무관함 판정은 이 손+SQL 어절 검사의 합 — 의미적 무관 보장 아님. "
          "② 반사실 순위는 풀(top-200) 내 상대 순위 — 서버 기본 임계 아래 행은 풀 밖. "
          "③ H_C1 교차 계산은 저장소 rule×라이브 vector 합성 — 몸 혼합이므로 판정의 "
          "보조 근거로만 쓴다. ④ 단일 시점·현 스택.")


if __name__ == "__main__":
    main()
