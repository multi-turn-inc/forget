#!/usr/bin/env python3
"""c69 진단 2 — c68의 OFF 최고점(0.6037)이 하루 만에 0.6925가 된 이유 (read-only, $0).

배제된 설명 두 가지 (먼저 죽인 가설을 기록한다 — c64 자기규율):
  · **깊이 아님**: top-1은 깊이 5~400에서 완전히 불변이다(c69_depth_and_chain_diagnosis).
  · **스토어 성장 아님**: c68 상태 기록(2026-08-06T20:15:58) 이후 새 행은 **1개**뿐이다.

남은 가설: **그 1개가 c68 자신의 기록이고, 그것이 OFF 대조군의 어휘를 담고 있다.**
c68의 사이클 보고문에는 OFF 질의 목록이 그대로 적혀 있다 —
"OFF 8건(김치찌개·lattice QCD·자동차보험·몬스테라 등) 전원 5/5 통과". 이 문장이 기억으로
저장되면 다음 사이클의 OFF 질의는 **더 이상 무관 질의가 아니다**: 스토어에 그 주제어를
담은 기억이 실재하게 된다.

그렇다면 이것은 계측 오류가 아니라 **라벨의 만료**다. OFF 라벨의 뜻은 "이 주제의 기억은
스토어에 없다"이고, 사이클 보고를 기억에 쓰는 행위가 그 명제를 거짓으로 만든다.
즉 **루프의 기록 행위가 자신의 대조군을 소비한다.** 다음 사이클이 지난 사이클의 OFF 어휘를
재사용하면 다른 것을 재게 되고, 그 차이는 항상 **OFF 점수를 올리는 방향**이다
(= 게이트가 실제보다 나쁘게 보이고, 허용 구간은 실제보다 빨리 소멸한다).

검증 (제품 자신의 시간여행 기능을 쓴다 — 재구현하지 않는다):
  search_memories의 `memory_as_of`는 그 시각 이후 생성/수정된 행을 후보에서 제외한다
  (store.py:4781-4786). c68 시각으로 되감아 같은 질의를 다시 재면:
    · 되감은 최고점이 c68의 0.6037을 재현하면 → **오염 가설 확정**.
    · 재현하지 않으면 → 원인은 아직 미규명이며 처치 판정을 내지 않는다.

read-only: search_memories만. 쓰기 0 · LLM 0 · $0.

    .venv/bin/python research/devloop/scripts/c69_off_arm_contamination.py
"""
from __future__ import annotations

import importlib.util
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
c59 = c68.c59

# c68이 상태를 기록한 시각. 그 사이클의 측정은 이 시각 **이전**에 일어났다.
C68_AS_OF = "2026-08-06T20:15:58"
C68_OFF_MAX = 0.6037          # c68 정본 메모의 OFF top-1 최고
C68_OFF_MIN = 0.5575          # c68 정본 메모의 OFF top-1 최저
DB = c68.DB


def probe(query: str, top_k: int, as_of: str | None = None) -> list[dict]:
    from forget_project import layered_filter, project_key_for_path, scope_disabled
    args = {"query": query, "top_k": top_k, "recall": "low", "score_breakdown": True}
    if as_of:
        args["memory_as_of"] = as_of
    if not scope_disabled():
        project = project_key_for_path(c59.CWD)
        if project:
            args["filters"] = layered_filter(project)
    rows = c59.hook._rpc("search_memories", args).get("results") or []
    out = []
    for r in rows:
        bd = r.get("score_breakdown") or {}
        out.append({"id": r.get("id") or "", "score": float(r.get("score") or 0.0),
                    "rule": float(bd.get("rule") or 0.0),
                    "vector": float(bd.get("vector") or 0.0),
                    "created_at": str(r.get("created_at") or ""),
                    "text": " ".join((r.get("memory") or "").split())})
    return sorted(out, key=lambda r: -r["score"])


def newest_rows(n: int = 5) -> list[tuple[str, str, str]]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("select id, created_at, memory from memories where deleted=0 "
                "order by created_at desc limit ?", (n,))
    rows = [(str(a), str(b), " ".join(str(c).split())) for a, b, c in cur.fetchall()]
    con.close()
    return rows


def main() -> None:
    print("c69 진단 2 — OFF 대조군 오염 가설")
    print(f"c68 as_of={C68_AS_OF}  c68 OFF top-1 범위={C68_OFF_MIN}~{C68_OFF_MAX}")

    print("\n[스토어 최신 행 — c68 이후 추가된 것이 무엇인가]")
    for mid, created, text in newest_rows(3):
        print(f"  {mid[:8]} {created}  {text[:120]}")

    print("\n" + "=" * 78)
    print("[시간여행 대조] 같은 질의 · 같은 몸 · 스토어 상태만 c68 시점으로 되감음")
    print(f"  {'질의':<14}{'현재':>9}{'되감음':>9}{'차이':>9}   현재 top-1 출처")
    now_tops, past_tops = [], []
    contaminated = []
    for label, q in c68.OFF:
        now = probe(q, 5)
        past = probe(q, 5, as_of=C68_AS_OF)
        n_top = now[0]["score"] if now else 0.0
        p_top = past[0]["score"] if past else 0.0
        now_tops.append(n_top)
        past_tops.append(p_top)
        src = now[0]["created_at"][:19] if now else "n/a"
        fresh = bool(now and now[0]["created_at"] > C68_AS_OF)
        if fresh:
            contaminated.append((label, n_top, p_top, now[0]["text"][:100]))
        print(f"  {label:<14}{n_top:>9.4f}{p_top:>9.4f}{n_top - p_top:>+9.4f}   "
              f"{src}{'  ★c68 이후 생성' if fresh else ''}")

    print(f"\n  현재  OFF 최고={max(now_tops):.4f}  최저={min(now_tops):.4f}")
    print(f"  되감음 OFF 최고={max(past_tops):.4f}  최저={min(past_tops):.4f}")
    print(f"  c68 보고 OFF 최고={C68_OFF_MAX:.4f}  최저={C68_OFF_MIN:.4f}")

    reproduced = abs(max(past_tops) - C68_OFF_MAX) <= 0.0002
    print(f"\n  되감은 최고점이 c68을 재현하는가: "
          f"{'**예 — 오염 가설 확정**' if reproduced else '아니오 — 원인 미규명'}")
    if reproduced:
        print("  → c68 이후 저장된 행이 OFF 대조군의 어휘를 담고 있고, 그것이 OFF 최고점을 "
              f"{C68_OFF_MAX:.4f} → {max(now_tops):.4f}로 밀어 올렸다.")
        print("  → 이것은 계측 오류가 아니라 **OFF 라벨의 만료**다: '이 주제의 기억은 없다'는 "
              "명제가 사이클 보고를 기억에 쓰는 행위로 거짓이 됐다.")
        print("  → 함의 ①: **루프의 기록 행위가 자신의 대조군을 소비한다.** 지난 사이클의 OFF "
              "어휘를 재사용하는 측정은 매번 다른 것을 재고, 편향은 항상 한 방향이다"
              "(OFF 점수 상승 = 게이트가 실제보다 나쁘게 보인다).")
        print("  → 함의 ②: c68이 '존재한다'고 보고한 허용 구간은 **하루 만에 소멸**했다"
              f"(OFF 최고 {max(now_tops):.4f} > ON-real 최저 0.6346). 방향은 P22 (a)의 연역과 "
              "같지만 **원인이 다르므로 P22 (a)의 표본으로 계상하지 않는다** — 질의 추가가 "
              "아니라 대조군 라벨 만료다.")
    for label, n_top, p_top, text in contaminated:
        print(f"\n  [증거] {label}: {p_top:.4f} → {n_top:.4f}\n     {text}")

    print("\n" + "=" * 78)
    print("[신선한 OFF 대조군] 스토어에 어휘가 없는 질의를 새로 뽑아 오염되지 않은 값을 낸다")
    print("  선정 규약: 이 손이 고르고, **주제어가 스토어 전문에 등장하지 않는지 SQL로 확인**한다")
    fresh_off = [
        ("nf-1 어업", "명태 자망 어구 그물코 규격과 금어기 조정"),
        ("nf-2 지질", "화강암 절리 발달과 풍화 토르 지형 형성"),
        ("nf-3 제빵", "사워도우 르방 수분율과 오븐 스프링 실패"),
        ("nf-4 안과", "각막 난시 축 측정과 토릭 렌즈 회전 안정성"),
        ("nf-5 항해", "조석표 저조시 여유수심과 계류 색줄 장력"),
        ("nf-6 도자", "환원 소성 유약 발색과 가마 재임 온도 곡선"),
        ("nf-7 곤충", "말벌 영소 습성과 페로몬 경보 전파 거리"),
        ("nf-8 회계", "감가상각 정률법 잔존가액과 세무조정 차이"),
    ]
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()
    keep = []
    for label, q in fresh_off:
        # 질의의 각 어절이 스토어 전문에 등장하는지 — 하나도 안 걸리는 어절이 있어야 한다.
        tokens = [t for t in q.split() if len(t) >= 3]
        hits = {}
        for t in tokens:
            cur.execute("select count(*) from memories where deleted=0 and memory like ?",
                        (f"%{t}%",))
            hits[t] = cur.fetchone()[0]
        clean = sum(1 for v in hits.values() if v == 0)
        print(f"  {label:<12} 어절 {len(tokens)}개 중 스토어 미등장 {clean}개  "
              f"{'적격' if clean >= 2 else '★ 부적격(어휘가 이미 스토어에 있다)'}")
        if clean >= 2:
            keep.append((label, q))
    con.close()

    print(f"\n  적격 신선 OFF {len(keep)}/{len(fresh_off)} — 실측:")
    fresh_tops = []
    for label, q in keep:
        rows = probe(q, 5)
        top = rows[0]["score"] if rows else 0.0
        fresh_tops.append(top)
        n_pass = sum(1 for r in rows if r["score"] >= c68.GATE_NOW)
        print(f"  {label:<12} top1={top:.4f}  게이트 통과 {n_pass}/{len(rows)}  "
              f"rule={rows[0]['rule'] if rows else 0} vec={rows[0]['vector'] if rows else 0}")
        if rows:
            print(f"       {rows[0]['text'][:88]}")
    if fresh_tops:
        print(f"\n  신선 OFF top-1: 최고={max(fresh_tops):.4f} 최저={min(fresh_tops):.4f} "
              f"산포={max(fresh_tops) - min(fresh_tops):.4f}")
        print(f"  대조: 오염된 OFF(c68 어휘 재사용) 최고={max(now_tops):.4f} / "
              f"되감은 OFF 최고={max(past_tops):.4f}")
        print("  ★ 이 셋의 차이가 '대조군을 매 사이클 새로 뽑아야 하는 비용'의 실측값이다.")

    print("\nCAVEAT: ① '무관함'과 '어휘 미등장'은 이 손의 판단 + SQL like 검사의 합이며 "
          "의미적 무관함을 보장하지 않는다(형태소 분석 없이 어절 단위로 봤다). "
          "② memory_as_of는 생성·수정 시각 기준이라 **삭제된 행은 되살리지 못한다** — "
          "되감기는 근사이며 완전한 시간여행이 아니다. ③ 단일 시점·현 스택.")


if __name__ == "__main__":
    main()
