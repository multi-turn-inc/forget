#!/usr/bin/env python3
"""forget_toolrecall — 진행-중 회상 v0 (PostToolUse, Bash 전용).

설계 정본: research/proxy-native-redesign.md §3.6 지평 1. 트리거는 사용자
프롬프트가 아니라 진행 중인 사고의 내용물 — 도구가 **실패**했을 때 그 에러
서명으로 러닝북을 소환해 결과에 동승시킨다. 원조 사례: 2026-08-12 새벽 pkill
자기-매칭 침묵 자살 3연속 — 첫 실패 때 러닝북이 도착했다면 한 번으로 끝났다.

v0 규율:
- Bash 결과에만 반응 (서명 전부 Bash-급 함정 + Read/Grep가 러닝북 파일을
  읽을 때의 자기-매칭 차단 — pkill 러닝북이 가르친 바로 그 함정의 훅판).
- 정적 패턴만, LLM·서버 호출 없음 (ms급 — 지연 예산 논쟁 원천 차단).
- 실패 판정이 애매한 페이로드는 발동하지 않되 **형상을 원장에 남긴다**
  (계기-우선 — 내일 실측으로 보정). 원장엔 내용 무기록, 형상 메타만.
- 세션당 같은 러닝북 1회. 텍스트 4000자 초과는 실패 메시지가 아니라
  산출물로 간주하고 침묵.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

RUNBOOKS = Path(os.environ.get("FORGET_RUNBOOKS", str(Path.home() / ".forget/runbooks.md")))
STATE_DIR = Path.home() / ".forget/hooks/state"
LEDGER = STATE_DIR / "toolrecall_ledger.jsonl"
MAX_BODY_CHARS = 700
MAX_ERR_CHARS = 4000

SIGNATURES: list[tuple[str, str]] = [
    (r"contains multiple operations|requires approval", "복합 Bash 명령 승인 회피"),
    (r"brace with quote character", "heredoc·따옴표 중괄호 차단"),
    (r"rm in '.*내-프롬프트를", "워크트리 한글 경로 rm 차단"),
    (r"timed out after|output discarded", "타임아웃 계층 산수"),
]


def _note(kind: str, **fields) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%F %T"), "kind": kind, **fields}
        with LEDGER.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _response_text(response) -> tuple[str, bool | None]:
    """(텍스트, 실패 여부) — 실패를 모르면 None."""
    if isinstance(response, str):
        return response, None
    if isinstance(response, dict):
        err = response.get("is_error", response.get("isError"))
        parts = [str(response.get(k) or "") for k in ("error", "stderr", "stdout", "content", "message")]
        text = "\n".join(p for p in parts if p) or json.dumps(response, ensure_ascii=False)
        if err is None and response.get("stderr"):
            err = None  # stderr 존재만으로 실패 단정 금지 (경고 흔함)
        return text, bool(err) if err is not None else None
    return "", None


def _load_runbook(title: str) -> str | None:
    try:
        text = RUNBOOKS.read_text(encoding="utf-8")
    except Exception:
        return None
    match = re.search(rf"## runbook: {re.escape(title)}.*?(?=\n## |\Z)", text, re.S)
    return match.group(0)[:MAX_BODY_CHARS] if match else None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if str(payload.get("tool_name") or "") != "Bash":
        return
    text, failed = _response_text(payload.get("tool_response"))
    if not text or len(text) > MAX_ERR_CHARS:
        return
    hit = next((title for pattern, title in SIGNATURES if re.search(pattern, text, re.I)), None)
    if hit is None:
        return
    if failed is False:
        _note("sig_in_success", sig=hit, chars=len(text))
        return
    if failed is None:
        # 형상 미상 — 발동 대신 관측 (내일 이 원장으로 실패 판정을 보정한다)
        _note("sig_shape_unknown", sig=hit, chars=len(text),
              keys=sorted(payload.get("tool_response", {}).keys()) if isinstance(payload.get("tool_response"), dict) else "str")
        return

    session_id = str(payload.get("session_id") or "nosession")
    seen_path = STATE_DIR / f"toolrecall_{session_id}.json"
    try:
        seen = set(json.loads(seen_path.read_text()))
    except Exception:
        seen = set()
    if hit in seen:
        return
    body = _load_runbook(hit)
    if not body:
        _note("runbook_missing", sig=hit)
        return
    seen.add(hit)
    try:
        seen_path.write_text(json.dumps(sorted(seen), ensure_ascii=False))
    except Exception:
        pass
    _note("injected", sig=hit)
    print(f"[forget 러닝북 — 이 실패 서명엔 검증된 절차가 있음]\n{body}")


if __name__ == "__main__":
    main()
