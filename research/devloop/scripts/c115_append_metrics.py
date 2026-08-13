#!/usr/bin/env python
"""c115 원장 행 append (회고 사이클 — 2세션 승계 완주).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 0회 (세션1: 회고 입력은 전부 파일·원장 직독 — amendment-115 입력 명세.
  세션2: 승계 판단 재료는 git status·mtime·grep 실측이지 회상이 아니다).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: session_count
(audit-110 R3 채택 — amendment-115 §5-R3, 무게이트 선례 open_observations c105 준용).

중복 방지: cycle 115 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 115,
    "date": "2026-08-14",
    "session_count": 2,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "2세션 사이클 — 채점 원천은 세션2(수확 세션, 08-14 00:50 개시); 세션1(회고 본문 "
        "필자, 08-13 13:35 개시)의 자기 step0은 amendment-115 부록 B에 보존(같은 값: turns "
        "3·full/캡슐 miss). 세션2 턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 "
        "기적재 하네스, ToolSearch 불요) / 턴2 = get_task_state + c48_step0_check.py + git "
        "status 병렬 — N=115 회고(스크립트 첫 줄 정본), 파트 S ledger_last=114/"
        "task_state_cycle=114 판정=일치, freshness fresh(age 11.6h), Body 24/24 일치 / "
        "턴3 = 첫 유효 행동(선기재 산출물 실재 검증 직행) = 3. 규약 ③ 준수 — metrics 접촉은 "
        "파트 F 인쇄·append 스크립트뿐, tail/cat/head 0회. ★ grade full 근거 한 줄: "
        "task_state 승계 규약(완주 선기재 시 산출물 실재 검증 우선)이 발견 상황(amendment-115 "
        "선기재 + 세션1 사망)을 정확히 지시, 재구성 0으로 승계 판단 즉결 — 관측 43 처치 "
        "계보의 승계 비용 절감 실측 1건. 채널 분해: task_state full / 캡슐 miss — W-트랙/"
        "전략 재정렬 점유(복구된 F2 캡슐 절 표 기준 c90~c115 = 26/26 · 세션 29연속 확정"
        "(+방증 4), 세션2 파트 B capsule_sha f28bfa53bce3a7ee 실측, 세션1 sha 주장 "
        "69723d2a는 미커밋 초안뿐이라 방증 재분류 — c109 준용)."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 19,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 모드 재확인 규칙·쓰기 규약 3종·영토 경고·승계 규약(이 세션 첫 행동의 직접 "
        "원천)까지 배달. ② 캡슐 = miss — W-트랙 점유, 실작업 무교차. 세션1(부록 B)도 동일 "
        "계상이라 단일 행으로 수렴. ★ (1·1) 19연속 — recall_constant_streak>0 구간이므로 "
        "회상 품질 표본 아님(audit-110 R5 마커 6회째 — R5는 이 회고에서 관행 성립 판정, "
        "처분 종료). 검산: 직전 행 c114 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R "
        "인쇄 확인)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 1,
    "frictions_note": (
        "신규 관측 1 = 관측 64(F2 캡슐 절 증분 채널 표류 — 관측 57 계열, 회부; 수용 기준 ① "
        "표 소급 복구는 이 사이클 집행, ② 감시 3사이클 잔여). 보강 1(신규 번호 아님) = 관측 "
        "55 재발 표본: 세션1이 amendment-115의 집행 선언(관측 64 등재·표 복구)을 완료형으로 "
        "기재한 채 수확 전 사망 — 승계 규약이 작동해 세션2가 검증 후 잔여 집행. fixed 1 = "
        "관측 61 회부 이탈(amendment-115 §3-1 — 수용 기준 3항 이행 실측: P34 판정 완료 + "
        "키 차집합 처치 3표본 관행 성립 + append-only 유지; 처치 코드 자체는 c112 기설치, "
        "이 계상은 마감 시점 기준). 추가 처분(존속, fixed 아님): 관측 62·63 계열 표기 + "
        "63의 격발어 회피 잠정 규약 성문(amendment-115 §3-2·§3-3)."
    ),
    "open_observations": 33,
    "open_observations_note": (
        "Δ 선언: c114=32 → c115=33, Δ+1 = 신규 등재 +1(관측 64). 관측 61은 c114 인쇄에서 "
        "이미 이탈(파서 위양성)이었고 이 회고의 실마감(§3-1, 처분 헤더에 정형 마감어)으로 "
        "이탈이 정당화됐다 — c115부터 파트 F 인쇄와 진실 재정렬, 원장 행 존속 선언 보정 "
        "의무 소멸. 무태그 {27,42,49,52} 불변 · 회부 이탈 {53,56,57,61}."
    ),
    "tests": (
        "437 passed(9.25s, 8 warnings) — c114 기재 436 대비 델타 +1. 소유권 병기(관측 54 "
        "관행): 트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py· "
        "research/twin/discriminator_gate_v0.py) 잔존 — +1은 그 미커밋 diff의 신규 테스트 "
        "함수 1건(git diff `def test_` +1/−0 실측)으로 귀속, devloop 소유 델타 0. devloop의 "
        "제품 코드·tests/ 접촉 0, 절차 4 커밋 게이트 비발동(문서·원장·스크립트만), "
        "regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 8,
    "gate_pending": (
        "이 회고의 큐 정리: audit-110 R2(집행 완료 확인)·R5(관행 성립) 처분 종료 — 큐 −2. "
        "신규 상신 2: A-115.1(절차 2 선택문 사유 명기 — audit-110 R4 문면화) · A-65.2 6차"
        "(부분 해제, 계열 표기 6건째 근거). 1급 산출물: §6 원터치 결정 패킷(큐 전 항목 서열 "
        "+1줄 승인 요청 — N5 루프 몫 집행). 유지: 배포 영수증(강등 상신 중) · audit-110 R1· "
        "R4(→A-115.1) · A-106.1 · A-105.1 · A-105.2 · ㉖㉗㉙ · A-95.1 · A-95.2 · A-95.3 · "
        "A-55.1 · 묶음 B. 시계: P2 2026-08-31 기한(17일) · A-85.1 c116 · P30 (b)(c) 트리거형 "
        "· P35 c122(구현은 §6 서열 2 상신) · P36 2026-09-10(실행 세션 몫) · 관측 59 ③ 창 "
        "마감 대조 = c116 1순위 승계(세션2 개시 00:50으로 조건 충족했으나 회고 단일 단위 "
        "규율로 승계 — 조건 게이트는 상시 충족 진입, c116에서 소멸). 원칙 5 준수 — 전부 큐, "
        "무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**회고 사이클(115%5=0) — amendment-115 + 2세션 승계 완주.** 세션1: 개정안 전문"
        "(헤드라인 = 게이트 큐 서비스율 0이 창의 지배 변수, §6 원터치 결정 패킷) + frictions "
        "처분 3건(관측 61 마감·62·63 계열 표기, 63 격발어 회피 잠정 규약) 기재 후 수확 전 "
        "사망. 세션2(이 행의 필자): 선기재 검증(관측 55 재발 표본 보강 기재) → 선언-미집행 "
        "2건 집행 — ① 관측 64 등재(증분 채널 표류, 관측 57 계열) ② F2 캡슐 절 표 소급 복구"
        "(c113·c114·c115 행 + 갱신 문단 재개, c90~c115 = 26/26 · 세션 29연속 확정(+방증 4), "
        "세션1 sha는 c109 준용 방증 재분류) → 부록 C(승계 기록)·§5-R3 정정(session_count 2)· "
        "§7 Q3 병기 → 원장 R3 채택 행. audit-110 처분 5건 완결: R1 존속·R2 종료·R3 채택"
        "(이 행부터)·R4→A-115.1 상신·R5 종료. 외부 API $0 · 실DB 파괴적 조작 0 · 배포 0 · "
        "제품 코드 0(사유 병기: 회고 사이클은 절차 1이 문서 대상으로 지정 + 영토에 twin "
        "트랙 미커밋 잔존 — A-115.1 문면의 선제 이행)."
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
