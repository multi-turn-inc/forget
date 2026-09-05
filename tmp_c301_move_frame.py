import sys
sys.path.insert(0, "research/devloop/scripts")
import queue_mover as qm

path = "research/devloop/gate-queue.md"
with open(path, encoding="utf-8") as f:
    text = f.read()

reports = []
n = 292
target = 301
while n < target:
    text, q, p = qm.move_frame(text, n, n + 1)
    reports.append((n, n + 1, q, p))
    n += 1

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

for old_n, new_n, q, p in reports:
    print(f"step {old_n}->{new_n}: queue changed={len(q['changed'])} skipped={len(q['skipped'])} bad={len(q['bad'])} | perm header={p['header']} rows={len(p['rows'])} drift={p['drift']} no_formula={p['no_formula']}")
    sp = p['settlement_prev']
    print(f"  settlement_prev(c{old_n}): present={sp['present']} kind={sp['kind']}")
