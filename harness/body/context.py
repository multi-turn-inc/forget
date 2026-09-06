"""문맥 조립 — 매 호출마다 다시 만든다. 정체성 + 정훈의 모델 + 기억 블록 + 자원 + 최근 턴.
덧붙이기가 아니라 교체다. 틀린 줄은 다음 호출에 사라진다."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

REPO = Path(os.getenv("FORGET_REPO", Path(__file__).resolve().parents[2]))
ATTN = Path(os.getenv("FORGET_ATTENTION_DIR", Path.home() / ".forget" / "attention"))
IDENTITY = REPO / ".pi" / "IDENTITY.md"
KEEP_TURNS = int(os.getenv("BODY_KEEP_TURNS", "60"))          # 최근 메시지 수
TOOL_ECHO = int(os.getenv("BODY_TOOL_ECHO", "4000"))          # 과거 도구 결과는 이만큼만 남긴다


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except Exception:
        return ""


def system_prompt(brain_name: str, channel: str) -> str:
    parts = []
    ident = _read(IDENTITY)
    parts.append(ident or "너는 정훈의 에이전트다. 반말. 짧게. 지어내지 않는다.")
    parts.append(f"## 지금\n- {datetime.now():%Y-%m-%d %H:%M} KST · 뇌: {brain_name} · 채널: {channel} · 작업 트리: {REPO}\n"
                 "- 이 하네스는 우리 것(몸). 도구는 함수다: bash·read·write·edit·glob·memory_search·memory_add·self_note·task_state.\n"
                 "- 긴 일은 끝까지 한다. 중간 보고 대신 task_state에 남긴다. 정훈에게 묻지 않는다. 파괴적 조작(남의 데이터 삭제·실DB·외부 발신·결제)만 예외.")
    schema = _read(ATTN / "schema.md")
    if schema:
        parts.append("## 정훈의 모델 (밤마다 다시 씀 — 예측의 기준. 틀리면 짚고 supersede)\n" + schema[:9000])
    block = _read(ATTN / "block.md")
    if block:
        parts.append("## 기억 블록 (사이드카가 대화를 보며 고른 것, 매 호출 교체)\n" + block)
    return "\n\n".join(parts)


def compact_history(msgs: list[dict]) -> list[dict]:
    """최근 KEEP_TURNS개만, 오래된 도구 결과는 잘라서. 나머지는 세션 파일과 원장에 산다."""
    tail = msgs[-KEEP_TURNS:]
    # 첫 항목이 tool이면 그 앞의 assistant(tool_calls)까지 포함되도록 앞을 자른다
    while tail and tail[0].get("role") == "tool":
        tail = tail[1:]
    out = []
    for i, m in enumerate(tail):
        m = dict(m)
        if m.get("role") == "tool" and i < len(tail) - 6 and isinstance(m.get("content"), str) and len(m["content"]) > TOOL_ECHO:
            m["content"] = m["content"][:TOOL_ECHO] + "\n…(잘림)"
        out.append(m)
    return out


def brief_summary(msgs: list[dict], limit: int = 1200) -> str:
    """세션 요약 한 덩이(문맥이 잘릴 때 앞에 둔다) — 마지막 사용자 말 셋과 마지막 답."""
    users = [m["content"] for m in msgs if m.get("role") == "user" and isinstance(m.get("content"), str)][-3:]
    last_a = [m.get("content") for m in msgs if m.get("role") == "assistant" and m.get("content")][-1:]
    s = "이전 대화 요지 — 정훈: " + " / ".join(u[:200] for u in users) + (" — 나: " + last_a[0][:300] if last_a else "")
    return re.sub(r"\s+", " ", s)[:limit]
