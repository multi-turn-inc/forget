"""c83 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80·c81·c82 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c82 정본을 승계하고 정산 문장만 38회차로 교체한다(신규 0·해소 0·이관 0 —
관측 38 처치는 무게이트 계기 수리라 게이트 대기 목록 무변동).

관측 36 이행 — 능동 프로브 질의 원문은 이 계기 파일에만 둔다:
  PROBE_QUERY = "git porcelain 리네임 quotepath 비ASCII 경로 파싱 처리 결정 선례 —
                 -z NUL 형식, surrogateescape 인코딩"  (trace=c83_need_probe)
"""
import json
import re

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 82, f"직전 행이 c82가 아님: c{prev['cycle']}"

# gate_pending: c82 정본 승계 + 정산 문장만 38회차 교체
gate = prev["gate_pending"]
gate = re.sub(
    r"정산 1줄\(audit-40 R6, 37회차\):.*$",
    "정산 1줄(audit-40 R6, 38회차): 신규 0건, 해소 0건, 이관 0건.",
    gate,
)
assert "38회차" in gate and "㉒" in gate, "정산 문장 교체 실패"

active_hit, active_miss, inj_hit, inj_miss = 0, 1, 1, 3
row = {
    "cycle": 83,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(83%10=3·83%5=3, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(4스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(관측 38 수용 기준·"
        "파서 실체 정독) = floor **3**, 일반 계열 17연속 floor. metrics tail/cat/head "
        "0회. ★ 경고 선행 도착 13연속. **grade full**: task_state가 c82 완주본을 "
        "현재로 서빙(요약 커밋 5fb80c5 = HEAD 일치), c83 턴 계획·작업 후보(① 관측 38 "
        "처치, 처치 스케치·수용 기준 위치·c73 선례·기대값까지 병기)·기대값(Body "
        "20/22·part_recall c82 fields 1·4 vs 성분 0·1/1·3) 전부 정확·현재본, 재구성 0. "
        "R4 포화 표지 병기: turns 리허설화 계열(턴 계획이 next_actions로 배달됨)·"
        "grade 사건-구동화 계열 — 이 행도 무사건이라 full이 기본값임을 명기. "
        "관측 35 이행(git status 클린 선확인, 수확 잔존물 0). "
        "[Body] 대조: 20/22 **일치**(기대값, R5 이행)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 23행째, 정본 형식: **능동 1회(hit 0·miss 1) / 주입 4건(hit 1·miss 3)**. "
        "능동: need-aligned 프로브 1회(R3 상시 3사이클째, 주제=이번 처치의 기술 선례 "
        "축 — task_state 미배달 영역을 노렸다, :8000 라이브 읽기 전용, 질의 원문은 "
        "c83_append_metrics.py 헤더에만 — 관측 36). 판정 **miss**(정직): 반환 5건 "
        "전부(관측 38 기억·c82 task_state·c76/c31/c35 원장류) 기배달 재확인, 스토어에 "
        "porcelain 기술 선례 자체가 부재 — 행동 변경 0(c21 엄격 규칙). 능동 3연속 "
        "miss: c82 선언대로 task_state 선배달의 구조적 산물 + 미배달 영역을 골라도 "
        "스토어가 그 축을 애초에 모르면 miss라는 두 번째 기전 확인. 주입: 캡슐/"
        "task_state hit 1 — c83 후보 ①·처치 스케치·수용 기준·기대값까지 직접 배달"
        "(선택 선결정). 훅 3건(c43·c42·c45) miss — 동일 트리오 19행째 회전"
        "(record_context_outcome 기록, selection_failure). part_recall 검산(step0): "
        "직전 행 c82 fields(1·4) vs 성분(0·1/1·3) **일치**(기대값). R4 표지: (1·4) "
        "쌍 3행째 — c82가 선언한 새 정착값 후보가 강화됨(정의 A 불변)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 1,
    "frictions_note": (
        "fixed 1 — **관측 38 처치**(frictions.md 수용 기준 ② 집행, 해소 병기): "
        "리네임/카피 행 양쪽 경로 분리(_split_rename_columns, 인용 old 화살표 보호 "
        "+ 무-R/C 행 비분리로 역방향 오인 차단) + 인용 경로 C 스타일 8진 디코드"
        "(_dequote_c_style, surrogateescape — strict는 죽고 replace는 같은 방향 거짓 "
        "음성 재생산이라 유일 복원). c82가 울리라고 둔 종 2건이 의도대로 울리고 정상 "
        "동작 단언으로 교체됨(c73 선례의 완주 첫 표본). 잔여 한계(정직): porcelain "
        "v1 무인용 경로 속 ` -> ` 모호성 — 근본 처치 -z 미집행, 발생 조건 인위적이라 "
        "부채 미등재, 재발 검사 ③ 커버. logged 0 — 신규 마찰 없음. "
        "관측 34: 라이브 프로브 1건(능동 검색) — 읽기 전용·$0·질의 무인용. "
        "관측 37 ③: 원장 정독 없음(append 스크립트 경유만) — 해당 없음 명기."
    ),
    "tests": (
        "373 passed, 1 warning in 7.58s — 제품 322 + 계기 51(R2 병기). c82 대비 "
        "+6 전부 계기 계열(관측 38 단언 2건 교체 + 경계 6종 신규: 카피 행 분리·"
        "무-R/C 화살표 비분리·인용 old 화살표·한국어 리네임 new·이스케이프 3종·"
        "비UTF-8 surrogateescape 왕복). 기존 단언 완화 0건 — 교체 2건은 c82가 "
        "울리라고 둔 종의 의도된 갱신(수용 기준 ② 문면). 제품 코드 무변경(계기 "
        "전용 사이클). 종단 검증 별도: c83_porcelain_e2e.py — 일회용 저장소 실제 "
        "git porcelain(한국어 리네임 양쪽 인용형) 3경로 전부 디스크 실재 복원 OK."
    ),
    "work": (
        "c83 후보 ① 집행 — 관측 38 처치: porcelain_changed_paths 거짓 음성 2종 "
        "수리(부채 계보 c64 등재→c71 부분 상환→c82 잔여 상환+발견→c83 해소). "
        "순수 함수 2종 추가(_split_rename_columns·_dequote_c_style), 검증 3중 = "
        "단위 16종 + 종단(c83_porcelain_e2e.py, 실제 git 출력이 단위 테스트에 없던 "
        "양쪽 인용 리네임형을 실측) + 라이브(출력 문면 불변, part_a가 이 사이클 WIP "
        "3파일 정확 감지). 노트: notes/cycle-83-porcelain-false-negatives-fix.md. "
        "라이브 :8000 접촉 = 읽기(프로브 1회) + 규약 쓰기(task_state·add_memory·"
        "record_context_outcome — 도그푸딩 원칙의 정규 경로)뿐, 실험적 조작 0, "
        "실DB 파괴적 접촉 0, 외부 비용 $0."
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
