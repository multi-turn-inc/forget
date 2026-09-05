"""c82 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80·c81 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c81 정본을 승계하고 정산 문장만 37회차로 교체한다(신규 0·해소 0·이관 0).

관측 36 이행 — 능동 프로브 질의 원문은 이 계기 파일에만 둔다:
  PROBE_QUERY = "devloop c48_step0_check part_a part_b 파싱 테스트 부채 — porcelain
                 파싱 결함과 계기 테스트 상환 이력"  (trace=c82_need_probe)
"""
import json
import re

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 81, f"직전 행이 c81이 아님: c{prev['cycle']}"

# gate_pending: c81 정본 승계 + 정산 문장만 37회차 교체
gate = prev["gate_pending"]
gate = re.sub(
    r"정산 1줄\(audit-40 R6, 36회차\):.*$",
    "정산 1줄(audit-40 R6, 37회차): 신규 0건, 해소 0건, 이관 0건.",
    gate,
)
assert "37회차" in gate and "㉒" in gate, "정산 문장 교체 실패"

active_hit, active_miss, inj_hit, inj_miss = 0, 1, 1, 3
row = {
    "cycle": 82,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(82%10=2·82%5=2, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(4스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(frictions 확인 + 부채 "
        "실체 정독) = floor **3**, 일반 계열 16연속 floor. metrics tail/cat/head 0회. "
        "★ 경고 선행 도착 12연속. **grade full**: task_state가 c81 완주본을 현재로 "
        "서빙(요약 커밋 a702cd4 = HEAD 일치), c82 턴 계획·작업 후보(① 파싱 부채 "
        "상환, 근거 audit-80 §3-(b)·c64 등재까지 병기)·기대값(Body 20/22·part_recall "
        "c81 fields 1·4 vs 성분 0·1/1·3) 전부 정확·현재본, 재구성 0. R4 포화 표지 "
        "병기: turns 리허설화 계열(턴 계획이 next_actions로 배달됨)·grade 사건-구동화 "
        "계열 — 이 행도 무사건이라 full이 기본값임을 명기. 관측 35 이행(git status "
        "클린 선확인, 수확 잔존물 0). [Body] 대조: 20/22 **일치**(기대값, R5 이행)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 22행째, 정본 형식: **능동 1회(hit 0·miss 1) / 주입 4건(hit 1·miss 3)**. "
        "능동: need-aligned 프로브 1회(R3 상시 이행 2사이클째, 주제=이번 부채의 상환 "
        "이력, :8000 라이브 읽기 전용, 질의 원문은 c82_append_metrics.py 헤더에만 — "
        "관측 36). 판정 **miss**(정직): 반환 5건 중 audit-80 판정 ②(계기 테스트 합산 "
        "인플레)·c71 상환 이력이 온토픽이나 task_state 기배달 내용의 재확인 — 행동 "
        "변경 0(c21 엄격 규칙). 주입: 캡슐/task_state hit 1 — c82 후보 ①·설계 선례"
        "(c71 순수 함수 분리)·기대값까지 직접 배달(선택 선결정). 훅 3건(c43·c42·c45) "
        "miss — 동일 트리오 18행째 회전(record_context_outcome 기록, selection_failure). "
        "part_recall 검산(step0): 직전 행 c81 fields(1·4) vs 성분(0·1/1·3) **일치**"
        "(기대값). R4 표지: (1·4) 값은 c81과 동일 2행째 — 능동 팔 상시화로 이 쌍이 "
        "새 정착값이 될 수 있음을 선언(포화 재형성 후보, 정의 A 불변)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 1 — **관측 38**(frictions.md 등재): part_a 영토 검사의 잔존 거짓 음성 "
        "2종 정독 발견 — ① 스테이지된 리네임 행(`R old -> new` 통짜 문자열 → exists "
        "탈락) ② core.quotepath 8진 이스케이프(비ASCII 경로가 디스크에 없는 문자열로 "
        "탈락, 한국어 파일명 저장소라 실질 노출). 둘 다 c64 결함과 같은 방향(변경 "
        "있음→'깨끗함'), 이번 사이클 발화는 없음(정독 발견, 사건 아님). 고치기 전 "
        "기록(원칙 2) + 현행 동작을 테스트로 고정(처치 시 단언이 울린다 — c73 선례). "
        "fixed 0 — 처치는 후속 사이클 몫(계기 수리, 무게이트). "
        "관측 34: 라이브 프로브 1건(능동 검색) — 읽기 전용·$0·질의 무인용. "
        "관측 37 ③: 원장 정독 없음(append 스크립트 경유만) — 해당 없음 명기."
    ),
    "tests": (
        "367 passed, 1 warning in 7.39s — 제품 322 + 계기 45(R2 병기). c81 대비 "
        "+10 = tests/test_devloop_step0_parsing.py(계기 계열: porcelain 파싱 7종 — "
        "c64 결함 양방향 고정·상태코드·인용 경로·공백 행·거짓 음성 2종 현행 단언 / "
        "예산 파싱 3종 — 밑줄 리터럴·소스 내장·마커 부재 시끄러운 실패). 기존 단언 "
        "완화 0건. 제품 코드 무변경(계기 전용 사이클)."
    ),
    "work": (
        "c82 후보 ① 집행 — c48_step0_check part_a/part_b 파싱 부채 잔여 상환(c64 "
        "등재→c71 부분 상환→audit-80 §3-(b) 재지적, 10사이클 잔존 종결). c71 선례 "
        "그대로: 순수 함수 분리(porcelain_changed_paths·capsule_char_budget) + 테스트 "
        "10종, **출력 문면 불변**(전후 재실행 대조 — part_a가 이 사이클 WIP 3파일을 "
        "정확히 감지, 파서의 라이브 자기 검증). 이 상환으로 스크립트의 파서 중 무감시 "
        "잔여 0(part_n·recall 2종·needle·fingerprint·porcelain·예산) — 단 mtime 비교 "
        "루프·캡슐 취득 I/O는 순수 분리 대상이 아니라 통합 실행에서만 검증(정직 한계: "
        "'파서 전부 감시'이지 'part 전부 감시' 아님). 부수 발견 = 관측 38(위). "
        "노트: notes/cycle-82-step0-parsing-tests.md. 라이브 :8000 무접촉(프로브 "
        "읽기 전용 제외), 외부 비용 $0, 실DB 무접촉."
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
