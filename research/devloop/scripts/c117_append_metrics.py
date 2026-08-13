#!/usr/bin/env python
"""c117 원장 행 append (일반 사이클 — 관측 65 수용 기준 ① 이분 판정 실측).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 0회 (계기 c117_obs65_latency_probe.py의 search_memories 24회는
  계기의 검색 호출이므로 계상 제외 — c68 선언).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: ∅ (c116 스키마 그대로).

중복 방지: cycle 117 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 117,
    "date": "2026-08-14",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스, ToolSearch "
        "불요 — 규약 ④ 목적물 충족) / 턴2 = get_task_state + c48_step0_check.py + git status "
        "병렬 — N=117 일반(스크립트 첫 줄 정본), 파트 S ledger_last=116/task_state_cycle=116 "
        "판정=일치, freshness fresh(age 0.35h), Body 24/24 일치 / 턴3 = 첫 유효 행동(관측 65 "
        "원문 정독 + 훅 타임아웃 상수 grep 병렬) = 3. 규약 ③ 준수 — metrics 접촉은 파트 F "
        "인쇄·append 스크립트뿐, tail/cat/head 0회. ★ grade full 근거 한 줄: task_state "
        "next_actions가 영토 조건 분기(twin 잔존 시 측정 사이클)와 1순위 측정 후보(관측 65 "
        "수용 기준 ① 이분 판정)·기준선 좌표(관측 59 표 high 7/11)까지 지정, 재구성 0으로 "
        "착수. 채널 분해: task_state full / 캡슐 miss — W-트랙/전략 재정렬 점유(F2 캡슐 절 표 "
        "c117 행, 파트 B sha e339160370b6194c 실측, c90~c117 = 28/28 · 세션 31연속 확정"
        "(+방증 4))."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 21,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 측정 사이클 전환 분기·1순위 후보·기준선 좌표까지 배달(이 사이클 선택의 직접 "
        "원천). ② 캡슐 = miss — W-트랙 점유, 실작업 무교차. ★ (1·1) 21연속 — "
        "recall_constant_streak>0 구간이므로 회상 품질 표본 아님(마커 8회째). 검산: 직전 행 "
        "c116 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 관측 0 · 이탈 0 — 이번 사이클은 관측 65의 부분 처분(수용 기준 ① 이행, 존속): "
        "이분 판정 실측으로 병목 = 서버 측 high 기어 지연 귀속. 훅 상수(문면): high 7s·low "
        "5s·강등 2s, 배포본=저장소 일치. 서버 실측(계기 c117_obs65_latency_probe.py, 게이트 "
        "실관여 12/12 gate-v2·ollama qwen3.5): high 웜 p50 6.25s·p95 12.79s vs 데드라인 7s "
        "(p95가 1.8배) · low 대조 p50 0.35s·p95 0.70s(강등 예산 2s 안) · 널 대조 high−low "
        "중앙값 차 +5.90s 청정. 부수 발견 2건은 처분 절에 병기(훅 주석 12s vs 문면 7s · "
        "store.py:4790 다이어트 기대 ~2s vs 실측 6.25s). 정직 병기: 프로브 질의 = prompt_head "
        "80자 하한 근사. 관측 64 감시 ② 2/3회차 이행: F2 표 c117 행 + 갱신 문단 동반(원장 이 "
        "행의 계수는 표 재계수의 전사). 파트 F 파서 검증: 편집 직후 재실행 — 관측 65 "
        "처분文有(존속)·open 33 확인."
    ),
    "open_observations": 33,
    "open_observations_note": (
        "Δ 선언: c116=33 → c117=33, Δ+0 = 구성 불변(등재 0·이탈 0, 관측 65는 부분 처분으로 "
        "존속). 무태그 {27,42,49,52} 불변 · 회부 이탈 {53,56,57,59,61}."
    ),
    "tests": (
        "437 passed(10.80s, 8 warnings) — c116 기재 437과 동일. 소유권 병기(관측 54 관행): "
        "트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py·"
        "research/replay/candidates_v0.jsonl) 잔존 — +1은 그 diff 소유(c115 실측 승계), "
        "devloop 소유 델타 0. devloop의 제품 코드·tests/ 접촉 0(신규 파일은 "
        "research/devloop/scripts/ 계기 2본), regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 10,
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷(배포 영수증 강등안 잔여 실측 전부 완결 — "
        "남은 것은 정훈의 사후 승인 1문장). 유지: A-106.1(서열 1) · P35 구현(서열 2, 시계 "
        "c122) · A-65.2 6차 · 묶음 B(A-85.1 포함, 다음 시계 c126) · A-95.1 · A-115.1 · "
        "A-105.2+영토 TTL · R1 · 후순위 종속. 시계: P2 2026-08-31(17일) · P30 (b)(c) "
        "트리거형 · P36 2026-09-10(실행 세션 몫). 신규 게이트 산출물 없음 — 관측 65 처치(수용 "
        "기준 ②)는 코드 사이클 몫이라 큐가 아니라 백로그. 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반 사이클(측정 전환 — 영토에 twin 미커밋 잔존, 절차 2) — 관측 65 수용 기준 ① "
        "이분 판정 실측: 병목 = 서버 측 high 기어 지연.** 계기 "
        "scripts/c117_obs65_latency_probe.py(읽기 전용·trace 미전달·질의 무인쇄, 프로브 = "
        "게이트 원장 gear=high prompt_head 중복 제거 12건). 결과: 훅 상수 high 7s(배포본="
        "저장소 문면 일치, L449) vs 서버 high 웜 p50 6.25s·p95 12.79s(게이트 실관여 12/12) — "
        "웜 p95가 데드라인 1.8배, 콜드 귀속만으로 설명 불가. low 대조 p50 0.35s·p95 "
        "0.70s(강등 예산 안), 널 대조 high−low +5.90s 청정. 부수 발견: 훅 주석 12s vs 문면 "
        "7s 불일치 · store.py 다이어트 기대 ~2s vs 실측 3배 괴리. 처치 후보 서열(실측 시사): "
        "기어 선택 정책 ≥ 상수 조정 > 지연 단축 — ②③은 코드 사이클 몫으로 존속. F2 표 c117 "
        "갱신(28/28·세션 31연속, 관측 64 감시 2/3). 외부 API $0(ollama 로컬) · 실DB 파괴적 "
        "조작 0(검색 읽기 전용) · 배포 0 · 제품 코드 0(사유 병기: twin 잔존 — 측정 사이클)."
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
