#!/usr/bin/env python
"""c114 원장 행 append (신몸 기준선 v2 사이클).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 0회 (task_state가 작업 단위·조건 게이트·영토 경고까지 배달했고, 기준선 런의
  재료는 커밋 고정 스크립트 3종 실행이지 회상이 아니다. 계기의 search_memories 호출은
  c68 선언으로 계상 제외 — c59_oracle_replay.py 재실행 2회가 여기 해당).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다.

중복 방지: cycle 114 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 114,
    "date": "2026-08-13",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 선적재 하네스 — ToolSearch "
        "불요, 규약 ④ 목적물 충족 계상) / 턴2 = get_task_state + c48_step0_check.py + git "
        "status 병렬 — 파트 S ledger_last=113/task_state_cycle=113 판정=일치, freshness "
        "fresh·age 0.35h / 턴3 = 첫 유효 행동(1순위 조건 판정 + frictions 우선순위 확인 + "
        "작업 단위 확정) = restore_turns 3. 규약 ③ 준수 — metrics 접촉은 파트 F 인쇄·append "
        "스크립트뿐, tail/cat/head 0회. ★ grade full 근거 한 줄: task_state가 1순위 조건 "
        "게이트(관측 59 ③ 창 마감 = 13:40:22 이후, 이 세션 12:47 개시로 미충족 — c113과 "
        "같은 세션-개시 독법)·영토 경고(replay/wtrack)·차순위 지명(oracle replay 신몸 "
        "기준선 런)·관측 60 규약(>7분 디태치)까지 배달, 작업 선택이 재구성 없이 즉결. "
        "채널 분해: task_state 단독 full / 캡슐 단독 miss — W-트랙 점유 지속(F2 재계수 "
        "c90~c114 = 25/25 · 세션 28연속, 파트 B capsule_sha 7a3d35a84deaac41 실측)."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 18,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 작업 단위·조건 게이트·영토·관측 60 규약 배달, 이 세션 작업 선택의 원천. "
        "② 캡슐 = miss — W-트랙 점유, 실작업 무교차. 계기 검색 제외(c68): "
        "c59_oracle_replay.py 재실행 2회의 search_memories는 계상 밖. ★ (1·1) 18연속 — "
        "recall_constant_streak>0 구간이므로 회상 품질 표본 아님(audit-110 R5 마커 관행 "
        "5회째). 검산: 직전 행 c113 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 2,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 관측 2. ① 관측 62 = 이웃 동반이 계기 분모에 무표지로 승차 — temporal neighbor가 "
        "세 regime 전부 top_k+1, 점수=앵커×0.5, 마커 톱레벨이라 classify() 무시야; 첫 동반 "
        "표본이 자격증명 인접 기억 = read-side disclosure 백로그 #9 실측 1호(관측 33 계열 "
        "귀속 후보, 회부). ② 관측 63 = 부정문이 이탈 마커를 격발 — c113 처분 문단 '종결이 "
        "아니다'가 파서(_EXIT_MARKS 부분문자열)에 종결로 읽혀 관측 61이 인덱스에서 소실, "
        "P34 (b)팔 창-후 첫 실물(창 밖이라 P34 판정 불변; 관측 36 계열 귀속 후보, 회부). "
        "해소 계상 0 — 관측 60 규약은 이 사이클 실발동(gate_audit 9m36s 디태치 수확)으로 "
        "유효성이 실증됐으나 관측 자체는 존속(처분 아님)."
    ),
    "open_observations": 32,
    "open_observations_note": (
        "Δ 선언: c113=31 → c114=32, Δ+1 = 신규 등재 +2(관측 62·63) − 계기측 이탈 1(관측 61 "
        "— **파서 위양성**: c113 처분 문단 '종결이 아니다'의 부분문자열 격발, 진실은 존속 "
        "= 관측 63). P34 관행(필드는 계기 눈을 위한 것)에 따라 값은 c115 파트 F 예상 "
        "인쇄값(세션 개시 인쇄 30 + 신규 2 = 32)을 따르고, 61의 존속 진실은 이 선언이 "
        "보정한다(관측 63 수용 기준 ① 1호 이행). 무태그 {27,42,49,52} 불변 · 회부 이탈 "
        "{53,56,57} + 계기한정 {61}."
    ),
    "tests": (
        "436 passed(8.94s, 7 warnings) — c113 기재 436과 동수, 델타 0·드리프트 없음. devloop의 "
        "tests/·제품 코드 접촉 0. 절차 4 커밋 게이트: 코드 변경 0으로 비발동, regression_watch "
        "녹색. 몸 지문(파트 Body) 대조 일치 — 훅 상수 MAX_RECALLS=3·gate=0.45 문면 불변 확인."
    ),
    "product_code_unchanged_streak": 7,
    "gate_pending": (
        "신규 상신 0 · 판정 마감 0. 이 사이클로 해제된 금지 1: oracle replay 계열 판정 금지는 "
        "신몸 기준선 v2 수립(notes/cycle-114-newbody-baseline.md)으로 해제 — 단 다음 표본부터 "
        "neighbor 채널 분리(관측 62 수용 기준 ①) 필요. 유지: 배포 영수증(무게이트 후속 강등 "
        "상신 중) · audit-110 R1·R4 · A-106.1 · A-105.1 · A-105.2 · A-65.2 5차 · R4 · R5 · "
        "㉖㉗㉙ · A-95.1(지시서 몫+아카이브 분할②) · A-95.2 · A-95.3 · A-55.1 · 묶음 B. 시계: "
        "P2 2026-08-31 기한(18일) · A-85.1 c116 · P30 (b)(c) 트리거형 · P35 트리거형 c122 · "
        "P36 2026-09-10(실행 세션 몫) · 관측 59 ③ 창 마감 대조 = **c115 1순위 승계**(조건: "
        "세션 개시 08-13 13:40:22 이후 — 이 세션 12:47 개시로 미충족; 기준 문면 notes/"
        "cycle-111 §3 표). 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**신몸 기준선 v2 수립 — oracle replay 계열 3종 프로토콜 고정 재실행 (관측·측정, "
        "코드 0).** 영토: replay/wtrack 타 트랙 미커밋 → 코드 금지(절차 2). 1순위 관측 59 ③ "
        "조건 미충족(12:47 개시)으로 c115 승계, 차순위 = c111 §2 지정 신몸 기준선 런 집행. "
        "① oracle replay v2(c59 스크립트 무수정, 1.3s): regime A/B/C = 6/16/26행(top_k+1 "
        "전부), UNSEEN-PASS C분모 8건 전건 판정 아니오 → silent_miss(c58, v2)=0(v2 첫 점, "
        "구몸 연쇄와 불연속). near-miss 대역 0건 — pre-c58 동일 행 상향 실측 = c111 산술 "
        "비교 금지의 직접 실증. ② score_weight v2(seed 43, 3.1s): top-1 changed 6/25(24%)· "
        "tau 0.7660·pool 3668. ③ gate_audit v2(9m36s — 관측 60 규약 실발동·디태치 수확): "
        "add_events 36,621·coverage 0.0393·부분창 retention 1.0(주간 런 심문 후보). "
        "④ 관측 62 등재: temporal neighbor 동반의 계기 분모 오염 위험 + 자격증명 인접 표본 "
        "= 백로그 #9 실측 1호(기전 코드 확정 mcp.py:1362→store.py:4888, 끄기 스위치 "
        "MEM1_RECALL_TEMPORAL=0 실존 확인). ⑤ 관측 63 등재: 파트 F Δ-1 심문 중 파서 "
        "위양성 발견 — '종결이 아니다'가 _EXIT_MARKS 부분문자열에 격발, 관측 61 인덱스 "
        "소실(진실 존속, 이 행이 선언 보정 1호). 외부 API $0 · 실DB 파괴적 조작 0 · "
        "배포 0 · 제품 코드 0."
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
