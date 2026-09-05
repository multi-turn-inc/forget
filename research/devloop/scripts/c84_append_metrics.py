"""c84 원장 append — 쓰기 전 자기 검산(c71·c75·c76·c80~c83 관행) 포함.

recall 항등식: recall_hits = 능동hit+주입hit, recall_misses = 능동miss+주입miss.
gate_pending은 c83 정본을 승계하고 정산 문장만 39회차로 교체한다(신규 0·해소 0·이관 0 —
c84는 판정·문서 사이클, 게이트 대기 목록 무변동. 후보 ① 은퇴는 next_actions 처분이지
게이트 항목이 아니다).

관측 36 이행 — 능동 프로브 질의 원문은 이 계기 파일에만 둔다:
  PROBE_QUERY = "아핀 재척도 제거 이후 FPR 축 남은 처치 방향 결정 — 리랭커 어휘 성분
                 재설계, 게이트 값 재교정, 왜 등록하지 않았나"  (trace=c84_need_probe)
"""
import json
import re

PATH = "research/devloop/metrics.jsonl"
rows = [json.loads(l) for l in open(PATH, encoding="utf-8") if l.strip()]
prev = rows[-1]
assert prev["cycle"] == 83, f"직전 행이 c83이 아님: c{prev['cycle']}"

# gate_pending: c83 정본 승계 + 정산 문장만 39회차 교체
gate = prev["gate_pending"]
gate = re.sub(
    r"정산 1줄\(audit-40 R6, 38회차\):.*$",
    "정산 1줄(audit-40 R6, 39회차): 신규 0건, 해소 0건, 이관 0건.",
    gate,
)
assert "39회차" in gate and "㉒" in gate, "정산 문장 교체 실패"

active_hit, active_miss, inj_hit, inj_miss = 1, 0, 1, 3
row = {
    "cycle": 84,
    "date": "2026-08-09",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(84%10=4·84%5=4, 스크립트 정본). 턴 원장: 턴1 "
        "LOOP.md+cycle-prompt.md Read + ToolSearch(4스키마) / 턴2 get_task_state + "
        "c48_step0_check + git status 병렬 / 턴3 첫 유효 행동(frictions 미해소 스캔 + "
        "P22/P23 정독 = 선택 착수) = floor **3**, 일반 계열 18연속 floor. metrics "
        "tail/cat/head 0회. ★ 경고 선행 도착 14연속. **grade full**: task_state가 "
        "c83 완주본을 현재로 서빙(요약 커밋 7afffb0 = HEAD 일치), c84 턴 계획·작업 "
        "후보(① P22/P23 축 검토 문면·⑮ 비대화 병기 지시까지)·기대값(Body 20/22·"
        "part_recall c83 fields 1·4 vs 성분 0·1/1·3) 전부 정확·현재본, 재구성 0. "
        "R4 포화 표지 병기: 무사건 행이라 full이 기본값임을 명기. 관측 35 이행"
        "(git status 클린 선확인, 수확 잔존물 0). [Body] 대조: 20/22 **일치**"
        "(기대값, R5 이행 — c84도 제품 코드 무변경이라 다음 행 기대값 불변)."
    ),
    "recall_hits": active_hit + inj_hit,
    "recall_misses": active_miss + inj_miss,
    "recall_note": (
        "정의 A 24행째, 정본 형식: **능동 1회(hit 1·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "능동: need-aligned 프로브 1회(R3 상시 4사이클째, 주제=이 축의 결정 이력 — "
        "후보 ② 설계 그대로 '스토어가 아는 영역×작업 필요' 교차를 시도, :8000 라이브 "
        "읽기 전용, 질의 원문은 c84_append_metrics.py 헤더에만 — 관측 36). 판정 "
        "**hit 1 — R3 계열 첫 hit**(정직 근거): 반환 8건 중 c75 결정 기억이 A-75.2 "
        "요건 문면의 존재를 표면화 → 계획에 없던 amendment-75 §6-2 정독 → 처분 노트 "
        "§3 재개봉 조건의 틀이 바뀜(행동 변경 영수증 = 노트 §3-3, c64 확장 규칙 부합). "
        "게이트 목록엔 'A-75.1~3' 번호만 있었으므로 task_state 선배달 아님. 나머지 "
        "7건은 기배달 재확인. 3연속 miss의 두 기전(선배달·축 부재)을 피해 설계한 "
        "프로브가 hit — hit 가능 조건(미배달 결정 세부×실need) 분리 검증 1례. 주입: "
        "캡슐/task_state hit 1 — c84 후보 문면·기대값 직접 배달(선택 선결정). 훅 "
        "3건(c43·c42·c45) miss — 동일 트리오 20행째 회전(record_context_outcome "
        "기록, selection_failure). part_recall 검산(step0): 직전 행 c83 fields(1·4) "
        "vs 성분(0·1/1·3) **일치**(기대값). R4 표지: (1·4) 쌍 3행에서 종료 — 정착값 "
        "후보였던 쌍이 능동 hit 사건으로 깨짐, 다음 행 기대값 fields(2·3) vs "
        "성분(1·0/1·3)."
    ),
    "frictions_logged": 0,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 0 — 신규 마찰 없음. fixed 0 — 이 사이클은 처치가 아니라 **판정**"
        "(c77 선례: 처분·기각은 frictions_fixed로 계상하지 않는다). 아핀/중심화 축 "
        "방향 전수 처분: 착수 가능한 무게이트 처치 0 — 중심화 반증(c69/c71)·아핀 "
        "제거 집행(c72)·자격 필터 집행(c81)·절대 상수 폐쇄(c68)·margin/재교정/리랭커 "
        "사람 게이트·어휘 재설계 의도적 미착수(판정 채널 부재 + 미정산 적치 + c77 "
        "표적 불일치). 재개봉 조건 성문화 = 노트 §3. 관측 34: 신선 OFF 팔 미추출"
        "(측정 없는 사이클은 대조군 어휘를 소모하지 않는다 — 프로브는 능동 검색 "
        "1회뿐, 읽기 전용·$0·질의 무인용). 관측 37 ③: 원장 정독 없음(append 스크립트 "
        "경유만) — 해당 없음 명기."
    ),
    "tests": (
        "373 passed, 1 warning in 7.80s — 제품 322 + 계기 51(R2 병기). c83 대비 "
        "증감 0(제품 코드·계기 테스트 무변경 — 판정·문서 사이클, 신규 계기 "
        "c84_deploy_debt.py는 read-only 측정 프린터라 동결할 판정 불변식 없음). "
        "기존 단언 완화 0건."
    ),
    "work": (
        "c83 후보 ① 집행 — 아핀/중심화 축 처분 판정: 방향 전수 표(중심화 T1·T3~T8 "
        "반증 / T2 아핀 c72 집행 / 절대 상수 폐쇄 / margin·재교정·리랭커 게이트 / "
        "어휘 재설계 미착수 판정 — 근거 3종: 판정 채널 부재·미정산 처치 적치·c77 "
        "표적 불일치) + 재개봉 조건 성문화(⑩/⑮ 배포 후 실 FPR에서 rule 지배 누수 "
        "관측 시 A-75.2 요건 등록) + ⑮ 배포 부채 실측(c84_deploy_debt.py: 발산 "
        "2파일·55라인(+42/−13)·원인 커밋 3건 142c56e/98c421a/a702cd4, 몸 지문 20/22와 "
        "정합) + 배포 전 점수 산술 추가 변경 금지 선언(노트 §4). 후보 ① 은퇴 — "
        "notes/cycle-84-affine-axis-disposition.md + predictions.md P23 처분 부기. "
        "라이브 :8000 접촉 = 읽기(프로브 1회) + 규약 쓰기(task_state·add_memory·"
        "record_context_outcome)뿐, 실험적 조작 0, 실DB 파괴적 접촉 0, 외부 비용 $0."
    ),
    "gate_pending": gate,
}

# 쓰기 전 자기 검산 (recall 항등식)
assert row["recall_hits"] == active_hit + inj_hit == 2
assert row["recall_misses"] == active_miss + inj_miss == 3
m = re.search(r"능동 (\d+)회\(hit (\d+)·miss (\d+)\) / 주입 (\d+)건\(hit (\d+)·miss (\d+)\)", row["recall_note"])
assert m, "recall_note 정본 형식 불일치 — part_recall 추출기가 다음 사이클에 실패한다"
a_h, a_m, i_h, i_m = int(m.group(2)), int(m.group(3)), int(m.group(5)), int(m.group(6))
assert a_h + i_h == row["recall_hits"] and a_m + i_m == row["recall_misses"], "항등식 위반"

with open(PATH, "a", encoding="utf-8") as f:
    f.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"appended c{row['cycle']} — recall 검산 OK (fields {row['recall_hits']}·{row['recall_misses']} = 성분 {a_h}·{a_m}/{i_h}·{i_m})")
