#!/usr/bin/env python3
"""c62 — 턴 회상 주입 0/3 분기의 채널 귀속 (read-only, 2026-08-07).

c61 관측 ③: 실세션 턴 회상 주입 0건인데 c52_p10_premise_replay.py 재생은 3건
상한 보고. c61은 원인 미규명으로 남기고 "P10 전제 흔들림" 표시만 부착했다.
후보 원인은 HEAD fd30a68(평탄도 소음 게이트 + 의미 바닥)이었으나 반대 증거는
"실서버가 읽는 것은 설치본(~/.forget/hooks)이므로 저장소 커밋은 무관"이었다.

이 스크립트는 그 분기를 세 채널로 가른다 — 전부 1차 증거, 읽기 전용.

  채널 A (설치본 표류): ~/.forget/hooks/*.py vs 저장소 hooks/*.py — sha256 +
      mtime + 게이트 상수/필터 리터럴 등장 여부. "설치본이니까 무관"이 참인지
      직접 검사한다. 파일을 쓰지 않는다.
  채널 B (재생기 충실도): 설치본 훅 main()의 필터 단계 목록 대 재생 스크립트
      classify()가 재현하는 단계 목록. 차집합 = 재생기가 구조적으로 못 보는 것.
  채널 C (세션 층 1차 계수): 트랜스크립트에서 UserPromptSubmit 회상 블록과 그
      항목 수를 사이클별로 계수. 재생 스크립트를 경유하지 않는다.

용법: .venv/bin/python research/devloop/scripts/c62_injection_channel.py
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
INSTALLED_DIR = os.path.expanduser("~/.forget/hooks")
REPO_HOOK_DIR = os.path.join(REPO, "hooks")
TRANSCRIPTS = os.path.expanduser(
    "~/.claude/projects/-Users-junghunkim-orca-workspaces-forget----------------"
)
REPLAY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c52_p10_premise_replay.py")

HOOK_FILES = ("forget_turnrecall.py", "forget_sessionstart.py", "forget_project.py")

# 채널 A 니들: fd30a68(body A1-A4)이 도입한 게이트/계기 리터럴.
GATE_NEEDLES = (
    "FLATNESS_MARGIN",
    "flat_distribution",
    "SEMANTIC_FLOOR",
    "score_breakdown",
    '"trace": "turn_recall"',
    "trace_id",
)

# 채널 B: 설치본 훅 main()이 후보를 떨어뜨리는 지점 → 재생기 classify()의 대응 니들.
# (없으면 재생기가 그 단계를 재현하지 못한다는 뜻.)
FILTER_STEPS = [
    ("seen ledger", "memory_id in seen", "seen"),
    ("capture pointer", 'metadata.get("hook")', 'md.get("hook")'),
    ("task_state", 'assertion_kind") == "task_state"', 'assertion_kind") == "task_state"'),
    ("conflict pair", "_conflict_pair(item)", "superseded_by"),
    ("score gate", "score < SCORE_THRESHOLD", "SCORE_THRESHOLD"),
    ("flatness gate", "if flat_distribution", "flat"),
    ("semantic floor", "SEMANTIC_FLOOR", "SEMANTIC_FLOOR"),
]

# 채널 C 니들: 훅이 실제로 인쇄하는 헤더 문면 (forget_turnrecall.py main()).
RECALL_HEADER = "[forget 회상 — 이 턴과 관련된 기억 제안"
CONFLICT_HEADER = "[forget 충돌지대"
CAPSULE_HEADER = "[forget 캡슐"
BULLET = re.compile(r"^- \((green|yellow|red|현재|red/구본)\)", re.M)
CYCLE_PROMPT = "devloop 사이클을 정확히 한 바퀴 실행하라"


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def stamp(path: str) -> str:
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%m-%d %H:%M")


def channel_a() -> dict:
    print("=" * 78)
    print("[채널 A] 설치본 표류 — ~/.forget/hooks vs 저장소 hooks/ (읽기 전용)")
    print("=" * 78)
    out = {}
    for name in HOOK_FILES:
        inst = os.path.join(INSTALLED_DIR, name)
        repo = os.path.join(REPO_HOOK_DIR, name)
        if not (os.path.exists(inst) and os.path.exists(repo)):
            print(f"  {name:<26} 부재 (설치본={os.path.exists(inst)} 저장소={os.path.exists(repo)})")
            continue
        si, sr = sha(inst), sha(repo)
        same = si == sr
        out[name] = same
        print(f"  {name:<26} {'동일' if same else '★상이'}  설치본 {si} ({stamp(inst)})"
              f"  저장소 {sr} ({stamp(repo)})")
    tr_inst = os.path.join(INSTALLED_DIR, "forget_turnrecall.py")
    tr_repo = os.path.join(REPO_HOOK_DIR, "forget_turnrecall.py")
    ti = open(tr_inst, encoding="utf-8").read()
    tr = open(tr_repo, encoding="utf-8").read()
    print(f"\n  fd30a68 게이트 리터럴 등장 (turnrecall):")
    verdict_gates = {}
    for needle in GATE_NEEDLES:
        gi, gr = ti.count(needle), tr.count(needle)
        verdict_gates[needle] = (gi, gr)
        mark = "  " if (gi > 0) == (gr > 0) else "★"
        print(f"   {mark} {needle:<26} 설치본 {gi}회  저장소 {gr}회")
    installed_has_flatness = ti.count("flat_distribution") > 0
    print(f"\n  → 설치본이 평탄도 게이트를 갖는가: {installed_has_flatness}")
    return {"same": out, "gates": verdict_gates, "installed_has_flatness": installed_has_flatness,
            "installed_text": ti}


def channel_b(installed_text: str) -> list:
    print()
    print("=" * 78)
    print("[채널 B] 재생기 충실도 — 설치본 훅 필터 단계 vs c52 재생기 classify()")
    print("=" * 78)
    replay_src = open(REPLAY, encoding="utf-8").read()
    missing = []
    for label, hook_needle, replay_needle in FILTER_STEPS:
        in_hook = hook_needle in installed_text
        in_replay = replay_needle in replay_src
        if in_hook and not in_replay:
            missing.append(label)
        mark = "★누락" if (in_hook and not in_replay) else ("  ok " if in_hook else "  n/a")
        print(f"  {mark}  {label:<18} 설치본훅={in_hook!s:<5} 재생기={in_replay}")
    print(f"\n  → 재생기가 구조적으로 못 보는 단계: {missing or '없음'}")
    return missing


def scan_session(path: str) -> dict | None:
    """트랜스크립트 1개에서 훅 주입을 1차 계수. 사이클 프롬프트 세션만.

    정본 레코드 경로 (c62_probe_shape.py로 확정): type=attachment ·
    attachment.hookName=UserPromptSubmit · attachment.content.
    **1차 계수기는 message.content를 읽어 전 세션 0을 보고했다 — 계측기 거짓
    음성 5종째.** 훅 출력은 message에 앉지 않는다.

    이 경로는 "0"을 세 상태로 가른다:
      - fired=0        → 훅이 아예 돌지 않았다 (하네스/설정 채널)
      - fired>0·items=0 → 돌았고 침묵했다 (게이트 채널)
      - items>0        → 주입됐다
    """
    is_cycle = False
    fired = 0            # UserPromptSubmit 훅 실행 횟수 (성공 레코드)
    failed = 0           # exitCode != 0
    silent = 0           # 실행됐으나 회상/충돌 블록 없음
    recall_blocks = 0
    conflict_blocks = 0
    recall_items = 0
    traces = 0
    capsule = False
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if CYCLE_PROMPT in line:
                    is_cycle = True
                if '"type":"attachment"' not in line and '"type": "attachment"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if obj.get("type") != "attachment":
                    continue
                att = obj.get("attachment") or {}
                text = att.get("content") or ""
                if att.get("hookEvent") == "SessionStart" and CAPSULE_HEADER in text:
                    capsule = True
                if att.get("hookName") != "UserPromptSubmit":
                    continue
                fired += 1
                if att.get("exitCode") not in (0, None):
                    failed += 1
                    continue
                has_recall = RECALL_HEADER in text
                has_conflict = CONFLICT_HEADER in text
                if has_recall:
                    recall_blocks += 1
                if has_conflict:
                    conflict_blocks += 1
                if not (has_recall or has_conflict):
                    silent += 1
                    continue
                recall_items += len(BULLET.findall(text))
                if "record_context_outcome(trace_id=" in text:
                    traces += 1
    except Exception:
        return None
    if not is_cycle:
        return None
    return {
        "file": os.path.basename(path)[:8],
        "mtime": stamp(path),
        "capsule": capsule,
        "fired": fired,
        "failed": failed,
        "silent": silent,
        "recall_blocks": recall_blocks,
        "conflict_blocks": conflict_blocks,
        "items": recall_items,
        "traces": traces,
    }


def channel_c() -> list:
    print()
    print("=" * 78)
    print("[채널 C] 세션 층 1차 계수 — 사이클 세션별 훅 주입 (attachment 레코드 원문)")
    print("=" * 78)
    files = sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")), key=os.path.getmtime)
    window = files[-140:]
    rows = []
    for path in window:
        row = scan_session(path)
        if row:
            rows.append(row)
    print(f"  스캔 {len(window)}개 중 사이클 프롬프트 세션 {len(rows)}개")
    print(f"  {'세션':<9} {'mtime':<12} {'캡슐':<6} {'발화':<5} {'침묵':<5} {'실패':<5} "
          f"{'회상':<5} {'충돌':<5} {'항목':<5} {'trace'}")
    for row in rows:
        print(f"  {row['file']:<9} {row['mtime']:<12} {str(row['capsule']):<6} "
              f"{row['fired']:<5} {row['silent']:<5} {row['failed']:<5} "
              f"{row['recall_blocks']:<5} {row['conflict_blocks']:<5} {row['items']:<5} {row['traces']}")
    return rows


def main() -> None:
    a = channel_a()
    missing = channel_b(a["installed_text"])
    rows = channel_c()
    print()
    print("=" * 78)
    print("[귀속 요약]")
    print("=" * 78)
    print(f"  A 설치본이 fd30a68 게이트 보유: {a['installed_has_flatness']}")
    print(f"  B 재생기 미재현 단계: {missing or '없음'}")
    never = [r for r in rows if r["fired"] == 0]
    silenced = [r for r in rows if r["fired"] > 0 and r["items"] == 0]
    injected = [r for r in rows if r["items"] > 0]
    print(f"  C 사이클 세션 {len(rows)}개 분해:")
    print(f"      훅 미발화(하네스 채널) {len(never)}개")
    print(f"      발화·전량 침묵(게이트 채널) {len(silenced)}개")
    print(f"      주입>0 {len(injected)}개 (항목 합 {sum(r['items'] for r in rows)})")


if __name__ == "__main__":
    main()
