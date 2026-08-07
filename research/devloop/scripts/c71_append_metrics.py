#!/usr/bin/env python3
"""사이클 71 원장 append (c64~c70 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=71 행이 이미 있으면 아무것도 하지 않는다.
c71 신규: 쓰기 전에 이 행 자신을 recall_identity로 검산한다 — P24 처치의 쓰기측
반쪽(audit-70 §1-a 부가 권고)을 append 스크립트가 직접 이행하는 첫 표본.
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 71,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(71%10=1·71%5=1). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch 묶음 / 턴2 get_task_state + c48_step0_check.py + git status 병렬 — metrics.jsonl "
        "tail/cat/head 0회(정본 경로 준수, F-절차0 위반 0. c70과 달리 ★ 경고가 next_actions[0] "
        "선두에 있어 행동보다 먼저 도착했다) / 턴3 첫 유효 행동(predictions·frictions·c69 노트·"
        "원장 스키마 정독 = 작업 단위 선택 착수). 포함 계상 **3**(floor 3, 초과 0 — P20 시계는 "
        "c69 종료, A-65.1 미승인이라 절대값 3을 대리 지표로 명기). 자[尺] 공지: 계상 규약 c61 "
        "이후의 포함, 미변경. **grade full**: get_task_state가 c70 완주본을 현재로 서빙(요약의 "
        "커밋 38538a2 = 실제 HEAD 일치), **관측 35 규약 첫 이행** — next_actions를 따르기 전에 "
        "git status의 수확 잔존물을 먼저 검사(클린 트리 확인 후 신뢰). 작업 포인터(⑮/⑰ 양립 "
        "후보)와 의무 목록이 전부 정확·현재본 — c68~c70 3연속 'hit 품질 비이진'(포인터 구본/"
        "프레이밍 오염) 계열이 이 행에서 끊겼다(직전 세션이 수확을 완주하면 포인터는 신선하다 — "
        "관측 35의 대우 명제 표본). [Body] 대조: **일치**(forget_ai 0.4.0 / fastembed "
        "bge-small-en-v1.5 384 / MEB1:384 / inst==repo 22/22) — P21 (b) 계상: 오발 아님, "
        "audit-70 R5(매 행 명기) 이행."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 11행째 — 성분 분해 병기(P24 배선 사이클, 정본 형식 사용): "
        "**능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. 캡슐/task_state hit 1: 턴 계획·"
        "작업 후보·c71 의무 목록(P15 기입·P17/P19 처분·P21/P22 판정·P10 처분·관측 34/35 규약)이 "
        "전부 현재본으로 행동을 직접 형성했다. 훅 주입 3건 miss: c43·c42·c45 발견(전부 [devloop] "
        "온토픽이나 task_state가 이미 더 완전한 형태로 준 내용의 부분집합 — 신규 정보 0, c21 엄격 "
        "규칙 유지). 능동 검색 0회 — 작업이 원장·감사문 정독으로 충분했고 add_memory 1회는 검색이 "
        "아니다(계상 밖). 이 행 자신이 part_recall 검산기의 첫 신규 표본이며 append 스크립트가 "
        "쓰기 전 검산했다(위 항등식: hits 1=0+1, misses 3=0+3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 마찰 0. **fixed 0 정직 계상** — ⑰(P15 처방)의 배선은 처치이지 해소가 아니다(판정 "
        "P24, c76 — c19 규율 유지). audit-70 위임 의무의 c71 집행분: R1(P24 등록+part_recall 배선) "
        "· R2(P17 (b)·P19 (b) 폐기 처분 — 원장 선언 완료) · R3(flaky '게이트 큐' 라벨 폐기·재분류, "
        "gate_pending) · R5(몸 대조 매 행 명기 개시). **R4(관측 32 누계 4 vs 성분 합 3의 원자료 "
        "재도출)는 c72 명시 이월** — 침하가 아니라 이월 선언이며 다음 행이 계승하지 않으면 audit-80 "
        "계상 대상."
    ),
    "tests": (
        "**329 passed**, 1 warning in 8.92s — 318 → 329(+11, 전부 tests/test_devloop_step0_recall.py). "
        "제품 코드 0행 — audit-70 §2-a 프레이밍 유지: 이 +11도 제품 개선이 아니라 계기 감시 비용이다. "
        "내용: P15 반증 재발을 잡는 검산기의 회귀 고정(c64형 불일치 검출·추출 불가 비침묵·소급 "
        "10행 고정) + cycle_number_and_mode·needle_reach 커버 — c48_step0_check 파싱 테스트 부채"
        "(c64→c70 7회 이월)의 **부분 상환**(part_a·part_b I/O 경로는 여전히 미커버, 잔여 부채 명시). "
        "baseline 비결정성 유지(c24 계측 0.114% flaky — 이 행부터 라벨 정정: 게이트 큐 아님, "
        "무게이트 코드 부채)."
    ),
    "work": (
        "**일반 사이클 — 작업 단위 = ⑰ P15 처방 집행(audit-70 R1) + c71 계수 의무 일괄.** "
        "① **P24 등록(코드 처치에 선행, 절차 3 준수) → c48_step0_check.py part_recall() 배선**: "
        "정의 A를 step 0 절단 불가능 채널에 인쇄(c64 캡슐 hit 확장의 성문화 = 그림자 해제이지 승인 "
        "아님 — 타당성 판정은 그림자 규약 게이트 건 합류(audit-70 N7); c68 계기 배제 포함) + 직전 "
        "원장 행의 `성분 합 = 필드 값` 항등식 기계 검산(일치/불일치/추출 불가 3치, 모르는 것을 "
        "일치로 접지 않는다). **소급 자기 시험: c61~c70 실제 10행 추출 10/10 · 판정 c64 단독 "
        "불일치 · 나머지 9행 일치 = audit-70 §1-a 수작업 계수의 기계 재현, 위양성 0**(과적합 "
        "캐비앗 병기 — 같은 손이 본 표본, (b) 채널 팔이 미래 행으로 잰다). "
        "② **원장 의무 집행**: P15 (a) 반증·(b) 성립 9/9 기입 / P17 (b)·P19 (b) **폐기**(기한 "
        "도과·계상 미이행, P2 전례 — 처치와 계기는 존속, 폐기는 처치 무효가 아니라 미계상 판정) / "
        "P21 판정: (a) 사건 미발생 판정 불능 종결(part_body는 상시 계기 존속, 재발 시 관측 채널 "
        "신규 표본), (b) 성립·약한 지지(오발 0/3 기록 표본 — c68 공백은 '기재 없음=무오발'로 계상 "
        "안 함, audit-70 D5) / P22 판정: **(b) 반증 확정, (a) 지지 — 실측 표본은 c69 1사이클 한정 "
        "정직 병기, 상수 경로 폐쇄 불변**(c71은 이 축 미측정: 관측 34 규약상 신선 OFF 어휘 없이 "
        "측정하지 않으며 아핀 축은 ⑮ 단독 사이클 몫) / P10 재서술 8사이클 부채 **종결**(새 문면 "
        "불요 — 보류+재무장 조건이 정본, '우회 행 지배' 재서술은 c69 실측 0/23으로 반증돼 금지). "
        "③ cycle_number_and_mode 순수 함수 분리(part_n 출력 불변, 산술 첫 회귀 감시 진입). "
        "제품 코드 0행 · 외부 비용 $0 · 신규 예측 1건(P24, 처분 조항 동봉 — 닫히지 않은 예측은 "
        "늙지 않는다 병리의 선제 차단)."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 6사이클 ② A-65.2 거버넌스 동결 부분 해제 — 미분류 "
        "관측 9건(26·27·29~35) ③ A-55.1 지시서 절차 0 문면 교체 — 16사이클(실측 표본 2호 유지, "
        "c71은 경고 선행 도착으로 준수 — 도착 순서 의존성 그대로) ④ 개헌 채널 처분 — 66사이클 0/4 "
        "⑤ 부채 캐리어 항구 소재 — 11사이클 ⑥ 케이던스 전환 — 11사이클, 유효 선행 조건 = ⑮ "
        "⑦ 그림자 규약 10건 + 1(신규 합류: c64 캡슐 hit 확장 — c71이 정의 문면에 성문화했으나 "
        "타당성 승인은 정훈 몫, audit-70 N7) ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · F6 "
        "feedback/ · **flaky 결정화 — audit-70 R3 집행: '게이트 큐 N사이클' 라벨 폐기(봉쇄 게이트 "
        "부존재 확정 — 영토 규약은 c51 해제), 무게이트 코드 부채로 재분류**(테스트 결정화 팔은 "
        "루프 자력 소형 후보, checksum 강화 팔만 설계 변경 게이트) · launchd enforce · Sol 재검증 "
        "⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계(62·60·55사이클째 봉쇄) ⑫ 관측 31 제품 처치 "
        "⑭ 평탄도 margin 축(자[尺] 단독, ⑮와 동시 금지) ⑮ **아핀 제거 처치(P23, 무게이트 1순위, "
        "자[尺] 단독 사이클 + 영토 검사 선행 + OFF 어휘 신규 추출)** ⑯ 관측 33 제품 처치 "
        "⑰ **해소**(P24 배선 완료, 판정 c76) ⑱ 예측 처분 규약 — c71이 개별 집행(P17·P19 폐기 + "
        "P24 처분 조항 동봉)으로 선례 확립, 규약 성문화는 게이트. 정산 1줄(audit-40 R6, 26회차): "
        "신규 0건, 해소 1건(⑰), 재분류 1건(flaky), 예측 원장 정리 6건(P15 기입·P17b 폐기·P19b "
        "폐기·P21 판정·P22 판정·P10 부채 종결), R4 1건 c72 명시 이월."
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
