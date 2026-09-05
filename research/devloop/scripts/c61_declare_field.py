"""c61 자기집행 — 신규 필드 frictions_note를 행 안에서 명시 선언한다.

audit-60 §2가 적발한 비대칭: 필드 '추가'(silent_misses)는 게이트로 막혔고 '삭제'
(gate_pending)는 무공지로 통과했다. c60 교훈은 "계기와 캐리어는 선언 없이 바꾸지 마라".
c61이 frictions_note를 추가했으므로 같은 규율을 자신에게 적용한다 — 지우지 않고,
무공지로 두지도 않고, 행 안에 근거와 지위를 선언한다.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
METRICS = ROOT / "research/devloop/metrics.jsonl"

lines = METRICS.read_text(encoding="utf-8").splitlines()
row = json.loads(lines[-1])
assert row["cycle"] == 61, row["cycle"]

declaration = (
    "**[신규 필드 선언 — frictions_note, c61 도입]** 60행 전례 없는 필드다. 근거: 지시서 절차 5가 "
    "허용 스키마를 'frictions_*'로 와일드카드 지정하고, restore_note·recall_note가 *_note 관례를 "
    "이미 세웠다 — 그 관례의 frictions 판본. 지위: **자기 선언한 무게이트 추가이며, 정훈의 사후 기각에 "
    "열려 있다**(기각 시 내용은 work로 흡수, 시계열 손실 0). audit-60 §2의 비대칭(추가는 게이트·삭제는 "
    "무공지)을 c61이 되풀이하지 않기 위해 지우거나 숨기지 않고 행 안에 남긴다 — c60 교훈 '계기와 캐리어는 "
    "선언 없이 바꾸지 마라'의 자기적용. gate_pending에도 병기. "
)
row["frictions_note"] = declaration + row["frictions_note"]
row["gate_pending"] = row["gate_pending"] + (
    " [**신규 필드 frictions_note 사후 승인/기각 — 정훈.** c61이 자기 선언으로 추가(60행 전례 없음). "
    "근거=지시서 'frictions_*' 와일드카드 + *_note 관례. 기각 시 work로 흡수하면 시계열 손실 0]"
)

lines[-1] = json.dumps(row, ensure_ascii=False)
METRICS.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("declared. frictions_note len =", len(row["frictions_note"]))
