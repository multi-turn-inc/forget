"""c61 R1 검증 — 죽은 런(04:39) 판정문의 근거 주장을 metrics 원문으로 대조한다.

c57 규율: 죽은 런의 완성품은 재실행/대조 검증 후에만 채택.
이 스크립트는 판정문이 인용한 값(c21 문면, c55~c60 계상)을 1차 원문에서 다시 뜬다.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
METRICS = ROOT / "research/devloop/metrics.jsonl"
PREDICTIONS = ROOT / "research/devloop/predictions.md"
LOOP = ROOT / "LOOP.md"

rows = [json.loads(line) for line in METRICS.read_text().splitlines() if line.strip()]
by_cycle = {r["cycle"]: r for r in rows}

print("[1] 판정문 인용값 대조 — recall 계상과 restore_turns")
for c in (21, 55, 56, 57, 58, 59, 60):
    r = by_cycle.get(c)
    if r is None:
        print(f"  c{c}: MISSING")
        continue
    print(
        f"  c{c}: hits={r.get('recall_hits')} misses={r.get('recall_misses')} "
        f"turns={r.get('restore_turns')} grade={r.get('restore_grade')}"
    )

print()
print("[2] c21 recall_note 문면 — '무용 주입=miss' 규칙의 1차 출처")
note21 = by_cycle[21].get("recall_note", "")
print("  " + note21[:600].replace("\n", " "))

print()
print("[3] A-환산 전제 검증 — c57~c59 note가 '주입 3건·신규 정보 0'을 말하는가")
# c61 수정: 1차 판본은 리터럴 '신규 정보 0'만 매칭해 c57을 False로 오판했다.
# 원문은 "이번 작업(oracle replay 채택)에 새 정보 0" — 동일 사실의 의역이다.
# 계측기 거짓 음성 4종째(c44 버그·c47 판본 표류·c49 의역 맹점·c61 검증기 의역 맹점).
# 처치: 리터럴 매칭을 사실 판정의 대리로 쓰지 않는다 — 의역 변형을 모두 시도하고,
# 그래도 미스면 원문을 인쇄해 사람 판독으로 승격한다(어휘 일치 ≠ 사실 일치).
ZERO_VARIANTS = ("신규 정보 0", "새 정보 0", "신규정보 0")
for c in (57, 58, 59):
    note = by_cycle[c].get("recall_note", "")
    has_three = bool(re.search(r"주입 3", note))
    matched = [v for v in ZERO_VARIANTS if v in note]
    if matched:
        print(f"  c{c}: '주입 3'={has_three}  '신규 정보 0'=True (도달 어휘: {matched})")
    else:
        print(f"  c{c}: '주입 3'={has_three}  '신규 정보 0'=MATCH-FAIL → 사람 판독 필요")
        print(f"       원문: {note[:300]}")

print()
print("[4] 헌장 문면 — recall 지표 정의 (정직 병기의 대상)")
for line in LOOP.read_text().splitlines():
    if "recall_hits" in line:
        print("  " + line.strip())

print()
print("[5] P15 실제 등록 여부 (판정문은 '등록'이라 서술)")
ptext = PREDICTIONS.read_text()
ids = re.findall(r"^#+\s*(P\d+)", ptext, re.M)
print(f"  predictions.md 존재 ID: {sorted(set(ids), key=lambda s: int(s[1:]))}")
print(f"  P15 등장 횟수: {len(re.findall(r'P15', ptext))}")
print(f"  P7 등장 횟수: {len(re.findall(r'P7', ptext))}")
