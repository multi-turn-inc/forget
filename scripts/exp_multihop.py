"""다홉 탐침 — 교차 에피소드 도달. (본선 4-R R3 판정, 2026-08-24)

형제-도달 탐침(exp_spreading)이 재는 것: 같은 에피소드 안의 조각들.
이것이 재는 것: **다른 에피소드**에 있는, 술어 간선으로만 이어진 기억.
어휘·벡터·일화 동기 어느 것도 이 경로를 못 만든다 — 술어 간선이 유일한 길이며,
"검색 천장은 랭킹으로 못 올린다"에 대한 그래프 쪽 답의 최종 시험이다.

절차: 기질에서 엔티티 E를 골라, E를 언급하는 기억이 **두 개 이상의 다른
에피소드**에 걸쳐 있는 경우를 찾는다. 에피소드 A의 기억 텍스트로 질의하고
(A에 고유한 어휘 위주), 에피소드 B의 기억이 후보에 오는지 본다.

비순환: 질의는 원문에서, 판정 대상은 다른 에피소드의 실기억. 두 팔은 같은
실DB·같은 기질을 쓰고 MEM1_SPREADING만 다르다.

## 사전 등록 (docs/graph-substrate-research.md §4.6 R3 판정)
  지지: 교차-에피소드 도달 +10pp 이상 그리고 자기 top-1 후퇴 ≤2pp
  반증: +3pp 미만 또는 자기 top-1 후퇴 >2pp → 본선 4 최종 기각, 기질만 잔류

사용: MEM1_GRAPH_SUBSTRATE=<graph.sqlite3> .venv/bin/python scripts/exp_multihop.py [--n 40]
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

SUBSTRATE = os.environ.get("MEM1_GRAPH_SUBSTRATE", str(Path.home() / ".forget/graph_substrate.sqlite3"))
LEDGER = os.environ.get("MEM1_DB_PATH", str(Path.home() / ".forget/forget.sqlite3"))


def words(text: str) -> list[str]:
    return [w for w in re.split(r"[^\w가-힣%-]+", text.lower()) if len(w) >= 3 and not w.isdigit()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()

    sub = sqlite3.connect(f"file:{SUBSTRATE}?mode=ro", uri=True)
    led = sqlite3.connect(f"file:{LEDGER}?mode=ro", uri=True)

    # 엔티티별 (기억, 에피소드) — 에피소드는 술어 간선의 출처 표식
    ep_of: dict[str, str] = {}
    for src, dst, ep in sub.execute("SELECT src, dst, episode_key FROM edges"):
        ep_of.setdefault(str(src), str(ep))
        ep_of.setdefault(str(dst), str(ep))
    by_entity: dict[str, list[str]] = {}
    for mid, entity in sub.execute("SELECT memory_id, entity FROM mentions"):
        by_entity.setdefault(str(entity), []).append(str(mid))

    text_of, user_of = {}, {}
    for mid, mem, uid in led.execute(
            "SELECT id, memory, user_id FROM memories WHERE deleted = 0"):
        text_of[str(mid)] = str(mem)
        user_of[str(mid)] = str(uid or "junghunkim")

    # 기억 → 에피소드: ADD input 동일성 (기질 빌더와 같은 열쇠)
    mem_episode: dict[str, int] = {}
    for mid, raw in led.execute(
            "SELECT memory_id, input FROM memory_history WHERE event='ADD' AND input IS NOT NULL"):
        mem_episode[str(mid)] = hash(str(raw))

    cases = []
    for entity, mids in by_entity.items():
        mids = [m for m in dict.fromkeys(mids) if m in text_of]
        groups: dict[int, list[str]] = {}
        for m in mids:
            groups.setdefault(mem_episode.get(m, 0), []).append(m)
        if len(groups) < 2:
            continue
        keys = sorted(groups, key=lambda k: -len(groups[k]))[:2]
        a, b = groups[keys[0]][0], groups[keys[1]][0]
        ta, tb = text_of[a], text_of[b]
        if min(len(ta), len(tb)) < 40:
            continue
        other = set(words(tb))
        uniq = [w for w, _ in Counter(w for w in words(ta) if w not in other).most_common(6)]
        query = " ".join(uniq)
        if len(query) >= 10:
            cases.append({"q": query, "self": a, "target": b, "uid": user_of[a], "entity": entity})
        if len(cases) >= args.n:
            break
    print(f"교차-에피소드 사례 {len(cases)}개 (기질 엔티티 {len(by_entity)})\n")
    sub.close()
    led.close()

    from forget.store import search_memories

    def arm(flag: str):
        os.environ["MEM1_SPREADING"] = flag
        hit = self_top1 = 0
        for c in cases:
            res = (search_memories({"query": c["q"], "filters": {"user_id": c["uid"]},
                                    "top_k": args.k}) or {}).get("results") or []
            ids = [str(m.get("id")) for m in res]
            hit += c["target"] in ids
            self_top1 += bool(ids) and ids[0] == c["self"]
        return hit, self_top1

    off_hit, off_self = arm("0")
    on_hit, on_self = arm("1")
    n = max(1, len(cases))
    print(f"{'팔':6s} {'교차 도달':>9s} {'자기 top-1':>10s}")
    print(f"{'off':6s} {off_hit:4d}/{n:<4d} {off_self:5d}/{n:<4d}")
    print(f"{'on':6s} {on_hit:4d}/{n:<4d} {on_self:5d}/{n:<4d}")
    da = 100 * (on_hit - off_hit) / n
    ds = 100 * (on_self - off_self) / n
    print(f"\n도달 Δ{da:+.0f}pp → {'지지 (≥+10)' if da >= 10 else ('반증 (<+3)' if da < 3 else '회색')}")
    print(f"가드 자기 top-1 Δ{ds:+.0f}pp → {'통과' if ds >= -2 else '실패'}")


if __name__ == "__main__":
    main()
