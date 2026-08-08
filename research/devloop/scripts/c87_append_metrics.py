"""c87 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80~c86 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c86 정본을 승계하고 정산 문장만 42회차로 교체(신규 0·해소 0·이관 0 —
관측 39 등재는 미분류 관측이고 그 수용 기준 ①은 무게이트 루프 규약이라 게이트 항목 아님).

관측 36 이행 — 능동 프로브 질의 원문은 이 계기 파일에만 둔다:
  PROBE_QUERY = "압축률 측정 3종 진행 상태 — 원시 압축비, rate-distortion, 용량 곡선 중
                 남은 것"  (trace=c87_need_probe, top_k=8, score_breakdown=True)
  [측정 후 병기] 응답에 trace_id 미반환 — 원장 부착 확인은 다음 원장 정독 사이클로
  (노트 §5). 결과 8행 중 self-echo 2행(관측 39 등재 사유), hit 근거 행은 08-01 생성.
"""
import json

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 86, f"직전 행이 c86이 아님: c{prev['cycle']}"

# gate_pending: c86 정본 승계 + 정산 문장 42회차 교체 (항목 변동 없음)
gate = prev["gate_pending"]
OLD_SETTLE = ("정산 1줄(audit-40 R6, 41회차): 신규 0건, 해소 0건, 이관 0건 — c86 "
              "일반 사이클, 관측 36 카운터 집행은 루프 몫(게이트 항목 불변).")
NEW_SETTLE = ("정산 1줄(audit-40 R6, 42회차): 신규 0건, 해소 0건, 이관 0건 — c87 "
              "일반 사이클, 관측 39 등재는 무게이트 루프 규약(게이트 항목 불변).")
assert OLD_SETTLE in gate, "c86 정산 문장을 찾지 못함"
gate = gate.replace(OLD_SETTLE, NEW_SETTLE)
assert "42회차" in gate and "A-85.1" in gate and "㉒" in gate, "정산 교체 검산 실패"

active_hit, active_miss, inj_hit, inj_miss = 1, 0, 1, 3
row = {
    "cycle": 87,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(87%10=7·87%5=2, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(4스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(R3 문면·c84 hit 영수증 "
        "정독 = 선택 착수) = floor **3**. metrics tail/cat/head 0회. ★ 경고 선행 도착 "
        "17연속(A-85.1 미승인 — c87은 N%10=7이라 비해당이나 문면 준수 유지). **grade "
        "full**: task_state가 c86 완주본을 현재로 서빙(요약 커밋 b7924af = HEAD 일치), "
        "c87 턴 계획·모드·작업 후보 순위·기대값(Body 20/22·part_recall c86 쌍) 전부 "
        "정확·현재본, 재구성 0. 관측 35 이행(git status 클린 선확인 — 수확 잔존물 0). "
        "[Body] 대조: 20/22 **일치**(기대값, R5 이행 — 제품 코드 무변경, 다음 행 "
        "기대값 불변)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 27행째, 정본 형식: **능동 1회(hit 1·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "능동 1회 = R3 재가동 프로브(질의 원문은 이 파일 헤더에만, 관측 36): **hit** — "
        "[devloop] c28 기억(2026-08-01 생성, 이 세션 밖)이 압축 3종 중 ① 완료 상태+"
        "산출물 3좌표(노트·커밋 2b8f7d0·스크립트)를 저장소 정독 **전에** 배달, 1차 증거 "
        "교차 검증(커밋 실재·compression-baseline.md 일치) 전부 통과, 도착이 정독 "
        "순서를 바꿈(정의 A·c64 확장). 선등록 판정 규칙(add_memory, 측정 전) 충족. "
        "**self-echo 병기(관측 39 ② 첫 집행): 결과 8행 중 2행이 이 사이클 선등록 기억 "
        "자신** — 판정 무관(hit 근거 행이 선등록 6일 전 생성), 상세 frictions.md 관측 "
        "39. 주입: 캡슐 hit 1 — c87 턴 계획·기대값·후보 순위 직접 배달(선행 도착 "
        "17연속). 훅 3건(c43·c42·c45) miss — 동일 트리오 23행째 회전"
        "(record_context_outcome 기록, selection_failure). §5-2 이분법 성분 명기: 훅 "
        "miss 3 = 채널 선택 실패(배달 포화 아님); 능동 팔 miss 0이라 이분법 비해당. "
        "R4 포화 표지: (1·3)→(2·3)은 능동 팔 재가동에 의한 조성 변화(포화 이탈 아님). "
        "part_recall 검산(step0): 직전 행 c86 fields(1·3) vs 성분(0·0/1·3) **일치**"
        "(기대값). 다음 행(c88) 검산 기대값: fields(2·3) vs 성분(1·0/1·3)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 1 — **미분류 관측 39 등재(유형 판정 회부, 거버넌스 동결 준수): 측정 전 "
        "add_memory 선등록(c86 선례)이 같은 세션 능동 프로브의 결과 창 2/8 슬롯을 "
        "점유** — 관측 30·34·35·36 계열(자기 기록이 측정을 왜곡)의 새 벡터: 잠복기 "
        "수 분(같은 세션)·왜곡 방식 창 점유(변위). c87 판정 자체는 오염 무관(정직 병기: "
        "hit 근거 행 08-01 생성). fixed 0 — 수용 기준 ①(판정 규칙 선등록을 저장소 "
        "파일로, add_memory 결정 기록은 프로브 후로 순서 교정)은 다음 능동 프로브부터 "
        "발효 예고만: 효과는 다음 프로브에서만 판정 가능(관찰 우선, 원칙 2). 관측 36 "
        "자기 이행: 질의 원문은 이 파일 헤더에만. 관측 37 ③: 원장 정독 0회(프로브 "
        "trace_id 미반환은 노트 §5 병기). 관측 34: 대조군 어휘 미소모(게이트 특성화 "
        "0회 — R3 프로브는 need 질의이지 대조군 아님)."
    ),
    "tests": (
        "**373 passed**, 1 warning in 7.79s — 제품 322 + 계기 51(R2 병기). c86 대비 "
        "증감 0(제품·테스트 코드 무변경 — 신규 파일은 노트·frictions 보강·이 append "
        "스크립트뿐). 기존 단언 완화 0건."
    ),
    "work": (
        "**일반 사이클 — R3 능동 팔 재가동(audit-80 R3, c86 후보 ①): 표본이 "
        "돌아왔다.** ① 능동 1회 **hit** — need(c88 후보 제안 의무에 필요한 '압축 3종 "
        "잔여 상태', 후보 ③ 문면이 포인터만 배달)를 제품 검색 경로로 먼저 라우팅: "
        "c28 기억이 ① 완료+산출물 3좌표를 정독 전 배달, 교차 검증 전부 일치, yellow "
        "trust 규약(행동 전 1차 증거 확인)과 교차 검증 의무가 실제로 맞물린 표본. "
        "R3 원장: c84 hit 1 → c85·c86 공백 → c87 hit 1(2연속 공백 종결, c84 hit "
        "조건 '포인터만 배달된 문면'의 동형 재현 성공). ② need 해소: 압축 3종 잔여 = "
        "②의 곡선화(top-k 스윕 중간점)+③ 용량 곡선 전체, 둘 다 격리 인스턴스 작업"
        "(무게이트) — c88 후보 '백로그 재평가'가 실행 가능한 문면이 됨. ③ **관측 39 "
        "등재**: 선등록의 자기 점유(2/8 변위, 같은 세션 수 분 잠복기) — 순서 교정"
        "(선등록→저장소 파일·git 타임스탬프, add_memory→프로브 후) 다음 능동 프로브부터 "
        "발효 예고. ④ 프로브 trace_id 미반환 병기(노트 §5 — 원장 부착 확인은 다음 원장 "
        "정독 사이클). 산출물 = 노트 cycle-87-r3-arm-reactivation.md + frictions.md "
        "관측 39 + 이 append 스크립트. 라이브 접촉 = 제품 검색 1회(R3 표본, trace 라벨 "
        "전달)+규약 쓰기(add_memory 2·task_state·record_context_outcome)뿐 · 원장 정독 "
        "0회 · 실DB 무접촉 · 외부 비용 $0. A-85.1 미승인 준수(비해당 사이클이나 문면 "
        "유지)."
    ),
    "gate_pending": gate,
}

# 자기 검산 — recall 항등식
assert row["recall_hits"] == active_hit + inj_hit
assert row["recall_misses"] == active_miss + inj_miss
assert "능동 1회(hit 1·miss 0) / 주입 4건(hit 1·miss 3)" in row["recall_note"]
assert "self-echo" in row["recall_note"], "관측 39 ② self-echo 병기 누락"

with open(PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended: cycle={row['cycle']} hits={row['recall_hits']} misses={row['recall_misses']}")
