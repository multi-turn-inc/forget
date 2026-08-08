"""c80 원장 append — 쓰기 전 자기 검산(c71·c75·c76 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c79 정본을 승계하고 정산 문장만 35회차로 교체한다(장부 무변동).
"""
import json
import re

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 79, f"직전 행이 c79가 아님: c{prev['cycle']}"

# gate_pending: c79 정본 승계 + 정산 문장 교체
gate = prev["gate_pending"]
gate = re.sub(
    r"정산 1줄\(audit-40 R6, 34회차\):.*$",
    "정산 1줄(audit-40 R6, 35회차): 신규 0건, 해소 0건, 이관 0건 — 감사 권고 R1~R5는 "
    "게이트 항목이 아니라 c81+ 작업 후보이며, R4 후반부(블라인드 복원 프로브)만 회고 85 "
    "안건으로 예약(audit-80 §4).",
    gate,
)
assert "35회차" in gate, "정산 문장 교체 실패"

active_hit, active_miss, inj_hit, inj_miss = 0, 0, 1, 3
row = {
    "cycle": 80,
    "date": "2026-08-09",
    "restore_turns": 2,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 적대 감사(80%10=0 — N%5=0 동시 충족이나 감사 우선, 스크립트 정본). "
        "감사 맹검 준수: LOOP.md·백로그·과거 감사문 미열람 — 절차 0의 LOOP.md Read는 "
        "next_actions의 c80 계획 문면대로 생략. 턴 원장: 턴1 cycle-prompt.md Read + "
        "ToolSearch(5스키마) + c48_step0_check.py 병렬 / 턴2 get_task_state + 심문 재료 "
        "4종(metrics 프로그램 파싱·frictions·predictions·git log) 병렬 = 첫 유효 행동 동턴. "
        "포함 계상 **2**(감사 모드 floor 2 — 작업 단위가 지시서로 고정돼 get_task_state 내용에 "
        "비의존, c61 실측 2·감사 전례 c60=2와 정합; A-65.1 미승인이라 절대값 명기. c66~c79 "
        "14연속 floor(3)와의 비교는 모드가 달라 비등가 — 일반 사이클 floor 3 계열은 c80이 "
        "표본을 내지 않음). metrics tail/cat/head 0회(F-절차0 위반 0, ★ 경고 선행 도착 "
        "10연속 — 캡슐이 턴0에 감사 맹검 경고 배달). **grade full**: task_state가 c79 완주본을 "
        "현재로 서빙(요약 커밋 1adf8a2 = HEAD 일치), c80 턴 계획·모드 예고(적대 감사)·금지 "
        "목록·기대값 전부 정확·현재본, 재구성 0. 관측 35 이행(git status 클린 선확인, 수확 "
        "잔존물 0). [Body] 대조: 20/22 **일치**(기대값 그대로, R5 이행 — 미배포 처치 2파일 "
        "차이는 ⑮ 예정대로)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 20행째, 정본 형식: **능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "캡슐/task_state hit 1: c80 감사 절차 전체(맹검 목록·심문 축 3종·기대값·metrics 정독 "
        "허용 문면)를 직접 배달 — LOOP.md Read 생략 결정과 심문 재료 선정을 선결정했다. "
        "훅 주입 3건 miss: c43·c42·c45 기억 — 온토픽이나 task_state 부분집합(신규 정보 0, "
        "c21 엄격 규칙 유지), record_context_outcome 기록. 능동 검색 0회(감사 입력 제한 모드). "
        "part_recall 검산(step 0 스크립트): 직전 행 c79 fields(1·3) vs 성분(0·0/1·3) **일치**. "
        "부기(감사 발견의 자기 적용, audit-80 §1·R4 선이행): 이 행으로 hits=1·miss=3 동일값 "
        "**16행째** — 포화 계열 표지. 주입 트리오(c42·c43·c45)의 15+사이클 회전은 audit-80 "
        "§1-(b)의 표본이다."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 신규 마찰 대장 등재 없음: 감사 발견 5건(포화 3계열·tests 합산 인플레·"
        "F2/C1 스코어러 팔 회피)은 audit-80.md 소유이며 유형 등재 여부는 다음 손/회고 몫"
        "(거버넌스 동결 준수). fixed 0 — 감사 규정상 무처치. 관측 34: 라이브 프로브 0건 — "
        "해당 없음 명기. 관측 36: 질의·프로브 원문 인용 0(감사문·기억·이 행 모두). "
        "관측 37 ③: metrics.jsonl 정독 사이클 — 평문 비밀 스캔(패턴 5종: password류·ssh·"
        "private-key·api-key류·sk-ant) **0건**(c80_audit_extract.py, 건수만 계상·원문 무인용)."
    ),
    "tests": (
        "352 passed, 1 warning in 8.08s — 코드 변경 0행(감사 규정 준수: 신규 파일은 감사 "
        "보고서 + 읽기 전용 추출기 + 이 append 스크립트뿐). c79와 동수 — 회귀 감시가 아니라 "
        "환경 green 확인. audit-80 §2-(a) 병기: 누적 352 중 계기 테스트(tests/test_devloop_*) "
        "35건, 제품 계열 317건 — R2 선이행."
    ),
    "work": (
        "적대 감사 audit-80 (research/devloop/audits/audit-80.md). 판정 3종: ① 채점 물러짐 "
        "없음(무공지 자[尺] 변경 신규 0, P24 검산 가동) — 그러나 3계열 포화: restore_grade "
        "사건-구동화(c56 이후 비-full 1건), restore_turns 리허설화(계획이 next_actions로 "
        "배달됨), recall 능동 c64~c79 16연속 0회·hits/miss 15행 동일값 — '움직이지 않는 "
        "숫자는 방향 검출 감사망에 안 걸린다'(c65 (다)의 3차 확장). ② tests 헤드라인 "
        "+61(c62→c79) 중 57%가 계기 테스트 — 합산 인플레, 분해 부재. 라이브 개선 반영 0"
        "(⑮ 미배포), 저장소 개선 반영은 충실. 정훈측 게이트 해소 최근 5정산 0건(해소 2건 "
        "전부 루프 몫), 개헌 채널 74사이클 0/4 — 항목이 아니라 채널이 죽었다. ③ 회피 1건 "
        "확정: F2/C1 스코어러 팔 — 원인 확정 62사이클·처치 설계 58사이클·c72 방향 명시 후 "
        "7사이클 무착수, 자격 필터 단독은 $0·게이트 불요인데 '벤치 필요'가 알리바이화. "
        "권고 R1(c81 1순위=자격 필터 단독)~R5(게이트 결정 패키지). 회피 아님 판정 2건 병기"
        "(P4 집행·P10 보류). 감사 산출물의 자기 적용: 이 행 자체가 포화 계열 16행째임을 병기."
    ),
    "gate_pending": gate,
}

# 쓰기 전 자기 검산 (recall 항등식)
assert row["recall_hits"] == active_hit + inj_hit == 1
assert row["recall_misses"] == active_miss + inj_miss == 3
m = re.search(r"능동 (\d+)회\(hit (\d+)·miss (\d+)\) / 주입 (\d+)건\(hit (\d+)·miss (\d+)\)", row["recall_note"])
assert m, "recall_note 정본 형식 불일치 — part_recall 추출기가 다음 사이클에 실패한다"
a_h, a_m, i_h, i_m = int(m.group(2)), int(m.group(3)), int(m.group(5)), int(m.group(6))
assert a_h + i_h == row["recall_hits"] and a_m + i_m == row["recall_misses"], "항등식 위반"

with open(PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended c{row['cycle']} — recall 검산 OK (fields {row['recall_hits']}·{row['recall_misses']} = 성분 {a_h}·{a_m}/{i_h}·{i_m})")
