"""확산 활성 A/B — 형제 도달 탐침. (본선 4, 2026-08-23)

무엇을 재나: 한 일화(같은 ADD 선언)의 조각 하나에만 있는 고유 단어로 질의했을 때,
그 질의가 직접 못 닿는 **형제 조각들**이 후보에 오는가. 어휘·벡터 검색은 질의에
없는 말로 쓰인 형제를 원리적으로 못 데려온다 — 간선(일화 동기)이 유일한 길이며,
이것이 "검색 천장은 랭킹으로 못 올린다"(실측)에 대한 그래프 쪽 응답이다.

비순환: 질의를 원문 자체에서 유도하고(구 시스템 로그 무관), 두 팔이 같은 재생
DB를 쓴다 (MEM1_SPREADING 환경변수만 다름 — 호출 시점에 읽으므로 재적재 불요).

## 사전 등록 판정 (숫자를 보기 전에 고정)

  P4-A (도달): on 팔의 형제 회수율(top-10)이 off 팔보다 +10pp 이상 → 지지.
      +3pp 미만 → 반증 (간선이 실질 도달을 못 늘림 — 구현 무가치).
  P4-B (가드): 질의 조각 자신의 top-1 유지율이 off 대비 -2pp 이상 후퇴 금지
      (확산 후보가 정답을 밀어내면 안 된다).
  적용 규칙: A 지지 & B 통과 → 라이브 (기본 켜짐). A 반증 → MEM1_SPREADING=0
      기본 끔으로 배포하고 지도에 반증 기록.

사용: .venv/bin/python scripts/exp_spreading.py [--n 25] [--k 10]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

SRC = str(Path.home() / ".forget/forget.sqlite3")
USER = "spreaduser"


def real_payloads(limit: int) -> list[str]:
    con = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT payload FROM events WHERE event_type='ADD' ORDER BY created_at DESC LIMIT ?",
        (limit * 8,)).fetchall()
    con.close()
    out = []
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        messages = data.get("messages") or []
        text = messages[0].get("content") if messages and isinstance(messages[0], dict) else None
        if isinstance(text, str) and len(text) > 200 and not text.startswith("세션 캡처") \
                and re.search(r"[가-힣]", text):
            out.append(text)
        if len(out) >= limit:
            break
    return out


def distinctive_words(target: str, siblings: list[str], k: int = 5) -> str:
    """대상 조각에만 있고 형제들에는 없는 내용어 — 형제가 직접 매칭될 길을 막는다."""
    def words(t):
        return [w for w in re.split(r"[^\w가-힣%-]+", t.lower()) if len(w) >= 3 and not w.isdigit()]
    others = set()
    for s in siblings:
        others.update(words(s))
    uniq = [w for w, _ in Counter(w for w in words(target) if w not in others).most_common(k)]
    return " ".join(uniq)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=25)
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()

    db = Path(tempfile.mkdtemp()) / "spread.sqlite3"
    os.environ["MEM1_DB_PATH"] = str(db)
    os.environ["MEM1_RECALL_TEMPORAL"] = "0"
    from forget.db import get_db, init_db
    from forget.store import add_memories, search_memories
    init_db()

    payloads = real_payloads(args.n)
    episodes = []          # (질의 조각 id, 질의, {형제 id})
    for text in payloads:
        before = set()
        with get_db() as conn:
            before = {r[0] for r in conn.execute("SELECT id FROM memories")}
        add_memories({"messages": [{"role": "user", "content": text}], "user_id": USER,
                      "infer": True, "hebbian": False})
        with get_db() as conn:
            new = [(str(r[0]), str(r[1])) for r in conn.execute(
                "SELECT id, memory FROM memories WHERE deleted=0") if r[0] not in before]
        if len(new) < 3:
            continue
        for i, (mid, mtext) in enumerate(new):
            sib_texts = [t for j, (_, t) in enumerate(new) if j != i]
            q = distinctive_words(mtext, sib_texts)
            if len(q) >= 8:
                episodes.append((mid, q, {m for m, _ in new if m != mid}))
                break                      # 일화당 질의 1개 — 일화 다양성 우선
    print(f"재생 {len(payloads)}건 → 시험 일화 {len(episodes)}개 (조각≥3 & 고유어 확보)\n")

    def run_arm(flag: str):
        os.environ["MEM1_SPREADING"] = flag
        self_top1 = sib_hit = sib_total = 0
        for mid, q, sibs in episodes:
            res = (search_memories({"query": q, "filters": {"user_id": USER},
                                    "top_k": args.k}) or {}).get("results") or []
            ids = [str(m.get("id")) for m in res]
            self_top1 += bool(ids) and ids[0] == mid
            sib_total += len(sibs)
            sib_hit += len(sibs & set(ids))
        return self_top1, sib_hit, sib_total

    off = run_arm("0")
    on = run_arm("1")
    n = len(episodes)
    print(f"{'팔':6s} {'자기 top-1':>9s} {'형제 회수':>12s}")
    print(f"{'off':6s} {off[0]:4d}/{n:<4d} {off[1]:5d}/{off[2]:<5d} = {100*off[1]/max(1,off[2]):.0f}%")
    print(f"{'on':6s} {on[0]:4d}/{n:<4d} {on[1]:5d}/{on[2]:<5d} = {100*on[1]/max(1,on[2]):.0f}%")
    da = 100 * (on[1] - off[1]) / max(1, off[2])
    db_ = 100 * (on[0] - off[0]) / max(1, n)
    print(f"\nP4-A 도달 Δ{da:+.0f}pp → {'지지 (≥+10)' if da >= 10 else ('반증 (<+3)' if da < 3 else '회색')}")
    print(f"P4-B 가드 자기 top-1 Δ{db_:+.0f}pp → {'통과' if db_ >= -2 else '실패'}")


if __name__ == "__main__":
    main()
