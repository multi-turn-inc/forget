#!/usr/bin/env python3
"""c117 — 관측 65 수용 기준 ① 이분 판정 계기 (읽기 전용).

질문: high 기어 타임아웃의 병목은 어느 쪽인가 —
  (A) 훅 측 데드라인 상수 (코드 문면)  vs  (B) high 기어 서버 회상 지연 (p50/p95 실측)

설계 규약:
- 읽기 전용: search_memories 호출만. 쓰기 없음(trace 미전달 — 플라이휠 오염 방지),
  게이트 원장은 훅 전용이라 이 프로브는 행을 만들지 않는다.
- 질의 원문 무인쇄 (관측 36·37): sha256[:8] + 길이만 표기.
- 프로브 질의 = 실제 게이트 원장의 gear=high 행 prompt_head (80자 절단 — 훅 원문은
  300자 상한이므로 하한 근사임을 병기. 게이트 프롬프트는 후보 16×160자가 지배라
  질의 길이 차이는 부차 성분).
- 대조군 (원칙 1 + 자기 규칙 널 대조): 동일 질의를 recall=low로도 측정.
  계기가 기어를 구분하지 못하면(고=저) 지연이 아니라 수송을 잰 것이다.
- 유효성 필터: 응답 recall_layer로 게이트 실관여를 판정 — passthrough/unconfigured/
  v1 폴백 표본은 high 분포에서 제외하고 별도 계수(폴백을 high로 오계상하지 않는다).
- 콜드/웜 분리: 첫 high 표본은 콜드 후보로 별도 표기, p50/p95는 웜 표본으로도 병기.
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
DEPLOY_EPOCH = 1786077622  # 2026-08-12 13:40:22 +0900 — 관측 59 처분 절의 배포 시각
MAX_PROMPTS = 12
REQ_TIMEOUT = 30.0  # 데드라인(7s)보다 충분히 커서 실지연을 비검열로 관측

# ── 훅 측 상수 (코드 문면, 배포본과 저장소 대조) ─────────────────────────────
HOOK_DEPLOYED = os.path.expanduser("~/.forget/hooks/forget_turnrecall.py")
HOOK_REPO = os.path.join(os.path.dirname(__file__), "..", "..", "..", "hooks", "forget_turnrecall.py")


def hook_constants(path: str) -> dict:
    out = {"path": path, "high": None, "low": None, "degrade": None}
    try:
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            if 'timeout=7 if gear == "high" else 5' in line:
                out["high"], out["low"] = 7, 5
                out["line_main"] = i
            if "timeout=2)" in line and "_rpc" in line:
                out["degrade"] = 2
                out["line_degrade"] = i
    except OSError as exc:
        out["error"] = str(exc)
    return out


def sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


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
    except Exception as exc:  # 검열 표본도 데이터다
        return None, time.monotonic() - t0, type(exc).__name__


def local_llm_stack() -> str:
    for origin, path, list_key, name_key, token in [
        ("http://127.0.0.1:11434", "/api/tags", "models", "name", "ollama"),
        ("http://127.0.0.1:1234", "/v1/models", "data", "id", "lm-studio"),
    ]:
        try:
            with urllib.request.urlopen(origin + path, timeout=1) as r:
                body = json.loads(r.read().decode("utf-8"))
            names = [str(m.get(name_key)) for m in body.get(list_key) or []]
            if names:
                return f"{token}: {', '.join(sorted(names)[:6])}"
        except Exception:
            continue
    return "로컬 런타임 미감지 (recall LLM 없음 → high는 v1 폴백일 것)"


def pctl(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    ordered = sorted(xs)
    idx = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return ordered[idx]


def main() -> None:
    print("[c117 관측 65 이분 판정 — A. 훅 상수 (코드 문면)]")
    dep, rep = hook_constants(HOOK_DEPLOYED), hook_constants(os.path.normpath(HOOK_REPO))
    for tag, c in (("배포본", dep), ("저장소", rep)):
        print(f"  {tag} {c['path']}")
        print(f"    high={c['high']}s (L{c.get('line_main')}) low={c['low']}s 강등재시도={c['degrade']}s (L{c.get('line_degrade')})")
    match = (dep["high"], dep["low"], dep["degrade"]) == (rep["high"], rep["low"], rep["degrade"])
    print(f"  배포본=저장소 문면 일치: {match}")

    print("\n[B. 프로브 표본 — 게이트 원장 gear=high 행의 prompt_head, 배포 후 우선]")
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
    print(f"  원장 {len(rows)}행 · gear=high {len(high_rows)}행(배포 후 {len(recent)}) · 중복 제거 표본 {len(prompts)}건 (상한 {MAX_PROMPTS})")
    print(f"  recall LLM 스택: {local_llm_stack()}")

    print("\n[C. 실측 — 각 질의를 high→low 순으로, 요청 상한 30s (질의 무인쇄)]")
    samples = []
    for i, p in enumerate(prompts):
        row = {"i": i, "sha8": sha8(p), "len": len(p)}
        for gear in ("high", "low"):
            args = {"query": p, "top_k": 10, "recall": gear, "score_breakdown": True}
            result, elapsed, err = rpc("search_memories", args, REQ_TIMEOUT)
            layer = str((result or {}).get("recall_layer") or "")
            row[gear] = {"s": round(elapsed, 3), "err": err, "layer": layer,
                         "n": len((result or {}).get("results") or [])}
        samples.append(row)
        h, l = row["high"], row["low"]
        print(f"  #{i:02d} {row['sha8']} len={row['len']:3d}  high={h['s']:7.3f}s {h['err'] or h['layer'] or 'v1'!s:<24}  low={l['s']:6.3f}s {l['err'] or l['layer'] or 'v1'}")

    def gate_engaged(s: dict) -> bool:
        layer = s["high"]["layer"]
        return (not s["high"]["err"]) and layer.startswith("gate-v2") and "unconfigured" not in layer and "passthrough" not in layer

    engaged = [s for s in samples if gate_engaged(s)]
    excluded = [s for s in samples if not gate_engaged(s)]
    high_all = [s["high"]["s"] for s in engaged]
    high_warm = high_all[1:] if len(high_all) > 1 else high_all
    low_ok = [s["low"]["s"] for s in samples if not s["low"]["err"]]
    censored = [s for s in samples if s["high"]["err"]]

    print("\n[D. 분포 — 게이트 실관여 high 표본만 (폴백·오류 제외 계수 병기)]")
    print(f"  실관여 {len(engaged)} · 제외 {len(excluded)} (폴백/passthrough/오류) · 검열(>30s 또는 예외) {len(censored)}")
    if high_all:
        print(f"  high 전체 n={len(high_all)}: min={min(high_all):.2f} p50={pctl(high_all,0.5):.2f} p95={pctl(high_all,0.95):.2f} max={max(high_all):.2f}  (첫 표본={high_all[0]:.2f} 콜드 후보)")
        print(f"  high 웜   n={len(high_warm)}: p50={pctl(high_warm,0.5):.2f} p95={pctl(high_warm,0.95):.2f}")
    if low_ok:
        print(f"  low  대조 n={len(low_ok)}: p50={pctl(low_ok,0.5):.2f} p95={pctl(low_ok,0.95):.2f}  (널 대조: high−low 중앙값 차={pctl(high_all,0.5)-pctl(low_ok,0.5):+.2f}s — 0 근방이면 계기는 기어가 아니라 수송을 잰 것)")

    print("\n[E. 이분 판정 — 데드라인 7s (배포본 훅 L%s) 대비]" % dep.get("line_main"))
    if not high_all:
        print("  판정 불가: 게이트 실관여 표본 0 — recall LLM 미가동이면 관측 65의 재현 조건 자체가 부재")
        return
    p95w, p50w = pctl(high_warm, 0.95), pctl(high_warm, 0.5)
    if p95w > 7.0:
        print(f"  웜 p95={p95w:.2f}s > 7s → 병목=서버 측 (B). 상수가 웜 정상 경로조차 못 품는다 — 구조적.")
    elif high_all[0] > 7.0:
        print(f"  웜 p95={p95w:.2f}s ≤ 7s, 콜드 첫 표본={high_all[0]:.2f}s > 7s → 병목=콜드 경로. 웜은 상수 안. 처치 후보는 상수가 아니라 상주/예열.")
    else:
        print(f"  웜 p95={p95w:.2f}s ≤ 7s, 콜드={high_all[0]:.2f}s ≤ 7s → 이 창의 몸은 데드라인 안. 관측 65 창의 타임아웃은 당시 상태(모델 언로드·경합)로 귀속 — 재현 불가 병기.")
    print(f"  강등 예산 2s 대비: low p95={pctl(low_ok,0.95):.2f}s — {'안' if pctl(low_ok,0.95)<=2.0 else '밖(강등마저 죽을 수 있음)'}")


if __name__ == "__main__":
    main()
