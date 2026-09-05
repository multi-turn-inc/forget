#!/usr/bin/env python3
"""c123 — 무번호 관측의 처분 상태 판별 계기 (관측 69 수용 기준 ①).

왜. 파트 F 파서(c48_step0_check.parse_observations)의 OBS_HEADER는 번호를
필수 그룹으로 요구하므로 `## 미분류 관측 — 제목 (사이클 C, … 회부)` 계열은
한 번도 계상된 적이 없다(관측 69). 이 계기는 그 무번호 회부 관측을 열거하고,
각 절에서 **처분 신호 행만** 추출해 상수 크기 다이제스트로 만든다 —
317KB 대장 통독 없이 사람(=이 사이클의 손)이 절별로 존속/이탈을 판정하기 위한 재료.

이 계기는 판정하지 않는다. 판정은 손이 하고 결과는 c123 판정표에 적는다 —
파서 어휘를 무번호에 그대로 적용하면 관측 63(부정문 위양성)을 상속하기 때문이다.
"""
from __future__ import annotations

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
FRICTIONS = os.path.join(REPO, "research", "devloop", "frictions.md")

H2 = re.compile(r"^##\s+(.*)$")
NUMBERED = re.compile(r"^##\s+(?:미분류\s+)?관측\s+\d+")
UNNUMBERED = re.compile(r"^##\s+(?:미분류\s+)?관측\s*(?:—|-|\()")
# 절 안에서 처분 성격을 띨 수 있는 행의 머리말 (판정은 하지 않고 노출만 한다)
SIGNAL_HEAD = re.compile(
    r"^\*\*(처분|판정|해소|종결|승격|수리|반증|후속|귀속|유형 판정|이관|재발)")
SIGNAL_WORD = re.compile(r"(종결|승격|해소|수리 완료|회부 상태를 벗|F\d 로 |F\d로 |유형 귀속)")


def sections(text: str) -> list[tuple[str, int, list[str]]]:
    lines = text.splitlines()
    out: list[tuple[str, int, list[str]]] = []
    cur: tuple[str, int] | None = None
    body: list[str] = []
    for idx, line in enumerate(lines, 1):
        if H2.match(line):
            if cur is not None:
                out.append((cur[0], cur[1], body))
            cur, body = (line, idx), []
            continue
        if cur is not None:
            body.append(line)
    if cur is not None:
        out.append((cur[0], cur[1], body))
    return out


def tagged(head: str) -> bool:
    tail = head[head.rfind("(사이클"):] if "(사이클" in head else head
    return ("회부" in tail) or ("후보" in tail)


def main() -> int:
    with open(FRICTIONS, encoding="utf-8") as fh:
        text = fh.read()
    secs = sections(text)
    obs_secs = [s for s in secs if "관측" in s[0]]
    num = [s for s in obs_secs if NUMBERED.match(s[0])]
    unnum = [s for s in obs_secs if not NUMBERED.match(s[0])]

    print(f"[분모] 관측 헤딩 {len(obs_secs)} = 번호 {len(num)} + 무번호 {len(unnum)}")
    print(f"       무번호 중 회부/후보 태그 = {sum(1 for s in unnum if tagged(s[0]))}")
    print()
    tail_mode = "--tail" in sys.argv
    for head, lineno, body in unnum:
        mark = "회부" if tagged(head) else "무태그"
        if tail_mode and mark != "회부":
            continue
        print(f"--- L{lineno} [{mark}] {head[3:][:150]}")
        if tail_mode:
            # 절의 마지막 문단 = 그 관측에 대해 대장이 마지막으로 한 말.
            ne = [ln for ln in body if ln.strip()]
            for ln in ne[-7:]:
                print(f"    ] {ln.strip()[:190]}")
        else:
            hits = [ln for ln in body if SIGNAL_HEAD.match(ln) or SIGNAL_WORD.search(ln)]
            if not hits:
                print("    (처분 신호 행 없음)")
            for ln in hits[:6]:
                print(f"    | {ln.strip()[:180]}")
        print(f"    (절 길이 {len(body)}행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
