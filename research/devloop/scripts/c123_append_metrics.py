#!/usr/bin/env python
"""c123 원장 행 append (일반 사이클 — 관측 69 수용 기준 ① 집행: 무번호 절 처분 판정).

관측 61 ② 계보 승계 (c112 원형, c121·c122 판본): 직전 행과의 키 차집합을 쓰기 시점에
인쇄하고, 선언 없는 탈락이면 append를 거부한다.

이번 행의 키 변동: **없음** (added ∅ · dropped ∅). c122가 선언 탈락시킨 silent_misses
2키는 c123도 재생을 수행하지 않았으므로 계속 부재이며, 이는 직전 행 대비 차집합이
아니라 이미 반영된 상태다 — 재선언 불요(직전 행에도 없다).

자[尺] 불변 선언 (관측 990 규율): 이 사이클은 open_observations의 **자를 바꾸지 않았다.**
36은 c108 파서(번호 있는 회부)의 값 그대로이고, 이 사이클이 확정한 정직한 범위
48~57은 **같은 표에 병기**될 뿐 공식 델타를 대체하지 않는다. 분모 교체는 수용 기준 ②의
처치이고 그 조건은 audit-120 R1 재스코프(회고 c125)에 종속된다.
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {}

ROW = {
    "cycle": 123,
    "date": "2026-08-15",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스 — forget 5종 "
        "노출 상태라 ToolSearch 불요, 규약 ④ 목적물 충족) / 턴2 = get_task_state + "
        "c48_step0_check.py + git status 병렬 — N=123 일반(스크립트 첫 줄 정본: 123%10=3· "
        "123%5=3), 파트 S ledger_last=122/task_state_cycle=122 판정=일치, freshness "
        "fresh(age 0.35h), Body 24/24 일치 / 턴3 = 첫 유효 행동(파서 소스 + 대장 헤딩 조회 = "
        "계기 설계 개시) = 3. 규약 ③ 준수 — metrics 접촉은 c48 인쇄와 append 스크립트뿐, "
        "tail/cat/head 0회. ★ grade full 근거 한 줄: task_state next_actions가 모드·영토 "
        "판정 규칙·측정 후보 서열을 직접 지정했고 서열 ①(관측 69 수용 기준 ①)이 곧 이 "
        "사이클의 작업 단위였다 — 재구성 0으로 착수. 채널 분해: task_state full / 캡슐 miss "
        "— 심장박동·W-트랙 점유 지속(F2 계열, c90~c123 = 34/34 · 세션 37연속). 특기: 캡슐 "
        "자기: 라인이 c122 교훈(감사 권고 결론값은 입력이지 출력이 아니다)으로 갱신됐고 "
        "**이번 작업과 실제로 교차했다** — c120~c122 3사이클 무교차 뒤 첫 교차이나, 도착 "
        "시점에 이미 같은 규율을 계기 설계에 넣고 있어 행동을 바꾸지는 않았다(miss 유지)."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 4,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 측정 후보 서열 ①(관측 69 수용 기준 ①, '이 사이클이 미수행으로 남긴 몫'이라는 "
        "자기 표기까지 포함)·영토 판정 규칙·쓰기 규약 3종을 배달, 이 세션 선택의 직접 원천. "
        "② 캡슐 = miss — 심장박동/W-트랙 점유. 캡슐 자기: 라인은 c122 교훈으로 갱신돼 주제 "
        "교차는 있었으나 행동 변경 없음(도착 시 이미 같은 규율 적용 중) — 정의 A상 hit는 "
        "'행동을 바꾼 신규 정보'이므로 miss로 채점한다. (1·1) streak 4. 능동 0은 c97~c123 "
        "27사이클째 — c121 판별(가설 (b) 수요 소멸) 기전 재현: 이번 작업의 정본이 전부 "
        "저장소 파일(frictions.md 본문·파서 소스)이라 회상 수요가 파일 정독으로 흡수됐다. "
        "검산: 직전 행 c122 fields(1·1) = 성분(능동 0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 번호 0 · 해소 0 · **보강 1 = 관측 69 수용 기준 ① 집행**(무번호 절 21건의 처분 "
        "상태를 절별 판정). 판정표: 이탈 1(회상 트랙 혼선 c21 → F7 승격, 대장 헤딩 자체가 "
        "주석) / 실질 처분·이탈 주석 없음 4(회귀 flaky c24 · 자동캡처 스코프 c28 · 자[尺] "
        "동시 변경 c48 · 평탄도 봉우리 c62의 도달 계측 처치분만 c63 관측 26으로 승계) / "
        "존속-사람 게이트 6(코퍼스 c27 · 영토 오탐 c31 · 절차0 비용 c44·45 · 규칙 10/12 c45 · "
        "F-절차0 5회차 c49 · 포인터 축약 c51·55) / 존속-관측만 10. **두 건의 정정이 이 판정의 "
        "실수확이다.** ① c122의 계수(무번호 24·회부 23)는 **계수 규칙을 발행하지 않은 수**였다 "
        "— c123 규칙(계기에 성문화)으로는 25·21이고, 어느 쪽이 틀렸다기보다 대조가 원리적으로 "
        "불가능했다(관측 30·34 계열 = 자가 선언 없이 바뀌면 시점 간 비교가 소멸, 이번엔 그 "
        "자가 계수 규칙). ② 태그 기준 자체가 살아 있는 관측을 떨어뜨린다 — c41(권고-전사)은 "
        "c122가 보강을 붙인 살아 있는 관측인데 헤딩에 회부 태그가 없어 상한 21에도 미포함. "
        "무번호 사각은 위음성이 **두 겹**(번호 없음 → 파싱 탈락, 태그 없음 → 태그 계수에서도 "
        "탈락)이다. 수용 기준 ②③④(파서 확장·번호 소급 배정·R1 종속)는 **미집행 — 이 사이클은 "
        "분모를 고치지 않고 분모의 참값만 확정한다**."
    ),
    "open_observations": 36,
    "open_observations_note": (
        "Δ 선언: c122=36 → c123=36, Δ+0 (등재 0 − 이탈 0; 관측 69 보강 헤딩은 번호 있는 "
        "보강이라 파서가 last=123으로 갱신할 뿐 분모 무영향). **정직 병기 — 이 값은 재고의 "
        "일부다**: 이번 사이클이 문단 정독으로 확정한 정직한 크기는 **48~57**이다(자동 36 + "
        "무번호 존속 20(엄격 하한 16) + 무태그 생존 1(c41) − 중복 후보 4(절차5 미도달 c44↔관측 "
        "55 · F-절차0 계열 3건↔A-55.1/관측 47)). 즉 원장이 단일 진실로 인쇄해 온 36은 실제 "
        "재고를 약 25~37% 낮게 서술한다. c122의 grep 추정 '≈58'은 상한 근처였고 정독은 그것을 "
        "확정이 아니라 **범위의 위쪽 끝**으로 강등시켰다 — 정독을 건너뛰었다면 루프는 이번엔 "
        "재고를 **과대** 서술하는 쪽으로 틀렸을 것이다(c122 교훈의 반대 방향 표본). 자[尺] "
        "불변 선언(관측 990 규율): 공식 델타는 옛 자(파서 36)로 적고 새 범위는 병기만 한다 — "
        "분모 교체는 수용 기준 ②의 처치이고 R1 재스코프(회고 c125)에 종속된다."
    ),
    "tests": (
        "437 passed(9.36s, 8 warnings) — c122 기재 437과 동일, devloop 델타 0. 소유권 병기 "
        "(관측 54 관행): 트리에 타 트랙 미커밋 변경 5건 잔존(twin: forget/proxy.py· "
        "tests/test_forget_proxy.py·research/replay/candidates_v0.jsonl + 신규 미추적 2 "
        "research/replay/verdict_dataset_v1.jsonl·.manifest.json — persona 1건은 c122 이후 "
        "aabeaef로 커밋되어 영토에서 이탈). devloop의 제품 코드·tests/ 접촉 0(산출물은 "
        "frictions 보강 1 + 계기 2본), regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 16,
    "predictions_note": (
        "이 사이클의 예측 등록 0 (설계 변경이 아니라 기존 관측의 수용 기준 이행이므로 선등록 "
        "불요). 타 세션 산출물 관측(원장 기재만, devloop 몫 아님): P37 2026-08-17 시계가 "
        "커밋 4ed88f1로 **판정 완료** — 2×2 중 접지 축 반증·배분 공식 축 지지(p=0.0118). "
        "P35 (b)는 c122에 트리거 도과를 병기했고 존속 심리는 회고 c125 그대로 계류 "
        "(구현 미착수 — product_code_unchanged_streak 16으로 코드 사이클 16연속 봉쇄)."
    ),
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷. 유지: P7→P7-2 개명 패킷(c122 상신) · "
        "A-106.1(서열 1) · P35 구현(서열 2) · A-65.2 6차 · 묶음 B(A-85.1, 시계 c126) · "
        "A-95.1 · A-115.1 · A-105.2+영토 TTL · R1 · audit-120 R5(회고 경유). 시계: "
        "P2 2026-08-31(16일) · P30 (b)(c) 트리거형 · P36 2026-09-10(실행 세션 몫) · "
        "P37 **판정 완료**(4ed88f1, 타 세션). 회고 c125 의제 누적: R1·R3·R5·R6·R7·R8 — "
        "**R8에 이번 판정표를 재료로 첨부**(무번호 21건 중 실제 존속 16, 이탈 1, 실질 처분· "
        "주석 없음 4 → 번호 소급 배정의 대상 규모가 처음으로 수치화됐다). 원칙 5 준수 — "
        "전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반(123%10=3) — 관측 69 수용 기준 ① 집행: 무번호 관측 절의 처분 상태를 절별로 "
        "판정하고 미해소 재고의 정직한 크기를 범위로 확정. 제품 코드 변경 0(영토 규약: twin "
        "3 + replay 미추적 2 잔존 → 측정·문서 사이클, 16연속).** ① 계기 "
        "`c123_unnumbered_obs.py` — 대장의 무번호 절을 열거하고 절별 **마지막 문단**(대장이 "
        "그 관측에 대해 마지막으로 한 말)을 상수 크기로 인쇄. 계기는 판정하지 않는다: 파서 "
        "_EXIT_MARKS를 무번호에 재사용하면 관측 63(부정문 위양성)을 상속하므로 이탈 여부는 "
        "손이 정독으로 정한다. 판정 규칙도 계기에 성문화(대장이 정본 — 절 자체에 승격·종결 "
        "주석이 있어야 이탈, amendment 단독 처분은 이 눈 밖). ② 판정표 21건 = 이탈 1 / 실질 "
        "처분·주석 없음 4 / 존속-게이트 6 / 존속-관측만 10. ③ **정직한 재고 = 48~57** "
        "(원장 인쇄 36은 25~37% 과소). ④ 정정 2건: c122 계수는 규칙 미발행으로 대조 불가 "
        "(25·21 대 24·23) · 태그 기준이 살아 있는 c41을 떨어뜨림 = 위음성 두 겹. ⑤ 수용 기준 "
        "②③④는 미집행 — 처치가 관측 63과 같은 파일·같은 함수라 R1 재스코프(회고 c125)에 "
        "종속된다는 기준 ④를 준수. **분모를 고치지 않고 분모의 참값을 확정한 사이클.** "
        "산출물: frictions.md(관측 69 보강) · 계기 2본(판별 계기 + append). 외부 API $0 · "
        "실DB 쓰기 1건(add_memory 사이클 결정 기록)·파괴적 조작 0 · 배포 0."
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
