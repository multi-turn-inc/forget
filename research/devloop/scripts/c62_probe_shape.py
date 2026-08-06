#!/usr/bin/env python3
"""c62 보조 — 트랜스크립트에서 훅 출력이 실제로 어떤 레코드 모양으로 앉는지 확인.

c62 채널 C 1차 계수기가 전 세션 0을 보고했다. 계측기 결함 가능성이 원인 가설보다
먼저다 (c44·c47·c49·c61 = 계측기 거짓 음성 4종). 이 스크립트는 계수 이전에
레코드 모양 자체를 인쇄한다.

1차 실행 결과: 훅 출력은 type=attachment 레코드로 앉는다 (message.content가 아니라
attachment.*). 계수기는 attachment를 읽어야 한다 — 아래는 그 키 경로 확정용.
"""
import glob
import json
import os

TRANSCRIPTS = os.path.expanduser(
    "~/.claude/projects/-Users-junghunkim-orca-workspaces-forget----------------"
)

files = sorted(glob.glob(os.path.join(TRANSCRIPTS, "*.jsonl")), key=os.path.getmtime)[-3:]
for path in files:
    print("=" * 70)
    print(os.path.basename(path))
    shown = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if "[forget 회상" not in line and "[forget 캡슐" not in line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") != "attachment":
                continue
            att = obj.get("attachment") or {}
            print(f"  top keys: {sorted(obj.keys())}")
            print(f"  attachment keys: {sorted(att.keys())}")
            for key, val in att.items():
                if isinstance(val, str):
                    flat = val.replace("\n", " | ")
                    print(f"    {key} (str {len(val)}): {flat[:300]}")
                else:
                    print(f"    {key}: {type(val).__name__} {str(val)[:160]}")
            shown += 1
            if shown >= 2:
                break
