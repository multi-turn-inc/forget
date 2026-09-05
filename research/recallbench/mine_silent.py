#!/usr/bin/env python3
"""① 표본 후보 채굴 — 게이트 원장의 silent 턴 (은행 입행은 실전 확증 후만)."""
import json, os, time
path = os.path.expanduser("~/.forget/hooks/state/turnrecall_gate.jsonl")
cutoff = time.time() - 7 * 86400
out, seen = [], set()
for line in open(path):
    try: r = json.loads(line)
    except Exception: continue
    if r.get("at", 0) < cutoff or r.get("action") not in ("silent_scores",): continue
    if str(r.get("session", "")).startswith("rb"): continue   # 재생 자신 제외
    head = r.get("prompt_head", "")
    if len(head) < 15 or head in seen: continue
    seen.add(head)
    out.append({"at": r["at"], "gate": r["gate"], "prompt_head": head})
dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "candidates_silent.jsonl")
with open(dst, "w") as fh:
    for r in sorted(out, key=lambda x: -x["at"]):
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"침묵 후보 {len(out)}건 → candidates_silent.jsonl (입행은 정정-턴 대조 확증 후)")
