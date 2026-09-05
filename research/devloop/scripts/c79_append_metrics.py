#!/usr/bin/env python3
"""사이클 79 원장 append (c64~c78 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=79 행이 이미 있으면 아무것도 하지 않는다.
c71·c75~c78 선례 승계: 쓰기 전에 이 행 자신을 recall_identity로 검산한다.
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 79,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(79%10=9·79%5=4). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch(5스키마) 묶음 / 턴2 get_task_state + c48_step0_check.py + git status 병렬 — "
        "metrics.jsonl tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 9연속) / 턴3 첫 유효 "
        "행동(frictions 미해소 grep + 명세 정독 + hooks 목록 → 작업 선택). 포함 계상 **3**(floor "
        "3, 초과 0, A-65.1 미승인이라 절대값 명기) — c66~c79 **14연속 floor**. **grade full**: "
        "task_state가 c78 완주본을 현재로 서빙(요약 커밋 a9b77f0 = 실제 HEAD 일치), c79 턴 계획· "
        "모드 예고(일반)·작업 후보 1순위(P4 순서 2)·기대값([Body] 20/22, part_recall c78 검산값 "
        "fields(1·3) vs 성분(0·0/1·3)) 전부 정확·현재본 — 재구성 0. ★ c80 = 적대 감사 예고까지 "
        "선행 도착. 관측 35 규약 이행(git status 클린 → 수확 잔존물 없음 → 코드 사이클 허용). "
        "[Body] 대조 step 0: **일치**(forget_ai 0.4.0 / bge-small 384 / MEB1:384 / inst_vs_repo "
        "**20/22** = 기대값, 배포 사건 아님) — R5 매 행 명기 이행."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 19행째, 정본 형식: **능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "캡슐/task_state hit 1: c79 작업 후보 1순위(P4 순서 2 — ② PreCompact 플러시 + ③ 임계 "
        "감시, digest 상태 파일 공유까지 설계 지침 포함)가 이 사이클의 작업 선택과 구현 골격을 "
        "직접 배달했고, 정본 수치(metadata.digest='rolling-stage1' 표지, hook 키 금지 제약)가 "
        "플러시 metadata 설계를 선결정했다. 훅 주입 3건 miss: c43·c42·c45 기억 — 온토픽이나 "
        "task_state 부분집합(신규 정보 0, c21 엄격 규칙 유지), record_context_outcome 기록 완료. "
        "능동 검색 0회·계기 검색 0회(라이브 프로브 없는 코드+단위 테스트 사이클). part_recall "
        "검산(step 0): 직전 행 c78 fields(1·3) vs 성분(0·0/1·3) **일치**. 이 행 자신도 쓰기 전 "
        "자기 검산(항등식: hits 1=0+1, misses 3=0+3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 새 마찰 없음(서버 경계는 스텁, 실DB 무접촉; cp 샌드박스 차단 1건은 하네스 "
        "제약이지 기억 마찰이 아니라 비계상). fixed 0 — 정직 계상: P4 순서 2는 마찰 해소가 "
        "아니라 백로그 집행이고, P4 판정은 배선(정훈 게이트) 후 컴팩션 5사건 관측에 걸려 있다. "
        "관측 34: 라이브 질의 0건 — 대조군 어휘 의무 해당 없음(프로브 부재). 관측 36: 실측 "
        "프로브 없음 — 질의 원문 인용 0. 관측 37 ③: trace 원장 정독 없음(해당 없음 명기)."
    ),
    "tests": (
        "**352 passed**, 1 warning in 9.57s — 신규 7(test_hooks P4 순서 2 계열: 임계 플래그 "
        "무호출 설정·플러시 창 해제+배치 상한·플러시 실패 부분 전진+기준선 보존·컴팩션 기준선 "
        "리셋·PreCompact 위임(SessionEnd 비위임)·권고 1회+회상 0건 동작·권고 동승+backlog 정직 "
        "병기) + 기존 345 회귀 0."
    ),
    "work": (
        "**일반 사이클 — P4 순서 2 완료: ② PreCompact 최종 플러시 + ③ 임계 감시. 루프 몫 전량 "
        "소진, 순서 3은 릴리스 큐 등재.** ② forget_capture(PreCompact)가 forget_digest.flush 위임 "
        "— 미소화 구간 전체 소화(활성 창 보호 해제: 컴팩션은 창까지 증발시킨다), "
        "FLUSH_MAX_BATCHES=4 비용 상한, 오프셋은 전송 배치까지만 전진(손실 불가), "
        "compacted_at_bytes는 RPC 실패에도 기록(추정 기준선은 사건이지 플러시의 운이 아님), "
        "digest 상태 파일 digest-<sid>.json 공유. 임포트는 try/except 가드(packages 자산에 "
        "digest 부재 — 배포본 fail-open). ③ forget_digest(Stop)가 트랜스크립트 성장분/3.2 + "
        "오버헤드 25k로 사용률 추정, 0.70×200k에서 near_threshold=true → forget_turnrecall이 "
        "재부팅 권고 1줄(에피소드당 1회, advised 마커는 플래그 강하 시 digest가 소거, "
        "backlog_turns로 '소화 완료' 과잉 주장 방지 — 원칙 1). 회상 0건 턴에도 권고는 나가되 "
        "feedback footer는 회상 있을 때만. packages/forget-connect assets 사본 동기 2건 "
        "(capture·turnrecall). 순서 3 산출물 완성: research/devloop/p4-wiring-queue.md — 설치본 "
        "복사 3건 + settings.json Stop 항목(실제 도그푸드 형식 그대로) + PreCompact timeout "
        "10→60 + 스모크 + 롤백 2줄. predictions.md P4 부기(순서 2 완료, 시계 여전히 미시작). "
        "신규 예측 0건(정직 근거: P4가 선행 등록 예측이며 설계 이탈 없음 — 명세 ②③ 문면 그대로). "
        "외부 비용 $0."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 14사이클(14연속 floor) ② A-65.2 거버넌스 동결 부분 "
        "해제 — 14사이클·재상신 대기 ③ A-55.1 지시서 절차 0 문면 교체 — 24사이클 ④ 개헌 채널 "
        "처분 — 74사이클 0/4 ⑤ 부채 캐리어 — 19사이클 ⑥ 케이던스 전환 — 19사이클 ⑦ 그림자 규약 "
        "10+1건 ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · F6 feedback/ · launchd enforce · "
        "Sol 재검증 ⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계(70·68·63사이클) + ⑮ 배포 영수증 + 관측 "
        "33 라이브 재측정 — 단일 최대 레버(단 c77 실측: 배포는 어트랙터 표본의 충분조건 아님 — "
        "게이트 값 재교정과 묶을 것) ⑫ 관측 31 ⑭ 평탄도 margin 처치 설계 ⑱ 예측 처분 규약 성문화 "
        "⑲ 관측 36 제품 처치 · 관측 37 trace 마스킹 ⑳ A-75.1·A-75.2·A-75.3. **㉑ 신규 등재: P4 "
        "순서 3 settings.json Stop 훅 배선 — p4-wiring-queue.md 산출물 완성, '게이트 대기'** "
        "(승인 시 P4 시계 가동). 정산 1줄(audit-40 R6, 34회차): 신규 1건(㉑), 해소 0건, 이관 0건."
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
