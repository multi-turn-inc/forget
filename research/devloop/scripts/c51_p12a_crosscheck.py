#!/usr/bin/env python3
"""P12 (a)의 c46~c50 "지시서 밖 규약 집행" 계수를 1차 증거로 교차검증한다 (사이클 51, audit-50 R1).

자기보고(metrics work란의 "6건")가 아니라 **하네스가 남긴 tool_use 행동 기록**만 센다.
사이클이 자기 지표를 쓰기 전에 트랜스크립트에 이미 있고 사후 수정이 불가능한 채널이다
(사이클 42 F2 대장과 동일한 채널 선택 근거).

검증 가능 범위의 정직한 한계: 자기보고 6건 중 이 채널로 잡히는 것은 **도구 호출로
발현되는 규약**뿐이다. 채점 관행(dedup 계상·엄격 miss 규칙)과 산문 규율(★★ 자기규율)은
도구 흔적을 남기지 않으므로 이 스크립트의 판정 대상이 아니다 — 미검증으로 남긴다.

니들 (전부 cycle-prompt.md에 없는 규약, 판정은 P12 (a) "최소 1건 집행"):
  T1 2채널 조회        get_task_state 입력에 'devloop-self'
  T2 쓰기 순서         record_task_state가 devloop-self를 devloop보다 먼저
  T3 영토 검사 도구    -newer 즉석 구현(c46~48) 또는 c48_step0_check.py 실행(c48+)
  T4 계측기 재사용     c46_capsule_reach.py / c48_step0_check.py 실행
  T5 ToolSearch 조기   최초 3 tool_use 안에 Read와 ToolSearch 동시 (규약 ④의 약한
                       프록시 — 턴 경계는 tool_use 나열로 판별 불가, "묶기" 검증 아님)
보조 (규약 ③ tail 금지의 준수/위반 대조 — P12 (b) 기전 이분의 교차검증):
  V3 tail 사용         Bash에 metrics.jsonl 대상 tail 호출

사이클 앵커: f2_ledger_from_transcripts.py와 동일 — [birth, mtime] 창 안의
`loop(cycle N)` 커밋 시각. 창이 복수 사이클을 걸치면 행에서 제외.

읽기 전용. 아무것도 쓰지 않는다.

    .venv/bin/python research/devloop/scripts/c51_p12a_crosscheck.py
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
TARGET_CYCLES = range(46, 51)


def cycle_anchors() -> list[tuple[datetime.datetime, int]]:
    out = subprocess.run(
        ["git", "-C", REPO, "log", "--date=format-local:%Y-%m-%d %H:%M:%S",
         "--pretty=format:%ad|%s"],
        capture_output=True, text=True,
    ).stdout
    anchors = []
    for line in out.splitlines():
        ad, _, subj = line.partition("|")
        m = re.match(r"loop\(cycle (\d+)", subj)
        if m:
            anchors.append((datetime.datetime.strptime(ad, "%Y-%m-%d %H:%M:%S"), int(m.group(1))))
    return anchors


def tool_uses(path: str):
    """(순번, 도구명, 입력 dict, 입력 JSON 문자열) — 트랜스크립트 라인 순서가 곧 시간 순서."""
    idx = 0
    with open(path, errors="replace") as fh:
        for line in fh:
            if '"tool_use"' not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            msg = rec.get("message") or {}
            for blk in (msg.get("content") or []):
                if isinstance(blk, dict) and blk.get("type") == "tool_use":
                    inp = blk.get("input", {}) or {}
                    yield idx, blk.get("name", ""), inp, json.dumps(inp, ensure_ascii=False)
                    idx += 1


def analyze(path: str) -> dict:
    gets_self = None
    rec_self_idx = rec_devloop_idx = None
    territory = instrument = tail_used = None
    first3: list[str] = []
    rec_seq: list[tuple[int, str]] = []
    for idx, name, inp, raw in tool_uses(path):
        if len(first3) < 3:
            first3.append(name)
        # task_id 필드를 정확히 읽는다 — related_task_ids 문자열 매칭은 정본 쓰기를
        # 미러 쓰기로 오분류한다 (c49 등재 '계측기 거짓 음성' 계열 회피)
        tid = str(inp.get("task_id", ""))
        if name.endswith("get_task_state") and tid == "devloop-self":
            gets_self = gets_self if gets_self is not None else idx
        if name.endswith("record_task_state"):
            rec_seq.append((idx, tid, "mcp"))
            if tid == "devloop-self" and rec_self_idx is None:
                rec_self_idx = idx
            elif tid == "devloop" and rec_devloop_idx is None:
                rec_devloop_idx = idx
        elif "record_task_state" in raw:
            # HTTP 폴백 채널 (지시서 절차 0 허용): Write/Bash로 urllib·curl 스크립트를
            # 만들어 쓰는 경로. c47이 실제로 이 채널로 정본을 썼다 — MCP 도구명 니들만
            # 보면 거짓 음성 (c51에서 실측한 4종째 계측기 맹점: 채널 맹점).
            # 트랜스크립트의 tool_use 입력은 JSON 재직렬화라 내부 따옴표가 \" 로
            # 이스케이프된다 — 따옴표 클래스에 백슬래시를 포함해야 문다.
            q = r'[\\"\']*'
            m_self = re.search(r'task_id' + q + r'\s*[:=]\s*' + q + r'devloop-self', raw)
            m_main = re.search(r'task_id' + q + r'\s*[:=]\s*' + q + r'devloop' + r'[\\"\']', raw)
            if m_self:
                rec_seq.append((idx, "devloop-self", "http"))
                if rec_self_idx is None:
                    rec_self_idx = idx
            if m_main:
                rec_seq.append((idx, "devloop", "http"))
                if rec_devloop_idx is None:
                    rec_devloop_idx = idx
        if name == "Bash":
            inp = raw
            if re.search(r"-newer|st_mtime|c48_step0_check\.py", inp):
                territory = territory if territory is not None else idx
            if re.search(r"c46_capsule_reach\.py|c48_step0_check\.py", inp):
                instrument = instrument if instrument is not None else idx
            if re.search(r"tail[^|]*metrics\.jsonl", inp):
                tail_used = tail_used if tail_used is not None else idx
    return {
        "T1_two_channel": gets_self is not None,
        "T2_self_first": (rec_self_idx is not None and rec_devloop_idx is not None
                          and rec_self_idx < rec_devloop_idx),
        "T2_raw": rec_seq,
        "T3_territory": territory is not None,
        "T4_instrument": instrument is not None,
        "T5_bundle": ("Read" in first3 and "ToolSearch" in first3),
        "V3_tail_used": tail_used is not None,
    }


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
        if len(cycles) != 1 or cycles[0] not in TARGET_CYCLES:
            continue
        r = analyze(f)
        r["cycle"] = cycles[0]
        r["file"] = os.path.basename(f)[:8]
        r["start"] = start
        rows.append(r)

    rows.sort(key=lambda r: r["cycle"])
    hdr = f"{'cycle':>5} {'when':11} {'T1(2채널)':>9} {'T2(self먼저)':>11} {'T3(영토)':>8} {'T4(계측기)':>9} {'T5(묶기)':>8} {'검증계수':>7}   V3 tail(③위반)"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        n = sum(r[k] for k in ("T1_two_channel", "T2_self_first", "T3_territory",
                               "T4_instrument", "T5_bundle"))
        print(f"{r['cycle']:>5} {r['start']:%m-%d %H:%M} "
              f"{str(r['T1_two_channel']):>9} {str(r['T2_self_first']):>11} "
              f"{str(r['T3_territory']):>8} {str(r['T4_instrument']):>9} "
              f"{str(r['T5_bundle']):>8} {n:>6}/5   {r['V3_tail_used']}")
        if not r["T2_self_first"]:
            print(f"       └ record_task_state 순서 진단: {r['T2_raw']}")
    print()
    print("P12 (a) 판정 대상: 사이클별 지시서 밖 규약 집행 ≥1건 (도구 가시 부분집합 기준)")
    for r in rows:
        n = sum(r[k] for k in ("T1_two_channel", "T2_self_first", "T3_territory",
                               "T4_instrument", "T5_bundle"))
        print(f"  c{r['cycle']}: {'충족' if n >= 1 else '미충족'} ({n}/5 도구 검증, "
              f"자기보고 6건 중 채점 관행·산문 규율은 이 채널 판정 밖)")


if __name__ == "__main__":
    main()
