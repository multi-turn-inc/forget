#!/usr/bin/env python3
"""사이클 74 원장 append (c64~c73 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=74 행이 이미 있으면 아무것도 하지 않는다.
c71 선례 승계: 쓰기 전에 이 행 자신을 recall_identity로 검산한다 (P24 쓰기측 반쪽,
c74 = P24 표본 계상 3호 사이클).
"""

from __future__ import annotations

import importlib.util
import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 74,
    "date": "2026-08-08",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(74%10=4·74%5=4). 턴 원장: 턴1 LOOP.md+cycle-prompt.md Read + "
        "ToolSearch 묶음 / 턴2 get_task_state + c48_step0_check.py + git status 병렬 — metrics.jsonl "
        "tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 4연속) / 턴3 첫 유효 행동(frictions.md "
        "미해소 정독 + append 스크립트 승계 정독 → 작업 선택). 포함 계상 **3**(floor 3, 초과 0, "
        "A-65.1 미승인이라 절대값 명기). **grade full**: task_state가 c73 완주본을 현재로 서빙"
        "(요약의 커밋 13ee24b = 실제 HEAD 일치), 관측 35 규약 이행(수확 잔존물 검사 → 클린 확인 후 "
        "신뢰), 작업 후보(⑭ 평탄도 margin 축 1순위·영토 검사 선행 명시가 곧 이 사이클의 선택)·"
        "계수 의무 4건·[Body] 기대값(20/22)까지 전부 정확·현재본 — 즉시 착수 가능했다. [Body] 대조 "
        "step 0 시점: **일치**(forget_ai 0.4.0 / bge-small 384 / MEB1:384 / inst_vs_repo **20/22** = "
        "c72 갱신 baseline과 정확히 일치 — 저장소가 ⑮만큼 몸보다 앞선 정상 상태, 배포 사건 아님 "
        "확인) — R5 매 행 명기 이행."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 14행째 — P24 표본 계상 **3호**(c72~c76), 정본 형식: "
        "**능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. 캡슐/task_state hit 1: 턴 계획·작업 "
        "후보 목록(⑭ 1순위 명시)·계수 의무(P24 3호·R5 기대값 20/22·P23 재측정 불요·P22 폐쇄)·금지 "
        "조합이 전부 현재본으로 행동을 직접 형성했다. 훅 주입 3건 miss: c43·c42·c45 기억(전부 "
        "[devloop] 온토픽이나 task_state 부분집합 — 신규 정보 0, c21 엄격 규칙 유지, 오프토픽 0/3 — "
        "F2 대장은 c45 정지 상태라 recall_note가 정본 채널, record_context_outcome로 소음 피드백 "
        "반환). 능동 검색 0회 — 계기(c74 측정 스크립트·앵커 검시)의 search_memories 호출은 계상 "
        "제외(c68 선언), add_memory·record_task_state는 검색이 아니다(계상 밖). part_recall 검산"
        "(step 0): 직전 행 c73 fields(1·3) vs 성분(0·0/1·3) **일치** — P24 (a) 산술 분열 0건 유지. "
        "이 행 자신도 append 스크립트가 쓰기 전 검산했다(항등식: hits 1=0+1, misses 3=0+3)."
    ),
    "frictions_logged": 2,
    "frictions_fixed": 0,
    "frictions_note": (
        "**logged 2** — ① **관측 36**(관측 기록이 관측 대상을 바꾼다: c63 필드 노트가 침묵 질의 "
        "2건의 원문을 기억에 인용 → 그 질의만 평지→봉우리 ×29.8·×16.6 반전, 봉우리 정체 = 그 인용 "
        "기억 자신 rule=0.9301 — 루프 계측 노트가 사용자 턴 회상에 주입될 새 F2 제조 경로, 유일하게 "
        "사용자-대면인 자기 기록 왜곡) ② **관측 37**(trace 원장에 평문 SSH 비밀번호 실재 + 계측 "
        "산출물이 git으로 전파 직전 — 24자 절단+sha256 소독으로 차단, 커밋본 비밀 0건 grep 검증). "
        "fixed 0 — 관측 24는 해소가 아니라 수용 기준 (i) 충족(측정 완료, 처치는 게이트 유지). "
        "고치기 전에 기록(원칙 2) 준수: 두 관측 모두 처치 없이 등재, 무게이트 자기 이행분(질의 원문 "
        "무인용 지칭 규약·산출물 소독)만 즉시 발효. 신규 유형 미등록(거버넌스 동결 준수)."
    ),
    "tests": (
        "**334 passed**, 1 warning in 6.35s — 개수 불변(제품 코드 무변경, 연구 계측 3파일 신설: "
        "c74_flatness_length_profile.py·c74_anchor_probe.py·c74_rows.json)."
    ),
    "work": (
        "**일반 사이클 — 작업 단위 = 관측 24 수용 기준 (i) '질의 길이 대 spread 분포' 실측**(⑭ 평탄도 "
        "margin 축, frictions.md 미해소 우선, c63·c68이 두 번 '미측정' 명기한 축). 표본 = 도그푸드 "
        "원장 실제 turn_recall 질의 **전수 67건**(유니크 8~300자, c63의 20건은 이 모집단의 표본), "
        "자[尺] 전부 고정(margin=0.03·min_samples=4·window=5·top_k=5), 몸 선언 = :8000 구척도 + "
        "effective fastembed bge-small 384(원칙 3). ① 판정 1: **길이 가설 기각** — rho=+0.1725"
        "(순열 p=0.1658, n=67), 오염 2행 제외 +0.2565(p=0.0415) = 방향은 가설대로나 순위 분산 ~7%의 "
        "약한 공변량, 밴드 평지율 비단조(50/71/41/47%) — '구조적'의 술어 기각, c68 반례가 n=67로 "
        "일반화. ② 판정 2: 침묵 기저율 **35/67=52% 과반**(c63 40%, 조성 혼합 정직 병기). ③ 판정 3"
        "(헤드라인): **앵커 자연실험** — c63이 원문 인용한 2건만 평지→봉우리 반전(0.0113→0.3371·"
        "0.0192→0.3184), 미인용 2건은 이틀 뒤 소수 4자리 재현(0.0264→0.0263·0.0120→0.0119, 런간 "
        "요동 1/67행 ±0.0001) → **평탄도는 질의 내재 속성이 아니라 질의×스토어 스냅샷의 결합 속성**, "
        "정적 margin은 시간 불변 보장이 원리적으로 없다. 관측 36·37 등재. ⑭ 잔여 팔 = 처치 설계만"
        "(3제약: ON/OFF 분포 겹침·침묵 과반·스토어 상대성). 제품 코드 무변경 · 외부 비용 $0 · 신규 "
        "예측 0건(측정이지 설계 변경 아님 — LOOP.md ② 의무 범위 밖, 수용 기준은 관측 24 기등재)."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 9사이클 ② A-65.2 거버넌스 동결 부분 해제 — 미분류 "
        "관측 11건(26·27·29~37, **36·37 신규 편입**) ③ A-55.1 지시서 절차 0 문면 교체 — 19사이클 "
        "④ 개헌 채널 처분 — 69사이클 0/4 ⑤ 부채 캐리어 — 14사이클 ⑥ 케이던스 전환 — 14사이클"
        "(선행 조건 ⑮ c72 충족) ⑦ 그림자 규약 10+1건 ⑧ frictions_note 사후 승인/기각 ⑨ F4 픽스처 · "
        "F6 feedback/ · launchd enforce · Sol 재검증 ⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계"
        "(65·63·58사이클) + ⑮ 배포 영수증(c63 재실행 · oracle replay 계열 재교정 · body-fingerprint "
        "22/22 복귀 확인 · 신척도 실 FPR/TPR 첫 측정) — 단일 최대 레버 재상신 ⑫ 관측 31 ⑭ 평탄도 "
        "margin — **수용 기준 (i) c74 충족·(ii) c68 부분 충족, 잔여 팔 = 처치 설계**(predictions.md "
        "선행 등록 + ⑮ 신척도 실 FPR/TPR 동반 설계 권고) ⑯ 관측 33 ⑰ P24 판정 c76 ⑱ 예측 처분 규약 "
        "성문화 ⑲ **신규**: 관측 36 처치(계측 노트의 사용자 턴 회상 격리) · 관측 37 제품 처치(trace "
        "기록 시점 비밀 마스킹, 기존 행 소급은 실DB라 백업 선행). 정산 1줄(audit-40 R6, 29회차): "
        "신규 2건(관측 36·37 → ②+⑲), 해소 0건, 예측 정리 0건, 재분류 1건(⑭ 잔여 팔 측정→처치 설계)."
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
