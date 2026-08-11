#!/usr/bin/env python3
"""audit-100 R2 판별 실행: c3~c20 시대의 restore_turns를 현행 정의로 재계수한다 (사이클 106).

질문 (amendment-105 §4): rt=1 시대는
  (i) 실제로 1턴 복원이었는가 (실퇴행 — 그렇다면 무엇이 3턴을 강제하게 됐는지 규명 후속)
  (ii) 계상 정의가 달랐는가 (자[尺] 교체 — 그렇다면 정의 경계 주석)

방법:
- 현행 정의: restore_turns = 세션 시작→첫 유효 행동까지의 턴 수. 턴 = 어시스턴트
  API 응답 1개(트랜스크립트에서 message.id로 묶임). 첫 유효 행동 = 복원 집합
  (헌장·지시서·CLAUDE.md·metrics·step0 스크립트 Read, ToolSearch, get_task_state/
  prepare_context_autopilot, git status/log, metrics tail류, c48 스크립트 실행,
  MCP curl 폴백) **밖의** 첫 도구 호출이 포함된 턴의 순번.
- 사이클 앵커: f2_ledger_from_transcripts.py 방식 재사용 — 트랜스크립트 [birth, mtime]
  창에 들어오는 `loop(cycle N)` 커밋. 창이 복수 사이클을 걸치면(대화형) 제외.
- 계기 교정(원칙 1 대조군): 같은 계수기를 현행 시대(c95~c105)에 먼저 돌려 원장의
  rt=3과 일치하는지 확인한 뒤에만 구시대 수를 읽는다.

읽기 전용. 아무것도 쓰지 않는다.

    .venv/bin/python research/devloop/scripts/c106_r2_rt_recount.py
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import subprocess

TRANSCRIPTS = os.path.expanduser(
    "~/.claude/projects/-Users-junghunkim-orca-workspaces-forget----------------"
)
REPO = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CYCLE_PROMPT = "devloop 사이클을 정확히 한 바퀴 실행하라"

OLD_ERA = (3, 20)      # 판별 대상 (rt=1 시대, amendment-105 §4)
CTRL_ERA = (95, 105)   # 계기 교정 대조군 (원장 rt=3 상수 시대)

RESTORE_TOOLS = {
    "ToolSearch",
    "mcp__forget__get_task_state",
    "mcp__forget__prepare_context_autopilot",
}
RESTORE_READ_SUFFIX = (
    "LOOP.md", "cycle-prompt.md", "CLAUDE.md",
    "metrics.jsonl", "c48_step0_check.py",
)
RESTORE_BASH = re.compile(
    r"git (-C \S+ )?status|git (-C \S+ )?log|metrics\.jsonl|c48_step0_check"
    r"|localhost:8000|forget-server status"
)


def cycle_anchors() -> list[tuple[datetime.datetime, int]]:
    out = subprocess.run(
        ["git", "-C", REPO, "log",
         "--date=format-local:%Y-%m-%d %H:%M:%S", "--pretty=format:%ad|%s"],
        capture_output=True, text=True,
    ).stdout
    anchors = []
    for line in out.splitlines():
        ad, _, subj = line.partition("|")
        m = re.match(r"loop\(cycle (\d+)", subj)
        if m:
            anchors.append(
                (datetime.datetime.strptime(ad, "%Y-%m-%d %H:%M:%S"), int(m.group(1))))
    return anchors


def ledger_rt() -> dict[int, tuple]:
    path = os.path.join(REPO, "research/devloop/metrics.jsonl")
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            c = r.get("cycle")
            if isinstance(c, int):
                out[c] = (r.get("restore_turns"), r.get("restore_grade"))
    return out


def classify(name: str, inp: dict) -> str:
    """도구 호출 1건을 restore | valid 로 분류한다."""
    if name in RESTORE_TOOLS:
        return "restore"
    if name == "Read":
        fp = str(inp.get("file_path", ""))
        if fp.endswith(RESTORE_READ_SUFFIX):
            return "restore"
        return "valid"
    if name == "Bash":
        cmd = str(inp.get("command", ""))
        if RESTORE_BASH.search(cmd):
            return "restore"
        return "valid"
    # Edit/Write/Grep/Glob/pytest/add_memory/search_memories/기타 MCP = 작업
    return "valid"


def recount(path: str):
    """트랜스크립트 1건: (rt_current, 첫 유효 행동 설명, 턴 요약 리스트)."""
    turn_order: list[str] = []          # message id, 첫 등장 순
    turn_calls: dict[str, list] = {}    # mid -> [(name, verdict, brief)]
    with open(path, errors="replace") as fh:
        for line in fh:
            if '"assistant"' not in line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("type") != "assistant" or r.get("isSidechain"):
                continue
            msg = r.get("message") or {}
            mid = msg.get("id")
            if not mid:
                continue
            if mid not in turn_calls:
                turn_calls[mid] = []
                turn_order.append(mid)
            for b in msg.get("content") or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                name = b.get("name", "?")
                inp = b.get("input") or {}
                verdict = classify(name, inp)
                brief = name
                if name == "Read":
                    brief += ":" + os.path.basename(str(inp.get("file_path", "")))[:40]
                elif name == "Bash":
                    brief += ":" + str(inp.get("command", ""))[:60].replace("\n", " ")
                turn_calls[mid].append((name, verdict, brief))

    turns = []
    rt, first = None, None
    for i, mid in enumerate(turn_order, start=1):
        calls = turn_calls[mid]
        kinds = {v for _, v, _ in calls}
        turns.append((i, [c[2] for c in calls], kinds))
        if rt is None and "valid" in kinds:
            rt = i
            first = next(br for _, v, br in calls if v == "valid")
    return rt, first, turns


def main() -> None:
    anchors = cycle_anchors()
    ledger = ledger_rt()
    rows = []
    for f in glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")):
        with open(f, errors="replace") as fh:
            if CYCLE_PROMPT not in fh.read(200_000):
                continue
        st = os.stat(f)
        start = datetime.datetime.fromtimestamp(st.st_birthtime)
        end = datetime.datetime.fromtimestamp(st.st_mtime)
        cycles = sorted({c for t, c in anchors if start <= t <= end})
        rows.append({"file": f, "start": start, "cycles": cycles})
    rows.sort(key=lambda r: r["start"])

    for era_name, lo, hi in (("대조군(현행 시대) — 계기 교정", *CTRL_ERA),
                             ("판별 대상(구시대)", *OLD_ERA)):
        print(f"\n=== {era_name}: c{lo}~c{hi} ===")
        print(f"{'cycle':>6} {'when':11} {'rt재계수':>7} {'원장rt':>6} {'원장grade':>9}  첫 유효 행동")
        print("-" * 100)
        agree = tot = 0
        recounts = []
        for r in rows:
            cyc = r["cycles"]
            if len(cyc) != 1 or not (lo <= cyc[0] <= hi):
                continue
            rt, first, turns = recount(r["file"])
            lrt, lgrade = ledger.get(cyc[0], (None, None))
            recounts.append((cyc[0], rt, lrt))
            tot += 1
            if rt == lrt:
                agree += 1
            print(f"{cyc[0]:>6} {r['start']:%m-%d %H:%M} {str(rt):>7} {str(lrt):>6} "
                  f"{str(lgrade)[:9]:>9}  {str(first)[:55]}")
            for i, briefs, kinds in turns[: (rt or 0)]:
                tag = "복원" if "valid" not in kinds else "◀ 첫 유효"
                print(f"{'':6} 턴{i} [{tag}] {'; '.join(briefs)[:88]}")
        vals = [x[1] for x in recounts if x[1] is not None]
        if vals:
            print(f"\n  표본 {tot}건 · 재계수 rt 분포: "
                  f"{sorted(set(vals))} (중앙값 {sorted(vals)[len(vals)//2]}) · "
                  f"원장과 일치 {agree}/{tot}")

    print("\n=== 전 구간 스윕 (의미론 전이 경계 특정 — 압축 표) ===")
    print(f"{'cycle':>6} {'when':11} {'재계수':>5} {'원장':>4} {'일치':>4}  비고")
    for r in rows:
        cyc = r["cycles"]
        if len(cyc) != 1 or not (3 <= cyc[0] <= 105):
            continue
        rt, _, _ = recount(r["file"])
        lrt, _ = ledger.get(cyc[0], (None, None))
        mode = "감사" if cyc[0] % 10 == 0 else ("회고" if cyc[0] % 5 == 0 else "")
        print(f"{cyc[0]:>6} {r['start']:%m-%d %H:%M} {str(rt):>5} {str(lrt):>4} "
              f"{'○' if rt == lrt else '×':>4}  {mode}")

    print("\n=== 원장 rt 시계열 (전이 경계 탐색) ===")
    seq = [(c, v[0]) for c, v in sorted(ledger.items()) if v[0] is not None]
    runs = []
    for c, v in seq:
        if runs and runs[-1][2] == v:
            runs[-1][1] = c
        else:
            runs.append([c, c, v])
    print("  " + " | ".join(f"c{a}~c{b}: rt={v}" if a != b else f"c{a}: rt={v}"
                            for a, b, v in runs))


if __name__ == "__main__":
    main()
