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
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from forget.attention import clean_text, LIGHT_GLYPH   # 설치본 훅은 저장소 밖일 수 있다 → 폴백
    except Exception:
        LIGHT_GLYPH = {"green": "●", "yellow": "◐", "red": "○"}
        clean_text = lambda t, limit=160: str(t).replace("\n", " ")[:limit]
    lines = [f"[기억 블록 — 새 줄 {len(fresh)} (전체 {len(block)}). ● 근거 ◐ 확인 ○ 참고. 채택은 네 판단]"]
    for b in fresh:
        g = LIGHT_GLYPH.get(str(b.get("light", "yellow")), "◐")
        lines.append(f"{g} {clean_text(b['text'])}")
    print("\n".join(lines))
    try:
        inj_path.write_text(json.dumps(sorted(injected | {b["id"] for b in fresh})))
    except Exception:
        pass
    return 0

if __name__ == "__main__":
    sys.exit(main())
