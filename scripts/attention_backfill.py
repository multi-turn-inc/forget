#!/usr/bin/env python3
"""소급 관찰 — 과거 전사를 창으로 훑어 정훈의 결정·거부·정정·선호만 원장에 남긴다 (2026-09-07).
자원 규칙: 유휴 Spark를 묻지 않고 쓴다. 블록은 건드리지 않는다(observe 전용).

  .venv/bin/python scripts/attention_backfill.py <transcript.jsonl> [--every 3] [--since 2026-09-05] [--dry] [--limit N]
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forget import attention as T


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("--every", type=int, default=3, help="사용자 턴 N개마다 한 창")
    ap.add_argument("--since", default=""); ap.add_argument("--dry", action="store_true"); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--window", type=int, default=10)
    a = ap.parse_args()
    turns, _ = T.read_turns(Path(a.src), 0)
    spoken = [t for t in turns if t["role"] != "action" and (not a.since or t["ts"] >= a.since)]
    user_idx = [i for i, t in enumerate(spoken) if t["role"] == "user"]
    windows = user_idx[a.every - 1::a.every] or user_idx[-1:]
    if a.limit:
        windows = windows[: a.limit]
    print(f"turns {len(spoken)} · user {len(user_idx)} · windows {len(windows)}", file=sys.stderr)
    saved_total = 0; t0 = time.time()
    for n, i in enumerate(windows, 1):
        tail = spoken[max(0, i - a.window + 1): i + 1]
        try:
            j = T.judge(tail, [], [])
        except Exception as e:
            print(f"[{n}] judge error {e}", file=sys.stderr); continue
        obs = j.get("observe") or []
        if a.dry:
            for o in obs:
                print(f"[{n}] {o.get('kind')} {o.get('conf')} {str(o.get('text',''))[:140]}")
        else:
            saved = T.record_observations(j)
            saved_total += len(saved)
            for s_ in saved:
                print(f"[{n}] 저장: {s_}")
        T.log("backfill", src=a.src.split("/")[-1], window=n, at_turn=spoken[i]["ts"], observed=len(obs))
    print(f"done · windows {len(windows)} · saved {saved_total} · {time.time()-t0:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
