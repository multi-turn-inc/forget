"""P33 control replay: what the treated code says about generations already received.

Read-only. Takes no live action -- it feeds real timestamps (the generation this
session was handed by live :8000, and the two-cycle-old one cycle 93 was handed)
into the new marker and prints the verdict. The control group needs no new
measurement because it is already on the record: neither response carried any
freshness field at all.
"""

from __future__ import annotations

import json

from forget.store import task_state_freshness

CASES = [
    (
        "c94 수신 세대 (live :8000, 턴2 실측)",
        {"task_id": "devloop", "valid_from": "2026-08-09T21:32:55Z"},
        "",
    ),
    (
        "c93 대조군 (c91 세대를 현재로 받은 세션)",
        {"task_id": "devloop", "valid_from": "2026-08-08T15:32:55Z"},
        "",
    ),
    ("세대 부재 (기록이 아예 없음)", None, ""),
    ("판독 불가 타임스탬프", {"task_id": "devloop", "valid_from": "not-a-date"}, ""),
    ("의도된 과거 조회 (as_of 재생)", {"task_id": "devloop", "valid_from": "2026-08-01T00:00:00Z"}, "2026-08-02T00:00:00Z"),
]


def main() -> None:
    print("[P33 대조 재생] 처치 전 응답에는 이 블록이 통째로 없었다 (표지 0개).")
    for label, current, as_of in CASES:
        marker = task_state_freshness(current, as_of)
        age = marker["age_hours"]
        age_text = f"{age:.1f}h" if isinstance(age, (int, float)) else "-"
        print(f"  {label}")
        print(f"    state={marker['state']:8s} stale={str(marker['stale']):5s} age={age_text:>8s} ttl={marker['ttl_hours']:g}h")
        if marker["advice"]:
            print(f"    advice: {marker['advice']}")
    print()
    print("전문 (첫 사례):")
    print(json.dumps(task_state_freshness(CASES[0][1]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
