#!/usr/bin/env python3
"""사이클 77 원장 append (c64~c76 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=77 행이 이미 있으면 아무것도 하지 않는다.
c71·c75·c76 선례 승계: 쓰기 전에 이 행 자신을 recall_identity로 검산한다.
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 77,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(77%10=7·77%5=2). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch(5스키마) 묶음(P20 배치) / 턴2 get_task_state + c48_step0_check.py + git status "
        "병렬 — metrics.jsonl tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 7연속) / 턴3 첫 "
        "유효 행동(frictions.md 미해소 정독 → 작업 선택). 포함 계상 **3**(floor 3, 초과 0, A-65.1 "
        "미승인이라 절대값 명기) — c66~c77 **12연속 floor**. **grade full**: task_state가 c76 "
        "완주본을 현재로 서빙(요약 커밋 98c421a = 실제 HEAD 일치), c77 턴 계획·작업 후보 3건(부수 "
        "관측 포함)·상시 계수 의무·게이트 축 정본 수치(강등 배율·아핀 차이까지) 전부 정확·현재본 — "
        "재구성 0. 관측 35 규약 이행(수확 잔존물 검사 → git status 클린). [Body] 대조 step 0: "
        "**일치**(forget_ai 0.4.0 / bge-small 384 / MEB1:384 / inst_vs_repo **20/22** = 기대값, "
        "배포 사건 아님) — R5 매 행 명기 이행."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 17행째, 정본 형식: **능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "캡슐/task_state hit 1: c77 작업 후보(부수 관측 지목)·게이트 축 정본 수치(강등 배율 "
        "×0.5/×0.45/×0.88, 두 몸의 아핀 차이)가 이 사이클의 작업 선택과 계기 설계(반사실 산술· "
        "몸 분리 선언)를 직접 형성했다. 훅 주입 3건 miss: c43·c42·c45 기억 — 온토픽이나 "
        "task_state 부분집합(신규 정보 0, c21 엄격 규칙 유지), record_context_outcome 기록 완료. "
        "계기의 검색 호출(probe_full 12질의 × 풀 200)은 계상 제외(c68 선언). part_recall "
        "검산(step 0): 직전 행 c76 fields(1·3) vs 성분(0·0/1·3) **일치**. 이 행 자신도 쓰기 전 "
        "자기 검산(항등식: hits 1=0+1, misses 3=0+3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "**logged 0 · fixed 0 — 정직 계상: 관측 33 부수 관측(a9402b0c 강등 누출)을 기각·재귀속으로 "
        "종결했으나 처치가 아니라 판정이므로 fixed로 세지 않는다.** 판정(신선 무관 질의 10건, 적격 "
        "10/10): ① 침입 재현 9/10이나 침입 질의 전부 풀 200/200 게이트 통과(c68 FPR=1.00 재확인) — "
        "표지 소급 ×0.5는 회전이지 감소가 아니다(반사실 9/9 rank 200 추락, F1 2000/2000 검증). "
        "② junk 기전(F2/C1) 기각 0/9 — rule 0.0703은 전부 recency, 지배 성분은 임베딩(무관 질의에 "
        "cos 0.747~0.798, 0.55×vector 단독 통과 9/9)+피드백 +0.05. ③ hook 표지 행 중 "
        "trust.source=user 0행 실측 — 강등은 애초에 user-source 행을 겨냥한 적 없고 이 행은 정당한 "
        "녹색 사실(c69 '그 성질'은 대상 정의의 오독). ④ 클래스 강등(무hook user행 131개)은 자기 "
        "주제 rank 3→182 매장 — trust 계약 역전. ⑤ 저장소 몸 투영(아핀 제거)에서도 9/9 통과 — "
        "⑮ 배포는 충분조건 아님, 잔여 몫은 게이트 재교정(⑭·A-65 계열)으로 이관. 부수 발견: 이 "
        "행은 자기 주제에서 rank 12로 매장당하는 중(같은 기전의 가해자=피해자). 관측 34 이행(어휘 "
        "신규+미등장 기계 검사 10/10), 관측 36 이행(질의·본문 원문 무인용 — 계기 파일에만, 보고는 "
        "라벨·id·해시). 관측 37 ③: trace 원장 정독 없음(해당 없음 명기)."
    ),
    "tests": (
        "**339 passed**, 1 warning in 7.56s — 제품 코드 0행, 기존 339 회귀 0(c76과 동일 스위트)."
    ),
    "work": (
        "**일반 사이클 — 관측 33 부수 관측(a9402b0c '강등 누출')의 기전 귀속: 프레임 기각, 게이트 "
        "척도 트랙으로 재귀속·종결.** 계기 scripts/c77_demotion_leak_attribution.py(read-only·$0): "
        "경합 가설 3개(H_A 강등 누락 / H_C1 junk rule / H_V 임베딩)와 판정 규칙을 실행 전 선선언, "
        "신선 무관 질의 10건(관측 34 규약)으로 판별. 결과: H_C1 기각 0/9, H_V 지지 9/9, H_A는 "
        "기계적 9/9이나 **선선언 규칙 자체의 결함을 사후 발견**(행 수준 반사실은 해악 수준에서 "
        "회전을 감소로 오독 — 풀 200/200 통과가 물증, 사후임을 명기하고 병기). 클래스 반사실(131행 "
        "×0.5)로 처치 일반화 기각(자기 주제 rank 3→182), 저장소 몸 투영으로 ⑮ 배포 불충분 확인. "
        "산출물: 판정 노트 notes/cycle-77-demotion-leak-attribution.md + frictions.md 종결 부기. "
        "코드 변경 0 → 신규 예측 0건(정직 근거: 설계 변경 없음 — 측정·판정 사이클). 자기규율 c77 "
        "추가분: **반사실 판정 규칙은 해악 수준에서 선언하라 — 행 수준 반사실은 회전을 감소로 "
        "오독한다.** 외부 비용 $0."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 12사이클(12연속 floor) ② A-65.2 거버넌스 동결 부분 "
        "해제 — 12사이클·재상신 대기 ③ A-55.1 지시서 절차 0 문면 교체 — 22사이클 ④ 개헌 채널 "
        "처분 — 72사이클 0/4 ⑤ 부채 캐리어 — 17사이클 ⑥ 케이던스 전환 — 17사이클 ⑦ 그림자 규약 "
        "10+1건 ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · F6 feedback/ · launchd enforce · "
        "Sol 재검증 ⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계(68·66·61사이클) + ⑮ 배포 영수증 + 관측 "
        "33 라이브 재측정 — 단일 최대 레버(단 c77 실측: 배포는 a9402b0c류 어트랙터 표본의 충분조건 "
        "아님 — 게이트 값 재교정과 묶어야 함) ⑫ 관측 31 ⑭ 평탄도 margin 처치 설계 — **c77 증거 "
        "합류(무관 질의 풀 200/200 통과 재확인, 어트랙터 행 실측 cos 0.747~0.798)** ⑱ 예측 처분 "
        "규약 성문화 ⑲ 관측 36 제품 처치 · 관측 37 trace 마스킹 ⑳ A-75.1·A-75.2·A-75.3. P4는 "
        "루프 몫 ~77사이클 — c78+ 후보 1순위(집행 또는 폐기·재등록 택일 선언). 정산 1줄(audit-40 "
        "R6, 32회차): 신규 0건, 해소 1건(관측 33 부수 관측 — 기각·재귀속 종결, 루프 몫), 이관 "
        "1건(어트랙터 표본 → ⑭ 게이트 재교정 증거로)."
    ),
}


def main() -> None:
    spec = importlib.util.spec_from_file_location(
        "c48_step0_check", os.path.join(os.path.dirname(os.path.abspath(__file__)), "c48_step0_check.py"))
    c48 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c48)
    verdict, detail = c48.recall_identity(ROW)
    if verdict != "일치":
        raise SystemExit(f"[abort] 이 행이 자기 검산에 실패: {verdict} — {detail}")

    with open(LEDGER, encoding="utf-8") as fh:
        cycles = {json.loads(ln)["cycle"] for ln in fh if ln.strip()}
    if ROW["cycle"] in cycles:
        print(f"[skip] cycle={ROW['cycle']} 이미 존재")
        return
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ROW, ensure_ascii=False) + "\n")
    print(f"[ok] cycle={ROW['cycle']} append, keys={len(ROW)}, 자기 검산={verdict} ({detail})")


if __name__ == "__main__":
    main()
