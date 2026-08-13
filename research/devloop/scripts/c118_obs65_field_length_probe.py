#!/usr/bin/env python3
"""c118 — 관측 65 처치 설계 입력: 질의 길이(하한 80자 vs 훅 상한 300자) 짝지은 대조 (읽기 전용).

질문: c117 실측(80자 하한 계기)과 필드 발생률(관측 59 표 high 7/11=0.636)의 괴리는
질의 길이 몫인가 — c117은 "게이트 프롬프트는 후보 16×160자가 지배라 질의 길이 차이는
부차 성분"이라고 주장만 하고 실측하지 않았다. 이 계기가 그 주장을 검증한다.

설계 규약 (c117_obs65_latency_probe.py 승계):
- 읽기 전용: search_memories만, trace 미전달, 게이트 원장 행 생성 없음.
- 질의 원문 무인쇄 (관측 36·37): sha8 + 길이만.
- 표본 = 게이트 원장 gear=high prompt_head 중복 제거 (c117과 동일 풀).
- 300자 판본 = 같은 prompt_head를 공백 연결로 반복해 300자 절단 — 합성 패딩임을 병기.
  토큰 분포는 원문 유사, 의미 중복은 게이트 후보 선별에 영향 가능(계기 한계 선언).
- 짝지은 설계: 같은 프롬프트의 80자/300자를 연속 측정, 순서는 인덱스 홀짝으로 교대
  (웜 드리프트의 순서 교란 상쇄). 첫 프롬프트 전에 웜업 high 1회(비계상, 표기).
- 널 대조 (자기 규칙): 같은 짝을 recall=low로도 측정 — Δ길이(low) ≈ Δ길이(high)면
  길이 효과는 게이트 LLM이 아니라 수송/임베딩 몫이다.
- 유효성 필터: recall_layer가 gate-v2로 시작하는 표본만 high 분포 계상 (c117 동일).

판정 기준 (선행 선언 — 계기 관례이며 자의적 문턱임을 명시):
- 짝지은 Δ = high(300) − high(80)의 중앙값이 +2s 이상 → 길이가 필드 괴리의 주성분,
  상수 설계는 상계(300자) 분포 기준으로 간다.
- |중앙값 Δ| < 1s → c117의 "부차 성분" 주장 지지, 필드 괴리는 부하/상태 몫으로 좁혀지고
  처치 서열에서 기어 선택 정책(정적 상수로는 필드 꼬리를 못 품음)이 강화된다.
- 1s ≤ |Δ| < 2s → 판정 유보, 표본 확대는 다음 측정 사이클 몫.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
import urllib.request

FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://localhost:8000/mcp/forget/http/junghunkim")
LEDGER = os.path.expanduser("~/.forget/hooks/state/turnrecall_gate.jsonl")
DEPLOY_EPOCH = 1786077622  # 2026-08-12 13:40:22 +0900 — c117과 동일 기준
MAX_PROMPTS = 8
FIELD_LEN = 300  # 훅 원문 절단 상한 (forget_turnrecall.py)
REQ_TIMEOUT = 30.0


def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def pad_to_field(prompt: str, target: int = FIELD_LEN) -> str:
    body = prompt
    while len(body) < target:
        body = body + " " + prompt
    return body[:target]


def rpc(name: str, arguments: dict, timeout: float) -> tuple[dict | None, float, str]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    req = urllib.request.Request(FORGET_URL, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        body = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        elapsed = time.monotonic() - t0
        return json.loads(body["result"]["content"][0]["text"]), elapsed, ""
    except Exception as exc:
        return None, time.monotonic() - t0, type(exc).__name__


def measure(query: str, gear: str) -> dict:
    result, elapsed, err = rpc("search_memories",
                               {"query": query, "top_k": 10, "recall": gear,
                                "score_breakdown": True}, REQ_TIMEOUT)
    layer = str((result or {}).get("recall_layer") or "")
    return {"s": round(elapsed, 3), "err": err, "layer": layer,
            "n": len((result or {}).get("results") or [])}


def engaged(m: dict) -> bool:
    return (not m["err"]) and m["layer"].startswith("gate-v2")


def pure_gate(m: dict) -> bool:
    """서버 내부 폴백(gate-v2(fallback→v1))은 게이트 완주가 아니라 중도 포기다 —
    그 지연을 high 분포에 넣으면 검열 표본이 p95를 하향 편향시킨다 (1차 런 자기 적발)."""
    return engaged(m) and "fallback" not in m["layer"]


def pctl(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    ordered = sorted(xs)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def main() -> None:
    print("[A. 표본 — 게이트 원장 gear=high prompt_head, c117 동일 풀]")
    rows = []
    with open(LEDGER, encoding="utf-8") as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    high_rows = [r for r in rows if r.get("gear") == "high" and r.get("prompt_head")]
    recent = [r for r in high_rows if int(r.get("at") or 0) >= DEPLOY_EPOCH]
    pool = recent if len(recent) >= 6 else high_rows
    seen: dict[str, dict] = {}
    for r in sorted(pool, key=lambda r: -int(r.get("at") or 0)):
        seen.setdefault(r["prompt_head"], r)
    prompts = list(seen.keys())[:MAX_PROMPTS]
    print(f"  원장 {len(rows)}행 · gear=high {len(high_rows)}행(배포 후 {len(recent)}) · 표본 {len(prompts)}건 (상한 {MAX_PROMPTS})")

    if not prompts:
        print("  표본 0 — 측정 불가")
        return

    print("\n[B. 실측 — 짝지은 80자/300자, 순서 홀짝 교대, 웜업 1회 비계상 (질의 무인쇄)]")
    warm = measure(prompts[0], "high")
    print(f"  웜업(비계상): high={warm['s']:.3f}s {warm['err'] or warm['layer']}")
    pairs = []
    for i, p in enumerate(prompts):
        short, field = p[:80], pad_to_field(p)
        order = [("80", short), ("300", field)] if i % 2 == 0 else [("300", field), ("80", short)]
        row = {"i": i, "sha8": sha8(p), "order": "+".join(k for k, _ in order)}
        for tag, q in order:
            row[f"high{tag}"] = measure(q, "high")
        for tag, q in (("80", short), ("300", field)):
            row[f"low{tag}"] = measure(q, "low")
        pairs.append(row)
        h8, h3 = row["high80"], row["high300"]
        l8, l3 = row["low80"], row["low300"]
        print(f"  #{i:02d} {row['sha8']} 순서={row['order']:6s}"
              f"  high80={h8['s']:7.3f}s {h8['err'] or h8['layer']:<14}"
              f"  high300={h3['s']:7.3f}s {h3['err'] or h3['layer']:<14}"
              f"  low80={l8['s']:6.3f}s low300={l3['s']:6.3f}s")

    valid = [r for r in pairs if engaged(r["high80"]) and engaged(r["high300"])]
    dropped = len(pairs) - len(valid)
    pure = [r for r in valid if pure_gate(r["high80"]) and pure_gate(r["high300"])]
    fb = [r for r in valid if r not in pure]
    d_high = [r["high300"]["s"] - r["high80"]["s"] for r in valid]
    d_pure = [r["high300"]["s"] - r["high80"]["s"] for r in pure]
    d_low = [r["low300"]["s"] - r["low80"]["s"] for r in pairs
             if not r["low80"]["err"] and not r["low300"]["err"]]
    h300 = [r["high300"]["s"] for r in valid]
    h80 = [r["high80"]["s"] for r in valid]
    h300p = [r["high300"]["s"] for r in pure]

    print("\n[C. 분포 — 게이트 실관여 짝만, 순수/폴백 층화]")
    print(f"  유효 짝 {len(valid)} · 제외 {dropped} (비관여/오류) · 순수 gate-v2 짝 {len(pure)}"
          f" · 서버 내부 폴백 포함 짝 {len(fb)} (fallback→v1 = 검열 표본, 상계 분포에서 제외)")
    if valid:
        print(f"  high80 : p50={pctl(h80,0.5):.2f} p95={pctl(h80,0.95):.2f}")
        print(f"  high300 전체: p50={pctl(h300,0.5):.2f} p95={pctl(h300,0.95):.2f}  (폴백 혼입 — 하향 편향)")
        if h300p:
            print(f"  high300 순수: p50={pctl(h300p,0.5):.2f} p95={pctl(h300p,0.95):.2f}  ← 필드 상계 후보 (상수 설계 입력)")
        print(f"  짝지은 Δ(high300−high80) 전체: 중앙값={statistics.median(d_high):+.2f}s"
              f"  min={min(d_high):+.2f} max={max(d_high):+.2f}")
        if d_pure:
            print(f"  짝지은 Δ 순수 짝만:          중앙값={statistics.median(d_pure):+.2f}s  (검열 제거 — 판정 정본)")
    if d_low:
        print(f"  짝지은 Δ(low300−low80):  중앙값={statistics.median(d_low):+.2f}s  (널 대조)")

    print("\n[D. 판정 — 헤더 선언 기준 (판정 정본 = 순수 짝 Δ, 폴백 검열 제거)]")
    if not valid:
        print("  판정 불가: 유효 짝 0")
        return
    med = statistics.median(d_pure) if d_pure else statistics.median(d_high)
    h300_ref = h300p if h300p else h300
    if med >= 2.0:
        print(f"  Δ중앙값={med:+.2f}s ≥ +2s → 길이가 주성분. 상수 설계는 300자 분포"
              f" (순수 p95={pctl(h300_ref,0.95):.2f}s) 기준.")
    elif abs(med) < 1.0:
        print(f"  |Δ중앙값|={abs(med):.2f}s < 1s → c117 '부차 성분' 주장 지지."
              " 필드 괴리는 부하/상태 몫 — 기어 선택 정책 서열 강화.")
    else:
        print(f"  Δ중앙값={med:+.2f}s (1~2s) → 판정 유보, 표본 확대는 다음 측정 사이클 몫.")
    if d_low:
        ml = statistics.median(d_low)
        verdict = "게이트 몫" if abs(med) > 3 * abs(ml) + 0.05 else "수송/임베딩 성분 혼입 의심"
        print(f"  널 대조: Δlow 중앙값={ml:+.2f}s vs Δhigh={med:+.2f}s → 길이 효과는 {verdict}")
    print(f"  12s 복원안 대비: high300 순수 p95={pctl(h300_ref,0.95):.2f}s —"
          f" {'안' if pctl(h300_ref,0.95) <= 12.0 else '밖(12s로도 꼬리 못 품음)'}"
          f"  (단일 런·소표본 — 일간 상태 드리프트는 c117 대조로 별도 판정)")


if __name__ == "__main__":
    main()
