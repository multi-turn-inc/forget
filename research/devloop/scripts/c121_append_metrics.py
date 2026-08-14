#!/usr/bin/env python
"""c121 원장 행 append (일반 사이클 — 관측 68 수용 기준 ① oracle replay 판별 실측).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 계기 stdout에만 둔다 (sha8+길이만 기재).
계기 검색(c121_obs68_oracle_replay.py의 search_memories 5회)은 c68 선언으로 계상 밖.

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: silent_misses,
silent_misses_note (백로그 #8 문면 "metrics에 silent_misses 필드 추가"의 첫 이행 —
c58 계열 표본은 노트 산문으로만 있었다).

중복 방지: cycle 121 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 121,
    "date": "2026-08-15",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스, ToolSearch "
        "불요 — 규약 ④ 목적물 충족) / 턴2 = get_task_state + c48_step0_check.py + git status "
        "병렬 — N=121 일반(스크립트 첫 줄 정본: 121%10=1·121%5=1), 파트 S ledger_last=120/"
        "task_state_cycle=120 판정=일치, freshness fresh(age 16.6h), Body 24/24 일치 / 턴3 = "
        "첫 유효 행동(승계 검증: 미커밋 c121 계기 스크립트 실재 확인 + 관측 68 처분 문단 "
        "정독) = 3. 규약 ③ 준수 — metrics 접촉은 c48 인쇄·계기의 프로그램 파싱·append "
        "스크립트뿐, tail/cat/head 0회. ★ grade full 근거 한 줄: task_state next_actions가 "
        "모드 후보·측정 1순위(관측 68 ① oracle replay)·영토 판정 규칙·승계 규약(미커밋 "
        "devloop 파일 검증)까지 직접 지정, 재구성 0으로 착수 — 직전 세션(08-14 08:17)이 "
        "선작성한 계기 초안을 승계 규약대로 검증 후 채택(완주 선기재 없음, 순수 계기 초안). "
        "채널 분해: task_state full / 캡슐 miss — 심장박동/W-트랙 점유 지속(파트 B sha "
        "fe6814854c115a17, c120 cbcf8c5be9ec8c5e에서 변경 — 변경 원천은 상대 시각 버킷. "
        "F2 캡슐 절 표 c121 갱신, c90~c121 = 32/32 · 세션 35연속 확정(+방증 4))."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 2,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 후보 서열·영토 규칙·승계 규약 배달(이 세션 선택의 직접 원천). ② 캡슐 = "
        "miss — 심장박동/W-트랙 점유, 자기: 라인 c120 동일(방향일치/dir_actual)로 실작업 "
        "무교차. (1·1) streak 2 (c120부터 재적립 — 구간 중 회상 품질 표본 아님 마킹 관행 "
        "유지). 계기 검색 5회(oracle replay)는 c68 선언으로 계상 밖. 검산: 직전 행 c120 "
        "fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인). 특기: 능동 0은 "
        "c97~c121 25사이클째이나 이번 사이클이 그 0의 의미를 판별했다 — silent_misses 참조."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 등재 0 (audit-120 총평 준수 — 새 관측이 아니라 기존 관측의 처치 집행). "
        "해소 0이되 처분 전진 1: 관측 68 수용 기준 ① 이행(판별 실측 완료, 처분 문단 "
        "기재 — 관측은 ③에 따라 존속, 파트 F 재실행 검증 open 35·Δ0·회부 이탈 집합 "
        "불변). ② 는 차집합 0으로 불발효. 존속 의미론 재정의(R6 후보: (b) 지지 + 차기 "
        "replay 재확인 시 회부 마감 허용)를 회고 c125 의제로 상신 — 관측 63 잠정 규약 "
        "준수(처분 문단에 이탈 마커 2원소·부정문 없음, 파서 재실행으로 확인)."
    ),
    "silent_misses": 0,
    "silent_misses_note": (
        "관측 68 ① 판별 실측 (계기 c121_obs68_oracle_replay.py — 읽기 전용·recall=low· "
        "trace 미전달·질의 무인쇄·적격 상한 = 직전 사이클 수확 epoch·서버+클라 이중 검증): "
        "재생 c116~c120 5건, 적격 고유 24건·연 45건, 항목별 채점 전량 처분 문단 기재. "
        "silent_miss = 0 → 가설 (b) 수요 소멸 지지. 기전 분해: 등가 배달 7/24(task_state "
        "체인) + 저장소 정본 중복 6/24 + 무관 8/24 + 판정 불변 2/24 + 감사 격리 금기 "
        "1/24(94f40d97 — audit-70 내용, c120에 배달됐다면 오염). 한계 병기: top_k=10· "
        "300자 절단·단일 질의 = 재현율 하한('이 조건에서 0'). 부수 방증: e7f68d63이 5/5 "
        "사이클 반환 — 질의-독립 이웃 신호(관측 62 계열). 대조군: 백로그 #8 계보 c36·c57· "
        "c58 silent_miss=0과 정합(당시는 단일 사이클 재생, 이번은 5사이클 일괄+배달 대조)."
    ),
    "open_observations": 35,
    "open_observations_note": (
        "Δ 선언: c120=35 → c121=35, Δ0 = 등재 0 − 이탈 0. 무태그 {27,42,49,52} 불변 · "
        "회부 이탈 {53,56,57,59,61,64} 불변 (관측 68 처분 문단 추가 후 파서 재실행 실측)."
    ),
    "tests": (
        "437 passed(10.74s, 8 warnings) — c120 기재 437과 동일. 소유권 병기(관측 54 관행): "
        "트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py·"
        "research/replay/candidates_v0.jsonl) 잔존 — devloop 소유 델타 0. devloop의 제품 "
        "코드·tests/ 접촉 0(신규 파일은 계기 2본 + frictions 처분 문단), regression_watch "
        "녹색."
    ),
    "product_code_unchanged_streak": 14,
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷(남은 것은 정훈의 사후 승인 1문장). 유지: "
        "A-106.1(서열 1) · P35 구현(서열 2, 시계 c122) · A-65.2 6차 · 묶음 B(A-85.1 포함, "
        "다음 시계 c126) · A-95.1 · A-115.1 · A-105.2+영토 TTL · R1 · audit-120 R5(회고 "
        "경유). 시계: P2 2026-08-31(16일) · P30 (b)(c) 트리거형 · P36 2026-09-10(실행 세션 "
        "몫). 신규 게이트 상신 0 — R6 후보는 회고 c125 의제(frictions 내부 의미론, 무게이트). "
        "원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반(121%10=1) — 관측 68 수용 기준 ① oracle replay 판별 실측. 제품 코드 변경 "
        "0(영토 규약: twin 미커밋 잔존 → 측정 사이클).** 승계: 직전 세션(08-14 08:17)이 "
        "선작성·미실행 사망한 계기 c121_obs68_oracle_replay.py를 승계 규약(관측 43·55·60)대로 "
        "검증(완주 선기재 없음) 후 채택·실행. 실측: c116~c120 작업 선언문 재생 → 적격 고유 "
        "24건 전량 채점, silent_miss=0 → 가설 (b) 수요 소멸 지지(하한 조건 병기). 핵심 "
        "발견 = 기전 분해: task_state 등가 배달 7/24 + **저장소 정본 이중 기록 6/24** — "
        "devloop는 결정을 커밋 파일에도 쓰므로 회상 수요가 파일 정독으로 흡수된다. 도그푸딩 "
        "대표성 한계 성문화: 이 워크로드의 능동 회상 0은 결함 증거도 건강 증거도 아니다. "
        "부수: 감사 격리 금기 1건 발견(94f40d97 — 능동 회상이 감사 세션에선 오염 채널), "
        "e7f68d63 5/5 반환 = 관측 62 이웃 신호 방증. 산출물: frictions.md 관측 68 처분 "
        "문단 + F2 표 c121 행 + 계기 2본. R6 후보(존속 의미론) 회고 c125 상신. 외부 API "
        "$0(recall=low 게이트 LLM 미경유) · 실DB 읽기 전용 5질의 · 배포 0."
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
