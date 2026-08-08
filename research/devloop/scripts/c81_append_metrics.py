"""c81 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c80 정본을 승계하고 ㉒(처치 2 벤치 판정) 신규 등재 + 정산 문장을
36회차로 교체한다.

관측 36 이행 — 능동 프로브 질의 원문은 이 계기 파일에만 둔다:
  PROBE_QUERY = "devloop F2 스코어러 phrase_bonus 자격 필터 설계 — c21 c22
                 처치 설계와 상한 회귀성 실측 내용"  (trace=c81_need_probe)
"""
import json
import re

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 80, f"직전 행이 c80이 아님: c{prev['cycle']}"

# gate_pending: c80 정본 승계 + ㉒ 신규 등재 + 정산 문장 교체
gate = prev["gate_pending"]
gate = re.sub(
    r"정산 1줄\(audit-40 R6, 35회차\):.*$",
    "㉒ 처치 2(자격 필터, c81 본체 진입) 벤치 판정 — LongMemEval 풀런 승인 필요"
    "(P8 (i-b)·P25 (d), 원칙 6 비용 게이트) · 정산 1줄(audit-40 R6, 36회차): "
    "신규 1건(㉒), 해소 0건, 이관 0건.",
    gate,
)
assert "36회차" in gate and "㉒" in gate, "정산 문장 교체 실패"

active_hit, active_miss, inj_hit, inj_miss = 0, 1, 1, 3
row = {
    "cycle": 81,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(81%10=1·81%5=1, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(5스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(능동 프로브+스코어러 "
        "코드 탐색+frictions 확인) = floor **3**, 일반 계열 15연속 floor. metrics "
        "tail/cat/head 0회. ★ 경고 선행 도착 11연속. **grade full**: task_state가 "
        "c80 완주본을 현재로 서빙(요약 커밋 3db1681 = HEAD 일치), c81 턴 계획·작업 "
        "후보(R1 1순위, 설계 지침 '상한 배제·자[尺] 단독', 영토 검사 지시)·기대값 "
        "전부 정확·현재본, 재구성 0. R4 포화 표지 병기: turns 리허설화 계열(턴 "
        "계획이 next_actions로 배달됨)·grade 사건-구동화 계열 — 이 행도 무사건이라 "
        "full이 기본값임을 명기. 관측 35 이행(git status 클린 선확인, 수확 잔존물 0). "
        "[Body] 대조: 20/22 **일치**(기대값, R5 이행)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 21행째, 정본 형식: **능동 1회(hit 0·miss 1) / 주입 4건(hit 1·miss 3)**. "
        "능동 팔 복원(audit-80 R3 이행 — c64~c80 17사이클 만의 첫 능동 검색): "
        "need-aligned 프로브 1회(주제=F2 처치 설계 세부, :8000 라이브, 질의 원문은 "
        "c81_append_metrics.py 헤더에만 — 관측 36). 판정 **miss**(정직): 반환 5건 중 "
        "c18 원인·c21 설계 기억이 온토픽이나 task_state가 이미 배달한 설계의 재확인 — "
        "행동 변경 0(c21 엄격 규칙: 확인은 hit이 아니다). 주입: 캡슐/task_state hit 1 "
        "— R1 작업 단위·자격 술어·상한 배제 근거·판정 계기 경로까지 직접 배달(이 "
        "사이클의 선택과 설계를 선결정). 훅 3건(c43·c42·c45) miss — 동일 트리오 17행째 "
        "회전(record_context_outcome 기록, selection_failure). part_recall 검산(step0): "
        "직전 행 c80 fields(1·3) vs 성분(0·0/1·3) **일치**. R4 표지: hits/miss 동일값"
        "(1·3) 15행 계열은 이 행(1·4)로 이탈 — 분산 회복은 능동 팔 복원의 산물이지 "
        "채점 변경이 아니다(정의 A 불변)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 신규 마찰 없음(단위 테스트 초안의 full-query 보너스 간섭은 저자 "
        "실수, 제품 마찰 아님 — 같은 턴 수정). fixed 0 — **P25 (d) 준수: F2를 fixed로 "
        "계상하지 않는다**(c3 오진 교훈 — frictions_fixed는 검증 후에만). 사실만 병기: "
        "F2 지배 원인 C1의 채점기측 처치(자격 필터 단독)가 62사이클 만에 저장소 몸에 "
        "진입(P25 (a) 64/64·(b) 8/8) — 라이브 판정은 ⑮ 배포+P8 (i-b) 벤치 몫. "
        "관측 34: 라이브 프로브 1건(능동 검색) — 읽기 전용·$0·질의 무인용. "
        "관측 37 ③: 원장 정독 없음(append 스크립트 경유만) — 해당 없음 명기."
    ),
    "tests": (
        "357 passed, 1 warning in 7.53s — 제품 322 + 계기 35(R2 병기). c80 대비 "
        "+5 = tests/test_phrase_qualification.py(제품 계열: 조사 무보너스·숫자 "
        "무보너스·자격 토큰 0.02·무상한 0.12 생존·full-query 0.25 불변). 기존 단언 "
        "완화 0건 = P25 (c) 적중."
    ),
    "work": (
        "audit-80 R1 집행 — F2/C1 스코어러 팔 착수·당일 완료(62사이클 회피 종결). "
        "순서: P25 선등록(predictions.md, 코드 선행) → score_memory phrase_bonus "
        "자격 필터 단독 구현(len≥2·not isdigit, 상한 0.10 배제 — c22 회귀성 실측 "
        "준수; coverage/jaccard/category/recency/temporal 불변 = 자[尺] 단독 규율 c48) "
        "→ 단위 5종 → 판정 계기 c81_phrase_qual_regression.py: **(a) 대수 동치 "
        "64/64 히트**(fixtures_cycle22 전수, 신점수=구점수−junk — 유일 델타가 junk "
        "항임을 동결 재현으로 기계 확인) · **(b) c22 T2b 랭크 재현 8/8 쿼리**(tau·"
        "top-1 전수 일치: e2ee 0.6429, compression top-1 훼손까지 재현 — recency "
        "앵커 캐비앗 무발동) → pytest 357. c22 스윕 계기는 역사 강등 표기(처치 "
        "본체 진입 후 proj 대수는 이중 차감). 라이브 :8000 무접촉(⑮ 미배포 — 도그푸드 "
        "몸의 산술은 이 사이클로 불변). P25 (d) 범위 준수: 벤치·라이브 효과 무주장."
    ),
    "gate_pending": gate,
}

# 쓰기 전 자기 검산 (recall 항등식)
assert row["recall_hits"] == active_hit + inj_hit == 1
assert row["recall_misses"] == active_miss + inj_miss == 4
m = re.search(r"능동 (\d+)회\(hit (\d+)·miss (\d+)\) / 주입 (\d+)건\(hit (\d+)·miss (\d+)\)", row["recall_note"])
assert m, "recall_note 정본 형식 불일치 — part_recall 추출기가 다음 사이클에 실패한다"
a_h, a_m, i_h, i_m = int(m.group(2)), int(m.group(3)), int(m.group(5)), int(m.group(6))
assert a_h + i_h == row["recall_hits"] and a_m + i_m == row["recall_misses"], "항등식 위반"

with open(PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended c{row['cycle']} — recall 검산 OK (fields {row['recall_hits']}·{row['recall_misses']} = 성분 {a_h}·{a_m}/{i_h}·{i_m})")
