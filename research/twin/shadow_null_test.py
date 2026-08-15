#!/usr/bin/env python3
"""섀도 곡선 순열 널 검정 — "이 예측은 이 턴에 대한 것인가?"

배경: 방향 일치는 다수 클래스 기저율(널 0.75~0.92)에 먹혔고, sim은 절대값
0.68~0.71로 평평해 판독 불가였다. 두 지표 다 "이 곡선이 무엇을 재는가"를
답하지 못했다.

이 검정의 널: **순열(permutation)** — 예측 i를 실발화 i가 아닌 j에 짝지어
얻는 유사도 분포. 매칭 sim이 순열 널을 유의하게 넘지 못하면, 그 예측은
*그 턴에 대한 정보를 담고 있지 않다* (한국어 기술 대화의 일반 유사도 바닥일
뿐). 이것이 "얼마나 그가 되었나"를 재는 유일한 정직한 축이다.

격언 이행: 새 계기는 채점 전에 널부터. 여기서는 널이 지표에 내장돼 있다.
"""
from __future__ import annotations

import json
import random
import sys
import urllib.request
from pathlib import Path

SCORES = Path.home() / ".forget/twin/shadow_scores.jsonl"
EMB_URL = "http://127.0.0.1:11434/api/embed"
EMB_MODEL = "nomic-embed-text"
SHUFFLES = 200


def embed(texts: list[str]) -> list[list[float]]:
    req = urllib.request.Request(
        EMB_URL, data=json.dumps({"model": EMB_MODEL, "input": texts}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read())["embeddings"]


def cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / max(1e-9, na * nb)


def main() -> None:
    only_retro = "--retro" in sys.argv
    rows = [json.loads(l) for l in SCORES.open()]
    if only_retro:
        rows = [r for r in rows if r.get("retro")]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r.get("variant") or f"prompt-only/{r.get('engine','?')}", []).append(r)

    rng = random.Random(7)
    out = []
    for variant, items in sorted(by.items()):
        # 턴 중복 제거 (같은 ts는 1건만)
        uniq: dict[str, dict] = {}
        for i in items:
            uniq[str(i.get("ts"))] = i
        items = list(uniq.values())
        if len(items) < 20:
            print(f"{variant}: n={len(items)} — 표본 미달, 건너뜀", file=sys.stderr)
            continue
        preds = [str(i.get("pred_head") or "") for i in items]
        acts = [str(i.get("actual") or "")[:800] for i in items]
        E_p, E_a = embed(preds), embed(acts)
        matched = [cos(E_p[i], E_a[i]) for i in range(len(items))]
        idx = list(range(len(items)))
        nulls = []
        for _ in range(SHUFFLES):
            sh = idx[:]
            rng.shuffle(sh)
            pairs = [(i, sh[i]) for i in idx if sh[i] != i]
            nulls.append(sum(cos(E_p[i], E_a[j]) for i, j in pairs) / max(1, len(pairs)))
        m = sum(matched) / len(matched)
        n = sum(nulls) / len(nulls)
        sd = (sum((x - n) ** 2 for x in nulls) / len(nulls)) ** 0.5
        z = (m - n) / max(1e-9, sd)
        out.append({"variant": variant, "n": len(items), "matched_sim": round(m, 4),
                    "permutation_null": round(n, 4), "null_sd": round(sd, 4),
                    "excess": round(m - n, 4), "z": round(z, 2),
                    "verdict": "턴-수준 예측 정보 있음" if z >= 2 else "정보 없음 (널 이내)"})
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
