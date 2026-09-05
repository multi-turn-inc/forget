#!/usr/bin/env python3
"""사이클 78 원장 append (c64~c77 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=78 행이 이미 있으면 아무것도 하지 않는다.
c71·c75·c76·c77 선례 승계: 쓰기 전에 이 행 자신을 recall_identity로 검산한다.
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 78,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(78%10=8·78%5=3). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch(4스키마) 묶음(P20 배치) / 턴2 get_task_state + c48_step0_check.py + git status "
        "병렬 — metrics.jsonl tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 8연속) / 턴3 첫 "
        "유효 행동(P4 원문 grep + 명세 정독 → 작업 선택). 포함 계상 **3**(floor 3, 초과 0, A-65.1 "
        "미승인이라 절대값 명기) — c66~c78 **13연속 floor**. **grade full**: task_state가 c77 "
        "완주본을 현재로 서빙(요약 커밋 cc4b589 = 실제 HEAD 일치), c78 턴 계획·모드 예고(일반)· "
        "작업 후보 1순위(P4 처분 택일)·기대값([Body] 20/22, part_recall c77 검산값) 전부 정확· "
        "현재본 — 재구성 0. 관측 35 규약 이행(git status 클린 → 수확 잔존물 없음 → 코드 사이클 "
        "허용). [Body] 대조 step 0: **일치**(forget_ai 0.4.0 / bge-small 384 / MEB1:384 / "
        "inst_vs_repo **20/22** = 기대값, 배포 사건 아님) — R5 매 행 명기 이행."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 18행째, 정본 형식: **능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "캡슐/task_state hit 1: c78 작업 후보 1순위(P4 처분 — forget_digest.py 미구현, 집행/폐기 "
        "택일)가 이 사이클의 작업 선택을 직접 배달했고(지시서 우선순위 스캔 대체), 게이트 축 정본 "
        "수치(metadata.hook 강등 ×0.5)가 구현 제약(소화 기억에 hook 키 금지) 발견을 앞당겼다. "
        "훅 주입 3건 miss: c43·c42·c45 기억 — 온토픽이나 task_state 부분집합(신규 정보 0, c21 "
        "엄격 규칙 유지), record_context_outcome 기록 완료. 능동 검색 0회·계기 검색 0회(라이브 "
        "프로브 없는 코드+단위 테스트 사이클). part_recall 검산(step 0): 직전 행 c77 fields(1·3) "
        "vs 성분(0·0/1·3) **일치**. 이 행 자신도 쓰기 전 자기 검산(항등식: hits 1=0+1, "
        "misses 3=0+3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 새 마찰 없음(서버 경계는 스텁, 실DB 무접촉). fixed 0 — 정직 계상: P4 착공은 "
        "마찰 해소가 아니라 백로그 집행이고, P4 자체의 판정은 배선(정훈 게이트) 후 컴팩션 5사건 "
        "관측에 걸려 있다. 관측 34: 라이브 질의 0건 — 대조군 어휘 의무 해당 없음(프로브 부재). "
        "관측 36: 실측 프로브 없음 — 질의 원문 인용 0. 관측 37 ③: trace 원장 정독 없음(해당 없음 "
        "명기)."
    ),
    "tests": (
        "**345 passed**, 1 warning in 8.71s — 신규 6(test_hooks: forget_digest 계열: 활성 창 "
        "보호·배치 미달 무호출·실패 비전진 후 재시도·오프셋 전진·문자 상한 부분 전진·기계 페이로드 "
        "스킵) + 기존 339 회귀 0."
    ),
    "work": (
        "**일반 사이클 — P4 처분 택일 선언: 집행 시작(폐기·재등록 기각), 명세 순서 1 완료.** "
        "hooks/forget_digest.py 신규(Stop 훅, rolling-consolidation-stage1.md ① 그대로): "
        "RECENT_WINDOW_TURNS=30 활성 창 보호 · DIGEST_BATCH_TURNS=20 배치 임계 · "
        "add_memory(messages, infer=True) 배치당 1회 · BATCH_CHAR_LIMIT=48k 부분 전진(오프셋은 "
        "실제 전송분까지만) · 실패 시 오프셋 비전진(다음 Stop 재시도) · fail-open exit 0. 판정 "
        "없는 훅 — 추출·게이트는 서버 파이프라인 몫(명세 문면). 구현 중 확정 제약: 소화 기억 "
        "metadata에 `hook` 키 금지 — 회상 훅이 metadata.hook 행을 스킵하고 점수가 ×0.5 강등되어 "
        "컴팩션 대체재 역할이 죽는다(테스트로 고정). predictions.md P4에 처분 부기 — 착공 선언이지 "
        "판정 아님, 시계는 여전히 배선 게이트 후 가동. 잔여: ② PreCompact 플러시 + ③ 임계 "
        "플래그(다음 코드 사이클 후보) → 순서 3 settings.json 배선(정훈 게이트). 신규 예측 "
        "0건(정직 근거: P4가 이 구현의 선행 등록 예측이며 설계 이탈 없음). 외부 비용 $0."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 13사이클(13연속 floor) ② A-65.2 거버넌스 동결 부분 "
        "해제 — 13사이클·재상신 대기 ③ A-55.1 지시서 절차 0 문면 교체 — 23사이클 ④ 개헌 채널 "
        "처분 — 73사이클 0/4 ⑤ 부채 캐리어 — 18사이클 ⑥ 케이던스 전환 — 18사이클 ⑦ 그림자 규약 "
        "10+1건 ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · F6 feedback/ · launchd enforce · "
        "Sol 재검증 ⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계(69·67·62사이클) + ⑮ 배포 영수증 + 관측 "
        "33 라이브 재측정 — 단일 최대 레버(단 c77 실측: 배포는 어트랙터 표본의 충분조건 아님 — "
        "게이트 값 재교정과 묶을 것) ⑫ 관측 31 ⑭ 평탄도 margin 처치 설계(c77 증거 합류분 유지) "
        "⑱ 예측 처분 규약 성문화 ⑲ 관측 36 제품 처치 · 관측 37 trace 마스킹 ⑳ A-75.1·A-75.2· "
        "A-75.3. 게이트 예고: P4 순서 3(settings.json Stop 훅 배선)은 ②③ 완료 후 릴리스 큐 "
        "등재 예정 — 아직 미등재(산출물 미완이라 큐에 올릴 것이 없음, 원칙 5 위반 아님). 정산 "
        "1줄(audit-40 R6, 33회차): 신규 0건, 해소 0건, 이관 0건 — P4 착공은 루프 몫이라 게이트 "
        "장부 무변동."
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
