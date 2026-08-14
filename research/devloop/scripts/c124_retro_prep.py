#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""c124 — 회고 c125 사전 재료 추출기 (프로그램 재도출본)

목적
----
회고 사이클의 입력은 헌장이 정한 넷이다: 지표 추세 · 마찰 분류 · 감사 결과 ·
예측 대차대조 (LOOP.md "개선 절차"). c125가 이 넷을 **직전 사이클 요약문에서
전사(轉寫)하지 않고 원본에서 재도출**할 수 있도록, 이 계기가 셋을 인쇄한다
(감사 결과는 audits/ 정독 몫이라 여기서는 목록·미처분 권고 열거까지만).

계수 규칙 발행 의무 (c123 신규 R9)
---------------------------------
"원장에 계수를 적는 사이클은 그 계수의 규칙을 계기에 성문화한다."
c122의 무번호 24 vs c123의 25는 어느 쪽이 틀린 게 아니라 **규칙이 없어 대조가
원리적으로 불가능**했다. 그래서 아래 세 절의 계수는 모두 규칙을 함께 인쇄한다.

거짓 양성 회피 (c123 관측 63 상속 금지)
--------------------------------------
관측 63은 처분 판정을 격발어 존재만으로 내려 부정문("…로 닫지 않는다")을
처분으로 오독한 사고다. 이 계기는 그 기전을 상속하지 않기 위해:
  (1) 판정 격발어를 **절 전체가 아니라 표지 있는 줄에서만** 찾는다
      (`- 결과:` / `- **판정 …**:` / `- 처분 …` 계열).
  (2) 지지·반증 격발어가 **한 예측 안에서 공존**하면 자동 판정하지 않고
      SPLIT으로 인쇄해 사람 눈에 넘긴다.
  (3) 표지 줄이 없으면 시계 줄로 강등 분류하고, 그것도 없으면 UNRESOLVED.
즉 이 계기는 **열거와 증거 인쇄**를 하고, 애매한 것은 판정하지 않는다.

사용: .venv/bin/python research/devloop/scripts/c124_retro_prep.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEVLOOP = ROOT / "research" / "devloop"
PRED = DEVLOOP / "predictions.md"
FRIC = DEVLOOP / "frictions.md"
LEDGER = DEVLOOP / "metrics.jsonl"
AUDITS = DEVLOOP / "audits"
AMENDS = DEVLOOP / "amendments"

# ── 계수 규칙 (성문) ────────────────────────────────────────────────────────
RULE_PRED = """[계수 규칙 — 예측]
  단위    = P-식별자 1개. 서식지 둘: (H1) 문서 상단 표의 `| Pn |` 행,
            (H2) `## Pn — …` 절. 둘 다 있으면 절이 정본, 표행은 부기로만 센다.
  중복    = 같은 P-식별자가 절 2개 이상이면 DUPLICATE로 별도 인쇄(분모에서 빼지 않음).
  판정근거 = 절 안에서 정규식 `^-\\s*\\*{0,2}(결과|판정|처분)` 에 걸리는 **표지 줄만**.
            산문 문단은 근거로 쓰지 않는다(관측 63 기전 회피).
  상태    = 표지 줄의 격발어로 분류. 지지계열={성립,적중,지지,확정,인정}
            반증계열={반증,기각,불성립} 폐기계열={폐기,표본 부재,마감}
            공존 시 SPLIT(자동 판정 안 함). 표지 줄 없으면 시계 줄
            (`^-\\s*\\*{0,2}시계`)로 강등: 미시작/미가동 → CLOCK_UNSTARTED,
            가동 → CLOCK_RUNNING. 시계 줄도 없으면 UNRESOLVED."""

RULE_FRIC = """[계수 규칙 — 마찰/관측]
  단위    = frictions.md의 `^## ` 헤딩 1개(= 1절).
  분류    = 헤딩 문자열만 본다(본문 미열람 — 이 계기는 처분 판정을 하지 않는다).
            NUMBERED  : `관측 <숫자>` 가 있고 `보강` 이 없음
            REINFORCE : `보강` 포함 (신규 번호 아님 — 분모 무영향)
            UNNUMBERED: `미분류 관측` 인데 숫자 없음
            F_SERIES  : `F<숫자>` 로 시작하는 대장/절
            OTHER     : 나머지
  재발    = 헤딩에 `재발` 또는 `n=<숫자>` 포함 여부(헤딩 자기 신고 기준).
  주의    = 이 계수는 **재고(미해소 수)가 아니다.** 재고는 c123이 정독으로
            48~57 범위를 냈고, 원장의 open_observations(자동 36)는 그 범위의 하단이다."""

RULE_METRIC = """[계수 규칙 — 지표 추세]
  단위    = metrics.jsonl 한 행 = 한 사이클. 창 = 10사이클 고정 폭.
  결측    = 필드가 없는 행은 그 필드의 분모에서 제외하고 n을 병기(0으로 채우지 않음).
  tests   = 문자열에서 `^(\\d+) passed` 를 뽑아 정수화. 실패 서술은 None으로 두고 별도 열거."""

SUP = ("성립", "적중", "지지", "확정", "인정")
REF = ("반증", "기각", "불성립")
DIS = ("폐기", "표본 부재", "마감")

MARK_RE = re.compile(r"^-\s*\*{0,2}(결과|판정|처분)")
CLOCK_RE = re.compile(r"^-\s*\*{0,2}시계")

# ── 규칙 v2 (c124 신설) — 표지 줄의 다의성 처치 ─────────────────────────────
# 이 대장에서 `- 판정:` 은 **두 가지**를 라벨한다: (α) 등록 시 판정 **기준**
# ("각 처치 배선 후 +5사이클. 양방향 반증 가능") 과 (β) 사후 판정 **결과**
# ("**판정 (c76, 2026-08-08)**: 적중"). v1은 둘을 구분하지 않아 (α)의
# "양방향 **반증** 가능"·"…이면 **반증**으로 계상" 같은 **조건절의 격발어**를
# 결과로 읽는다 — 관측 63과 같은 계열의 거짓 양성이며, 서식지만 다르다.
# 판별자: 결과 줄은 **판정 시점 도장**(사이클 N / cN / 날짜)을 달고 있다.
#         조항 줄(`처분 조항`·`판정 조항`·`판정 시한`)은 미래 조건이므로 제외.
STAMP_RE = re.compile(r"\(\s*(?:사이클\s*\d+|c\d+|\d{4}-\d{2}-\d{2})")
CLAUSE_RE = re.compile(r"^-\s*\*{0,2}(처분 조항|판정 조항|판정 시한|판정 채널)")


def _is_verdict_line(s: str) -> bool:
    """v2: 표지 줄이 '판정 결과'를 담는가 (기준 선언·조항이 아니라)."""
    if CLAUSE_RE.match(s):
        return False
    return bool(STAMP_RE.search(s))
PSEC_RE = re.compile(r"^##\s+(P\d+[a-z]?)\s*[—-]")
PROW_RE = re.compile(r"^\|\s*(P\d+[a-z]?)\s*\|")


# ── 손 판정 (c124, v1↔v2 불일치 17건 전수) ─────────────────────────────────
# 규칙: 각 절의 표지 줄 전문을 읽고 "이 예측의 실제 처분"을 정한 뒤, v1·v2가
# 그것을 맞혔는지 채점한다. **불일치 집합만** 판정했다 — 두 규칙이 일치하는
# 24건은 미감사이며, 따라서 아래 오류율은 전수가 아니라 **하한**이다.
# 값 = (실제 처분, v1 정오, v2 정오). 'BOTH_WRONG'은 어느 규칙도 못 맞힌 것.
ADJUDICATED: dict[str, tuple[str, bool, bool]] = {
    "P3b": ("CLOCK_UNSTARTED", False, True),
    "P5":  ("CLOCK_UNSTARTED", False, True),
    "P6":  ("CLOCK_UNSTARTED", False, True),
    "P11": ("CLOCK_UNSTARTED", False, True),
    "P27": ("CLOCK_UNSTARTED", False, True),
    "P12": ("CLOCK_RUNNING", False, True),
    "P25": ("UNRESOLVED(판정줄 부재)", False, True),
    "P36": ("PENDING(달력 시계 09-10)", False, True),
    "P37": ("PENDING→외부 판정(커밋 4ed88f1, 대장 미반영)", False, True),
    # v1이 맞고 v2가 틀린 것 — 도장 없는 진짜 처분 줄을 v2가 버렸다
    "P26": ("DISCARDED(기한 도과 강제 마감)", True, False),
    "P29": ("DISCARDED(표본 2로 마감)", True, False),
    "P8":  ("PARTIAL(문면 성립·처치 귀속 불가)", True, False),
    # 둘 다 틀린 것 — 어휘에 없는 상태이거나, 도장 없는 처분 줄
    "P10": ("전제 소멸(예측 자체가 무효화)", False, False),
    "P18": ("DISCARDED(처분=폐기, 무도장)", False, False),
    "P28": ("DISCARDED(표본 1로 마감, 무도장)", False, False),
    "P33": ("무판정 마감(지지도 반증도 아님)", False, False),
    # 어느 쪽도 단독으로 옳다고 하기 어려운 것
    "P30": ("혼합(예측 존속 + (a) 표본 부재 마감)", False, False),
}

# 어휘 밖 상태 — 두 규칙 다 원리적으로 표현할 수 없는 처분들
VOCAB_GAP = ["무판정 마감(P33)", "표본 부재 마감(P30)", "전제 소멸(P10)",
             "문면 성립·귀속 불가(P8)"]


def _read(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


# ── 1. 예측 대차대조 ────────────────────────────────────────────────────────
def predictions() -> dict:
    lines = _read(PRED)
    # 절 경계
    sections: list[tuple[str, int, int]] = []
    starts = [(i, m.group(1)) for i, l in enumerate(lines) if (m := PSEC_RE.match(l))]
    for k, (i, pid) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        # 다음 `## ` 헤딩(P가 아닌 것 포함)에서도 끊는다
        for j in range(i + 1, end):
            if lines[j].startswith("## "):
                end = j
                break
        sections.append((pid, i, end))

    table_only = []
    seen_sec = {pid for pid, _, _ in sections}
    for i, l in enumerate(lines):
        m = PROW_RE.match(l)
        if m and m.group(1) not in seen_sec:
            table_only.append((m.group(1), i))

    dup = [pid for pid, c in Counter(p for p, _, _ in sections).items() if c > 1]

    def _classify(marks: list[str], clocks: list[str]) -> str:
        blob = " ".join(marks)
        flags = [any(t in blob for t in SUP), any(t in blob for t in REF),
                 any(t in blob for t in DIS)]
        if marks:
            if sum(flags) > 1:
                return "SPLIT"
            if flags[0]:
                return "SUPPORTED"
            if flags[1]:
                return "REFUTED"
            if flags[2]:
                return "DISCARDED"
            return "MARK_NO_TOKEN"
        if clocks:
            cb = " ".join(clocks)
            return "CLOCK_UNSTARTED" if ("미시작" in cb or "미가동" in cb) else "CLOCK_RUNNING"
        return "UNRESOLVED"

    recs = []
    for pid, s, e in sections:
        body = lines[s:e]
        marks = [l.strip() for l in body if MARK_RE.match(l.strip())]
        clocks = [l.strip() for l in body if CLOCK_RE.match(l.strip())]
        v_marks = [l for l in marks if _is_verdict_line(l)]
        status = _classify(marks, clocks)          # v1 (나이브)
        status2 = _classify(v_marks, clocks)       # v2 (도장 판별)
        ev = (v_marks[-1] if v_marks else (marks[-1] if marks else
              (clocks[-1] if clocks else "")))[:150]
        recs.append({"id": pid, "line": s + 1, "status": status, "status2": status2,
                     "marks": len(marks), "vmarks": len(v_marks), "evidence": ev,
                     "title": lines[s].lstrip("# ").strip()[:90]})

    for pid, i in table_only:
        cell = lines[i].split("|")
        last = cell[-2].strip() if len(cell) >= 3 else ""
        has_sup = any(t in last for t in SUP)
        has_ref = any(t in last for t in REF)
        if has_sup and has_ref:
            status = "SPLIT"
        elif has_ref:
            status = "REFUTED"
        elif has_sup:
            status = "SUPPORTED"
        elif "대기" in last:
            status = "CLOCK_RUNNING"
        else:
            status = "UNRESOLVED"
        recs.append({"id": pid, "line": i + 1, "status": status, "status2": status,
                     "marks": 0, "vmarks": 0,
                     "evidence": last[:150], "title": "(표행 단독)"})

    recs.sort(key=lambda r: (int(re.sub(r"\D", "", r["id"]) or 0), r["id"]))
    return {"records": recs, "duplicates": dup,
            "counts": Counter(r["status"] for r in recs),
            "counts2": Counter(r["status2"] for r in recs),
            "disagree": [r for r in recs if r["status"] != r["status2"]]}


# ── 2. 마찰/관측 헤딩 계수 ──────────────────────────────────────────────────
def frictions() -> dict:
    heads = [(i + 1, l) for i, l in enumerate(_read(FRIC)) if l.startswith("## ")]
    buckets: dict[str, list] = defaultdict(list)
    recur = []
    for ln, h in heads:
        t = h[3:].strip()
        if "보강" in t:
            kind = "REINFORCE"
        elif re.search(r"관측\s*\d+", t):
            kind = "NUMBERED"
        elif "미분류 관측" in t:
            kind = "UNNUMBERED"
        elif re.match(r"F\d+", t):
            kind = "F_SERIES"
        else:
            kind = "OTHER"
        buckets[kind].append((ln, t))
        if "재발" in t or re.search(r"n=\d+", t):
            recur.append((ln, kind, t[:100]))
    return {"buckets": buckets, "recurrences": recur,
            "counts": {k: len(v) for k, v in sorted(buckets.items())}}


# ── 3. 지표 추세 ────────────────────────────────────────────────────────────
def ledger() -> dict:
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows.sort(key=lambda r: r["cycle"])
    out = []
    lo = 0
    while lo <= rows[-1]["cycle"]:
        hi = lo + 9
        w = [r for r in rows if lo <= r["cycle"] <= hi]
        if w:
            rt = [r["restore_turns"] for r in w if isinstance(r.get("restore_turns"), (int, float))]
            gr = Counter(r.get("restore_grade") for r in w)
            hits = sum(r.get("recall_hits", 0) or 0 for r in w)
            miss = sum(r.get("recall_misses", 0) or 0 for r in w)
            fl = sum(r.get("frictions_logged", 0) or 0 for r in w)
            ff = sum(r.get("frictions_fixed", 0) or 0 for r in w)
            tp = []
            fails = []
            for r in w:
                m = re.match(r"(\d+)\s+passed", str(r.get("tests", "")))
                if m:
                    tp.append(int(m.group(1)))
                else:
                    fails.append((r["cycle"], str(r.get("tests"))[:60]))
            out.append({"window": f"c{lo}-c{hi}", "n": len(w),
                        "rt_n": len(rt), "rt_mean": (sum(rt) / len(rt)) if rt else None,
                        "rt_max": max(rt) if rt else None,
                        "grades": dict(gr), "hits": hits, "misses": miss,
                        "fl": fl, "ff": ff,
                        "tests_min": min(tp) if tp else None,
                        "tests_max": max(tp) if tp else None,
                        "tests_nonnum": fails})
        lo += 10
    oo = [(r["cycle"], r["open_observations"]) for r in rows if "open_observations" in r]
    pcu = [(r["cycle"], r["product_code_unchanged_streak"]) for r in rows
           if "product_code_unchanged_streak" in r]
    return {"windows": out, "open_obs": oo, "pcu": pcu, "rows": rows}


def main() -> int:
    print("=" * 78)
    print("c124 — 회고 c125 사전 재료 (프로그램 재도출 / 전사 금지)")
    print("=" * 78)

    # 1
    p = predictions()
    print("\n" + RULE_PRED)
    print(f"\n[1] 예측 대차대조 — 총 {len(p['records'])}건")
    if p["duplicates"]:
        print(f"    !! DUPLICATE 식별자: {p['duplicates']}  (개명 패킷 게이트 대기 항목과 대조할 것)")
    print("    상태     v1(나이브)  v2(도장 판별)")
    for k in sorted(set(p["counts"]) | set(p["counts2"])):
        print(f"    {k:16s} {p['counts'].get(k, 0):3d}  →  {p['counts2'].get(k, 0):3d}")
    print(f"\n    v1↔v2 불일치 {len(p['disagree'])}건 / {len(p['records'])} "
          f"= {100*len(p['disagree'])/len(p['records']):.1f}%  (아래 * 표시)")
    print("\n    id      line  v1               v2               증거(v2가 채택한 줄)")
    for r in p["records"]:
        flag = "*" if r["status"] != r["status2"] else " "
        print(f"  {flag} {r['id']:6s} {r['line']:5d}  {r['status']:16s} {r['status2']:16s} {r['evidence'][:96]}")

    # ── 손 판정 채점 (불일치 집합 전수) ──────────────────────────────────
    dis_ids = [r["id"] for r in p["disagree"]]
    scored = [(i, ADJUDICATED[i]) for i in dis_ids if i in ADJUDICATED]
    missing = [i for i in dis_ids if i not in ADJUDICATED]
    v1_ok = sum(1 for _, (_, a, _) in scored if a)
    v2_ok = sum(1 for _, (_, _, b) in scored if b)
    both_wrong = [i for i, (_, a, b) in scored if not a and not b]
    print(f"\n    [손 판정 채점] 불일치 {len(dis_ids)}건 중 판정 {len(scored)}건"
          f"{f' · 미판정 {missing}' if missing else ''}")
    print(f"      v1 적중 {v1_ok}/{len(scored)}  ·  v2 적중 {v2_ok}/{len(scored)}"
          f"  ·  둘 다 오답 {len(both_wrong)}건 {both_wrong}")
    print(f"      → 오류율 **하한**: v1 ≥ {len(scored)-v1_ok}/{len(p['records'])}"
          f" = {100*(len(scored)-v1_ok)/len(p['records']):.1f}%"
          f" · v2 ≥ {len(scored)-v2_ok}/{len(p['records'])}"
          f" = {100*(len(scored)-v2_ok)/len(p['records']):.1f}%")
    print(f"      (일치 {len(p['records'])-len(dis_ids)}건은 **미감사** — 둘 다 틀렸을 수 있으므로 하한)")
    print("      실제 처분(손):")
    for i, (truth, a, b) in scored:
        print(f"        {i:5s} {truth:42s} v1={'○' if a else '✗'} v2={'○' if b else '✗'}")
    print(f"\n    [어휘 공백] 두 규칙 어느 쪽도 표현할 수 없는 처분 상태 {len(VOCAB_GAP)}종:")
    for v in VOCAB_GAP:
        print(f"        - {v}")
    print("      → 결론: 대차대조는 **현 대장 서식에서 기계 도출 불가**하다. 처분이 도장 없는")
    print("        자유 산문에 살고, 지지/반증 이분법 밖의 상태가 최소 4종 존재하기 때문.")

    # 2
    f = frictions()
    print("\n" + RULE_FRIC)
    print(f"\n[2] 마찰/관측 헤딩 — 총 {sum(f['counts'].values())}절")
    for k, v in f["counts"].items():
        print(f"    {k:12s} {v:3d}")
    print(f"    재발 자기신고 헤딩 {len(f['recurrences'])}건:")
    for ln, kind, t in f["recurrences"]:
        print(f"      L{ln:5d} {kind:10s} {t}")

    # 3
    g = ledger()
    print("\n" + RULE_METRIC)
    print(f"\n[3] 지표 추세 — {len(g['rows'])}행 (c{g['rows'][0]['cycle']}~c{g['rows'][-1]['cycle']})")
    print("    window     n  rt_mean(n)  rt_max  recall h/m   fric l/f  tests min~max  grades")
    for w in g["windows"]:
        rtm = f"{w['rt_mean']:.2f}({w['rt_n']})" if w["rt_mean"] is not None else "  —  "
        tm = f"{w['tests_min']}~{w['tests_max']}" if w["tests_min"] is not None else "—"
        print(f"    {w['window']:9s} {w['n']:2d}  {rtm:>10s}  {w['rt_max']:>6}  "
              f"{w['hits']:4d}/{w['misses']:<4d}  {w['fl']:3d}/{w['ff']:<3d}  {tm:>12s}  {w['grades']}")
    nonnum = [x for w in g["windows"] for x in w["tests_nonnum"]]
    print(f"    tests 비수치 행 {len(nonnum)}건: {[c for c, _ in nonnum]}")
    print(f"    open_observations 기재 {len(g['open_obs'])}행: {g['open_obs']}")
    print(f"    product_code_unchanged_streak 기재 {len(g['pcu'])}행: 최대 {max(v for _, v in g['pcu'])} "
          f"(c{[c for c, v in g['pcu'] if v == max(x for _, x in g['pcu'])][0]})")

    # 4 감사·개정 목록 (정독 몫은 c125)
    print("\n[4] 감사·개정 문서 재고 (정독은 c125 몫 — 여기서는 존재 열거만)")
    au = sorted(AUDITS.glob("audit-*.md"), key=lambda x: int(re.sub(r"\D", "", x.stem)))
    am = sorted(AMENDS.glob("amendment-*.md"), key=lambda x: int(re.sub(r"\D", "", x.stem)))
    print(f"    audits {len(au)}: {[x.stem for x in au]}")
    print(f"    amendments {len(am)}: {[x.stem for x in am]}")
    nxt = (g["rows"][-1]["cycle"] + 1)
    print(f"    다음 감사 = c{((nxt // 10) + 1) * 10} · 다음 회고 = c{((nxt // 5) + 1) * 5 if nxt % 5 else nxt}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
