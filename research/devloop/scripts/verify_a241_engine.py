#!/usr/bin/env python3
"""A-241.1 수용 기준 ① 검증 — B층 요약 엔진이 LLM으로 복귀했는지 확인.

정본 판정: ~/.forget/bstate/forget.json 의 최신 캡처 engine 필드가
'structural-fallback'이 아니면 통과(LLM 복귀). gate-queue.md A-241.1(서열 30)
"기동 승인" 처분 후 이 스크립트로 재검증한다. 코드 변경 없음 — 읽기 전용 검증.
"""
import json
import os
import sys

BSTATE_PATH = os.path.expanduser(
    os.environ.get("FORGET_BSTATE_PATH", "~/.forget/bstate/forget.json")
)


def check(path: str = BSTATE_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    engine = data.get("engine", "?")
    return {
        "path": path,
        "captured_at": data.get("captured_at"),
        "engine": engine,
        "passed": engine != "structural-fallback",
    }


if __name__ == "__main__":
    result = check()
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["passed"] else 1)
