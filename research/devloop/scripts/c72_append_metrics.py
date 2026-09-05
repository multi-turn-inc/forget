#!/usr/bin/env python3
"""사이클 72 원장 append (c64~c71 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=72 행이 이미 있으면 아무것도 하지 않는다.
c71 선례 승계: 쓰기 전에 이 행 자신을 recall_identity로 검산한다 (P24 쓰기측 반쪽,
c72 = P24 표본 계상 1호 사이클).
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 72,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(72%10=2·72%5=2). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch 묶음 / 턴2 get_task_state + c48_step0_check.py + git status 병렬 — metrics.jsonl "
        "tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 2연속) / 턴3 첫 유효 행동(P23·P18 원문 + "
        "처치 지점 코드 + 계수 의무 원자료 정독 = 작업 착수). 포함 계상 **3**(floor 3, 초과 0, "
        "A-65.1 미승인이라 절대값 명기). **grade full**: task_state가 c71 완주본을 현재로 서빙"
        "(요약의 커밋 a3807d6 = 실제 HEAD 일치), 관측 35 규약 이행(수확 잔존물 검사 → 클린 확인 후 "
        "신뢰), 작업 1순위(⑮)·계수 의무 4건·금지 조합(⑭ 동시 금지)까지 전부 정확·현재본 — 즉시 "
        "착수 가능했다. [Body] 대조 step 0 시점: **일치**(forget_ai 0.4.0 / bge-small 384 / "
        "MEB1:384 / inst==repo 22/22) — P21 (b) 계상: 오발 아님, R5 매 행 명기 이행. 단 이 행을 "
        "쓰는 시점의 지문은 **20/22로 갈라졌다** — 몸이 아니라 저장소가 움직인 것(⑮ 미배포 처치, "
        "F2 3798/3798이 1차 증거)이며 baseline을 절차대로(_how_to_update ①→②→③) 20/22로 갱신했다. "
        "다음 배포가 22/22로 되돌리는 순간이 진짜 재교정 사건이다(notes/cycle-72 §5)."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 12행째 — P24 표본 계상 **1호**(c72~c76), 정본 형식: "
        "**능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. 캡슐/task_state hit 1: 턴 계획·"
        "작업 1순위(⑮ 문면·처치 지점 좌표·수용 기준 R≥1.0)·계수 의무(관측 32 R4·P24 개시·R5·"
        "P18b 조건)·금지 조합이 전부 현재본으로 행동을 직접 형성했다. 훅 주입 3건 miss: c43·c42·"
        "c45 발견(전부 [devloop] 온토픽이나 task_state 부분집합 — 신규 정보 0, c21 엄격 규칙 유지). "
        "능동 검색 0회 — 작업이 원장·코드·감사문 정독으로 충분했고 add_memory·record_task_state는 "
        "검색이 아니다(계상 밖). part_recall 검산(step 0): 직전 행 c71 fields(1·3) vs 성분(0·0/1·3) "
        "**일치** — P24 (a) 산술 분열 0건 유지, (b) 채널 팔 추출 성공. 이 행 자신도 append 스크립트가 "
        "쓰기 전 검산했다(항등식: hits 1=0+1, misses 3=0+3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 마찰 0 · fixed 0 정직 계상 — ⑮는 P23 축(예측 원장) 처치이지 frictions.md 미해소 "
        "항목의 해소가 아니고, 관측 32 누계 4→3 정정(audit-70 R4·N2, c71 명시 이월분 집행 완료 — "
        "성분 합 3이 정본, '세 번째·네 번째' 원제가 4의 유일 출처였음을 원자료로 확정, 흔적 보존 "
        "정정)은 계수 정정이지 마찰 해소가 아니다. F1 기지 우회 2행(관측 33 서명)은 기존 관측의 "
        "재확인이라 신규 계상 없음."
    ),
    "tests": (
        "**334 passed**, 1 warning in 7.81s — 329 → 334(+5, tests/test_vector_scale.py: 신척도 "
        "자[尺] 회귀 고정 — 직교쌍 0.0(구척도는 0.5로 게이트 0.45를 넘었다)·음수 코사인 클램프·"
        "항등 1.0·스칼라 라운딩 항등·배치==스칼라 비트 단위 80행). 수반 갱신 1건: "
        "test_korean_search 비평탄 단언을 threshold=0.0 검색으로 — 신척도에서 무관 행이 검색 기본 "
        "임계 0.1 아래로 떨어져 기본 검색이 관련 기억만 반환하게 된 것은 처치의 의도된 귀결이며, "
        "단언 의도(관련 1위·랭킹 비평탄)는 보존하고 제품 상수는 불변."
    ),
    "work": (
        "**일반 사이클 — 작업 단위 = ⑮ 아핀 재척도 제거 처치(P23) + c72 계수 의무 일괄.** "
        "① **처치 집행(자[尺] 단독, 영토 클린 선행)**: memory_engine.cosine_similarity · "
        "store._batch_cosine_scores의 (cos+1)/2 → max(0,cos), 등록 문면 그대로 2지점. 게이트 "
        "상수·평탄도 margin 미변경. **배포는 게이트 ⑩ — :8000 몸은 구척도 유지**(F2 1차 증거). "
        "② **수용 측정(c72_affine_verdict.py, read-only·$0)**: 계기 전제 F1 99.95%(기지 우회 "
        "2행 선언 제외·미지 0)/F2 완전 일치(몸 미처치 확정)/F3 스칼라·배치 비트 단위(구현 증명) "
        "전부 충족. **P23 판정 — (a) 성립: 신선 OFF 11(후보 14, SQL 적격, 어휘는 계기 파일에만 "
        "— 관측 34 ①②③)로 표본 확대 후 T2 R=1.040 ≥ 1.0**(여유 얇음 명기), **(b) 성립: 접두열 "
        "band 넓어짐 0회** — 상수 경로 폐쇄 유지, P22 (a) 재개봉 조건 소진. 관찰(비기준): 게이트 "
        "0.45 모사 OFF top-1 통과 11/11 불변 — **아핀 제거는 산술 위생이지 FPR 수리가 아니다**"
        "(OFF top-1은 rule·부스트 성분으로 넘는다. 다음 방향 = 리랭커·어휘 성분 재설계, 미등록). "
        "③ **P18 (b) 처분(c71 위임)**: c63_depth_invariance 재실행 — 20/20 깊이 불변·자격<4 "
        "0건(지지) — 하되 **폐기(계상 미이행, P17b·P19b 전례) + 재등록 안 함**, 세 번째 조건 "
        "이전 대신 배포 게이트 ⑩ 영수증에 'c63 재실행' 동봉(P21 (a) 종결 전례). ④ 관측 32 누계 "
        "4→3 정정(R4 집행) ⑤ body-fingerprint baseline 20/22 갱신(_how_to_update 절차 준수). "
        "제품 코드 2파일 · 외부 비용 $0 · 신규 예측 0건."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 7사이클 ② A-65.2 거버넌스 동결 부분 해제 — 미분류 "
        "관측 9건(26·27·29~35) ③ A-55.1 지시서 절차 0 문면 교체 — 17사이클 ④ 개헌 채널 처분 — "
        "67사이클 0/4 ⑤ 부채 캐리어 — 12사이클 ⑥ 케이던스 전환 — 12사이클, **선행 조건 ⑮ 이 "
        "사이클 충족** ⑦ 그림자 규약 10+1건 ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · F6 "
        "feedback/ · launchd enforce · Sol 재검증 (flaky는 무게이트 코드 부채 유지) ⑩ **라이브 "
        "배포 1건 → P6·P3b·P7b 3시계(63·61·56사이클) + 신규 합류: ⑮ 배포 영수증(배포 후 c63 "
        "재실행 · oracle replay 계열 재교정 · body-fingerprint 22/22 복귀 확인 · 신척도 실 "
        "FPR/TPR 첫 측정) — 단일 최대 레버 재상신** ⑫ 관측 31 ⑭ 평탄도 margin(⑮ 집행 완료로 "
        "동시 금지 해제 — 다음 자[尺] 단독 사이클 후보) ⑯ 관측 33 ⑰ P24 판정 c76 ⑱ 예측 처분 "
        "규약 성문화. 정산 1줄(audit-40 R6, 27회차): 신규 0건, 해소 1건(⑮ 처치+판정 — 배포 팔만 "
        "⑩ 합류), 예측 정리 2건(P23 판정 성립·P18b 폐기), R4 집행 1건(관측 32 정정), 재분류 0건."
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
