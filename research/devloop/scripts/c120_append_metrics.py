#!/usr/bin/env python
"""c120 원장 행 append (적대 감사 사이클 — audit-120.md).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 계기 헤더에만 둔다.
- 능동 검색 0회 (감사 입력은 metrics/frictions/predictions/git log — DB 질의 없음).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: ∅ (c119 스키마 그대로).

중복 방지: cycle 120 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 120,
    "date": "2026-08-14",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스, ToolSearch "
        "불요 — 규약 ④ 목적물 충족) / 턴2 = get_task_state + c48_step0_check.py + git status "
        "병렬 — N=120 적대 감사(스크립트 첫 줄 정본: 120%10=0), 파트 S ledger_last=119/"
        "task_state_cycle=119 판정=일치, freshness fresh(age 0.35h), Body 24/24 일치 / 턴3 = "
        "첫 유효 행동(감사 입력 4종 수집 착수) = 3. 규약 ③ 준수 — metrics 접촉은 파트 F "
        "인쇄·프로그램 추출·append 스크립트뿐, tail/cat/head 0회(감사 정독 임무는 파이썬 "
        "필드 추출로 이행 — c48 인쇄 허용 문면). ★ grade full 근거 한 줄: task_state "
        "next_actions가 모드(적대 감사)·감사 규약(입력 4종·금지 3종)·보고서 경로·심문 "
        "표적까지 직접 지정, 재구성 0으로 착수. 격리 오염 2건은 audit-120 §0에 축소 없이 "
        "선언(LOOP.md 절차 0 강제 정독 — 관측 47 기전 재현 · task_state의 감사 표적 조향). "
        "채널 분해: task_state full / 캡슐 miss — 심장박동/W-트랙 점유 회귀(파트 B sha "
        "cbcf8c5be9ec8c5e, c119에서 변경. 자기: 라인은 twin 감사 내용으로 이 세션 행동 "
        "무교차 — c119 기여 hit는 1회성. F2 캡슐 절 표 c120 갱신, c90~c120 = 31/31 · 세션 "
        "34연속 확정(+방증 4))."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 1,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 모드·감사 규약·보고서 경로·심문 표적 배달(이 세션 행동의 직접 원천). ② 캡슐 "
        "= miss — 심장박동/W-트랙 점유, 자기: 라인 포함 실작업 무교차. ★ (1·1) 재개 1회째 "
        "— c119 (2·0)로 상수 22 구간이 끝났고 이 행부터 streak 1 재적립(구간 중 회상 품질 "
        "표본 아님 마킹 관행 유지). 감사 특기: 능동 0의 24사이클 누적 자체를 관측 68로 "
        "등재 — 이 필드가 주입 품질계로 의미가 좁아진 상태(audit-120 §2-2). 검산: 직전 행 "
        "c119 fields(2·0) = 성분(능동 0·0/주입 2·0) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "등재 1 = 관측 68(능동 회상의 소멸 — c97~c120 24사이클 능동 search_memories 0회, "
        "같은 구간에 회상 경로 결함 실측 최정밀(관측 65·66·67); 경합 가설 3종(적응 회피/"
        "수요 소멸/습관 표류) 미판별 병기, 수용 기준 = oracle replay 차집합 판별 → 최소 "
        "개입 전후 대조. 관측 65·66·67 인접·F5 읽기측 대칭, 회부). 해소 0 — 감사 규약상 "
        "코드 변경 금지. 감사 권고 5건(audit-120 §5): R1 관측 63 처치 조건 재스코프(파서는 "
        "devloop 전속 계기 영토 — twin 잔존과 무관, 회고 몫) · R2 처치-대기 나이 파트 F "
        "인쇄 · R3 상수 종료 hit 영수증 의무화 · R4 P16 결과란 소급+P7 ID 중복 해소 · R5 "
        "restore_turns 목표 1 문면 처분(규약 바닥 3과 모순). 파트 F 파서 검증: 편집 직후 "
        "재실행 — open 35(Δ+1: +68), 회부 이탈 {53,56,57,59,61,64} 불변."
    ),
    "open_observations": 35,
    "open_observations_note": (
        "Δ 선언: c119=34 → c120=35, Δ+1 = 등재 1(관측 68) − 이탈 0. 무태그 {27,42,49,52} "
        "불변 · 회부 이탈 {53,56,57,59,61,64} 불변."
    ),
    "tests": (
        "437 passed(10.58s, 8 warnings) — c119 기재 437과 동일. 소유권 병기(관측 54 관행): "
        "트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py·"
        "research/replay/candidates_v0.jsonl) 잔존 — +1은 그 diff 소유(c115 실측 승계), "
        "devloop 소유 델타 0. devloop의 제품 코드·tests/ 접촉 0(신규 파일은 감사 보고서 + "
        "이 append 스크립트), regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 13,
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷(남은 것은 정훈의 사후 승인 1문장). 유지: "
        "A-106.1(서열 1) · P35 구현(서열 2, 시계 c122) · A-65.2 6차 · 묶음 B(A-85.1 포함, "
        "다음 시계 c126) · A-95.1 · A-115.1 · A-105.2+영토 TTL · R1 · 후순위 종속. 시계: "
        "P2 2026-08-31(17일) · P30 (b)(c) 트리거형 · P36 2026-09-10(실행 세션 몫). 신규 "
        "게이트 상신 1: audit-120 R5(restore_turns 목표 문면 처분 — 헌장 개정이므로 회고 "
        "경유 정훈 게이트). R1~R4는 무게이트(회고·계기·문서 몫). 원칙 5 준수 — 전부 큐, "
        "무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**적대 감사(120%10=0) — audit-120.md 작성 + 관측 68 등재. 코드 변경 0(감사 규약).** "
        "입력: metrics 120행(프로그램 추출+최근 6행 전문)·frictions(구조+관측 64~67 전문)·"
        "predictions(구조+P4/P5/P6/P7/P16/P19)·git log -30. 독립 재도출 1건: 파트 F 재실행 "
        "= c119 선언 34 일치. 판정 3문: ① 채점 연화 불검출(정의 A·상수 마킹·자기 불리 "
        "채점·반증 기재 실작동; c119 캡슐 hit는 기각 않되 규약 공백 — 타 채널 동시 배달 "
        "대조·턴 순서 영수증 부재) ② 지표 3개 정보 소진(restore_turns 26사이클 상수 3 = "
        "규약 바닥, 헌장 목표 1과 모순 방치 / recall = 능동 0 × 24사이클로 주입 품질계화 / "
        "fixed = 처치 용량 0 아래 문서 마감 계수, streak 13·open 단조 28→35) ③ 회피 마찰 "
        "2건 지명: 관측 63 파서 수정의 과잉 분류(계기 영토는 twin과 무관 — 신규 계기는 "
        "매 사이클 만들면서 기존 계기 수리만 코드 사이클로 묶은 무근거 선) · 능동 회상 "
        "소멸(관측 68 신규). 원장 위생 2건: P7 ID 중복·P16 결과란 부재(판정은 c66 원장 "
        "행에만). 총평: 위험은 채점 연화가 아니라 측정 대상의 협착 — 다음 5사이클의 "
        "가치는 새 관측이 아니라 관측 63·65·66·67 중 하나의 처치 집행. 외부 API $0 · "
        "실DB 파괴적 조작 0(읽기 없음) · 배포 0 · 제품 코드 0(감사 규약)."
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
