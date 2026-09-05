#!/usr/bin/env python3
"""사이클 76 원장 append (c64~c75 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=76 행이 이미 있으면 아무것도 하지 않는다.
c71·c75 선례 승계: 쓰기 전에 이 행 자신을 recall_identity로 검산한다
(c76 = P24 표본 계상 5호이자 판정 사이클).
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 76,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(76%10=6·76%5=1). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch(4스키마) 묶음(P20 배치) / 턴2 get_task_state + c48_step0_check.py + git status "
        "병렬 — metrics.jsonl tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 6연속) / 턴3 첫 "
        "유효 행동(P24 판정 근거 + frictions 관측 33 정독 → 작업 선택). 포함 계상 **3**(floor 3, "
        "초과 0, A-65.1 미승인이라 절대값 명기) — c66~c76 **11연속 floor**. **grade full**: "
        "task_state가 c75 완주본을 현재로 서빙(요약 커밋 b25da0c = 실제 HEAD 일치), c76 턴 계획·"
        "P24 판정 의무(처분 조항 포함)·작업 후보 3건·상시 계수 의무·게이트 큐 전부 정확·현재본 — "
        "재구성 0. 관측 35 규약 이행(수확 잔존물 검사 → git status 클린). [Body] 대조 step 0: "
        "**일치**(forget_ai 0.4.0 / bge-small 384 / MEB1:384 / inst_vs_repo **20/22** = 기대값, "
        "배포 사건 아님) — R5 매 행 명기 이행."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 16행째 — P24 표본 계상 **5호이자 판정 사이클**, 정본 형식: "
        "**능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. 캡슐/task_state hit 1: c76 턴 계획·"
        "P24 판정 의무·작업 후보(관측 33 1순위)·정본 수치(store.py 행 번호까지)가 전부 현재본으로 "
        "이 사이클의 작업 선택과 판정 기재를 직접 형성했다. 훅 주입 3건 miss: c43·c42·c45 기억 — "
        "전부 [devloop] 온토픽이나 task_state 부분집합(신규 정보 0, c21 엄격 규칙 유지). 능동 검색 "
        "0회(작업이 저장소 내부로 완결 — 검색 필요 미발생). part_recall 검산(step 0): 직전 행 c75 "
        "fields(1·3) vs 성분(0·0/1·3) **일치**. **P24 판정 기재 완료(predictions.md P24 절): "
        "(a) 산술 분열 0건(c72~c75 기계 검산 4/4 통과 + c76 자기 검산) · (b) 추출 실패 0회 < 2 → "
        "적중(비반증), 처분 조항 무발동, 쓰기측 강제는 발동 조건 미충족으로 보류.** 이 행 자신도 "
        "쓰기 전 자기 검산(항등식: hits 1=0+1, misses 3=0+3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 1,
    "frictions_note": (
        "**fixed 1 = 관측 33(F12 후보 '자기 보고와 산술의 분리') — 저장소 몸 한정 해소, 정직 "
        "계상: 라이브 몸(:8000, forget_ai 0.4.0 설치본)은 ⑮ 배포 전까지 이 수리가 닿지 않는다.** "
        "수용 기준 ① 피드백 적용 델타를 breakdown에 기록(보정 0이면 키 불증가 — 위양성 0 대조군 "
        "테스트 동봉) ② task_state 클레임에 합성 사슬 우회 표지(vector 키 위조 없음) ③ 재조립 "
        "100%를 테스트가 고정(tests/test_score_breakdown_reassembly.py 5건) — 전부 충족. 부수 "
        "관측(a9402b0c 강등 누출·대리 표지)은 범위 밖 미해소 존치. logged 0 — 신규 마찰 없음. "
        "관측 36 자기 이행: 산출물·기억에 실측 프로브 원문 인용 0건(테스트 질의는 계기 파일 "
        "내부에만 — 관측 34 ③ 허용 채널). 관측 37 ③: 이 사이클은 trace 원장 정독 없음(해당 없음 "
        "명기)."
    ),
    "tests": (
        "**339 passed**, 1 warning in 9.06s — 기존 334 회귀 0, 신규 +5"
        "(test_score_breakdown_reassembly.py: 피드백 델타 가시화·음수 델타 재조립·클레임 우회 "
        "표지·노출 opt-in 불변·혼합 행 전수 재조립)."
    ),
    "work": (
        "**일반 사이클 — 관측 33 처치(제품 코드): score_breakdown의 은닉 보정 두 개를 표지로 "
        "실었다.** ① feedback_adjusted_score가 점수를 바꾸면 **적용 델타(클램프 후 실값)**를 "
        "score_breakdown.feedback으로 기록 — 명목 라벨 가중치가 아니라 적용값이어야 재조립이 "
        "성립한다(경계 클램프 시 두 값이 다르다). 본체 사슬(store.py 검색 루프)과 task_state 경로 "
        "양쪽. ② task_state 클레임 결과에 {rule, task_state: true} breakdown — rule×w+vector×w "
        "합성 사슬을 우회했다는 표지가 실려 rule=vector=0을 '유사도 0'과 구별할 수 있다. vector "
        "키는 싣지 않는다(미계산의 정직한 표현). ③ 노출 계약 불변 — 기존 조건(keyword_search· "
        "filter_memories·criteria·score_breakdown 요청)을 expose_breakdown으로 호이스트해 두 "
        "경로가 같은 스위치를 탄다. 요청 없는 검색의 응답 형태 불변을 테스트로 고정. **신규 예측 "
        "0건(정직 근거: 점수 산술 무변경의 자기 보고 수리 — 수용 기준이 테스트로 즉시 판정되어 "
        "다사이클 반증 창이 필요 없다, LOOP.md ②의 '설계 변경' 아님).** 병행: **P24 판정 적중 "
        "기재**(predictions.md — 상세는 recall_note), frictions.md 관측 33 처치 부기. 제품 코드 "
        "store.py +26/-5(git diff --numstat 실측) · 외부 비용 $0."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 11사이클(11연속 floor) ② A-65.2 거버넌스 동결 부분 "
        "해제 — 11사이클·재상신 대기 ③ A-55.1 지시서 절차 0 문면 교체 — 21사이클 ④ 개헌 채널 "
        "처분 — 71사이클 0/4 ⑤ 부채 캐리어 — 16사이클 ⑥ 케이던스 전환 — 16사이클 ⑦ 그림자 규약 "
        "10+1건 ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · F6 feedback/ · launchd enforce · "
        "Sol 재검증 ⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계(67·65·60사이클) + ⑮ 배포 영수증 — 단일 "
        "최대 레버, 이번 사이클로 **관측 33 라이브 절반도 이 게이트에 합류**(재조립 100% 라이브 "
        "재측정) ⑫ 관측 31 ⑭ 평탄도 margin 처치 설계 ⑯ 관측 33 → **재분류: 저장소 몫 해소, "
        "잔여는 ⑩·⑮ 종속(독립 항목 폐지)** ⑰ P24 판정 → **해소(c76 기한 내 기재, 적중)** ⑱ 예측 "
        "처분 규약 성문화 ⑲ 관측 36 제품 처치 · 관측 37 trace 마스킹 ⑳ A-75.1·A-75.2·A-75.3. "
        "P4는 루프 몫 ~75사이클 — c77+ 후보(집행 또는 폐기·재등록 택일). 정산 1줄(audit-40 R6, "
        "31회차): 신규 0건, 해소 1건(⑰ P24 — 루프 몫 집행 완료), 예측 정리 1건(P24 적중 마감), "
        "재분류 1건(⑯ → ⑩·⑮ 종속)."
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
