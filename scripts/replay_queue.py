"""EVB 재생 큐 — 유휴 창 응고의 우선순위. (본선 1, 2026-08-23)

뇌 사양: 해마 재생은 무작위도 최신순도 아니고 기대 가치(EVB = gain × need) 순이다
(Mattar & Daw, Nature Neuroscience 2018). gain = 이 기억을 되새기면 뒤가 얼마나
달라지나(예측 오차·변화 압력), need = 앞으로 이 기억을 쓸 확률.

forget 번역:
  need(m, T) = ACT-R 기저 활성 = ln(1 + Σ_{선택 t<T} (T-t)^-d), d=0.8 (실측값)
  gain(m, T) = 변화 압력 = Σ_{사건 e<T} 0.5^((T-e)/7d)
               사건 = SUPERSEDE(양방향)·CONFIRM·UPDATE 이력 + harmful 라벨
  EVB(m, T)  = (ε + gain) · need,  ε=0.05  — gain이 전무하면 need 순으로 퇴화

## 사전 등록 (숫자를 보기 전에 고정)

백테스트: 과거 시점 T에서 위 식을 T 이전 자료만으로 계산해 top-K를 뽑고,
(T, T+7d]의 실제 인출(트레이스 selected_ids)을 얼마나 맞히는지 잰다.
T ∈ {45, 30, 14일 전}, K = 40 (캡슐 좌석 수).

  판정 1 (need의 존재 의의): need-단독이 최신순(created_at) top-K를
        세 시점 모두에서 이기면 지지. — 순환 주의: need는 과거 선택에서 계산돼
        미래 선택과 자기상관이 있다. 그래서 이건 "감쇠 계수가 예측력을 담는가"의
        확인이지 인과 주장이 아니다.
  판정 2 (gain의 추가 가치): EVB ≥ need-단독이 3시점 중 2곳 이상이면 gain 채택.
        예상을 미리 적는다: 변화 사건이 원장 전체에 ~36건뿐이라 EVB ≈ need로
        나올 공산이 크다. 그 경우 gain은 '희소하지만 있으면 우선'인 스파이크
        항으로 유지하되 backtest 재판정은 사건이 쌓인 뒤로 미룬다.
  판정 3 (서술): 변화 사건을 겪은 기억의 사건-후 7일 인출률 vs 짝지은 대조군.
        표본이 작으므로(≤36) 판정선 없이 서술만.

읽기 전용. 사용:
  MEM1_DB_PATH=<사본> .venv/bin/python scripts/replay_queue.py backtest
  MEM1_DB_PATH=<사본> .venv/bin/python scripts/replay_queue.py queue [--top 40]
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB = os.environ.get("MEM1_DB_PATH", str(Path.home() / ".forget/forget.sqlite3"))
DECAY_D = 0.8
GAIN_HALF_LIFE_D = 7.0
EPS = 0.05
DAY = 86400.0


def ts(raw: str) -> float:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def load(db: str):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    memories = {
        str(r[0]): {"born": ts(r[2]), "text": str(r[1] or "")}
        for r in con.execute("SELECT id, memory, created_at FROM memories WHERE deleted = 0")
    }
    selections: dict[str, list[float]] = defaultdict(list)
    for created, sel in con.execute(
        "SELECT created_at, selected_ids FROM context_traces WHERE selected_ids IS NOT NULL"
    ):
        t = ts(created)
        try:
            ids = json.loads(sel) or []
        except Exception:
            continue
        for mid in ids:
            selections[str(mid)].append(t)

    change_events: dict[str, list[float]] = defaultdict(list)
    for mid, event, created in con.execute(
        "SELECT memory_id, event, created_at FROM memory_history WHERE event IN ('SUPERSEDE','CONFIRM','UPDATE')"
    ):
        change_events[str(mid)].append(ts(created))
    for created, harm in con.execute(
        "SELECT created_at, harmful_memory_ids FROM context_outcomes WHERE harmful_memory_ids IS NOT NULL AND harmful_memory_ids != '[]'"
    ):
        t = ts(created)
        try:
            for mid in json.loads(harm) or []:
                change_events[str(mid)].append(t)
        except Exception:
            pass
    con.close()
    return memories, selections, change_events


def need(mid: str, T: float, selections) -> float:
    past = [t for t in selections.get(mid, []) if t < T][-64:]
    return math.log1p(sum(((T - t) / DAY + 1e-3) ** (-DECAY_D) for t in past))


def gain(mid: str, T: float, change_events) -> float:
    return sum(0.5 ** ((T - e) / DAY / GAIN_HALF_LIFE_D)
               for e in change_events.get(mid, []) if e < T)


def evb(mid: str, T: float, selections, change_events) -> float:
    return (EPS + gain(mid, T, change_events)) * need(mid, T, selections)


def backtest(memories, selections, change_events, k: int = 40) -> None:
    now = datetime.now(timezone.utc).timestamp()
    print(f"{'T':>6s} {'미래인출기억':>7s} | {'EVB':>6s} {'need':>6s} {'최신순':>6s} {'무작위':>6s}   (top-{k}의 미래 7d 적중 정밀도)")
    print("-" * 78)
    import random
    rng = random.Random(20260823)
    for days in (45, 30, 14):
        T = now - days * DAY
        future = {mid for mid, times in selections.items()
                  if any(T < t <= T + 7 * DAY for t in times)}
        alive = [m for m, v in memories.items() if v["born"] < T]
        if not alive or not future:
            print(f"{days:4d}d  자료 부족")
            continue

        def prec(ranked: list[str]) -> float:
            top = ranked[:k]
            return sum(1 for m in top if m in future) / len(top)

        by_evb = sorted(alive, key=lambda m: -evb(m, T, selections, change_events))
        by_need = sorted(alive, key=lambda m: -need(m, T, selections))
        by_recent = sorted(alive, key=lambda m: -memories[m]["born"])
        randomized = rng.sample(alive, min(k, len(alive)))
        print(f"{days:4d}d {len(future):7d} | {prec(by_evb):6.2f} {prec(by_need):6.2f} "
              f"{prec(by_recent):6.2f} {prec(randomized):6.2f}")

    # 판정 3 (서술): 변화 사건 후 7일 인출률 vs 같은 나이대 대조군
    hit = tot = ctl_hit = ctl_tot = 0
    import random as _r
    rng2 = _r.Random(7)
    all_ids = list(memories)
    for mid, events in change_events.items():
        if mid not in memories:
            continue
        for e in events:
            tot += 1
            hit += any(e < t <= e + 7 * DAY for t in selections.get(mid, []))
            ctl = rng2.choice(all_ids)
            ctl_tot += 1
            ctl_hit += any(e < t <= e + 7 * DAY for t in selections.get(ctl, []))
    if tot:
        print(f"\n판정 3 (서술): 변화 사건 {tot}건 — 사건 후 7d 인출률 {100*hit/tot:.0f}% "
              f"vs 무작위 대조 {100*ctl_hit/max(1,ctl_tot):.0f}%")


def show_queue(memories, selections, change_events, top: int = 40) -> None:
    now = datetime.now(timezone.utc).timestamp()
    scored = sorted(
        ((evb(m, now, selections, change_events), gain(m, now, change_events),
          need(m, now, selections), m) for m in memories),
        reverse=True)
    print(f"{'EVB':>7s} {'gain':>5s} {'need':>5s}  기억")
    for s, g, n, m in scored[:top]:
        print(f"{s:7.3f} {g:5.2f} {n:5.2f}  {memories[m]['text'][:64]}")


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    memories, selections, change_events = load(DB)
    n_events = sum(len(v) for v in change_events.values())
    print(f"기억 {len(memories)} · 선택 이력 {sum(len(v) for v in selections.values())} "
          f"· 변화 사건 {n_events} (보유 기억 {len(change_events)})\n")
    if mode == "queue":
        top = int(sys.argv[sys.argv.index("--top") + 1]) if "--top" in sys.argv else 40
        show_queue(memories, selections, change_events, top)
    else:
        backtest(memories, selections, change_events)


if __name__ == "__main__":
    main()
