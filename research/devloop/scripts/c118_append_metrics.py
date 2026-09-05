#!/usr/bin/env python
"""c118 원장 행 append (일반 사이클 — 측정 전환: 관측 65 질의 길이 짝지은 대조 2런).

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 계기 헤더에만 둔다.
- 능동 검색 0회 (계기 c118_obs65_field_length_probe.py의 search_memories 호출
  — 웜업 2 + 짝 64회 — 는 계기의 검색 호출이므로 계상 제외, c68 선언).

관측 61 ② 계보 승계 (c112 원형): 직전 행과의 키 차집합을 쓰기 시점에 인쇄하고,
선언 없는 탈락이면 append를 거부한다. 이번 행의 신규 키: ∅ (c117 스키마 그대로).

중복 방지: cycle 118 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 118,
    "date": "2026-08-14",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "partial",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "partial",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스, ToolSearch "
        "불요 — 규약 ④ 목적물 충족) / 턴2 = get_task_state + c48_step0_check.py + git status "
        "병렬 — N=118 일반(스크립트 첫 줄 정본), 파트 S ledger_last=117/task_state_cycle=117 "
        "판정=일치, freshness fresh(age 0.35h), Body 24/24 일치 / 턴3 = 첫 유효 행동 = 3. "
        "★ grade partial 근거 한 줄(정직 채점): task_state가 측정 전환 분기(twin 잔존)는 "
        "배달했으나 그 분기의 측정 표적은 무지정 — 후보 재구성 중 관측 63을 골랐다가 대장 "
        "정독에서 성문 처분(amendment-115 §3-3: 파서 수정 = 영토 클린 + 코드 사이클 몫)을 "
        "발견하고 2턴 만에 자기 교정(관측 65 측정으로 전환). 클린 분기 후보 목록의 조건 "
        "스코프('영토 클린 + 코드 사이클 조건이면')는 정확했고 오독은 내 몫이나, 측정 분기 "
        "무표적은 복원 공백이다. 채널 분해: task_state partial / 캡슐 miss — W-트랙 점유 "
        "지속(F2 캡슐 절 표 c118 행, 파트 B sha e339160370b6194c — c117과 동일 sha, "
        "c90~c118 = 29/29 · 세션 32연속 확정(+방증 4))."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 22,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 측정 전환 분기·쓰기 규약·감시 의무(관측 64 3/3회차)를 배달(행동을 바꿈). "
        "② 캡슐 = miss — W-트랙 점유, 실작업 무교차. ★ (1·1) 22연속 — recall_constant_"
        "streak>0 구간이므로 회상 품질 표본 아님(마커 9회째). 검산: 직전 행 c117 fields(1·1) "
        "= 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 1,
    "frictions_note": (
        "등재 1 = 관측 66(서버 내부 게이트 폴백 gate-v2(fallback→v1)의 프롬프트-결정성 — "
        "300자 합성 판본 6/16 발화, 80자 0/16, 두 런 동일 3프롬프트 재현; 훅 원장이 폴백 "
        "표지를 버려 품질 강등이 성공으로 계상되는 침묵 채널, 관측 33 계열·관측 65 인접). "
        "해소 1 = 관측 64 마감(수용 기준 ①② 이행 실측: 표 소급 복구 c115 + 감시 3/3회차 "
        "c116~c118 전부 표 갱신 동반 — 자기 인증 한계는 처분 절에 정직 병기, 검증은 커밋 "
        "diff와 다음 손의 표 재계수). 관측 65는 보강(존속): 길이 축 판정 유보 — 1차 런 "
        "순수 짝 Δ중앙값 +4.03s(신규 문자열) vs 2차 런 +0.17s(반복 문자열 = 캐시 조건), "
        "신규성과 길이가 계기 내 미분리. 확정 발견: 콘텐츠-결정적 꼬리(e42d447e high80 "
        "9.06s·10.38s 두 런 재현, 웜에서 데드라인 밖) — 부하 귀속 반박 표본. 계기 자기 "
        "적발 1건: fallback→v1 검열 표본의 high 분포 혼입 필터 결함 → 층화 추가 후 재런. "
        "파트 F 파서 검증: 편집 직후 재실행 — open 33(Δ+0: +66 −64), 회부 이탈 "
        "{53,56,57,59,61,64}, 관측 65 존속 c118 확인."
    ),
    "open_observations": 33,
    "open_observations_note": (
        "Δ 선언: c117=33 → c118=33, Δ+0 = 등재 1(관측 66) − 이탈 1(관측 64). 무태그 "
        "{27,42,49,52} 불변 · 회부 이탈 {53,56,57,59,61,64}."
    ),
    "tests": (
        "437 passed(9.05s, 8 warnings) — c117 기재 437과 동일. 소유권 병기(관측 54 관행): "
        "트리에 twin 트랙 미커밋 변경(forget/proxy.py·tests/test_forget_proxy.py·"
        "research/replay/candidates_v0.jsonl) 잔존 — +1은 그 diff 소유(c115 실측 승계), "
        "devloop 소유 델타 0. devloop의 제품 코드·tests/ 접촉 0(신규 파일은 "
        "research/devloop/scripts/ 계기 2본), regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 11,
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷(배포 영수증 강등안 잔여 실측 전부 완결 — "
        "남은 것은 정훈의 사후 승인 1문장). 유지: A-106.1(서열 1) · P35 구현(서열 2, 시계 "
        "c122) · A-65.2 6차 · 묶음 B(A-85.1 포함, 다음 시계 c126) · A-95.1 · A-115.1 · "
        "A-105.2+영토 TTL · R1 · 후순위 종속. 시계: P2 2026-08-31(17일) · P30 (b)(c) "
        "트리거형 · P36 2026-09-10(실행 세션 몫). 신규 게이트 산출물 없음 — 관측 65 처치 "
        "(수용 기준 ②)·관측 63 파서 수정·관측 66 ①②는 전부 코드/읽기 사이클 몫이라 큐가 "
        "아니라 백로그. 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반 사이클(측정 전환 — 영토에 twin 미커밋 잔존, 절차 2) — 관측 65 질의 길이 "
        "짝지은 대조 2런: 길이 축 판정 유보, 대신 확정 발견 2건.** 계기 "
        "scripts/c118_obs65_field_length_probe.py(읽기 전용·trace 미전달·질의 무인쇄, "
        "80자/300자 짝 8건·순서 교대·low 널 대조·순수/폴백 층화). 결과: 1차 런(신규 "
        "문자열) 순수 짝 Δ중앙값 +4.03s vs 2차 런(반복 문자열) +0.17s — 캐시/상태가 길이 "
        "축을 지배해 판정 유보(널 대조는 두 런 청정 +0.12s). 확정: ① 콘텐츠-결정적 꼬리 "
        "(e42d447e high80 9.06/10.38s 재현 — 부하 귀속 반박) ② 서버 내부 폴백 "
        "fallback→v1 프롬프트-결정성(동일 3/8, 300자 판본만) → 관측 66 신규 등재. 처치 "
        "서열 함의: 기어 선택 정책 ≥ 상수 조정 유지·강화(일간 드리프트 실증: c117 p50 "
        "6.25s vs c118 2.71s 같은 풀). 관측 64 마감(감시 3/3, F2 표 29/29·세션 32연속). "
        "선택 정정 1회 기록: 관측 63 후보를 성문 처분(영토 클린 몫) 확인 후 기각. 외부 "
        "API $0(ollama 로컬) · 실DB 파괴적 조작 0(검색 읽기 전용) · 배포 0 · 제품 코드 "
        "0(사유 병기: twin 잔존 — 측정 사이클)."
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
