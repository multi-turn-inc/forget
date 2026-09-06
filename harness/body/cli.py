"""터미널 채널 + 단발 실행.
  python -m harness.body --brain astra                 # 대화(REPL). 바쁠 때 치면 steer.
  python -m harness.body --brain spark -p "…"          # 한 턴만 돌리고 종료
  python -m harness.body --resume <session_id>         # 세션 이어 살기
  python -m harness.body --transplant <claude.jsonl>   # Claude 세션 꼬리를 우리 세션으로
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from .loop import BODY_DIR, Body


def _printer(ev: dict) -> None:
    t = ev.get("type")
    if t == "text":
        print(ev["text"], flush=True)
    elif t == "tool_start":
        a = ev.get("args") or {}
        head = a.get("command") or a.get("path") or a.get("query") or a.get("pattern") or ""
        print(f"  › {ev['name']} {str(head)[:90]}", file=sys.stderr, flush=True)
    elif t == "tool_end":
        print(f"    ↳ {ev.get('result', '')[:160].replace(chr(10), ' ')}", file=sys.stderr, flush=True)
    elif t == "steer":
        print(f"  (끼어듦 반영: {ev['text'][:60]})", file=sys.stderr, flush=True)
    elif t == "error":
        print(f"  ! {ev['text']}", file=sys.stderr, flush=True)


def transplant_claude(src: str) -> str:
    """Claude 전사 꼬리(마지막 압축 이후)를 우리 세션으로. 말만 옮기고 도구 결과는 버린다."""
    rows = [json.loads(l) for l in Path(src).read_text().splitlines() if l.strip()]
    # 마지막 압축 요약 이후만
    idx = max((i for i, r in enumerate(rows) if r.get("type") == "user" and r.get("isCompactSummary")), default=-1)
    tail = rows[idx:] if idx >= 0 else rows
    sid = "transplant-" + Path(src).stem[:8] + "-" + time.strftime("%H%M%S")
    out = BODY_DIR / f"{sid}.jsonl"
    BODY_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w") as f:
        for r in tail:
            if r.get("type") not in ("user", "assistant") or r.get("isSidechain"):
                continue
            m = r.get("message") or {}
            c = m.get("content")
            if r["type"] == "user":
                if isinstance(c, str):
                    f.write(json.dumps({"type": "user", "timestamp": r.get("timestamp"), "sessionId": sid, "message": {"role": "user", "content": c[:6000]}}, ensure_ascii=False) + "\n")
                    n += 1
                elif isinstance(c, list) and c and c[0].get("type") == "text":
                    t = "".join(p.get("text", "") for p in c if p.get("type") == "text")
                    if t.strip() and not t.startswith("<") and not t.startswith("[Request"):
                        f.write(json.dumps({"type": "user", "timestamp": r.get("timestamp"), "sessionId": sid, "message": {"role": "user", "content": t[:6000]}}, ensure_ascii=False) + "\n")
                        n += 1
            else:
                t = "".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text") if isinstance(c, list) else ""
                if t.strip():
                    f.write(json.dumps({"type": "assistant", "timestamp": r.get("timestamp"), "sessionId": sid,
                                        "message": {"role": "assistant", "content": [{"type": "text", "text": t[:6000]}]}}, ensure_ascii=False) + "\n")
                    n += 1
    print(f"이식: {n} 메시지 → {out}", file=sys.stderr)
    return sid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brain", default="astra")
    ap.add_argument("--resume")
    ap.add_argument("--transplant")
    ap.add_argument("-p", "--prompt")
    a = ap.parse_args()
    sid = a.resume
    if a.transplant:
        sid = transplant_claude(a.transplant)
    body = Body(brain_name=a.brain, session_id=sid, channel="terminal", on_event=_printer)
    print(f"몸 · 뇌 {a.brain} · 세션 {body.session_id}", file=sys.stderr)
    if a.prompt:
        body.run_turn(a.prompt)
        return 0
    # REPL: 입력 스레드 — 바쁠 때 치면 steer로 들어간다
    def reader():
        for line in sys.stdin:
            t = line.strip()
            if t:
                body.say(t)
    threading.Thread(target=reader, daemon=True).start()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
