#!/usr/bin/env python
"""c119 원장 행 append (일반 사이클 — 측정 전환: 관측 66 ② 계상 가능성 판정).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 계기 헤더에만 둔다.
- 능동 검색 0회 (계기 3본은 search_memories를 호출하지 않는다 — DB·원장 읽기 전용).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: ∅ (c118 스키마 그대로).

중복 방지: cycle 119 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 119,
    "date": "2026-08-14",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "partial",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스, ToolSearch "
        "불요 — 규약 ④ 목적물 충족) / 턴2 = get_task_state + c48_step0_check.py + git status "
        "병렬 — N=119 일반(스크립트 첫 줄 정본), 파트 S ledger_last=118/task_state_cycle=118 "
        "판정=일치, freshness fresh(age 4.3h), Body 24/24 일치 / 턴3 = 첫 유효 행동 = 3. "
        "★ grade full 근거 한 줄: task_state next_actions가 측정 전환 분기(twin 잔존)와 그 "
        "분기의 측정 표적(관측 66 ② 또는 관측 65 재실측)을 직접 지정 — c118 복원 공백의 "
        "처치가 작동, 후보 재구성 없이 즉시 착수. 채널 분해: task_state full / 캡슐 partial — "
        "목표·다음행동 줄은 W-트랙 점유 지속이나 자기: 라인이 c118 교훈(성문 처분 정독 "
        "규칙)을 배달해 이번 선택 절차를 실제로 바꿈(F2 캡슐 절 표 c119 행, 파트 B sha "
        "5d33658ee023c1ed — c117·c118 sha에서 변경, 캡슐 동결 해제. c90~c119 = 30/30 · "
        "세션 33연속 확정(+방증 4))."
    ),
    "recall_hits": 2,
    "recall_misses": 0,
    "recall_constant_streak": 0,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 2·miss 0) → fields hits=2·misses=0. ① task_state = "
        "hit — 측정 표적 직접 지정이 선택 단계를 단축(행동을 바꿈). ② 캡슐 = hit — 자기: "
        "라인의 채택 규칙(후보 확정 전 성문 처분 정독)이 이번 세션에서 실집행됨(관측 66·65 "
        "처분 문단을 선택 전에 정독). ★ (1·1) 상수 구간은 22에서 끝(c97~c118) — c119 = "
        "(2·0), 상수 아님 → recall_constant_streak 0 재설정. 캡슐 hit의 경로가 목표 줄이 "
        "아니라 자기 층 라인인 점이 변화의 실체(F2 점유는 지속). 검산: 직전 행 c118 "
        "fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "등재 1 = 관측 67(high 기어 게이트 래퍼가 trace_id를 네 반환 경로 전부에서 버림 — "
        "store.py:4807·4810·4876·4885; 기억-의존 선언 턴의 record_context_outcome 주소 공백, "
        "고아 트레이스 72/72 실측(top_k=16 ×19 + 구 40 ×53), 관측 66 동근·관측 33 계열). "
        "해소 0 — 관측 66은 부분 처분(존속): 수용 기준 ② 이행 = 필드 발생률 계상 불가 판정 "
        "확정(훅 원장 recall_layer류 키 0 / 게이트 외곽 호출 이벤트 미기록 store.py:4975 / "
        "표지 포함 13행 전수 콘텐츠 인용 판별 / 결정적 음성 대조: c118 창 실측 폴백 6건에 "
        "표지 행 0). 가시화 처치는 코드 사이클 몫(후보 a 훅 _note_gate 필드 추가 — 훅 채널 "
        "게이트 별도 판정 / 후보 b 서버 게이트 자체 이벤트 — 관측 67과 동일 코드 자리, 묶음 "
        "처치 후보). ① 방향 부분 반증거: 폴백 코드 조건 = store.py:4868-4876 정규식 불일치·"
        "유효 인덱스 0·예외 → indices=[], temperature=0이라 프롬프트-결정성 기전과 정합. "
        "파트 F 파서 검증: 편집 직후 재실행 — open 34(Δ+1: +67), 회부 이탈 {53,56,57,59,"
        "61,64} 불변, 관측 66 존속 c119 확인."
    ),
    "open_observations": 34,
    "open_observations_note": (
        "Δ 선언: c118=33 → c119=34, Δ+1 = 등재 1(관측 67) − 이탈 0. 무태그 {27,42,49,52} "
        "불변 · 회부 이탈 {53,56,57,59,61,64} 불변."
    ),
    "tests": (
        "437 passed(10.18s, 8 warnings) — c118 기재 437과 동일. 소유권 병기(관측 54 관행): "
        "트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py·"
        "research/replay/candidates_v0.jsonl) 잔존 — +1은 그 diff 소유(c115 실측 승계), "
        "devloop 소유 델타 0. devloop의 제품 코드·tests/ 접촉 0(신규 파일은 "
        "research/devloop/scripts/ 계기 3본 — 전부 읽기 전용 프로브), regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 12,
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷(남은 것은 정훈의 사후 승인 1문장). 유지: "
        "A-106.1(서열 1) · P35 구현(서열 2, 시계 c122) · A-65.2 6차 · 묶음 B(A-85.1 포함, "
        "다음 시계 c126) · A-95.1 · A-115.1 · A-105.2+영토 TTL · R1 · 후순위 종속. 시계: "
        "P2 2026-08-31(17일) · P30 (b)(c) 트리거형 · P36 2026-09-10(실행 세션 몫). 신규 "
        "게이트 산출물 없음 — 관측 66 가시화 처치(후보 a는 훅 채널이라 배포 게이트 별도 "
        "판정, 후보 b 서버 측)·관측 67 처치·관측 65 잔여·관측 63 파서 수정은 전부 코드/읽기 "
        "사이클 몫이라 큐가 아니라 백로그. 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반 사이클(측정 전환 — 영토에 twin 미커밋 잔존, 절차 2) — 관측 66 수용 기준 ② "
        "이행: 필드 발생률 계상 가능성 판정 = 불가(확정), 부산물로 관측 67 신규 등재.** "
        "계기 scripts/c119_obs66_*.py 3본(전부 읽기 전용 — 실DB sqlite URI mode=ro, 질의 "
        "무인쇄). 판정 근거 3축: ① 훅 게이트 원장 368행에 recall_layer류 키 0(분모 21행 "
        "존재, 분자 분리 불가) ② 서버 게이트 외곽 호출은 이벤트·트레이스 미기록(내부 v1 "
        "기록은 게이트 판정 이전 시점) ③ 표지 포함 13행 전수 콘텐츠 인용 판별 + 결정적 "
        "음성 대조(c118 창 실측 폴백 6건, 표지 행 0). 부산물: 게이트 래퍼가 trace_id도 "
        "버림 — high 기어 턴 피드백 주소 공백·고아 트레이스 72/72 → 관측 67(관측 66 동근, "
        "묶음 처치 후보). 캡슐 첫 hit(c95 이후): 자기: 라인의 채택 규칙이 선택 절차를 실제 "
        "변경 — (1·1) 상수 22에서 종료, F2 점유는 30/30 지속(캡슐 동결 해제 실측). 외부 "
        "API $0(로컬 DB 읽기만) · 실DB 파괴적 조작 0(mode=ro) · 배포 0 · 제품 코드 0(사유 "
        "병기: twin 잔존 — 측정 사이클)."
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
