#!/usr/bin/env python3
"""c62 보조 — 침묵의 두 후보를 가른다 (읽기 전용, ~/.forget 상태 파일 미변경).

동일 프롬프트(437자 축자 동일)·동일 훅 sha256·34분 간격의 두 세션이 주입 0 대 3으로
갈렸다. 남은 후보 둘:
  (H1) 세션 ledger 억제 — 캡슐이 이미 제시한 memory_id는 턴 회상이 건너뛴다
       (`memory_id in seen`). 캡슐 내용이 세션마다 다르므로 seen 집합도 다르다.
       c52 재생기는 이 채널을 **재현하지 않는다고 스스로 선언**했다(CAVEAT: "여기
       '주입'은 상한이다").
  (H2) 훅 미실행 — 하네스가 UserPromptSubmit 훅을 아예 돌리지 않았다.

판별 근거: 빈 출력 UserPromptSubmit 레코드가 실재하면(창에서 4개 관측) 침묵도
레코드를 남긴다는 뜻 → 레코드 전무는 H2 쪽 증거. 그 4개의 정체를 먼저 확인한다.
"""
import glob
import json
import os

TRANSCRIPTS = os.path.expanduser(
    "~/.claude/projects/-Users-junghunkim-orca-workspaces-forget----------------"
)
STATE_DIR = os.path.expanduser("~/.forget/hooks/state")
SESSIONS = {
    "ab56525c": "c61 2차 런 (주입 0)",
    "84ae0a8d": "주입 0",
    "de5e17ea": "주입 0",
    "66923da9": "c62 이 세션 (주입 3)",
}

print("=" * 78)
print("[H2 검사] 빈 출력 UserPromptSubmit 레코드 4개의 정체")
print("=" * 78)
files = sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")), key=os.path.getmtime)
for path in files[-140:]:
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "attachment" not in line or "UserPromptSubmit" not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "attachment":
                continue
            att = obj.get("attachment") or {}
            if att.get("hookName") != "UserPromptSubmit":
                continue
            if len(att.get("content") or "") == 0:
                print(f"  {os.path.basename(path)[:8]}  type={att.get('type')} "
                      f"exit={att.get('exitCode')} ms={att.get('durationMs')} "
                      f"stdout_len={len(att.get('stdout') or '')} "
                      f"stderr={(att.get('stderr') or '')[:60]!r}")

print()
print("=" * 78)
print("[H1 검사] 세션 ledger — 캡슐이 제시한 memory_id 집합")
print("=" * 78)
if not os.path.isdir(STATE_DIR):
    print(f"  상태 디렉터리 없음: {STATE_DIR}")
else:
    all_state = os.listdir(STATE_DIR)
    for tag, label in SESSIONS.items():
        mine = [f for f in all_state if f.startswith(tag)]
        print(f"\n  [{tag}] {label}")
        if not mine:
            print("    ledger 파일 없음 (세션 만료 정리 또는 미기록)")
            continue
        for fname in sorted(mine):
            fpath = os.path.join(STATE_DIR, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception as exc:
                print(f"    {fname}: 읽기 실패 {exc}")
                continue
            ids = data.get("memory_ids") or data.get("injected") or []
            lines = data.get("capsule_lines") or []
            print(f"    {fname}: keys={sorted(data.keys())} ids={len(ids)} capsule_lines={len(lines)}")
            for one in ids[:8]:
                print(f"       id {one}")
