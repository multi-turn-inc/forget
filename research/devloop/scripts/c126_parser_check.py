#!/usr/bin/env python3
"""c126 — 파트 F 이탈 판정의 **수정 전후 대조** (관측 63 처치의 검증 계기).

왜 이 계기가 따로 필요한가. 관측 63의 수용 기준 ② **원문**은 "수정 후 파트 F가 관측
61을 존속으로 재계상하면 종결"이었다. 그런데 c115 회고가 61을 **실제로** 회부 종결시켰고
(§3-1, 대장에 "회부 종결" 주석 있음), 같은 회고가 원문 ②를 충족 불능으로 판정해
"**파서 수정 후 부정문 처분 합성 표본이 존속으로 계상되면 마감**"으로 교체했다.
이 계기가 그 교체된 ②의 집행체다 — 진실이 계기를 따라잡아 수정 전후 **대장** 판정은
동일하므로(61은 이제 이탈이 맞다), 위양성 제거의 증거는 대장이 아니라 합성 표본이
진다: 옛 규칙과 새 규칙을 **같은 입력**에 걸어 갈리는 자리를 명시적으로 인쇄한다.

두 부분.
  [1] 합성 표본 — 기대 판정을 손이 미리 적고, 신규칙이 그것을 맞히는지 본다.
      옛 규칙 열은 "무엇이 고쳐졌는가"의 대조군이다.
  [2] 대장 실측 — 실제 frictions.md에서 두 규칙의 open_observations 집합 차분.
      Δ가 0이면 0이라고 인쇄한다(처치가 현재 계수를 바꾸지 않았다는 것도 결과다).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import c48_step0_check as C  # noqa: E402


def old_exit_declared(para: str) -> bool:
    """c48~c125 판본: 처분 문단 내 **순수 부분문자열** 탐색 (관측 63의 기전)."""
    return any(mark in para for mark in C._EXIT_MARKS)


# (라벨, 처분 문단, 기대 판정). 출처 = 대장 실물의 축약 또는 그 변형.
CASES: list[tuple[str, str, bool]] = [
    ("관측 61 c113 실물 — 존속 명시",
     "**처분 (사이클 113, 수용 기준 ① 이행 — 존속).** 유형 귀속은 여전히 회부 "
     "상태 — 이 처분은 ①의 이행 기록이지 종결이 아니다.", False),
    ("관측 61 c115 실물 — 진짜 이탈",
     "**처분 (사이클 115 회고, amendment-115 §3-1 — 회부 종결).** 수용 기준 3항 "
     "전부 이행 실측 위의 마감이다.", True),
    ("관측 53 실물 계열 — 긍정 발생 + 뒤 절 부정어",
     "**처분 (사이클 105 회고).** → **종결.** 이월 주의: 종결되는 것은 \"원인 미상\" "
     "상태이지 침묵이 아니다.", True),
    ("관측 55 실물 계열 — 다른 마커의 긍정 발생",
     "**처분 (사이클 105 회고, amendment-105 §3-1).** 회부 상태를 벗어나되, "
     "**F2 대장 항목으로** 승계한다.", True),
    ("다른 마커의 부정 발생 (합성)",
     "**처분 (사이클 999).** 이것은 부분 처분이며 회부 상태를 벗어나지 않는다.", False),
    ("긍정 선언 + 먼 부정어 (합성 — 창 폭의 음성 대조)",
     "**처분 (사이클 999).** 회부 종결이며 더 이상 원장 행이 존속을 보정하지 않는다.", True),
    ("부정 활용형 '아니라' (합성)",
     "**처분 (사이클 999).** 이 문단은 종결이 아니라 이행 기록이다.", False),
    ("보조용언 부정 '보지 않는다' (합성 — 3어절 창의 경계)",
     "**처분 (사이클 999).** 이 절은 종결로 보지 않는다.", False),
    ("마커 없음 = 부분 처분 (합성)",
     "**처분 (사이클 999).** 수용 기준 ①만 이행했고 유형 귀속은 계속 심리한다.", False),
    ("알려진 잔여 위양성 (합성 — 4어절 밖 부정, 고쳐지지 않음)",
     "**처분 (사이클 999).** 이 절이 종결이라고 이 처분이 말하지는 않는다.", True),
]


def part_cases() -> int:
    print("[1. 합성 표본 — 같은 입력, 옛 규칙 vs 신규칙]")
    print("  기대 = 손이 미리 적은 판정. 신규칙이 기대와 갈리면 ★.")
    print(f"  {'구':2} {'옛':4} {'신':4} {'기대':4}  라벨")
    bad = 0
    flipped = 0
    for label, para, want in CASES:
        old = old_exit_declared(para)
        new = C._exit_declared(para)
        ok = new == want
        bad += not ok
        flipped += old != new
        print(f"  {'★' if not ok else ' ':2} {str(old):5} {str(new):5} {str(want):5} "
              f" {label}")
    print(f"  합계: 표본 {len(CASES)} · 신규칙 불일치 {bad} · 옛→신 판정 뒤집힘 {flipped}")
    print("  주: 마지막 표본은 **의도된 잔여 위양성**이다 — 기대를 True로 적어 처치의"
          " 사정거리를 문서가 아니라 표본으로 못박는다(4어절 밖 부정은 미처치).")
    return bad


def part_ledger() -> None:
    print("\n[2. 대장 실측 — 두 규칙의 open_observations 차분]")
    with open(C.FRICTIONS, encoding="utf-8") as fh:
        text = fh.read()
    new_obs = C.parse_observations(text)
    new_open = set(C.open_observation_numbers(new_obs))

    real = C._exit_declared
    try:
        C._exit_declared = old_exit_declared  # type: ignore[assignment]
        old_open = set(C.open_observation_numbers(C.parse_observations(text)))
    finally:
        C._exit_declared = real  # type: ignore[assignment]

    print(f"  옛 규칙 open={len(old_open)}  신규칙 open={len(new_open)}"
          f"  Δ{len(new_open) - len(old_open):+d}")
    only_new = sorted(new_open - old_open)
    only_old = sorted(old_open - new_open)
    print(f"  신규칙에서만 존속(= 위양성 회수): {only_new or '없음'}")
    print(f"  옛 규칙에서만 존속: {only_old or '없음'}")
    if not only_new:
        print("  판정: 현재 대장에서 두 규칙은 **같은 답**을 낸다. 관측 61은 c115 회고가"
              " 실제로 회부 종결시켰으므로(대장 주석 있음) 이탈이 맞고, 위양성 자리는"
              " 진실에 덮였다 — 그래서 관측 63 수용 기준 ②는 c115에 이미"
              " '합성 표본이 존속으로 계상되면 마감'으로 교체돼 있고, 그 집행이 [1]이다."
              " 이 Δ0은 처치 무효가 아니라 **대장이 더 이상 위양성을 겪을 자리에 있지"
              " 않다**는 뜻이다.")


if __name__ == "__main__":
    rc = part_cases()
    part_ledger()
    sys.exit(1 if rc else 0)
