"""일화 결합 A/B — 같은 원문, 결합만 켜고 끈다. (2026-08-23)

이 실험이 재는 것과 재지 않는 것을 먼저 못박는다.

  재는 것    구현이 실제로 작동하는가. 주제어 질의가 주제를 잃은 조각에 닿는가.
  재지 않는 것  이 설계가 좋은 설계인가. 질의를 앵커에서 기계적으로 유도하므로
              앵커를 실은 팔이 유리한 것은 당연하다 — 순환이다.

그래도 돌리는 이유: 배선이 조용히 안 먹는 경우를 잡는다. 독립 검증은 백필(게이트) 뒤
평가셋 v1으로 한다. 그때까지 이 숫자는 '구현 정합성'으로만 읽는다.

절차: 실원장의 ADD 원문을 임시 DB 두 개에 재생(A=결합 on, B=off) → 각 사실의 앵커
주제어로 질의 → 그 사실이 상위 k에 오는지 센다. 실원장은 읽기만 한다.

사용: .venv/bin/python scripts/exp_episodic_binding.py [--n 40] [--k 10]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path

SRC = str(Path.home() / ".forget/forget.sqlite3")
USER = "expuser"


def real_payloads(limit: int) -> list[str]:
    con = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT payload FROM events WHERE event_type='ADD' ORDER BY created_at DESC LIMIT ?",
        (limit * 6,),
    ).fetchall()
    con.close()
    out: list[str] = []
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        messages = data.get("messages") or []
        text = ""
        if messages and isinstance(messages[0], dict):
            content = messages[0].get("content")
            text = content if isinstance(content, str) else ""
        text = text or (data.get("text") if isinstance(data.get("text"), str) else "")
        # 세션 캡처는 기계 생성 정형문이라 표본을 지배한다 — 사람이 쓴 항목만 본다.
        if len(text) > 120 and not text.startswith("세션 캡처"):
            out.append(text)
        if len(out) >= limit:
            break
    return out


def topic_query(anchor: str) -> str:
    """앵커에서 주제어만 뽑는다 — 날짜·경로·괄호 주석은 질의어가 아니다."""
    body = re.sub(r"\([^)]*\)", " ", anchor)
    body = re.sub(r"\d{4}-\d{2}-\d{2}|/loop|forget/\S+|\S+\.(py|md|json)", " ", body)
    words = [w for w in re.split(r"[\s,·—–:\"'\[\]]+", body) if len(w) >= 2]
    return " ".join(words[:6])


def run_arm(binding: bool, payloads: list[str], k: int) -> tuple[int, int, list[str]]:
    db = Path(tempfile.mkdtemp()) / f"arm-{'on' if binding else 'off'}.sqlite3"
    os.environ["MEM1_DB_PATH"] = str(db)
    for mod in [m for m in list(__import__("sys").modules) if m.startswith("forget")]:
        del __import__("sys").modules[mod]
    from forget.db import init_db
    from forget.memory_engine import anchor_applies, episode_anchor
    from forget.store import add_memories, search_memories

    init_db()
    from forget.db import get_db

    def all_ids() -> set[str]:
        with get_db() as conn:
            return {r[0] for r in conn.execute("SELECT id FROM memories WHERE deleted = 0")}

    def texts_of(ids: set[str]) -> list[str]:
        if not ids:
            return []
        with get_db() as conn:
            q = "SELECT memory FROM memories WHERE id IN (%s)" % ",".join("?" * len(ids))
            return [str(r[0]) for r in conn.execute(q, tuple(ids))]

    facts_by_query: list[tuple[str, str]] = []      # (질의, 기대 사실)
    for text in payloads:
        # add_memories는 생성 목록을 반환하지 않는다(status만) — 전후 차집합으로 이 원문의 사실을 잡는다.
        before = all_ids()
        # infer=True가 원자화 경로다 — infer=False는 원문을 한 덩어리로 남겨 조각이 아예
        # 생기지 않는다(2026-08-23 확인). 원장의 52% 조각도 이 경로에서 나왔다.
        add_memories({"messages": [{"role": "user", "content": text}], "user_id": USER,
                      "infer": True, "episode_binding": binding, "hebbian": False})
        new_facts = texts_of(all_ids() - before)
        anchor = episode_anchor(text)
        if not anchor:
            continue
        query = topic_query(anchor)
        if len(query) < 6:
            continue
        for fact in new_facts:
            # 주제를 잃은 조각만 시험 대상 — 이미 주제어를 품은 사실은 이 병의 환자가 아니다.
            if fact and anchor_applies(fact, anchor):
                facts_by_query.append((query, fact))

    hit = 0
    misses: list[str] = []
    for query, fact in facts_by_query:
        found = search_memories({"query": query, "filters": {"user_id": USER}, "top_k": k})
        texts = [str(m.get("memory") or "") for m in (found.get("results") or [])]
        if fact in texts:
            hit += 1
        else:
            misses.append(fact[:70])

    # 후퇴 금지 가드 (사전 등록, docs/episodic-binding.md §판정 기준): 사실 자신을 질의로
    # 넣으면 1위여야 한다. 임베딩 입력을 "앵커 — 사실"로 바꾸면 사실의 벡터가 희석될 수
    # 있고, 앵커는 더하기만 해야지 문면 매칭을 깎으면 실패다.
    verbatim_top1 = 0
    seen: set[str] = set()
    for _, fact in facts_by_query:
        if fact in seen:
            continue
        seen.add(fact)
        found = search_memories({"query": fact, "filters": {"user_id": USER}, "top_k": 1})
        results = found.get("results") or []
        if results and str(results[0].get("memory") or "") == fact:
            verbatim_top1 += 1
    return hit, len(facts_by_query), misses, verbatim_top1, len(seen)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()

    payloads = real_payloads(args.n)
    print(f"실원장 원문 {len(payloads)}건 재생 · top_k={args.k}\n")

    on_hit, on_n, on_miss, on_v, on_vn = run_arm(True, payloads, args.k)
    off_hit, off_n, off_miss, off_v, off_vn = run_arm(False, payloads, args.k)

    print(f"{'팔':6s} {'조각':>5s} {'적중':>5s} {'비율':>7s} {'문면1위':>9s}")
    print("-" * 38)
    for name, hit, n, v, vn in (("결합 on", on_hit, on_n, on_v, on_vn),
                                ("결합 off", off_hit, off_n, off_v, off_vn)):
        vp = f"{100.0 * v / vn:5.1f}%" if vn else "    –"
        print(f"{name:6s} {n:5d} {hit:5d} {100.0 * hit / n if n else 0:6.1f}% {vp:>9s}")
    if on_vn and off_vn:
        guard = (100.0 * on_v / on_vn) - (100.0 * off_v / off_vn)
        verdict = "통과" if guard >= -1.0 else "실패 — 앵커가 문면 매칭을 깎았다"
        print(f"\n후퇴 금지 가드: 문면 1위 {guard:+.1f}pp → {verdict}")
    if on_n and off_n:
        delta = (100.0 * on_hit / on_n) - (100.0 * off_hit / off_n)
        print(f"\n차이 {delta:+.1f}pp (조각 표본 on={on_n} off={off_n})")
        print("읽는 법: 이것은 구현 정합성 확인이다. 질의를 앵커에서 유도했으므로 "
              "on 팔이 유리한 것은 설계상 당연하고, 여기서 확인되는 것은 배선이 먹는다는 사실뿐.")
    if off_miss[:5]:
        print(f"\n결합 없을 때 못 찾은 조각 예:")
        for m in off_miss[:5]:
            print(f"  ✗ {m}")


if __name__ == "__main__":
    main()
