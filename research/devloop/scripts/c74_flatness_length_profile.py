#!/usr/bin/env python3
"""c74 — 평탄도 침묵은 질의 길이의 함수인가: 관측 24 수용 기준 (i)의 첫 실측 (읽기 전용).

관측 24(c63)가 세운 가설: "짧은 후속 질문일수록 구조적으로 평지" — 단 *"질의 길이 대
spread 상관은 아직 재지 않았다"*. c68 보강이 완전한 주제어 질의 2건의 평지(부수 피해)로
가설을 좁혔지만 상관 자체는 *"여전히 미측정"*으로 남겼다. 이 스크립트가 그 축을 잰다.

측정 설계 (c63_depth_invariance.py 계보 승계):
  - 표본: 도그푸드 원장 `context_traces`의 실제 turn_recall 질의 **전수**(유니크,
    c63은 최신 20건 표본이었다). 재실행은 그 trace의 filters 그대로, top_k=5(훅 패리티),
    trace= 미전달 — 계측이 장부를 오염시키지 않는다.
  - 자[尺] 고정: margin=0.03 · min_samples=4 · window=5 전부 미변경 (c48 규율 —
    이 사이클은 자[尺]을 재지, 바꾸지 않는다).
  - 대조군 1 (c63 재현): 최신 20건 dedup = c63 프로토콜 복제 → 평지율을 c63 실측
    8/20과 대조. 스토어는 그 뒤 성장했으므로 차이는 드리프트 측정이지 재현 실패가 아니다.
  - 대조군 2 (앵커): 관측 24가 spread 값과 함께 인용한 실제 질의들을 접두 매칭으로
    찾아 당시 값과 병기한다.
  - 상관: 길이(문자·어절) 대 spread 스피어만 rho + 고정 시드 순열 p (게임내성 —
    손수 라벨 없음). 유형 축은 손 라벨 대신 길이 사분위 밴드별 평지율 + 밴드 내
    평지 질의 원문 전량 나열(선별 없음)로 대신한다.

측정 몸 선언 (원칙 3): 살아 있는 :8000 = 구척도 아핀 합성(score = 0.275 + rule*0.45 +
0.275*cos). 저장소 신척도(c72, 미배포 ⑮)와 혼용 금지 — 이 측정의 spread는 전부 구척도
값이며 margin=0.03이 실제로 대면하는 척도가 바로 이것이다. 스택은 실행 시
get_provider_health `effective`(관측 31: checks는 폴백 이름을 들고 있다)로 인쇄한다.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sqlite3
import urllib.request

DB = os.path.expanduser("~/.forget/forget.sqlite3")
FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
SHALLOW = 5          # 현행 top_k (MAX_RECALLS + 2) — 훅 패리티
WINDOW = 5           # 평탄도 창
MIN_SAMPLES = 4      # 자[尺] 미변경
MARGIN = 0.03        # 자[尺] 미변경
PERMS = 20_000       # 순열 p — 고정 시드로 결정적
SEED = 74
ROWS_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "notes", "c74_rows.json")
# 앵커 검시(c74_anchor_probe.py)로 확정된 자기 인용 오염 행 — c63 필드 노트 기억이
# 이 두 질의의 원문을 그대로 인용해 스스로 봉우리(rule≈0.93)가 됐다. 민감도 분석에서 제외.
CONTAMINATED = {"2026-08-06T15:10:24Z", "2026-08-06T09:32:16Z"}

# 관측 24가 인용한 앵커 (접두, 당시 spread). "잊은 것들" 질의는 두 턴 연속이라 두 값.
ANCHORS = [
    ("그런데 그러고 보니 잊은 것들의 목록은 후보에서 제외했네?", (0.0264, 0.0233)),
    ("c15 eta를 알려줘", (0.0113,)),
    ("응 c14는 잘 되고 있어? 언제 끝나?", (0.0120,)),
    ("에러가 발생했나?", (0.0192,)),
]


def rpc(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        FORGET_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(request, timeout=30).read())
    return json.loads(body["result"]["content"][0]["text"])


def eligible(item: dict) -> bool:
    """훅 `_injection_eligible` 판정 복제 (c63과 동일한 구조적 배제)."""
    md = item.get("metadata") or {}
    if md.get("hook"):
        return False
    if md.get("assertion_kind") == "task_state":
        return False
    if md.get("superseded_by"):
        return False
    supersedes = md.get("supersedes")
    if isinstance(supersedes, list) and supersedes:
        return False
    return True


def flat_verdict(scores: list[float]) -> tuple[bool, float, int]:
    if len(scores) < MIN_SAMPLES:
        return (False, float("nan"), len(scores))   # 게이트 미적용 = 전량 통과
    spread = scores[0] - scores[len(scores) // 2]
    return (spread < MARGIN, spread, len(scores))


def all_turn_recall_queries() -> list[tuple[str, str, dict | None]]:
    """유니크 turn_recall 질의 전수, 최신순 (c63과 같은 dedup 규칙, limit 없음)."""
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    out, seen = [], set()
    for row in conn.execute(
        "SELECT created_at, query, filters, payload FROM context_traces "
        "ORDER BY created_at DESC"
    ):
        if "turn_recall" not in (row["payload"] or ""):
            continue
        query = (row["query"] or "").strip()
        if not query or query in seen:
            continue
        seen.add(query)
        try:
            filters = json.loads(row["filters"] or "null")
        except Exception:
            filters = None
        out.append((row["created_at"], query, filters if isinstance(filters, dict) else None))
    conn.close()
    return out


def ranks(values: list[float]) -> list[float]:
    """평균 순위 (동률 처리)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def perm_pvalue(xs: list[float], ys: list[float], observed: float) -> float:
    rng = random.Random(SEED)
    ys2 = ys[:]
    hits = 0
    for _ in range(PERMS):
        rng.shuffle(ys2)
        if abs(spearman(xs, ys2)) >= abs(observed) - 1e-12:
            hits += 1
    return (hits + 1) / (PERMS + 1)


def stack_header() -> str:
    try:
        health = rpc("get_provider_health", {})
    except Exception:
        return "몸: :8000 응답 없음 — 측정 불가"
    eff = health.get("effective") or {}
    chk = (health.get("checks") or {}).get("embeddings") or {}
    return (f"몸: :8000 구척도(0.275+rule*0.45+0.275*cos) · "
            f"effective={eff.get('embedding_provider')}:{eff.get('embedding_model')} "
            f"res={eff.get('resolution')} · checks(폴백 거울)={chk.get('provider')}:{chk.get('model')}")


def main() -> None:
    print(stack_header())
    samples = all_turn_recall_queries()
    print(f"실제 turn_recall 질의 전수 {len(samples)}건 (유니크, 최신순) — "
          f"자[尺] 고정: margin={MARGIN} min_samples={MIN_SAMPLES} window={WINDOW} top_k={SHALLOW}\n")

    rows = []
    for created_at, query, filters in samples:
        args = {"query": query[:300], "recall": "low", "score_breakdown": True,
                "top_k": SHALLOW}
        if filters:
            args["filters"] = filters
        results = rpc("search_memories", args).get("results") or []
        scores = sorted((float(i.get("score") or 0) for i in results if eligible(i)),
                        reverse=True)[:WINDOW]
        flat, spread, n = flat_verdict(scores)
        rows.append({"created_at": created_at, "query": query, "chars": len(query),
                     "words": len(query.split()), "n": n, "spread": spread, "flat": flat})

    print(f"{'created_at':21} {'자격':>4} {'chars':>5} {'spread':>8} {'평지':>5}  질의")
    for r in rows:
        sp = "  n/a " if math.isnan(r["spread"]) else f"{r['spread']:.4f}"
        print(f"{r['created_at']:21} {r['n']:>4} {r['chars']:>5} {sp:>8} "
              f"{str(r['flat']):>5}  {r['query'][:42]!r}")

    # ── 대조군 1: c63 프로토콜 복제 (최신 20건) ────────────────────────────
    head20 = rows[:20]
    gated20 = [r for r in head20 if r["n"] >= MIN_SAMPLES]
    flat20 = sum(1 for r in gated20 if r["flat"])
    print(f"\n[대조군 1 — c63 재현] 최신 20건: 평지 {flat20}/{len(head20)}"
          f" (게이트 적용 {len(gated20)}건 기준 {flat20}/{len(gated20)})"
          f" — c63 실측 8/20. 표본창은 5일치 이동, 차이는 드리프트.")

    # ── 대조군 2: 관측 24 앵커 질의 ──────────────────────────────────────
    print("[대조군 2 — 관측 24 앵커 spread 재현]")
    for prefix, then in ANCHORS:
        hit = next((r for r in rows if r["query"].startswith(prefix[:20])), None)
        if hit is None:
            print(f"  미발견(창 이탈): {prefix[:30]!r} 당시 {then}")
            continue
        now = "n/a" if math.isnan(hit["spread"]) else f"{hit['spread']:.4f}"
        print(f"  {prefix[:30]!r}: 당시 {'/'.join(f'{v:.4f}' for v in then)} → 현재 {now}"
              f" (자격 {hit['n']})")

    # ── 본 측정: 길이 대 spread ──────────────────────────────────────────
    gated = [r for r in rows if r["n"] >= MIN_SAMPLES]
    off = [r for r in rows if r["n"] < MIN_SAMPLES]
    flat_all = [r for r in gated if r["flat"]]
    print(f"\n[기저율 — 전수] 게이트 적용 {len(gated)}/{len(rows)}"
          f" (자격<4 전량통과 {len(off)}건) · 평지 = 침묵 {len(flat_all)}/{len(gated)}"
          f" ({100 * len(flat_all) / max(1, len(gated)):.0f}%)")

    xs = [float(r["chars"]) for r in gated]
    ws = [float(r["words"]) for r in gated]
    ys = [r["spread"] for r in gated]
    rho_c = spearman(xs, ys)
    rho_w = spearman(ws, ys)
    p_c = perm_pvalue(xs, ys, rho_c)
    p_w = perm_pvalue(ws, ys, rho_w)
    print(f"[상관] spread ~ 길이(문자): Spearman rho={rho_c:+.4f} (순열 p={p_c:.4f}, n={len(gated)})")
    print(f"[상관] spread ~ 길이(어절): Spearman rho={rho_w:+.4f} (순열 p={p_w:.4f}, n={len(gated)})")

    # 민감도 — 자기 인용 오염 2행 제외 (오염은 짧은 질의에 큰 spread를 얹어
    # 가설 방향의 상관을 *깎는* 쪽이므로, 제외 시 rho가 어디까지 회복되는지 본다)
    clean = [r for r in gated if r["created_at"] not in CONTAMINATED]
    cx = [float(r["chars"]) for r in clean]
    cy = [r["spread"] for r in clean]
    rho_cl = spearman(cx, cy)
    p_cl = perm_pvalue(cx, cy, rho_cl)
    print(f"[민감도] 오염 2행 제외: rho={rho_cl:+.4f} (순열 p={p_cl:.4f}, n={len(clean)})")

    # 길이 사분위 밴드별 평지율
    by_len = sorted(gated, key=lambda r: r["chars"])
    quarts = [by_len[i * len(by_len) // 4:(i + 1) * len(by_len) // 4] for i in range(4)]
    print("[길이 사분위 밴드 — 평지율]")
    for i, band in enumerate(quarts):
        if not band:
            continue
        nf = sum(1 for r in band if r["flat"])
        spreads = sorted(r["spread"] for r in band)
        print(f"  Q{i + 1} chars {band[0]['chars']}~{band[-1]['chars']}: "
              f"평지 {nf}/{len(band)} · spread min/med/max = "
              f"{spreads[0]:.4f}/{spreads[len(spreads) // 2]:.4f}/{spreads[-1]:.4f}")

    # 최장 사분위의 평지 질의 전량 (길이 가설의 반례 후보 — 선별 없이 전부)
    print("[Q4(최장 밴드) 평지 질의 전량 — 길이 가설 반례 후보]")
    for r in quarts[3]:
        if r["flat"]:
            print(f"  chars {r['chars']} spread {r['spread']:.4f}: {r['query'][:80]!r}")
    print("[Q1(최단 밴드) 봉우리 질의 전량 — 역방향 반례 후보]")
    for r in quarts[0]:
        if not r["flat"]:
            print(f"  chars {r['chars']} spread {r['spread']:.4f}: {r['query'][:80]!r}")

    # 커밋 산출물에는 질의 원문을 싣지 않는다 — 원장(context_traces)에 평문 비밀이
    # 실재함을 이 측정이 확인했다(관측 37). 행 식별은 created_at + sha256으로 충분하고,
    # 재현은 스크립트가 원장에서 직접 다시 뽑는다.
    sanitized = [{**{k: v for k, v in r.items() if k != "query"},
                  "query_head": r["query"][:24],
                  "query_sha256": hashlib.sha256(r["query"].encode("utf-8")).hexdigest()[:16]}
                 for r in rows]
    with open(ROWS_OUT, "w", encoding="utf-8") as fh:
        json.dump(sanitized, fh, ensure_ascii=False, indent=1)
    print(f"\n[원자료] {len(rows)}행 → {ROWS_OUT} (재현 규약 — 관측 27 · 질의 원문은 24자 절단+sha256)")


if __name__ == "__main__":
    main()
