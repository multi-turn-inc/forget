"""c85 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80~c84 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c84 정본을 승계하고 ⑳에 A-85.1 합류 + 정산 문장 40회차 교체
(신규 1건 = A-85.1, audit-80 R4가 회고 85로 회부한 이행분 — 해소 0, 이관 0.
amendment-85 §6-2의 5묶음 재편은 R5 이행이며 항목 수 불변 재포장).

관측 36 이행 — 이 사이클 질의 원문은 이 계기 파일에만 둔다:
  PROBE_QUERY  = "정훈 결정 — devloop 개정안 승인 여부, 개헌 채널 처분, 게이트 결정
                  패키지 상신에 대한 응답"  (trace=c85_need_probe, 능동 계상)
  REPLAY_QUERY = "아핀 중심화 점수 축 처분 판정 — 남은 무게이트 처치가 있는가, 배포
                  부채 상한, 재개봉 조건"  (trace=c85_oracle_replay_c84, 계기 — 계상
                  제외 c68, 컷오프 created_at ≤ 2026-08-08T17:00Z)
"""
import json
import re

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 84, f"직전 행이 c84가 아님: c{prev['cycle']}"

# gate_pending: c84 정본 승계 + ⑳ A-85.1 합류 + 정산 문장 40회차 교체
gate = prev["gate_pending"]
gate = gate.replace(
    "⑳ A-75.1·A-75.2·A-75.3.",
    "⑳ A-75.1·A-75.2·A-75.3 · A-85.1(블라인드 복원 프로브 — amendment-85 §6-1).",
)
assert "A-85.1" in gate, "⑳ 합류 실패"
gate = re.sub(
    r"정산 1줄\(audit-40 R6, 39회차\):.*$",
    "정산 1줄(audit-40 R6, 40회차): 신규 1건(A-85.1 — audit-80 R4 회부 이행분), "
    "해소 0건, 이관 0건. 묶음 재편 = amendment-85 §6-2(R5 이행, 재포장 — 항목 수 불변, "
    "우선순위 권고 A배포>B문면>C거버넌스).",
    gate,
)
assert "40회차" in gate and "㉒" in gate, "정산 문장 교체 실패"

active_hit, active_miss, inj_hit, inj_miss = 0, 1, 1, 3
row = {
    "cycle": 85,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 회고 사이클(85%5=0·85%10=5, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(4스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(회고 입력 수집: "
        "frictions·predictions Read + amendments/audits 목록) = floor **3**, 회고 유형 "
        "2번째 floor-3(c75 선례 재현, c65의 4 대비 P20 배치 효과 유지). metrics "
        "tail/cat/head 0회. ★ 경고 선행 도착 15연속. **grade full**: task_state가 c84 "
        "완주본을 현재로 서빙(요약 커밋 b63aba8 = HEAD 일치), 회고 모드 판정·예약 안건 "
        "4건(R4 블라인드 설계·oracle replay·포화 해석·상신 점검)·산출물 경로·기대값"
        "(Body 20/22·part_recall c84 쌍) 전부 정확·현재본, 재구성 0. R4 포화 표지 병기: "
        "무사건 행 full 기본값. 관측 35 이행(git status 클린 선확인). [Body] 대조: "
        "20/22 **일치**(기대값, R5 이행 — c85도 제품 코드 무변경, 다음 행 기대값 불변)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 25행째, 정본 형식: **능동 1회(hit 0·miss 1) / 주입 4건(hit 1·miss 3)**. "
        "능동: R3 상시 5사이클째, need-aligned 프로브 1회(주제=이 회고의 실need인 상신 "
        "상태 점검, :8000 라이브 읽기 전용, 질의 원문은 이 스크립트 헤더에만 — 관측 36). "
        "판정 miss(정직 근거): 반환 8건 전부 루프 자기 기록 — 정훈 결정 기억의 **부재** "
        "재확인은 §1 논거로 쓰였으나 신규 정보 아님. amendment-85 §5-2의 이분법으로 "
        "**배달 포화형 miss**(채널 실패 아님 — need가 이미 원장·task_state로 전문 배달된 "
        "사이클). 계기 검색 1회 별도: oracle replay(trace=c85_oracle_replay_c84)는 c68 "
        "선언으로 계상 제외 — 결과는 silent_miss 0(amendment-85 부록 C, top-10 관측창 "
        "한정 병기). 주입: 캡슐/task_state hit 1 — 회고 안건·기대값 직접 배달(선행 도착이 "
        "턴 계획 결정). 훅 3건(c43·c42·c45) miss — 동일 트리오 21행째 회전"
        "(record_context_outcome 기록, selection_failure). part_recall 검산(step0): 직전 행 "
        "c84 fields(2·3) vs 성분(1·0/1·3) **일치**(기대값). R4 표지: (1·4) 쌍에 재진입 — "
        "c84 hit은 조건 교차의 사건이었고 이 회고는 조건 밖(전문 배달)임을 성분으로 명기. "
        "다음 행(c86) 검산 기대값: fields(1·4) vs 성분(0·1/1·3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 신규 마찰 없음. fixed 0 — 회고는 판정·문서 사이클(c77 선례). "
        "마찰 재발률 정독 결과는 amendment-85 §3: F-절차0 재발 0(23사이클)·F2 잠복 "
        "불변(처치 축은 c81 전진, 라이브 판정은 ⑮ 인질)·관측 38 등재→처치 간격 1사이클 "
        "완결·관측 36 카운터 집행 표본 여전히 0(§7 Q3 잔존 주의로 명기, c86+ 후보). "
        "관측 34: 신선 OFF 팔 미추출(프로브·replay 질의 무인용, 원문은 이 헤더에만). "
        "관측 37 ③: metrics.jsonl 정독 사이클 — 평문 비밀 스캔(패턴 5종) **실질 0건**"
        "(기계 매치 3건 전부 c80 행의 스캔 패턴 목록 자기 인용 — 기지 오탐 등재, "
        "amendment-85 서두)."
    ),
    "tests": (
        "**373 passed**, 1 warning in 7.27s — 제품 322 + 계기 51(R2 병기). c84 대비 "
        "증감 0(코드 변경 0행 — 회고 규정 준수, 신규 파일은 amendment-85.md와 이 append "
        "스크립트뿐). 기존 단언 완화 0건."
    ),
    "work": (
        "**회고 사이클(85%5=0) — 대상은 코드가 아니라 LOOP.md와 지시서. 산출물 = "
        "amendments/amendment-85.md(제안만, 적용 0 — 정훈 게이트).** ① 헤드라인: "
        "audit-80 루프 몫 권고 4건이 4사이클 안에 집행·상시화(R1 자격 필터 c81 당일 — "
        "62사이클 회피 종결·R2 분리 병기·R3 능동 팔 복원·R4 포화 공시) — audit-70에 이어 "
        "2번째 전량 집행 창. 사람 채널은 불변: 정훈측 해소 이 창 0건, 개헌 채널 80사이클 "
        "0/4. ② **A-85.1**(유일 신규 문면안, audit-80 R4 회부 이행): 블라인드 복원 프로브 "
        "— N%10==6 사이클에서 get_task_state **이전에** 캡슐+정본+검색≤1회로 복원 선언을 "
        "쓰고 사후 대조(blind_restore=match/partial/miss), 프로브 턴 분리 표기. restore "
        "계열의 리허설화(계획이 next_actions로 배달됨)에 판별력을 되돌리는 설계. ③ "
        "audit-80 R5 이행: 게이트 21+항목을 결정 5묶음으로 재포장(A 배포 한 번 = 3시계 "
        "76·74·69 + ⑮ + c84 재개봉 판정 + ㉑ 동승, 4번째 일치 권고 / B 문면 승인 5건 / "
        "C 거버넌스 / D 설계 / E 비용·외부), 우선순위 A>B>C. ④ oracle replay(백로그 8, "
        "예약분): c84 선언문 사후 재생(컷오프 c84 개시 이전) — **silent_miss 0**, 디스크+"
        "회상 합집합에 구멍 없음(top-10 관측창 한정·구척도 몸 유효성 병기, 부록 C). ⑤ "
        "포화 해석 갱신(예약분): 15행 상수는 지표 교체 없이 측정 설계(R3)로 깨졌다 — "
        "능동 miss 이분법(채널 실패/배달 포화) 판독 규칙 등재. ⑥ 동결 예외 4회차 자인 — "
        "A-65.2 3차 재상신 선결. 3문 판정: 물러짐 아니오(P25 선등록·당일 3/3, 완화 0) / "
        "반영 저장소 충실·라이브 0(부채는 c84 상한으로 봉인) / 신규 회피 0(잔존 주의 2건 "
        "명기). 신규 예측 0건(정직 근거: 적용 없는 제안만 — LOOP.md ② 의무는 적용 시점 "
        "발생, c75 선례). 제품 코드 무변경 · 라이브 접촉 = 읽기 프로브 2회(능동 1·계기 1) "
        "+ 규약 쓰기(task_state·add_memory·record_context_outcome)뿐 · 실DB 무접촉 · "
        "외부 비용 $0."
    ),
    "gate_pending": gate,
}

# 자기 검산 — recall 항등식
assert row["recall_hits"] == active_hit + inj_hit
assert row["recall_misses"] == active_miss + inj_miss
assert "능동 1회(hit 0·miss 1) / 주입 4건(hit 1·miss 3)" in row["recall_note"]

with open(PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended: cycle={row['cycle']} hits={row['recall_hits']} misses={row['recall_misses']}")
