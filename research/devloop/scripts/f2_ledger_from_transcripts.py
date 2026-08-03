#!/usr/bin/env python3
"""F2 재발 대장을 1차 증거에서 재구성한다 (사이클 42).

기존 F2 대장은 두 자기보고 장부(frictions.md 사례란, metrics recall_note)에만
근거했다. 이 스크립트는 그 대신 **devloop 사이클 세션의 트랜스크립트 자체**를 읽어
UserPromptSubmit 훅(forget_turnrecall.py)이 실제로 무엇을 주입했는지 뽑는다.
루프가 게임할 수 없는 채널이다 — 훅 출력은 사이클이 자기 지표를 쓰기 전에
하네스가 이미 기록해 둔 것이다.

사이클 번호 앵커: 트랜스크립트의 [birth, mtime] 창 안에 들어오는 `loop(cycle N)`
커밋 시각. 본문의 사이클 번호 언급으로 추정하지 않는다(과거·미래 사이클을 함께
언급하므로 최빈값이 틀린다 — 사이클 42가 실제로 겪은 오분류).

재현성(사이클 27 마찰 준수): 코퍼스 선정법이 코드로 고정되어 있다 —
CYCLE_PROMPT를 첫 200KB 안에 포함하는 트랜스크립트 전부.

읽기 전용. /tmp 밖에 아무것도 쓰지 않는다.

    .venv/bin/python research/devloop/scripts/f2_ledger_from_transcripts.py
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
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CYCLE_PROMPT = "devloop 사이클을 정확히 한 바퀴 실행하라"
RECALL_HDR = "[forget 회상"
CONFLICT_HDR = "[forget 충돌지대"

# 오프토픽/온토픽 라벨. 원문을 함께 출력하므로 라벨은 요약일 뿐 판정 근거가 아니다.
LABELS = [
    (r"pash @pashmerepat", "pash트윗", "OFF"),
    (r"heartbeat|박자 2026|stance:", "heartbeat", "OFF"),
    (r"Quant|Alpaca|토스증권|DeepInfra", "Quant", "OFF"),
    (r"ADHD", "정훈ADHD", "OFF"),
    (r"MemLoRA|arXiv|LongMemEval|리더보드|분기 4회", "연구조사", "OFF"),
    (r"오버엣지|YC", "YC", "OFF"),
    (r"PyPI|0\.3\.3", "릴리스", "OFF"),
    (r"Argo|경쟁 지형", "경쟁조사", "OFF"),
    (r"실행 순서 확정", "실행순서", "OFF"),
    (r"\[devloop|필드노트 #", "devloop기억", "ON"),
    (r"정훈의 설계 철학|정훈 설계 발안", "정훈설계", "ON~"),
]


def cycle_anchors() -> list[tuple[datetime.datetime, int]]:
    out = subprocess.run(
        ["git", "-C", REPO, "log", "--date=format-local:%Y-%m-%d %H:%M:%S", "--pretty=format:%ad|%s"],
        capture_output=True, text=True,
    ).stdout
    anchors = []
    for line in out.splitlines():
        ad, _, subj = line.partition("|")
        m = re.match(r"loop\(cycle (\d+)", subj)
        if m:
            anchors.append((datetime.datetime.strptime(ad, "%Y-%m-%d %H:%M:%S"), int(m.group(1))))
    return anchors


def walk_strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from walk_strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk_strings(v)


def blocks_in(text: str):
    """훅 블록 = 헤더 줄 + 뒤따르는 '- (' 불릿들."""
    lines, out = text.splitlines(), []
    for i, ln in enumerate(lines):
        kind = "recall" if ln.startswith(RECALL_HDR) else ("conflict" if ln.startswith(CONFLICT_HDR) else None)
        if not kind:
            continue
        items = []
        for ln2 in lines[i + 1:]:
            if ln2.startswith("- ("):
                items.append(ln2.strip())
            else:
                break
        if items:
            out.append((kind, tuple(items)))
    return out


def label(item: str) -> str:
    t = re.sub(r"^- \((green|yellow|red|red/구본|현재)\)\s*", "", item)
    for pat, name, side in LABELS:
        if re.search(pat, t):
            return f"{name}[{side}]"
    return t[:26].replace("\n", " ") + "[?]"


def main() -> None:
    anchors = cycle_anchors()
    rows = []
    for f in glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")):
        with open(f, errors="replace") as fh:
            if CYCLE_PROMPT not in fh.read(200_000):
                continue
        st = os.stat(f)
        start = datetime.datetime.fromtimestamp(st.st_birthtime)
        end = datetime.datetime.fromtimestamp(st.st_mtime)
        cycles = sorted({c for t, c in anchors if start <= t <= end})
        blocks = {}
        with open(f, errors="replace") as fh:
            for line in fh:
                if RECALL_HDR not in line and CONFLICT_HDR not in line:
                    continue
                # 에이전트가 훅 소스나 자기 트랜스크립트를 '읽은' 것은 훅 주입이 아니다
                if '"tool_result"' in line or '"toolUseResult"' in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                for s in walk_strings(rec):
                    for kind, items in blocks_in(s):
                        blocks[(kind, items)] = True
        rows.append({"file": os.path.basename(f)[:8], "start": start, "end": end,
                     "cycles": cycles, "blocks": [{"kind": k, "items": list(i)} for k, i in blocks]})

    rows.sort(key=lambda r: r["start"])
    print(f"{'cycle':>6} {'when':11} {'n':>2}  주입된 항목 (ON=주제 관련, OFF=무관)")
    print("-" * 96)
    seq = []
    for r in rows:
        # 대화형 세션이 여러 사이클 커밋을 걸치면 사이클 행이 아니다 — 제외하고 표시
        if len(r["cycles"]) > 1:
            print(f"{'(대화형)':>6} {r['start']:%m-%d %H:%M} "
                  f"{sum(len(b['items']) for b in r['blocks']):>2}  "
                  f"창이 사이클 {r['cycles'][0]}~{r['cycles'][-1]}를 걸침 — 사이클 행 아님, 대장에서 제외")
            continue
        cyc = str(r["cycles"][0]) if r["cycles"] else "—"
        items = [i for b in r["blocks"] if b["kind"] == "recall" for i in b["items"]]
        confl = [i for b in r["blocks"] if b["kind"] == "conflict" for i in b["items"]]
        labs = [label(i) for i in items]
        print(f"{cyc:>6} {r['start']:%m-%d %H:%M} {len(items):>2}  "
              f"{', '.join(labs) if labs else '(훅 침묵 — 주입 0)'}"
              + (f"   +충돌×{len(confl)}" if confl else ""))
        if cyc.isdigit():
            seq.append({"cycle": int(cyc), "fired": bool(r["blocks"]), "n": len(items),
                        "off": sum(1 for x in labs if "[OFF]" in x),
                        "on": sum(1 for x in labs if "[ON" in x),
                        "pash": any("pash" in x for x in labs),
                        "heartbeat": any("heartbeat" in x for x in labs)})

    seq.sort(key=lambda s: s["cycle"])
    fired = [s for s in seq if s["fired"]]
    print("\n=== 요약 ===")
    print(f"커밋 앵커가 붙은 사이클: {len(seq)} ({seq[0]['cycle']}~{seq[-1]['cycle']})")
    print(f"훅 발화: {len(fired)}/{len(seq)}   침묵: {[s['cycle'] for s in seq if not s['fired']]}")
    print(f"오프토픽 ≥1건 주입: {sum(1 for s in fired if s['off'])}/{len(fired)} (발화 사이클 기준)")
    print(f"pash 주입 사이클: {[s['cycle'] for s in seq if s['pash']]}")
    print(f"heartbeat(task_state) 주입 사이클: {[s['cycle'] for s in seq if s['heartbeat']]}")
    print("\n사이클별 오프토픽 비중 (off/n):")
    print("  " + "  ".join(f"c{s['cycle']}:{s['off']}/{s['n']}" for s in fired))


if __name__ == "__main__":
    main()
