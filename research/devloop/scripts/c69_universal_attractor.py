#!/usr/bin/env python3
"""c69 진단 3 — c68의 OFF 대조군을 죽인 것은 **c68 자신의 보고문**이었다 (read-only, $0).

죽인 가설을 순서대로 기록한다 (c64 자기규율: 앞선 손이 배제하지 못한 대안을 먼저 찾아라).
**그중 하나는 내가 잘못 죽였고, 이 스크립트가 그 오심을 뒤집는다** — 그 경과도 남긴다:
  가설 1 **깊이 절단** — 기각. top-1은 깊이 5~400에서 완전히 불변.
  가설 2 **스토어 성장** — 기각. c68 상태 기록 이후 새 행은 1개.
  가설 3 **OFF 어휘 오염**(c68 보고문이 기억이 되어 OFF 질의가 온토픽이 됐다) —
    ★ **1차 판정 '기각'은 오심이었다. 이 스크립트가 확정으로 뒤집는다.**
    오심의 기전: 되감기 시각을 c68의 **상태 기록 시각**(20:15:58)에서 가져왔는데, 오염
    행은 그보다 **앞선** 20:12:49에 쓰였다 → 되감기가 오염 행을 그대로 포함했고, 값이
    안 변하는 것을 보고 "원인 미규명"이라고 적었다. **되감기 커트오프는 보고 시각이 아니라
    측정 시각에서 와야 한다.** 단일 시점 되감기는 이 오류를 숨기고, 스윕은 드러낸다.
  가설 4 **보편 인입 행**: 특정 기억이 주제와 무관하게 많은 질의의 top-1을 차지한다 —
    가설 3과 배타가 아니며, 실제로 **둘 다 참**이다(오염 행이 곧 보편 인입 행이다).

임계 시각 스윕의 결과(본문): as_of ≤ **20:12:49**에서 OFF 최고 = **0.6037** (c68을 정확히
재현) / as_of ≥ 20:15:58에서 = **0.6925**. 그 사이에 쓰인 행이 원인이고, 그 행은
`b5cb4695` = **c68의 사이클 보고문 한 문장**이다:
    "무관 질의 8건(김치찌개·lattice QCD·자동차보험·몬스테라) 전원 5/5 통과."
이 문장이 기억이 되면서 그 8개 질의는 더 이상 무관 질의가 아니게 됐다 — 그리고 이 행은
지금 **무관 질의 4/15의 top-1**이며 vector가 0.845~0.957이다(무관 질의에 대해!).

따라서 c68의 OFF 최고 0.6037은 **측정 시점에는 옳았고**, c68의 허용 구간
[0.6100, 0.6346]은 **그것을 보고하는 행위가 저장되는 순간 소멸했다**(OFF 최고 0.6925 >
ON-real 최저 0.6346). 측정 3분 후, 그 측정을 보고한 커밋(20:13:51Z)보다도 먼저다.
**대조군의 라벨은 만료된다. 그리고 만료를 일으키는 것은 루프 자신의 기록 행위다.**

부수 귀속: store.py:4823-4830은 세션 캡처를 ×0.5로 강등하며 이유를 적어 뒀다 —
"They quote user utterances verbatim … so left at full weight they outrank real memories
for the very queries those utterances asked about." 강등 트리거는 `metadata.hook`이다.
본문의 top-5 집계에 나오는 `a9402b0c`는 사용자 발언을 그대로 인용하면서 `metadata.hook`이
없어 **자기를 겨냥해 만든 강등을 빠져나가고**, 무관 질의 11/15의 top-5에 든다.
강등이 '잡으려는 성질'이 아니라 '그 성질의 대리 표지'에 걸려 있다.

read-only: search_memories + sqlite mode=ro. 쓰기 0 · LLM 0 · $0.

    .venv/bin/python research/devloop/scripts/c69_universal_attractor.py
"""
from __future__ import annotations

import collections
import importlib.util
import json
import os
import sqlite3
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
c69off = _load("c69_off_arm_contamination")
c59 = c68.c59
DB = c68.DB
C68_OFF_MAX = 0.6037

AS_OF_SWEEP = [
    "2026-08-06T12:00:00",
    "2026-08-06T19:00:00",
    "2026-08-06T20:00:00",
    "2026-08-06T20:10:00",
    "2026-08-06T20:12:00",
    "2026-08-06T20:12:49",
    "2026-08-06T20:15:58",
    None,                      # 현재
]


def main() -> None:
    print("c69 진단 3 — 보편 인입 행 가설")
    print("=" * 78)
    print("[임계 시각 스윕] as_of를 앞으로 되감으며 OFF 최고점을 본다")
    print(f"  c68이 보고한 OFF 최고 = {C68_OFF_MAX:.4f}")
    print(f"\n  {'as_of':<22}{'OFF최고':>9}{'재현':>7}   최고점 질의 / top-1 생성시각")
    for as_of in AS_OF_SWEEP:
        tops = []
        for label, q in c68.OFF:
            rows = c69off.probe(q, 5, as_of=as_of)
            tops.append((rows[0]["score"] if rows else 0.0, label,
                         rows[0]["created_at"][:19] if rows else "n/a"))
        best = max(tops)
        hit = "예" if abs(best[0] - C68_OFF_MAX) <= 0.0002 else "아니오"
        print(f"  {str(as_of or '현재'):<22}{best[0]:>9.4f}{hit:>7}   {best[1]} / {best[2]}")

    # ---------------- 인입 행의 정체 ----------------
    print("\n" + "=" * 78)
    print("[인입 행의 정체] 무관 질의들의 top-1을 차지한 행을 세어 지목한다")
    all_queries = list(c68.OFF) + [
        ("nf-1 어업", "명태 자망 어구 그물코 규격과 금어기 조정"),
        ("nf-2 지질", "화강암 절리 발달과 풍화 토르 지형 형성"),
        ("nf-3 제빵", "사워도우 르방 수분율과 오븐 스프링 실패"),
        ("nf-4 안과", "각막 난시 축 측정과 토릭 렌즈 회전 안정성"),
        ("nf-5 항해", "조석표 저조시 여유수심과 계류 색줄 장력"),
        ("nf-7 곤충", "말벌 영소 습성과 페로몬 경보 전파 거리"),
        ("nf-8 회계", "감가상각 정률법 잔존가액과 세무조정 차이"),
    ]
    top1_counter: collections.Counter = collections.Counter()
    top5_counter: collections.Counter = collections.Counter()
    seen_text: dict[str, str] = {}
    vec_by_id: dict[str, list[float]] = collections.defaultdict(list)
    for label, q in all_queries:
        rows = c69off.probe(q, 5)
        if rows:
            top1_counter[rows[0]["id"]] += 1
        for r in rows:
            top5_counter[r["id"]] += 1
            seen_text[r["id"]] = r["text"]
            vec_by_id[r["id"]].append(r["vector"])
    n_q = len(all_queries)
    print(f"  무관 질의 {n_q}개 (c68 OFF 8 + 신선 OFF 7)")
    print(f"\n  {'행 id':<10}{'top1':>6}{'top5':>6}{'vec최저':>9}{'vec최고':>9}   본문")
    for mid, n1 in top1_counter.most_common(5):
        vs = vec_by_id[mid]
        print(f"  {mid[:8]:<10}{n1:>6}{top5_counter[mid]:>6}{min(vs):>9.4f}{max(vs):>9.4f}   "
              f"{seen_text[mid][:60]}")

    champion = top1_counter.most_common(1)[0][0] if top1_counter else None
    if not champion:
        print("  인입 행 없음 — 가설 4 판정 불가")
        return
    share = top1_counter[champion] / n_q
    print(f"\n  ★ 최다 인입 행 {champion[:8]}: 무관 질의 {top1_counter[champion]}/{n_q} "
          f"({100.0 * share:.0f}%)의 top-1이다.")

    # ---------------- 왜 이기는가: 제품 코드로 귀속 ----------------
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("select memory, metadata, created_at, length(memory) from memories where id = ?",
                (champion,))
    row = cur.fetchone()
    print("\n[귀속] 이 행이 강등을 빠져나가는가")
    if row:
        mem, md_raw, created, length = row
        md = {}
        try:
            md = json.loads(md_raw) if md_raw else {}
        except (ValueError, TypeError):
            md = {}
        quotes = "사용자 원문" in str(mem) or '"' in str(mem)
        print(f"  생성={created}  길이={length}자")
        print(f"  metadata.hook = {md.get('hook')!r}  ← 세션 캡처 ×0.5 강등의 **트리거**")
        print(f"  본문이 사용자 발언을 그대로 인용하는가: {quotes}")
        print(f"  metadata 키: {sorted(md.keys())[:12]}")
        if quotes and not md.get("hook"):
            print("  ★ **강등이 겨냥한 성질을 가졌으나 표지가 없어 강등을 빠져나간다.**")
            print("     store.py:4823-4830의 설계 의도: '사용자 발언을 그대로 인용하는 행은 "
                  "온전한 무게로 두면 그 발언이 물었던 질의에서 진짜 기억을 이긴다' → ×0.5.")
            print("     그 강등의 조건은 `metadata.hook`이라는 **대리 표지**이고, 이 행은 "
                  "성질은 같으면서 표지가 없다. 대리 표지에 걸린 규칙의 전형적 누출이다.")

        # 피드백 보정도 함께 — F1 불일치의 원인이었던 그 항목
        cur.execute("select feedback, metadata from feedback where memory_id = ?",
                    (champion,))
        fb = cur.fetchall()
        print(f"  피드백 행 {len(fb)}건: {[f[0] for f in fb][:4]} "
              f"← POSITIVE면 +0.05 (score_breakdown에 **나타나지 않는다**)")

    # ---------------- 같은 성질의 행이 몇 개인가 ----------------
    print("\n[모집단] 같은 누출 성질을 가진 행이 스토어에 몇 개인가")
    cur.execute("select id, memory, metadata from memories where deleted=0 "
                "and memory like '%원문%'")
    leak = 0
    tagged = 0
    for mid, mem, md_raw in cur.fetchall():
        try:
            md = json.loads(md_raw) if md_raw else {}
        except (ValueError, TypeError):
            md = {}
        if md.get("hook"):
            tagged += 1
        else:
            leak += 1
    print(f"  '원문'을 포함하는 행(발언 인용의 대리 검사): 강등됨(hook 있음) {tagged} / "
          f"**누출(hook 없음) {leak}**")
    cur.execute("select count(*) from feedback where upper(coalesce(feedback,'')) = 'POSITIVE'")
    print(f"  POSITIVE 피드백 행 수: {cur.fetchone()[0]} "
          f"(각 +0.05, breakdown 미노출 — c69 F1 불일치 135행의 원인)")
    con.close()

    print("\nCAVEAT: ① '사용자 원문' 문자열은 누출 성질의 **대리 검사**다 — 인용을 다른 형식으로 "
          "하는 행은 세지 못한다(과소추정). ② as_of 되감기는 생성·수정 시각 기준이며 삭제 행을 "
          "되살리지 못한다. ③ 이 스크립트는 제품을 바꾸지 않는다 — 귀속만 한다.")


if __name__ == "__main__":
    main()
