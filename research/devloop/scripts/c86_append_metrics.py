"""c86 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80~c85 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c85 정본을 승계하고 정산 문장만 41회차로 교체(신규 0·해소 0·이관 0 —
관측 36 카운터 집행은 루프 몫이라 게이트 항목 불변).

관측 36 이행 — 이 사이클의 질의 원문은 계기 파일에만 있다: 앵커 4건 원문은
scripts/c86_anchor_recurrence_probe.py의 ANCHORS 상수(c74 계기 2본에 이미 커밋된
동일 문자열). 능동 검색 0회라 프로브 질의는 없다.
"""
import json

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 85, f"직전 행이 c85가 아님: c{prev['cycle']}"

# gate_pending: c85 정본 승계 + 정산 문장 41회차 교체 (항목 변동 없음)
gate = prev["gate_pending"]
OLD_SETTLE = ("정산 1줄(audit-40 R6, 40회차): 신규 1건(A-85.1 — audit-80 R4 회부 "
              "이행분), 해소 0건, 이관 0건.")
NEW_SETTLE = ("정산 1줄(audit-40 R6, 41회차): 신규 0건, 해소 0건, 이관 0건 — c86 "
              "일반 사이클, 관측 36 카운터 집행은 루프 몫(게이트 항목 불변).")
assert OLD_SETTLE in gate, "c85 정산 문장을 찾지 못함"
gate = gate.replace(OLD_SETTLE, NEW_SETTLE)
assert "41회차" in gate and "A-85.1" in gate and "㉒" in gate, "정산 교체 검산 실패"

active_hit, active_miss, inj_hit, inj_miss = 0, 0, 1, 3
row = {
    "cycle": 86,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(86%10=6·86%5=1, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(5스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(작업 선택 정독: 관측 36 "
        "원문+c74 계기) = floor **3**. metrics tail/cat/head 0회. ★ 경고 선행 도착 "
        "16연속. **grade full**: task_state가 c85 완주본을 현재로 서빙(요약 커밋 "
        "28f2a49 = HEAD 일치), c86 턴 계획·모드·작업 후보 순위·기대값(Body 20/22·"
        "part_recall c85 쌍·A-85.1 미승인 금지 경고) 전부 정확·현재본, 재구성 0. "
        "**A-85.1 블라인드 프로브: c86이 N%10==6이지만 미승인이라 미실행**(미승인 "
        "선적용 금지 준수 — 경고가 next_actions로 선행 배달된 덕이며, 이 준수 자체가 "
        "문면 무해의 증거는 아니다, c67 (가)). 관측 35 이행(git status 클린 선확인). "
        "[Body] 대조: 20/22 **일치**(기대값, R5 이행 — 제품 코드 무변경, 다음 행 "
        "기대값 불변)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 26행째, 정본 형식: **능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "능동 0 정직 근거: 이 사이클의 need(관측 36 문면·c74 자[尺]·앵커 값)는 전부 "
        "저장소 파일 정독으로 충족 — 능동 검색을 쓸 결핍이 없었다(R3 프로브 지속은 "
        "후보 ②였으나 최소 가치 단위 1개 원칙으로 미집행, c87+ 후보 유지). 계기 검색 "
        "13회(3런: 절단 1차→접두 폴백 2차→창 검시 3차)+health 3회는 c68 선언으로 계상 "
        "제외(전부 trace 미전달 — 장부 무오염). 주입: 캡슐 hit 1 — c86 턴 계획·A-85.1 "
        "미승인 경고·기대값 직접 배달(선행 도착이 준수를 만든 16연속째). 훅 3건"
        "(c43·c42·c45) miss — 동일 트리오 22행째 회전(record_context_outcome 기록, "
        "selection_failure). §5-2 이분법 성분 명기: 훅 miss 3 = 채널 선택 실패(배달 "
        "포화 아님), 능동 팔은 표본 0이라 이분법 해당 없음. R4 포화 표지: (1·4)→(1·3)은 "
        "포화 이탈이 아니라 능동 팔 미가동에 의한 조성 변화. part_recall 검산(step0): "
        "직전 행 c85 fields(1·4) vs 성분(0·1/1·3) **일치**(기대값). 다음 행(c87) 검산 "
        "기대값: fields(1·3) vs 성분(0·0/1·3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 신규 관측 등재 없음(거버넌스 동결 유지), 관측 36에 **집행 보강** "
        "추가만. fixed 0 — 측정 사이클, 자[尺] 무변경(c48 규율). **관측 36 수용 기준 ② "
        "첫 집행: 카운터 0 유지, 집행 표본 1호 성립**(amendment-85 §7 Q3 잔존 주의 ①의 "
        "처방 이행) — A2·A3·A4 소수 4자리 재현(0.0119·0.3371·0.3184), A1만 경계 반전"
        "(0.0263→0.0324, margin +0.0024)이나 루프 기억 귀속 불가(top-10 전원 c74 이전 "
        "생성·배제 0·c74 대조 창 부재)로 선등록 규칙상 **증분 유보 — 감사 90 심문 대상 "
        "자기 병기**. 지속성: A3·A4 봉우리 유지(top-1=c63 노트, 등재 3일째) — '영구 "
        "발화' 두 번째 종단 점. 역치 아래 잠식 신규 계측: 루프 기억이 앵커 top-5의 "
        "5/20 슬롯(A2 top-1 포함), A1 개방 시 주입 3건 중 1건이 루프 — 처치 후보 ③ "
        "정량 근거. 관측 36 자기 이행: 질의 원문은 계기 파일에만. 관측 37 ③ 병기: "
        "원장 접촉 = 앵커 매칭 행 query·filters 컬럼 한정(정독 아님), 접촉 표면 비밀 "
        "0건. 관측 34: 대조군 어휘 소모 — 전 수치가 c74 직전 측정 대비."
    ),
    "tests": (
        "**373 passed**, 1 warning in 7.87s — 제품 322 + 계기 51(R2 병기). c85 대비 "
        "증감 0(제품·테스트 코드 무변경 — 신규 파일은 계기 스크립트·노트·원자료와 이 "
        "append 스크립트뿐). 기존 단언 완화 0건."
    ),
    "work": (
        "**일반 사이클 — 관측 36 재발 카운터 첫 집행(수용 기준 ②, 집행 표본 1호).** "
        "계기 scripts/c86_anchor_recurrence_probe.py(읽기 전용, 자[尺] c74와 동일 고정, "
        "판정 규칙 측정 전 선등록)로 앵커 4건 재측정: ① **카운터 0 유지** — 새 반전은 "
        "A1 1건(0.0263→0.0324, margin +0.0024 경계 반전)이나 창 검시(top-10 배제 포함) "
        "결과 루프 기억 귀속 불가(전원 c74 이전 생성·배제 0) → 선등록 규칙상 증분 유보, "
        "감사 90 심문 대상 자기 병기. ② A2·A3·A4는 c74 값 소수 4자리 재현 — 계기 "
        "정밀도(±0.0001) 1일 간격 유지. ③ 지속성: A3·A4 top-1이 여전히 c63 노트(3일째) "
        "— c74 '영구 발화' 주장의 두 번째 종단 점. ④ 역치 아래 잠식 신규 계측: 루프 "
        "기억이 앵커 top-5의 5/20 슬롯(A2 top-1), A1 게이트 개방 시 주입 3건 중 1건이 "
        "루프 기억 — 관측 36 처치 ③(격리, 게이트 묶음 D ⑲)의 정량 근거. ⑤ 계기 개선: "
        "4앵커 전창 원자료(c86_anchor_rows.json)를 남겨 다음 재측정부터 반전 원인의 "
        "기억 단위 귀속 가능(c74의 대조군 검시 부재 갭 봉합). ⑥ 재현 규약 교훈(정직): "
        "1차 실행이 접두 절단 질의·무필터로 0.0214(평지)를 냈다 — 질의·필터 동일성이 "
        "깨지면 verdict가 바뀐다, 접두 폴백으로 원장 전체 질의+filters 복원 후 확정. "
        "A-85.1 미승인 준수(N%10==6이나 미실행). 산출물 = 계기+원자료+노트 "
        "cycle-86-anchor-recurrence-counter.md+frictions.md 관측 36 보강. 라이브 접촉 = "
        "읽기 프로브(search 13·health 3, trace 미전달) + 규약 쓰기(add_memory·task_state·"
        "record_context_outcome)뿐 · 원장 접촉 ro 앵커 매칭 행 한정 · 실DB 무접촉 · "
        "외부 비용 $0."
    ),
    "gate_pending": gate,
}

# 자기 검산 — recall 항등식
assert row["recall_hits"] == active_hit + inj_hit
assert row["recall_misses"] == active_miss + inj_miss
assert "능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)" in row["recall_note"]

with open(PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended: cycle={row['cycle']} hits={row['recall_hits']} misses={row['recall_misses']}")
