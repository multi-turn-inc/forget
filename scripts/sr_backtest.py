"""후계 표현(SR) 백테스트 — 기억 사용에 전이 구조가 있는가. (본선 6 사전 탐침, 2026-08-24)

정훈의 질문: "다음에 필요할 것을 앞서 담았는가에 대한 정책망을 동적으로 조절할
수 있는 구조가 되어야겠군. 방법론이 문제인데, 사람과 비슷하게 가려면.."

사람의 방법 둘 중 이 스크립트는 둘째를 잰다:
  ① 명시적 시뮬레이션 (일화적 미래 사고) — 다음 장면을 상상하고 그 상상으로 인출
  ② 예측 지도 (SR, Stachenfeld 2017) — 전이 통계를 표현 자체에 굽는다:
     "기억 a가 쓰인 뒤에는 기억 b가 곧 쓰이더라"의 할인 누적

②는 우리 원장으로 즉시 학습 가능하다: context_traces가 한 달치 사용 순서를 이미
기록했다. 질의가 재발하지 않아 죽었던 라벨-학습 경로(2026-08-23 부정 결과)와
다르다 — 이것은 질의→질의가 아니라 **기억→기억 전이**이고, 그 구조는 질의
재발 없이도 존재할 수 있다.

## 방법 (숫자를 보기 전에 고정)

  계열: 트레이스를 시간순 정렬, 30분 무활동 간격으로 에피소드 분할.
  학습: 시간순 앞 70% 에피소드. M[a][b] += γ^(k-1), γ=0.7, 턴 거리 k=1..5,
        a∈sel(t), b∈sel(t+k), a≠b. (스윕 없음 — γ·지평은 선험 고정)
  시험: 뒤 30% 에피소드의 각 턴 t에서, 표적 = 같은 에피소드 다음 5턴에 쓰인
        **신규** 기억(sel(t)에 없던 것 — 지속 예측은 자명하므로 배제).
        점수(b) = Σ_{a∈sel(t)} M[a][b]. 후보 전집 = 학습에서 관측된 기억.
  기준선: need(decay-LFU d=0.8, t 이전 선택 이력) · 인기(학습 선택 수) · 무작위.
  지표: recall@20 (표적 중 상위 20에 든 비율), 시험 턴 평균.

## 판정 (등록)

  지지: SR가 need·인기 둘 다에 +5pp 이상 → 전이 구조 실재, 본선 6 착수 근거.
  회색: 최고 기준선 ±5pp — 구조 미약, 경로 ①(명시적 시뮬레이션)을 주로.
  반증: SR < 기준선.

## 등록된 한계

  트레이스의 selected_ids는 '검색기가 표면화한 것'이지 '실제 쓰인 것'이 아니다 —
  이 백테스트는 표면화-전이 구조의 존재를 재는 전제 조건 시험이고, 인과 판은
  의미 메아리 v3 라벨이 쌓인 뒤 재실행한다.

읽기 전용. 사용: .venv/bin/python scripts/sr_backtest.py
"""
from __future__ import annotations

import json
import math
import os
import random
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DB = os.environ.get("MEM1_DB_PATH", str(Path.home() / ".forget/forget.sqlite3"))
GAP_S = 30 * 60
GAMMA = 0.7
HORIZON = 5
TOP_K = 20
DECAY_D = 0.8
DAY = 86400.0


def ts(raw: str) -> float:
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    turns = []
    for created, sel in con.execute(
        "SELECT created_at, selected_ids FROM context_traces "
        "WHERE selected_ids IS NOT NULL AND selected_ids != '[]' ORDER BY created_at"
    ):
        try:
            ids = [str(x) for x in json.loads(sel) or []]
        except Exception:
            continue
        t = ts(created)
        if ids and t:
            turns.append((t, ids))
    con.close()

    episodes: list[list[tuple[float, list[str]]]] = []
    for t, ids in turns:
        if not episodes or t - episodes[-1][-1][0] > GAP_S:
            episodes.append([])
        episodes[-1].append((t, ids))
    split = int(len(episodes) * 0.7)
    train, test = episodes[:split], episodes[split:]
    print(f"턴 {len(turns)} · 에피소드 {len(episodes)} (중위 길이 "
          f"{sorted(len(e) for e in episodes)[len(episodes)//2]}) · 학습 {split} / 시험 {len(test)}")

    # 학습: SR 행렬 + 인기 + 선택 이력
    sr: dict[str, Counter] = defaultdict(Counter)
    popularity: Counter = Counter()
    history: dict[str, list[float]] = defaultdict(list)
    for ep in train:
        for i, (t, sel_i) in enumerate(ep):
            for m in sel_i:
                popularity[m] += 1
                history[m].append(t)
            for k in range(1, HORIZON + 1):
                if i + k >= len(ep):
                    break
                w = GAMMA ** (k - 1)
                for a in sel_i:
                    for b in ep[i + k][1]:
                        if a != b:
                            sr[a][b] += w
    universe = list(popularity)
    print(f"전집 {len(universe)} · SR 행 {len(sr)} · 평균 행 크기 "
          f"{sum(len(v) for v in sr.values())/max(1,len(sr)):.0f}")

    rng = random.Random(20260824)
    rec = {"sr": [], "need": [], "pop": [], "rand": []}
    n_eval = 0
    for ep in test:
        for i, (t, sel_i) in enumerate(ep):
            future = set()
            for k in range(1, HORIZON + 1):
                if i + k < len(ep):
                    future.update(ep[i + k][1])
            targets = future - set(sel_i)
            if not targets:
                continue
            n_eval += 1

            sr_score: Counter = Counter()
            for a in sel_i:
                for b, w in sr.get(a, {}).items():
                    sr_score[b] += w
            top_sr = {m for m, _ in sr_score.most_common(TOP_K)}

            def need(m: str) -> float:
                past = [x for x in history.get(m, []) if x < t][-32:]
                return sum(((t - x) / DAY + 1e-3) ** (-DECAY_D) for x in past)

            # need는 전집 전체 계산이 비싸므로 인기 상위 400 + SR 후보로 제한
            # (need 상위는 최근 다용 기억 — 인기 상위 밖에서 나올 수 없다에 가깝다)
            need_pool = set(m for m, _ in popularity.most_common(400)) | set(sr_score)
            top_need = set(sorted(need_pool, key=need, reverse=True)[:TOP_K])
            top_pop = {m for m, _ in popularity.most_common(TOP_K)}
            top_rand = set(rng.sample(universe, min(TOP_K, len(universe))))

            for name, top in (("sr", top_sr), ("need", top_need), ("pop", top_pop), ("rand", top_rand)):
                rec[name].append(len(targets & top) / len(targets))

    print(f"\n시험 턴 {n_eval} (신규 표적 보유)\n")
    print(f"{'방법':6s} {'recall@20':>10s}")
    means = {}
    for name in ("sr", "need", "pop", "rand"):
        means[name] = sum(rec[name]) / max(1, len(rec[name]))
        print(f"{name:6s} {means[name]:10.3f}")
    best_base = max(means["need"], means["pop"])
    delta = (means["sr"] - best_base) * 100
    print(f"\nSR − 최고 기준선 = {delta:+.1f}pp → ", end="")
    if delta >= 5:
        print("지지 — 전이 구조 실재, 본선 6 착수 근거 (등록선 ≥+5pp)")
    elif delta > -5:
        print("회색 — 구조 미약, 명시적 시뮬레이션 경로를 주로 (등록선 ±5pp)")
    else:
        print("반증 — 표면화 전이에 학습 가능한 구조 없음")


if __name__ == "__main__":
    main()
