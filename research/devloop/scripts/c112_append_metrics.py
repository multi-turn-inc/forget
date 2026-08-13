#!/usr/bin/env python
"""c112 원장 행 append (F2 처치 착수 사이클 — 승계 완결).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 0회 (task_state next_actions가 작업 후보·조건까지 배달했고, 기전 검증은
  소스 정독이지 회상이 아니다).

관측 61 수용 기준 ② 이행 (이 스크립트부터):
- 탈락 필드 복원: open_observations · recall_constant_streak.
- append 계기가 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고, 선언 없는 탈락이면
  append를 거부한다 — 무선언 탈락을 다음 사이클이 아니라 그 자리에서 잡는다.

중복 방지: cycle 112 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 112,
    "date": "2026-08-13",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 선적재 하네스 — ToolSearch "
        "불요, 규약 ④ 목적물 충족 계상) / 턴2 = get_task_state + c48_step0_check.py + git "
        "status 병렬 — 파트 S ledger_last=111/task_state_cycle=111 판정=일치, freshness "
        "fresh·age 11h / 턴3 = 첫 유효 행동(선임 세션 잔여물 조사 착수) = restore_turns 3. "
        "규약 ③ 준수 — metrics 접촉은 파트 F 인쇄와 이 스크립트뿐, tail/cat/head 0회. "
        "★ grade full 근거 한 줄: task_state가 승계 규약(git log 대조+빵부스러기 확인)과 "
        "창 마감 조건(13:40 이전 세션은 관측 59 ③ 닫지 말 것)까지 배달 — 죽은 선임 세션의 "
        "미커밋 잔여물을 첫 행동에서 정확히 식별·승계했다. 이 세션 자체가 승계 자연실험 "
        "표본이다. 채널 분해: task_state 단독 full / 캡슐 단독 miss — W-트랙 점유(F2 재계수 "
        "c90~c112 = 23/23 · 세션 기준 26연속, 후속 세션 sha dad9c98017611c55 파트 B 실측, "
        "선임 세션 앵커 sess 4034a1f0)."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 16,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 승계 규약·창 마감 조건·작업 후보 서열 배달, 이 세션 계획의 원천. ② 캡슐 = "
        "miss — W-트랙 점유, 실작업 무교차. ★ (1·1) 16연속 — recall_constant_streak>0 "
        "구간이므로 회상 품질 표본 아님(audit-110 R5 마커 관행 3회째). 계기 검색 제외 유지. "
        "검산: 직전 행 c111 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인). "
        "recall_constant_streak 필드는 c111에서 무선언 탈락(관측 61) — 이 행부터 복원, "
        "산문 계보(c111 '15연속')와 연속."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 관측 1 = 관측 61(원장 필드 무선언 탈락 — 선임 세션 기재, c112 계상): "
        "open_observations·recall_constant_streak가 c111 행에서 무선언 탈락, 파트 F Δ 눈이 "
        "한 사이클 멀었다. 수용 기준 ② 이행 = 이 행부터 필드 복원 + append 계기의 키 차집합 "
        "쓰기 시점 인쇄(scripts/c112_append_metrics.py). ① P34 판정(c113)이 심리, ③ "
        "append-only — 회부 존속, fixed 0(부분을 해소로 계상하지 않는다). 보강 2건: "
        "(a) F2 승계 병기 — 선임 세션(sess 4034a1f0) 완주 선기재 후 사망, 산출물 3종 부재를 "
        "후속 세션이 실작성으로 완결(관측 55·43 계열 라이브 재발, 무대는 대장 자신) + 제2 "
        "기전 다리 신규 실측(store.py:11996 goal-폴백 active-only 스캔). (b) 관측 54 계열 — "
        "tests +6이 공유 venv 환경 드리프트로 판명(아래 tests 선언)."
    ),
    "open_observations": 31,
    "open_observations_note": (
        "Δ 선언: c110=30 → c111 필드 부재(관측 61의 표본 그 자체) → c112=31, c110 대비 +1 = "
        "관측 61 신규 등재. 파트 F 인쇄값 31과 일치(P34 (a) 요건). 무태그 {27,42,49,52} · "
        "회부 이탈 {53,56,57} 불변."
    ),
    "tests": (
        "431 passed(10.59s, 7 warnings). **+6 vs c111 기재 425 — 선언 동반**: 테스트 파일 "
        "변경 0(fc17dd1·24baf54·이번 사이클 전부 tests/ 무접촉, git show --stat 실측), 제품 "
        "코드 변경 0. 델타는 공유 venv 환경 드리프트로 귀속 — importorskip 게이트(numpy· "
        "nacl·uvicorn 계열, test_vector_scale.py 5건은 numpy 게이트 실측)가 W-트랙 torch "
        "스택 설치로 수집 확대. 관측 54 계열(공유 작업장 소유권 — 파일에서 환경으로 확장) "
        "보강 계상. 절차 4 커밋 게이트: 코드 변경 0으로 비발동, regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 5,
    "gate_pending": (
        "신규 상신 0 · 등록 1: P35(트리거형 — F2 친화 줄 구현 코드 사이클 + 배포 게이트 통과 "
        "후 가동, c122 트리거 도과 조항). F2 구현 자체는 게이트 아님·코드 사이클 대기(이번 "
        "사이클은 replay 트랙 미커밋 변경으로 세션 영토 코드 금지). 유지: 배포 영수증(무게이트 "
        "후속 강등 상신 중) · audit-110 R1·R4 · A-106.1 · A-105.1 · A-105.2 · A-65.2 5차 · "
        "R4 · R5 · ㉖㉗㉙ · A-95.1(지시서 몫+아카이브 분할②) · A-95.2 · A-95.3 · A-55.1 · "
        "묶음 B. 시계: P2 2026-08-31 기한 · A-85.1 c116 · P30 (b)(c) 트리거형 · P34 판정 "
        "c113(이 행도 표본: 수기 재계수 0건·파트 F 값 31 = 이 행 open_observations 일치·Δ "
        "선언 동반) · P35 트리거형 c122 · 관측 59 ③ 창 마감 대조 = c113 몫(마감 08-13 "
        "13:40:22, 이 세션은 11:48 개시로 조건 미충족 — 닫지 않았다). 원칙 5 준수 — 전부 큐, "
        "무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**F2 처치 착수 사이클 — 죽은 선임의 선언을 후속이 완결 (승계 자연실험).** 선임 "
        "세션(sess 4034a1f0, 11:18)이 frictions.md에 처치 착수 문면(P35 등록+설계 노트)을 "
        "기재 직후 사망 — 산출물 3종 전부 부재(관측 55·43 계열, 완주 선기재의 대장판). 후속 "
        "세션: ① 기전 소스 재검증 — 선임 문면(store.py:6805 latest-write-wins) 일치 확인 + "
        "제2 다리 신규 실측(:11996~12026 goal-하이재킹 폴백도 active만 스캔 → completed로 "
        "닫는 devloop는 캡슐 1차 슬롯 양쪽 경로에서 구조 배제). ② P35 실등록(트리거형, 옵션 B "
        "'작업장 친화 줄' — 가산적, 1차 슬롯 불변; 옵션 A 재정렬 기각: 유동층 정직성+타 트랙 "
        "요동). ③ 설계 노트 notes/cycle-112-f2-capsule-affinity-design.md(승계 기록 §0 포함). "
        "④ 관측 61 수용 기준 ② 이행 — 이 스크립트가 탈락 필드 2종 복원 + 키 차집합 쓰기 시점 "
        "인쇄(무선언 탈락 거부). ⑤ F2 승계 병기(세션 26연속). 외부 API $0 · 실DB 파괴적 조작 "
        "0 · 배포 0 · 제품 코드 0."
    ),
}


def main() -> int:
    with open(LEDGER, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if any(r.get("cycle") == ROW["cycle"] for r in rows):
        print(f"cycle {ROW['cycle']} 행이 이미 있다 — 아무것도 하지 않음 (원장 무중복 불변식)")
        return 0
    prev = rows[-1]
    added = sorted(set(ROW) - set(prev))
    dropped = sorted(set(prev) - set(ROW))
    print(f"[키 차집합 — 관측 61 ②] 직전 행 cycle={prev.get('cycle')}")
    print(f"  added:   {added or '∅'}")
    print(f"  dropped: {dropped or '∅'}")
    undeclared = [k for k in dropped if k not in DECLARED_DROPS]
    if undeclared:
        print(f"  거부: 무선언 탈락 {undeclared} — DECLARED_DROPS에 사유를 선언하라")
        return 1
    for key, reason in DECLARED_DROPS.items():
        print(f"  선언된 탈락: {key} — {reason}")
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(ROW, ensure_ascii=False) + "\n")
    print(f"appended: cycle {ROW['cycle']} ({ROW['date']}) — 행 수 {len(rows)} → {len(rows)+1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
