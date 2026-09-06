#!/usr/bin/env python3
"""UserPromptSubmit: 사이드카가 유지하는 작업 블록의 **새 줄만** 주입한다 (2026-09-07).
사이드카가 없거나 블록이 비면 침묵. 파일만 읽으므로 1ms. fail-open."""
from __future__ import annotations
import json, os, sys
from pathlib import Path

D = Path(os.getenv("FORGET_ATTENTION_DIR") or Path.home() / ".forget" / "attention")

def main() -> int:
    try:
        st = json.loads((D / "state.json").read_text())
    except Exception:
        return 0
    block = st.get("block") or []
    inj_path = D / "injected.json"                      # 사이드카의 state.json과 분리 — 덮어쓰기 경합 방지
    try:
        injected = set(json.loads(inj_path.read_text()))
    except Exception:
        injected = set()
    fresh = [b for b in block if b.get("id") not in injected]
    if not fresh:
        return 0
    lines = ["[forget 주의 블록 — 사이드카가 대화를 보며 고른 것. 등불: green 행동 근거 / yellow 확인 / red 참고. 채택은 네 판단]"]
    for b in fresh:
        why = f" — {b['why']}" if b.get("why") else ""
        lines.append(f"- ({b.get('light', 'yellow')}) {b['text'][:240]}{why}")
    print("\n".join(lines))
    try:
        inj_path.write_text(json.dumps(sorted(injected | {b["id"] for b in fresh})))
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
