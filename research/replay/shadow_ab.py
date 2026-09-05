#!/usr/bin/env python3
"""섀도 A/B — 기억 접지 유무의 짝지은 비교 (같은 턴, 두 조건).

영점 결함의 수리: 무기억 예측(시스템 프롬프트뿐) vs 기억-접지 예측
(forget 장부에서 관련 기억·평결을 인출해 컨텍스트에 주입). R-WoM 원리
("검색으로 접지된 시뮬레이션")의 쌍둥이 적용. 어댑터 축은 디코더 훈련
완료 후 — 이 파일은 2×2의 기억 열을 먼저 닫는다.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shadow_daemon import (  # noqa: E402
    NOISE, direction, embed_sim, iter_turns, _post, TWIN_URL, TWIN_MODEL,
)

FORGET_MCP = "http://127.0.0.1:8000/mcp"
OUT = Path.home() / ".forget/twin/shadow_ab_clean.jsonl"
N_TURNS = 14

SYS_BASE = ("너는 정훈이다. 1인 창업자, forget(로컬 AI 기억 제품)을 만든다. "
            "아래는 네 에이전트의 최신 보고다. 정훈으로서 다음 메시지를 써라 — "
            "짧고 직설적으로, 실제 채팅처럼.")


def recall(query: str, k: int = 6, before_ts: str | None = None) -> list[str]:
    # 시간 컷오프 — 예측 대상 턴 이후에 쓰인 기억은 미래 정보 (답 누출 벡터).
    # 자기 감사(2026-08-13 "개주작 증명" 문답)에서 적발된 오염 경로의 봉쇄.
    args = {"query": query[:300], "limit": k, "trace": "shadow_ab"}
    if before_ts:
        args["filters"] = {"created_at": {"lt": before_ts}}
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "search_memories", "arguments": args}}
    req = urllib.request.Request(FORGET_MCP, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(req, timeout=20).read())
    result = json.loads(body["result"]["content"][0]["text"])
    return [str(m.get("memory") or "")[:280] for m in (result.get("results") or [])[:k]]


def predict(ctx: str, memories: list[str] | None) -> str:
    system = SYS_BASE
    if memories:
        system += ("\n\n[정훈에 대해 기록된 사실·결정·문화 — 반응의 근거로 써라]\n"
                   + "\n".join(f"- {m}" for m in memories))
    body = _post(TWIN_URL, {
        "model": TWIN_MODEL, "stream": False, "think": False, "keep_alive": "3h",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": ctx[-1600:]}],
        "options": {"temperature": 0.7, "num_predict": 150},
    })
    return str((body.get("message") or {}).get("content") or "").strip()


def main() -> None:
    turns = []
    for t in iter_turns():
        turns.append(t)
    turns = turns[-N_TURNS:]  # 최근 턴 우선 (이 세션 포함)
    print(f"대상 턴 {len(turns)}개 — 조건 2 × 짝지음", file=sys.stderr)

    rows = []
    for i, t in enumerate(turns):
        try:
            mems = recall(t["ctx"][-400:], before_ts=t.get("ts") or None)
        except Exception as exc:
            mems = []
            print(f"[{i}] recall 실패: {exc}", file=sys.stderr)
        try:
            p_plain = predict(t["ctx"], None)
            p_mem = predict(t["ctx"], mems)
        except Exception as exc:
            print(f"[{i}] 생성 실패: {exc}", file=sys.stderr)
            break
        row = {
            "ts": t["ts"], "actual": t["actual"][:300],
            "n_mems": len(mems),
            "plain": {"pred": p_plain[:300], "sim": embed_sim(p_plain, t["actual"]),
                      "dir": direction(p_plain)},
            "mem": {"pred": p_mem[:300], "sim": embed_sim(p_mem, t["actual"]),
                    "dir": direction(p_mem)},
            "dir_actual": direction(t["actual"]),
        }
        rows.append(row)
        with OUT.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{i+1}/{len(turns)}] plain {row['plain']['sim']:.2f} vs mem {row['mem']['sim']:.2f}",
              file=sys.stderr)

    if rows:
        d_sim = [r["mem"]["sim"] - r["plain"]["sim"] for r in rows
                 if r["mem"]["sim"] >= 0 and r["plain"]["sim"] >= 0]
        hit_p = sum(1 for r in rows if r["plain"]["dir"] == r["dir_actual"])
        hit_m = sum(1 for r in rows if r["mem"]["dir"] == r["dir_actual"])
        wins = sum(1 for d in d_sim if d > 0)
        print(json.dumps({
            "n": len(rows),
            "sim_delta_mean": round(sum(d_sim) / max(1, len(d_sim)), 4),
            "sim_wins": f"{wins}/{len(d_sim)}",
            "dir_plain": f"{hit_p}/{len(rows)}",
            "dir_mem": f"{hit_m}/{len(rows)}",
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
