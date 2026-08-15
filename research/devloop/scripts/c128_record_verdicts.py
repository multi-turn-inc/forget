#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""c128 — `무기재` 잔여 2건(P20·P25) 소급 기재 (c127 관측 71 잔여 하자의 종결)

무엇을 하는가
-------------
c127이 41건 전수에 `- 상태:` 를 부여하면서 P20·P25 둘만 `무기재`(하자 라벨)로
남겼다. 이유는 정직했다 — 대장 전문에 판정이 없었고, **짐작해 채우는 것은
소급 창작**이기 때문이다(관측 74가 명명한 기전의 반대 방향).

c128은 짐작하지 않는다. **원장(metrics.jsonl)의 해당 사이클 행을 직독**해
판정이 실재하는지 먼저 확인했고, 둘 다 실재했다. 따라서 이것은 창작이 아니라
**외부 판정의 대장 반영**이며, 전례는 P37(4ed88f1)이다.

원장 실측 (이 파일이 인용하는 1차 출처)
---------------------------------------
P20 (a): c69 `restore_note` — "**★ P20 (a) 판정 = 지지 확정 (4/4).** c66·c67·c68·c69
         전부 restore_turns 3 · floor 3 · 초과분 0."
         c70 `work` 재확인 — "P20 (a) 시계 종료(c69 지지 4/4)".
         c70 `restore_note` — "단 P20 (a)는 c69에서 4/4 지지 확정으로 시계 종료라
         이 값은 시계 밖 표본이다."
P25 (a): c81 `work` — "**(a) 대수 동치 64/64 히트**(fixtures_cycle22 전수,
         신점수=구점수−junk … 동결 재현으로 기계 확인)".
P25 (b): c81 `work` — "**(b) c22 T2b 랭크 재현 8/8 쿼리**(tau·top-1 전수 일치:
         e2ee 0.6429, compression top-1 훼손까지 재현 — recency 앵커 캐비앗 무발동)".
P25 (c): c81 `tests` — "기존 단언 완화 0건 = P25 (c) 적중."

즉 P25는 등록문의 "판정: (a)(b)(c)는 이 사이클 안에서 즉시"가 **실제로 지켜졌고**,
지켜진 판정이 대장으로만 오지 않았다. 하자는 판정 부재가 아니라 **전사 누락**이었다.

비-지지 팔의 배정 근거 — 선례 귀속 (짐작 금지의 실행)
-----------------------------------------------------
P20 (b)는 "역방향 반증 팔"이고 그 격발 조건("계획을 옮겼는데도 4가 유지되면")이
창(c66~c69) 안에서 **0회 발화**했다. 이 형태의 선례는 c127이 이미 세웠다:
P34 (b) "팔 비발동: 창 내 파서 오분류 0건 — 등록 조건 미충족 = 채널 건재" → `지지`.
같은 형태에 같은 값을 준다. 새 어휘를 만들지 않는다(14번째 값은 선례가 없을 때만).

**단, 이 배정에는 자기 유리 방향의 결함이 있다 — 숨기지 않고 병기한다.**
P34는 (a) 반증 · (b) 지지로 두 팔이 **독립 내용**을 가졌다. P20은 다르다:
(a)와 (b)는 **같은 이분법의 여집합**이라 (a)=지지이면 (b)=지지가 논리적으로
수반된다. 즉 이 절은 한 증거로 `지지` 칸을 **두 번** 채운다. 대차대조가 팔 단위
계수를 낼 때 이만큼 부풀려진다. 어휘에 "여집합 수반 팔"을 가르는 값이 없기
때문이며, 이는 c127이 이미 상신한 `마감-조기` 결함(닫힘 방식만 담고 방향을
버린다)과 **같은 계열의 어휘 결함**이다. → 회고 c130 의제로 상신(관측 75).

P20 (c)·P25 (d)는 등록문이 스스로 "비-예측"이라 선언한 팔이므로 `비예측`.
(P20 (c): "**(c) 비-예측(범위 한정)**: 이 예측은 **턴 수**만 다룬다."
 P25 (d): "**(d) 비-예측(정직·범위 한정)** — 이 사이클이 주장하는 것은 …까지다.")

왜 줄번호가 아니라 헤딩+현재값을 키로 쓰는가
--------------------------------------------
c127_assign_status.py는 줄번호를 키로 써서 **설계상 1회용**이 됐다(부여 후 파일이
밀려 재실행 불가). 이 계기는 헤딩 id로 절을 찾고 현재값이 `무기재`인지 확인한
뒤에만 쓴다 — 이미 적용됐으면 그 사실을 인쇄하고 **아무것도 하지 않는다**(멱등).
P7만 절이 2개이므로 대상 id의 절이 정확히 1개임을 단언한다.

사용: .venv/bin/python research/devloop/scripts/c128_record_verdicts.py [--apply]
      (기본 dry-run)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PRED = ROOT / "research" / "devloop" / "predictions.md"

HEAD_RE = re.compile(r"^##\s+(P\d+[a-z]?)\s*[—-]")
STATUS_RE = re.compile(r"^-\s*상태:\s*(.+?)\s*$")

# c127이 확립한 13값 + 하자 라벨. 어휘 밖 값은 하드 에러(c124_retro_prep와 동일 규율).
VOCAB = {
    "지지", "반증", "부분",
    "시계-미시작", "시계-가동",
    "마감-표본부재", "마감-무판정", "마감-기한도과", "마감-조기", "마감-미가동",
    "전제소멸", "폐기", "비예측",
    "무기재",
}

# ── 부여 표 (이 표가 감사 원본이다) ────────────────────────────────────────
# (P-id, 기대 현재값, 새 값, 원장 출처, 절에 덧붙일 처분 문단)
ASSIGN: list[tuple[str, str, str, str, str]] = [
    (
        "P20",
        "무기재",
        "(a) 지지 · (b) 지지 · (c) 비예측",
        "원장 c69 restore_note · c70 work/restore_note",
        """- **처분 (사이클 128, 소급 기재 — 판정은 c69, 대장 전사만 누락됐다)**: 이 절의 판정은
  등록 당시 실제로 내려졌고 원장에 있었으나 대장에 오지 않았다. 출처를 명시해 옮긴다.
  - **(a) 지지 (4/4).** 원장 c69 restore_note 원문: "★ P20 (a) 판정 = 지지 확정 (4/4).
    c66·c67·c68·c69 전부 restore_turns 3 · floor 3 · 초과분 0. 캡슐 next_actions[0]이
    이 턴 배치를 명시적으로 지시했고 그대로 따랐다." 원장 c70 work가 "P20 (a) 시계
    종료(c69 지지 4/4)"로 재확인. **캐비앗(등록문 정직 병기 ②의 발동)**: A-65.1 미승인으로
    원장에 `restore_floor` 필드가 없어 **절대값 3을 대리 지표로** 썼고, c69가 그 대리
    사용을 규정대로 자기 행에 명기했다. 따라서 "초과분 0"은 직접 측정이 아니라 대리 측정이다.
  - **(b) 지지 (팔 비발동).** 역방향 팔의 격발 조건("4가 유지되면")이 창 c66~c69에서
    0회 발화 = 등록 조건 미충족. 선례 귀속: P34 (b) "팔 비발동 … 등급 조건 미충족 =
    채널 건재"(c127 배정 `지지`)와 동형이므로 같은 값을 준다.
    **자기 불리 병기**: P34와 달리 P20의 (a)(b)는 같은 이분법의 여집합이라 (b)는 (a)에
    논리적으로 수반된다 — 이 절은 한 증거로 `지지` 칸을 두 배 채운다. 어휘에 "여집합
    수반 팔"이 없어 생기는 부풀림이며, 대차대조 팔 단위 계수를 이만큼 읽어내려야 한다.
    → 관측 75로 등재, 회고 c130 의제(`마감-조기` 결함과 같은 계열).
  - **(c) 비예측.** 등록문 자체가 "비-예측(범위 한정)"으로 선언 — 판정 대상 아님.""",
    ),
    (
        "P25",
        "무기재",
        "(a) 지지 · (b) 지지 · (c) 지지 · (d) 비예측",
        "원장 c81 work · tests",
        """- **처분 (사이클 128, 소급 기재 — 판정은 c81 당일, 대장 전사만 누락됐다)**: 등록문의
  "판정: (a)(b)(c)는 이 사이클 안에서 즉시"는 **지켜졌다.** 계기
  `c81_phrase_qual_regression.py`가 그날 돌았고 결과가 원장 c81 행에 있다. 하자는
  판정 부재가 아니라 **전사 누락**이었다 — 출처를 명시해 옮긴다.
  - **(a) 지지 — 대수 동치 64/64.** 원장 c81 work: "(a) 대수 동치 64/64 히트
    (fixtures_cycle22 전수, 신점수=구점수−junk — 유일 델타가 junk 항임을 동결 재현으로
    기계 확인)". 등록문의 반증 조건("1건이라도 불일치")은 발동하지 않았다.
  - **(b) 지지 — c22 T2b 랭크 재현 8/8.** 원장 c81 work: "tau·top-1 전수 일치:
    e2ee 0.6429, compression top-1 훼손까지 재현 — **recency 앵커 캐비앗 무발동**".
    등록문이 미리 선언한 캐비앗(c22 실행 시각 미기록 → recency 항이 박빙 쌍을 뒤집을
    수 있다)은 쓸 일이 없었다.
  - **(c) 지지 — 제품 테스트 무손상.** 원장 c81 tests: "357 passed … 기존 단언 완화
    0건 = P25 (c) 적중." 등록문의 롤백 조항(단언을 물러야 통과하면 회귀 신호)은 미발동.
  - **(d) 비예측.** 등록문이 "비-예측(정직·범위 한정)"으로 선언. 그 범위 규율은 c81이
    실제로 지켰다 — frictions_note에 "P25 (d) 준수: F2를 fixed로 계상하지 않는다"가
    기재됐고 `frictions_fixed`는 0이었다. 라이브·벤치 팔은 ⑮ 배포 + P8 (i-b) 몫으로 존속.""",
    ),
]


def parse_sections(lines: list[str]) -> dict[str, list[int]]:
    """P-id → 헤딩 줄 인덱스 목록 (P7은 2개)."""
    out: dict[str, list[int]] = {}
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if m:
            out.setdefault(m.group(1), []).append(i)
    return out


def section_bounds(lines: list[str], start: int) -> int:
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            return j
    return len(lines)


def check_vocab(value: str) -> list[str]:
    """`(a) X · (b) Y` 또는 단일값을 어휘 대조. 어휘 밖 값을 반환."""
    bad = []
    for part in value.split("·"):
        part = part.strip()
        part = re.sub(r"^\((?:[a-z]|비)\)\s*", "", part).strip()
        if part and part not in VOCAB:
            bad.append(part)
    return bad


def main() -> int:
    apply = "--apply" in sys.argv
    text = PRED.read_text(encoding="utf-8")
    lines = text.split("\n")
    sections = parse_sections(lines)

    print("c128 — 무기재 잔여 2건 소급 기재 (원장 직독 근거, 짐작 0)")
    print("=" * 78)

    # 검증 0: 어휘 사전 대조 (쓰기 전에 막는다)
    for pid, _, new, _, _ in ASSIGN:
        bad = check_vocab(new)
        if bad:
            print(f"[FATAL] {pid}: 어휘 밖 값 {bad} — VOCAB 추가 사유를 헤더에 남기고 다시 실행하라")
            return 2
    print("[검증 0] 어휘 대조 통과 — 신규 어휘 0값 (13값 체계 유지)")

    edits: list[tuple[int, str, int, str]] = []  # (상태줄idx, 새줄, 삽입idx, 처분문단)
    for pid, expect, new, src, disposition in ASSIGN:
        heads = sections.get(pid, [])
        # 검증 1: 절 유일성 (P7 번호 충돌 방어)
        if len(heads) != 1:
            print(f"[FATAL] {pid}: 절이 {len(heads)}개 — 헤딩 id 단독 지목 불가")
            return 2
        h = heads[0]
        end = section_bounds(lines, h)

        # 검증 2: 상태 줄 존재 + 현재값 일치 (멱등성 게이트)
        st_idx = None
        for j in range(h + 1, end):
            m = STATUS_RE.match(lines[j])
            if m:
                st_idx = j
                cur = m.group(1)
                break
        if st_idx is None:
            print(f"[FATAL] {pid}: `- 상태:` 줄 부재 — c127 부여가 훼손됐다")
            return 2
        if cur != expect:
            if cur == new:
                print(f"[SKIP ] {pid}: 이미 '{new}' — 멱등 통과, 아무것도 하지 않는다")
                continue
            print(f"[FATAL] {pid}: 현재값 '{cur}' ≠ 기대 '{expect}' — 제3자가 손댔다. 중단")
            return 2

        print(f"\n[{pid}] {cur}  →  {new}")
        print(f"       출처: {src}")
        print(f"       상태줄 L{st_idx + 1} / 처분 문단 삽입 L{end}")
        edits.append((st_idx, f"- 상태: {new}", end, disposition))

    if not edits:
        print("\n변경 없음 (전부 멱등 통과).")
        return 0

    if not apply:
        print("\n(dry-run — 적용하려면 --apply)")
        return 0

    # 뒤에서부터 적용해야 앞의 인덱스가 밀리지 않는다
    for st_idx, new_line, ins_idx, disposition in sorted(edits, key=lambda e: -e[0]):
        lines[st_idx] = new_line
        block = disposition.split("\n")
        lines[ins_idx:ins_idx] = block + [""]

    PRED.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[적용] {PRED.relative_to(ROOT)} — 상태 {len(edits)}건 갱신 + 처분 문단 {len(edits)}건 삽입")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
