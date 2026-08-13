#!/usr/bin/env python
"""c113 원장 행 append (P34 판정 사이클 — 기한 준수 마감).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 0회 (task_state가 P34 기한·우선순위·창 마감 조건까지 배달했고, 판정 재료는
  predictions.md/frictions.md 정독 + 원장 프로그램 파싱이지 회상이 아니다).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다.

중복 방지: cycle 113 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 113,
    "date": "2026-08-13",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 선적재 하네스 — ToolSearch "
        "불요, 규약 ④ 목적물 충족 계상) / 턴2 = get_task_state + c48_step0_check.py + git "
        "status 병렬 — 파트 S ledger_last=112/task_state_cycle=112 판정=일치, freshness "
        "fresh·age 0.35h / 턴3 = 첫 유효 행동(P34·관측 61 판정 재료 정독) = restore_turns 3. "
        "규약 ③ 준수 — metrics 접촉은 파트 F 인쇄·분석용 프로그램 파싱·append 스크립트뿐, "
        "tail/cat/head 0회. ★ grade full 근거 한 줄: task_state가 1순위의 조건 게이트(관측 "
        "59 ③ 창 마감 = 13:40:22 이후, 이 세션 12:19 개시로 미충족)와 동시 의무(P34 판정 "
        "기한 = c113 원장 행)·영토 규약(replay/wtrack 미커밋 → 코드 사이클 금지)까지 "
        "배달 — 조건 판정과 작업 선택이 재구성 없이 즉결됐다. 채널 분해: task_state 단독 "
        "full / 캡슐 단독 miss — W-트랙 점유(F2 재계수 c90~c113 = 24/24 · 세션 기준 "
        "27연속, 파트 B capsule_sha 7a3d35a84deaac41 실측)."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 17,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — P34 기한·창 마감 조건·영토 규약 배달, 이 세션 작업 선택의 원천. ② 캡슐 = "
        "miss — W-트랙 점유, 실작업 무교차. ★ (1·1) 17연속 — recall_constant_streak>0 "
        "구간이므로 회상 품질 표본 아님(audit-110 R5 마커 관행 4회째). 계기 검색 제외 유지. "
        "검산: 직전 행 c112 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 관측 0 · 해소 계상 0. 관측 61 수용 기준 ① 이행 — P34 판정(이 행 + "
        "predictions.md 부기)이 표본을 심리, 처분 문단 기재(존속 — 유형 귀속 회부 유지, "
        "부분을 해소로 계상하지 않는다: c112 관행 승계). ② 계보는 이 append 스크립트가 승계. "
        "판정 부산물 1건은 predictions.md 판정 부기로 기록(신규 관측 아님): P34 반증 조항이 "
        "위반 기전을 파서측 단일로 선예단 — 실제 위반(c111)은 쓰기측이었고 파서는 검출 "
        "당사자였다. 예측 설계 교훈으로 P-원장에 남긴다."
    ),
    "open_observations": 31,
    "open_observations_note": (
        "Δ 선언: c112=31 → c113=31, Δ+0 — 신규 등재 0·회부 이탈 0. 파트 F 인쇄값 31과 일치. "
        "무태그 {27,42,49,52} · 회부 이탈 {53,56,57} 불변. 관측 61 처분 문단은 존속 마커 "
        "규약('종결'/'회부 상태를 벗' 부재)으로 계상 불변임을 기재 시점에 확인."
    ),
    "tests": (
        "436 passed(10.22s, 7 warnings). **+5 vs c112 기재 431 — 선언 동반**: 델타는 타 세션 "
        "커밋 9c5f1bd(자기개선 세션, fix(recall/eval))의 신규 테스트 2파일 "
        "(test_claim_eval_matched.py·test_mcp_project_scope.py, git diff --stat d2c4ce4..HEAD "
        "실측)에 귀속 — c112의 venv 드리프트와 달리 이번 델타는 커밋된 소스가 특정된다. "
        "devloop의 tests/·제품 코드 접촉 0. 절차 4 커밋 게이트: 코드 변경 0으로 비발동, "
        "regression_watch 녹색. 몸 지문(파트 Body) 대조 일치 — 단 forget/server.py·store.py가 "
        "9c5f1bd로 변경됐음을 병기(타 세션 몫, devloop 계상 밖)."
    ),
    "product_code_unchanged_streak": 6,
    "gate_pending": (
        "신규 상신 0 · 판정 마감 1: **P34 (a) 반증 — 위반 1건(c111 무선언 필드 탈락), 기한 "
        "준수(판정 채널 = 이 행 + predictions.md 부기). (b) 팔 비발동(창 내 파서 오분류 0). "
        "산문-값 쟁점 기각 — 필드는 계기 눈을 위한 것, 산문 수용은 채점 기준 완화. 파생 계기 "
        "존속, A-95.1 지시서 몫 자동 승격 없음(게이트 큐 유지).** 유지: 배포 영수증(무게이트 "
        "후속 강등 상신 중) · audit-110 R1·R4 · A-106.1 · A-105.1 · A-105.2 · A-65.2 5차 · "
        "R4 · R5 · ㉖㉗㉙ · A-95.1(지시서 몫+아카이브 분할②) · A-95.2 · A-95.3 · A-55.1 · "
        "묶음 B. 시계: P2 2026-08-31 기한(18일) · A-85.1 c116 · P30 (b)(c) 트리거형 · P35 "
        "트리거형 c122 · P36 2026-09-10(실행 세션 몫) · 관측 59 ③ 창 마감 대조 = **c114 "
        "1순위 승계**(조건: 세션 시각 08-13 13:40:22 이후 — 이 세션 12:19 개시로 미충족, "
        "닫지 않았다; 기준 문면 notes/cycle-111 §3 표). 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**P34 판정 사이클 — 기한 도과 없이 마감 (관찰·판정, 코드 0).** 영토: replay/wtrack "
        "미커밋 타 트랙 변경 → 코드 사이클 금지, 관측·판정 사이클로 전환(절차 2). 1순위 관측 "
        "59 ③은 조건 미충족(13:40:22 이전)으로 c114 승계, 동시 의무 P34 판정(기한 = 이 행)을 "
        "수행. ① 원장 전행 프로그램 파싱 실측: c109=30·c110=30·c112=31(선언 동반) 값 충족, "
        "c111 두 필드 무선언 탈락(키 차집합 dropped 2종), 창 내 수기 재계수 스크립트 0건, "
        "파서 오분류 0건. ② 판정: (a) 반증 — 위반 1건(c111), 산문-값 쟁점 기각. (b) 비발동. "
        "③ 정직 병기: 등록 반증 결론('파서가 못 따라간다')은 기전 오예측 — 위반은 쓰기측, "
        "파서는 검출 당사자. 실처치는 관측 61 ② 계보(키 차집합 인쇄, 이 스크립트 승계)이고 "
        "A-95.1 지시서 몫은 자동 승격 없음. ④ 관측 61 처분 문단(① 이행, 존속) 기재. 외부 "
        "API $0 · 실DB 파괴적 조작 0 · 배포 0 · 제품 코드 0."
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
