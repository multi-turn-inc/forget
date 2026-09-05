#!/usr/bin/env python
"""c122 원장 행 append (일반 사이클 — audit-120 R4 집행: 예측 대장 위생, 무게이트 몫).

관측 61 ② 계보 승계 (c112 원형, c121 판본): 직전 행과의 키 차집합을 쓰기 시점에
인쇄하고, 선언 없는 탈락이면 append를 거부한다.

이번 행의 키 변동 (둘 다 선언):
- 탈락 2건 — silent_misses·silent_misses_note. c121이 oracle replay 판별을 수행해
  신설한 필드이고, c122는 재생을 수행하지 않았다. 값을 0으로 이어 적으면 "이번
  사이클도 차집합 0을 실측했다"는 거짓 주장이 되므로 필드를 싣지 않는다
  (측정하지 않은 것은 0이 아니다 — 관측 61이 막으려던 무선언 탈락과 반대 방향의 규율).
- 신설 1건 — predictions_note. P35 (b) 문면("c122까지 트리거 부재 시 '트리거 도과'를
  원장에 병기")이 이 사이클에 도래해 병기 자리가 필요해졌다.

중복 방지: cycle 122 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json
import os
import sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

# 이번 행에서 의도적으로 제거하는 직전 행 키 (사유 필수). 비어 있음 = 탈락 무선언 금지.
DECLARED_DROPS: dict[str, str] = {
    "silent_misses": (
        "c122는 oracle replay를 재생하지 않았다 — 미측정을 0으로 이어 적는 것은 "
        "허위 실측 주장이므로 필드 미기재. 차기 측정 사이클에서 c121 계기 재사용(CYCLES만 갱신)."
    ),
    "silent_misses_note": "동상 — 값 없는 노트를 싣지 않는다.",
}

ROW = {
    "cycle": 122,
    "date": "2026-08-15",
    "session_count": 1,
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "full",
    "restore_note": (
        "턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read 묶음(스키마 기적재 하네스 — forget 5종이 "
        "이미 노출돼 ToolSearch 불요, 규약 ④ 목적물 충족) / 턴2 = get_task_state + "
        "c48_step0_check.py + git status 병렬 — N=122 일반(스크립트 첫 줄 정본: 122%10=2· "
        "122%5=2), 파트 S ledger_last=121/task_state_cycle=121 판정=일치, freshness "
        "fresh(age 0.35h), Body 24/24 일치 / 턴3 = 첫 유효 행동(frictions.md 후보 정독 = "
        "선택 절차 개시) = 3. 규약 ③ 준수 — metrics 접촉은 c48 인쇄·P16 판정 추출용 "
        "프로그램 파싱·append 스크립트뿐, tail/cat/head 0회. ★ grade full 근거 한 줄: "
        "task_state next_actions가 모드·영토 판정 규칙·측정 후보 서열(②가 이번 작업 단위 "
        "audit-120 R4)·P35 시계 도래 경고·승계 규약까지 직접 지정해 재구성 0으로 착수. "
        "채널 분해: task_state full / 캡슐 miss — 심장박동·W-트랙 점유 지속(F2 계열, "
        "c90~c122 = 33/33 · 세션 36연속). 특기: 캡슐 자기: 라인은 '방향일치 dir_actual' "
        "(c120~c122 동일 3사이클)로 이번 작업과 무교차."
    ),
    "recall_hits": 1,
    "recall_misses": 1,
    "recall_constant_streak": 3,
    "recall_note": (
        "정의 A: 능동 0회 / 주입 2건(hit 1·miss 1) → fields hits=1·misses=1. ① task_state = "
        "hit — 측정 후보 서열 ②(audit-120 R4)·영토 판정 규칙·P35 시계 도래·승계 규약 배달, "
        "이 세션 선택의 직접 원천. ② 캡슐 = miss — 심장박동/W-트랙 점유, 자기: 라인 c120부터 "
        "불변으로 실작업 무교차. (1·1) streak 3 (구간 중 회상 품질 표본 아님 마킹 관행 유지). "
        "★ hit의 성질 병기(이번 사이클의 실수확과 직결): 같은 주입물이 audit-120 R4의 "
        "**결론값('P16 (a) 5/5 성립')을 미검증 표기 없이** 실어 왔다 — 도움과 위험이 같은 "
        "채널로 도착했고, 전사하지 않고 원장 1차 증거로 재도출한 결과 c67 반전을 찾았다. "
        "c41 무번호 관측(권고-전사) 수용 기준 ②의 작동 표본이며 상세는 frictions 보강. "
        "능동 0은 c97~c122 26사이클째 — c121 판별(가설 (b) 수요 소멸 지지)의 기전이 이 "
        "사이클에도 재현: 필요한 정본이 전부 저장소 파일(원장·predictions·amendments)이라 "
        "회상 수요가 파일 정독으로 흡수됐다. 검산: 직전 행 c121 fields(1·1) = 성분(능동 "
        "0·0/주입 1·1) 일치(파트 R 인쇄 확인)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "신규 등재 1 = **관측 69** (미해소 관측 인덱스의 분모가 무선언으로 좁아졌다: 파트 F "
        "파서 OBS_HEADER가 번호를 필수 그룹으로 요구해 **무번호 회부 관측 23건이 한 번도 "
        "계상된 적 없다** — 헤딩 99개 중 무번호 24개, 1차 계수 이 사이클 실측). 무선언 축소의 "
        "증거: amendment-65 §138이 c65에 '미분류 관측 27건(무번호 22 + …)'으로 무번호를 분모에 "
        "포함해 수기 계수했고, c108 파서 상설화(A-95.1·관측 52 처치) 때 그 계열이 조용히 빠졌다 "
        "— 관측 56(분모의 조용한 축소)이 관측 인덱스 자신에게 일어난 자리이며 관측 61의 필드→ "
        "분모 확장판. 한계 병기: '≈58'은 태그 기준 상한이고 무번호 23건의 실제 처분 상태 판별은 "
        "미수행(수용 기준 ①) — 확정 사실은 '23건이 계수 대상에서 구조적 배제'뿐. 관측 63과 "
        "동근·기전 반대(63=위양성, 69=위음성). 처치는 같은 파일·같은 함수이므로 R1 재스코프 "
        "판정에 종속(수용 기준 ④). 해소 0 · 보강 1(c41 무번호 관측 = 권고-전사, 신규 번호 "
        "아님 — 81사이클 만의 첫 실전 표본: 권고가 1항 위반·집행이 2항 준수). 파서 재실행 "
        "검증: open 36 · Δ+1 · 무태그 {27,42,49,52} 불변 · 회부 이탈 {53,56,57,59,61,64} 불변."
    ),
    "open_observations": 36,
    "open_observations_note": (
        "Δ 선언: c121=35 → c122=36, Δ+1 = 등재 1(관측 69) − 이탈 0. c41 보강은 무번호 "
        "헤딩이라 파서 눈 밖(Δ 무영향) — 그 사실 자체가 관측 69의 증상이다."
    ),
    "tests": (
        "437 passed(9.67s, 8 warnings) — c121 기재 437과 동일, devloop 델타 0. 소유권 병기 "
        "(관측 54 관행): 트리에 타 트랙 미커밋 변경 4건 잔존(twin: forget/proxy.py· "
        "tests/test_forget_proxy.py·research/replay/candidates_v0.jsonl / persona: "
        "research/persona/persona_gate_v0.py — c48 파트 A가 HEAD보다 48s 신선으로 검출). "
        "devloop의 제품 코드·tests/ 접촉 0(산출물은 문서 2본 + append 계기 1본), "
        "regression_watch 녹색."
    ),
    "product_code_unchanged_streak": 15,
    "predictions_note": (
        "**P35 (b) 트리거 도과 병기 (문면 이행 — 'c122까지 트리거 부재 시 원장에 병기').** "
        "트리거 = 구현 코드 사이클 완료 + 배포 게이트 통과. c122 시점 둘 다 부재: 구현 "
        "미착수(product_code_unchanged_streak 15 — 영토 규약으로 코드 사이클 15연속 봉쇄), "
        "배포 0. 따라서 **트리거 도과**이며 존속 여부는 회고 c125가 심리한다(문면대로). "
        "무판정 유지 — 등록만으로 진행 계상하지 않는다. 참고: P35가 겨냥한 F2 캡슐 점유는 "
        "이 사이클에도 재현(33/33)이라 표적 자체는 살아 있다. 대차대조 위생 집행분: P16 "
        "결과란 소급 기재 완료(56사이클 지연 해소, audit-120 R4 전반부) · P7 ID 충돌은 "
        "부기로 참조 무결성만 확보하고 개명은 게이트 큐(후반부, 아래 gate_pending)."
    ),
    "gate_pending": (
        "1급 = amendment-115 §6 원터치 결정 패킷. **신규 상신 1 = P7→P7-2 개명 패킷** "
        "(audit-120 R4는 '무게이트'로 배정했으나 c35 amendment-35가 '재넘버링은 절차 규약 "
        "= 정훈 게이트'로 선판정 — 격리 감사가 개정안 금독이라 도달 불가였다, 관측 47 계열. "
        "성문 게이트 우선해 미집행, 편집 3곳까지 확정한 패킷을 predictions.md P7(reembed) "
        "절 부기에 완성: 제목·상태표·frictions 2곳 갱신 + amendment-45 표는 불변 각주 + "
        "metrics 소급 편집 금지). 유지: A-106.1(서열 1) · P35 구현(서열 2 — **시계 c122 "
        "도과, predictions_note 병기**) · A-65.2 6차 · 묶음 B(A-85.1, 시계 c126) · A-95.1 · "
        "A-115.1 · A-105.2+영토 TTL · R1 · audit-120 R5(회고 경유). 시계: P2 2026-08-31(16일) · "
        "P30 (b)(c) 트리거형 · P36 2026-09-10(실행 세션 몫) · P37 2026-08-17(2일). "
        "회고 c125 의제 누적: R1·R3·R5·R6 + **신규 R7**(감사 권고표 몫 칸에 '게이트 상태는 "
        "격리 하 판정 — 집행 손이 성문 게이트와 대조 후 집행' 1줄 의무화, c122가 작동 표본 "
        "1호) + **신규 R8**(무번호 관측 번호 소급 배정 여부 = 관측 69 수용 기준 ③, c35 게이트 "
        "판정의 사정거리 명시 동반). 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**일반(122%10=2) — audit-120 R4 집행(예측 대장 위생, 무게이트 몫). 제품 코드 변경 "
        "0(영토 규약: twin+persona 미커밋 잔존 → 측정·문서 사이클).** ① **P16 결과란 소급 "
        "기재** — (a) 성립(c62~c66 tail/cat/head 0회, 1차 출처 c66 원장 행)을 56사이클 지연 "
        "끝에 대장에 기재. **핵심: 권고 결론값을 전사하지 않고 원장을 재도출해 c67 반전을 "
        "찾았다** — 판정 다음 사이클 c67이 F-절차0 14회차 위반을 냈고, (a)에서 파생된 해석 "
        "('그림자 처치 작동 → 문면 교체 덜 급하다')을 반증해 A-55.1 근거를 '약화'에서 '실측 "
        "표본 1건'으로 승격시켜 두었다. 성립만 실었다면 처치-작동 쪽으로 기운 결과란이 됐다. "
        "부수 확인: P16 (b) 범위 한정('(a)를 F-절차0 해소로 읽지 말 것')이 1사이클 뒤 실측 "
        "으로 검증된 표본. 상태표는 c45 스냅샷이라 P16 소급 삽입하지 않음을 명기. ② **P7 ID "
        "충돌** — 개명 대신 부기 2곳으로 참조 무결성 확보(사실상 식별자 P7(a)/P7b 대 "
        "P7(reembed) 명시 + 상호 참조), 개명은 c35 게이트 선판정 발견으로 패킷화해 큐. "
        "③ **신규 관측 69** — 파트 F 분모가 무번호 회부 관측 23건을 구조적 배제(자동 35 vs "
        "태그 기준 ≈58), amendment-65의 c65 수기 계수 27(무번호 22 포함)과 c108 파서 상설화 "
        "사이의 무선언 축소가 1차 증거. ④ **c41 관측 보강** — 수용 기준 81사이클 만의 첫 "
        "실전 표본(권고 1항 위반 / 집행 2항 준수). ⑤ P35 (b) 트리거 도과 병기(문면 이행). "
        "산출물: predictions.md(P16 결과란 + P7 부기 2) · frictions.md(관측 69 + c41 보강) · "
        "계기 1본. 회고 c125 의제 R7·R8 상신. 외부 API $0 · 실DB 쓰기 1건(add_memory 사이클 "
        "결정 기록)·파괴적 조작 0 · 배포 0."
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
