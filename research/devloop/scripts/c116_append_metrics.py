#!/usr/bin/env python
"""c116 원장 행 append (일반 사이클 — 관측 59 창 마감 대조·마감 + 관측 65 등재).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 0회 (이번 사이클 입력은 전부 파일·게이트 원장 직독 + task_state 주입).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: ∅ (c115 스키마 그대로,
session_count 유지).

중복 방지: cycle 116 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 116,
    "date": "2026-08-14",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스, ToolSearch "
        "불요 — 규약 ④ 목적물 충족) / 턴2 = get_task_state + c48_step0_check.py + git status "
        "병렬 — N=116 일반(스크립트 첫 줄 정본), 파트 S ledger_last=115/task_state_cycle=115 "
        "판정=일치, freshness fresh(age 0.35h), Body 24/24 일치 / 턴3 = 첫 유효 행동(작업 "
        "단위 확정 + 관측 59·cycle-111 §3 기준 문면 정독) = 3. 규약 ③ 준수 — metrics 접촉은 "
        "파트 F 인쇄·append 스크립트뿐, tail/cat/head 0회(분석 목적 grep 1회는 번호 결정 "
        "밖 — CLAUDE.md 허용 문면). ★ grade full 근거 한 줄: task_state next_actions가 "
        "1순위 작업(관측 59 ③ 창 마감 대조)·기준 문면 좌표(notes/cycle-111 §3 표)·병기 "
        "비교량(사망률+타임아웃류)까지 지정, 재구성 0으로 착수. 채널 분해: task_state full / "
        "캡슐 miss — W-트랙/전략 재정렬 점유(F2 캡슐 절 표 c116 행, 파트 B sha "
        "cfebb4393f7d7d49 실측, c90~c116 = 27/27 · 세션 30연속 확정(+방증 4))."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 20,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 작업 단위·기준 문면 좌표·영토 경고·A-85.1 시계까지 배달(이 사이클 선택의 "
        "직접 원천). ② 캡슐 = miss — W-트랙 점유, 실작업 무교차. ★ (1·1) 20연속 — "
        "recall_constant_streak>0 구간이므로 회상 품질 표본 아님(마커 7회째). 검산: 직전 행 "
        "c115 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 1,
    "frictions_note": (
        "fixed 1 = 관측 59 마감(회부 이탈 — 수용 기준 3항 이행 실측: ① TimeoutError 자연 "
        "표본 9/9 단일 클래스 귀속 ② 오류 필드 라이브(08-12 배포) ③ 동일 창 길이 24h 전후 "
        "대조 기재 — 계기 c116_obs59_window_close.py, c111 §3 두 창 재현 2/2 교정 통과). "
        "신규 관측 1 = 관측 65(high 기어 타임아웃의 구조성 — 후창 타임아웃류 7건 전부 high, "
        "high 내 7/11=0.636·low 0/17, 기어 구성이 창 대조 발생률 3배의 지배 성분; 관측 59 "
        "잔여 질문 승계, 회부). 관측 64 감시 ② 1/3회차 이행: F2 표 c116 행 + 갱신 문단 "
        "동반(원장 이 행의 계수는 표 재계수의 전사). 파트 F 파서 검증: 편집 직후 재실행으로 "
        "회부 이탈 {53,56,57,59,61}·관측 65 등재 확인."
    ),
    "open_observations": 33,
    "open_observations_note": (
        "Δ 선언: c115=33 → c116=33, Δ+0 = 구성 교체(관측 59 이탈 −1 + 관측 65 등재 +1). "
        "무태그 {27,42,49,52} 불변 · 회부 이탈 {53,56,57,59,61}."
    ),
    "tests": (
        "437 passed(9.79s, 8 warnings) — c115 기재 437과 동일. 소유권 병기(관측 54 관행): "
        "트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py·"
        "research/twin/discriminator_gate_v0.py·research/replay/candidates_v0.jsonl) 잔존 — "
        "+1은 그 diff 소유(c115 실측 승계), devloop 소유 델타 0. devloop의 제품 코드·tests/ "
        "접촉 0(신규 파일은 research/devloop/scripts/ 계기 2본), regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 9,
    "gate_pending": (
        "A-85.1 c116 표본 기회 경과: N%10==6 도래했으나 묶음 B 미승인 — 블라인드 프로브 "
        "미집행(미승인 문면의 그림자 집행 금지), 이 세션은 규약대로 턴2에 get_task_state를 "
        "호출해 프로브 전제 자체가 불성립. 다음 시계 c126. 배포 영수증 강등안(서열 3): "
        "잔여 실측 2건이 전부 완결됐다 — oracle replay 신몸 기준선(c114) + 관측 59 ③ 창 "
        "마감 대조(이 사이클). 남은 것은 정훈의 사후 승인 1문장뿐 — 원터치 결정 패킷 문면 "
        "유효. 유지: A-106.1 · P35 구현(서열 2) · A-65.2 6차 · 묶음 B · A-95.1 · A-115.1 · "
        "A-105.2+영토 TTL · R1 · 후순위 종속. 시계: P2 2026-08-31(17일) · P30 (b)(c) "
        "트리거형 · P35 c122 · P36 2026-09-10(실행 세션 몫). 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반 사이클 — 관측 59 수용 기준 ③ 창 마감 대조 → 3항 완비로 마감 + 관측 65 "
        "등재.** 계기 scripts/c116_obs59_window_close.py(읽기 전용, 게이트 원장 355행 전수 "
        "파싱, c111 §3 두 창 재현 2/2 교정 내장·prompt_head 무인쇄). 결과: 배포 전후 24h — "
        "(a) 사망률 2/24=0.083 → 1/21=0.048 (b) 타임아웃류/시도 2/26=0.077 → 7/28=0.250. "
        "판정 병기: 반감의 실체는 강등 전환, 3배의 지배 성분은 기어 구성(high 시도 1→11, "
        "타임아웃 7/7 전부 high). 정직 병기 2건: 원 창 재현 12/13(경계 반개구간 절단, 13번째 "
        "표본 08-11 20:38:59) · 원 13건 중 3건 테스트 세션(gatetest·nbtest1). 잔여 질문은 "
        "관측 65(high 기어 지연 vs 훅 데드라인)로 승계. F2 표 c116 갱신(27/27·세션 30연속, "
        "관측 64 감시 1/3). 외부 API $0 · 실DB 파괴적 조작 0(게이트 원장 읽기 전용) · 배포 0 "
        "· 제품 코드 0(사유 병기: 영토에 twin 트랙 미커밋 잔존 — 절차 2 관측·측정 사이클 "
        "전환, A-115.1 문면의 선제 이행)."
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
