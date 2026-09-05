#!/usr/bin/env python3
"""c62 보조 — 주입 0 세션의 1차 프롬프트와 훅 레코드 유무를 원문으로 본다.

채널 C가 53개 사이클 세션 중 3개만 주입 0(fired=0)으로 분해했다. fired=0은 두
상태의 합집합이다: (i) 훅이 돌지 않았다 (ii) 돌았으나 침묵해 출력이 없어 하네스가
attachment 레코드를 만들지 않았다. 이 스크립트는 그 3개 세션의 1차 프롬프트를 인쇄해
질의 텍스트 채널을 검사하고, 전 창에서 '빈 출력 UserPromptSubmit 레코드'가 존재하는지
세어 (i)/(ii) 구분 가능성 자체를 판정한다.
"""
import glob
import json
import os

TRANSCRIPTS = os.path.expanduser(
    "~/.claude/projects/-Users-junghunkim-orca-workspaces-forget----------------"
)
ZERO = ("ab56525c", "84ae0a8d", "de5e17ea")
MINE = ("66923da9",)


def first_prompt(path):
    """첫 사용자 프롬프트 원문 (훅 주입·시스템 리마인더 제외)."""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "user" or obj.get("isSidechain"):
                continue
            content = obj.get("message", {}).get("content")
            texts = []
            if isinstance(content, str):
                texts = [content]
            elif isinstance(content, list):
                texts = [c.get("text", "") for c in content if isinstance(c, dict)]
            for text in texts:
                stripped = text.strip()
                if not stripped or stripped.startswith("<"):
                    continue
                return obj.get("timestamp"), stripped
    return None, None


def hook_records(path):
    """모든 UserPromptSubmit 훅 레코드 (빈 출력 포함) 요약."""
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "attachment" not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "attachment":
                continue
            att = obj.get("attachment") or {}
            name = att.get("hookName") or ""
            if not name.startswith(("UserPromptSubmit", "SessionStart")):
                continue
            out.append((name, len(att.get("content") or ""), att.get("exitCode"),
                        att.get("durationMs")))
    return out


files = sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")), key=os.path.getmtime)

# (ii) 판정: 창 전체에서 빈 출력 UserPromptSubmit 레코드가 한 번이라도 있는가.
empty_ups = 0
total_ups = 0
for path in files[-140:]:
    for name, length, _code, _ms in hook_records(path):
        if name == "UserPromptSubmit":
            total_ups += 1
            if length == 0:
                empty_ups += 1
print(f"[구분 가능성] 창 전체 UserPromptSubmit 레코드 {total_ups}개 중 빈 출력 {empty_ups}개")
print("  → 빈 출력이 0개면 '침묵'은 레코드를 남기지 않는다 = fired=0으로 (i)/(ii) 구분 불가\n")

for tag in ZERO + MINE:
    match = [p for p in files if os.path.basename(p).startswith(tag)]
    if not match:
        print(f"[{tag}] 파일 없음")
        continue
    path = match[0]
    label = "주입 0" if tag in ZERO else "주입 3 (대조)"
    print("=" * 78)
    print(f"[{tag}] {label}  size={os.path.getsize(path)//1024}K")
    recs = hook_records(path)
    print(f"  훅 레코드: {[(n, l) for n, l, _, _ in recs]}")
    ts, prompt = first_prompt(path)
    print(f"  1차 프롬프트 ts={ts} len={len(prompt or '')}")
    print(f"  원문[:400]: {(prompt or '')[:400]!r}")
