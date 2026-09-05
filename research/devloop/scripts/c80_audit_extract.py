"""c80 적대 감사 — 원장 추출기 (read-only).

metrics.jsonl에서 감사 심문에 필요한 계열만 뽑는다:
c79 행 형식(append 템플릿), 능동 검색 0회 연속, frictions 합계,
게이트 정산 문구, 관측 37 ③ 비밀 스캔(건수만 — 원문 무인용).
"""
import json
import re

ROWS = []
with open('research/devloop/metrics.jsonl', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            ROWS.append(json.loads(line))

last = ROWS[-1]
print("[c79 keys]", list(last.keys()))
for k in ("gate_pending", "frictions_note", "restore_note", "recall_note"):
    v = json.dumps(last.get(k), ensure_ascii=False)
    print(f"[c79 {k} len={len(v)}] {v[:500]}")

print("\n[recall 성분 c57~c79]")
pat = re.compile(r"능동\s*(\d+)회")
for r in ROWS:
    c = r.get("cycle")
    if isinstance(c, int) and c >= 57:
        note = r.get("recall_note", "")
        m = pat.search(note)
        active = m.group(1) if m else "?"
        print(f"c{c}: 능동={active} hits={r.get('recall_hits')} miss={r.get('recall_misses')} note[:70]={note[:70]!r}")

fl = [(r.get("cycle"), r.get("frictions_logged"), r.get("frictions_fixed")) for r in ROWS]
tot_logged = sum(x[1] for x in fl if isinstance(x[1], int))
tot_fixed = sum(x[2] for x in fl if isinstance(x[2], int))
print(f"\n[frictions] logged 합={tot_logged} fixed 합={tot_fixed}")
print("fixed>=1 사이클:", [c for c, _, fx in fl if isinstance(fx, int) and fx >= 1])

print("\n[gate 정산 최근 5행]")
for r in ROWS[-5:]:
    g = r.get("gate_pending", "")
    s = g if isinstance(g, str) else json.dumps(g, ensure_ascii=False)
    m = re.search(r"정산[^)]*\)", s)
    print(f"c{r.get('cycle')}: {m.group(0) if m else '(정산 문구 없음)'} len={len(s)}")

text = open("research/devloop/metrics.jsonl", encoding="utf-8").read()
patterns = {
    "password-like": r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+",
    "ssh-uri": r"ssh://\S+|sshpass",
    "private-key": r"BEGIN (RSA|OPENSSH|EC) PRIVATE KEY",
    "api-key-like": r"(?i)(api[_-]?key|secret[_-]?key)\s*[:=]\s*[A-Za-z0-9_\-]{16,}",
    "sk-ant": r"sk-ant-[A-Za-z0-9\-_]{10,}",
}
print("\n[관측 37 비밀 스캔 — 건수만]")
for name, p in patterns.items():
    print(f"  {name}: {len(re.findall(p, text))}건")
