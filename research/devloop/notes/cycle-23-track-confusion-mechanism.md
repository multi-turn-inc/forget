# 사이클 23 — 회상 트랙 혼선: 메커니즘 확정·정정 + 무력 fix 실측 (2026-08-02)

관찰·측정 사이클(영토 규약: foreign untracked `uv.lock` → 코드 사이클 금지). read-only.
제품 코드 무변경, pytest 268 통과(회귀 감시 그린).

## 증상 (3번째 연속 관측)

이번 사이클의 0단계 restore가 또 **partial**이다. `get_task_state(task_id=devloop)`가
LME-V2 벤치 트랙 요약과 next_actions(전부 "단계 1 완료 → 오케스트레이터가 단계 3 발사",
"아침: forget vs RAG 대조 숫자 판정"…)를 반환했으나, 루프의 실제 작업 트랙은
metrics.jsonl 사이클 20~22가 보여주듯 F2/P8/감사다. 요약+next_actions만으로 착수 불가,
metrics.jsonl 꼬리로 실트랙을 재구성해야 했다.

이 마찰은 사이클 21(단발), 22(2번째, 단발 기각)에서 등재됐고 유형 판정은 회고 25에 회부돼
있었다. 이번이 **3번째 연속** — 재발 확정. frictions.md '미분류 관측' 섹션 갱신.

## 사이클 22 프레이밍 정정: 원인은 shell 오케스트레이터가 아니다

사이클 22 노트와 task_state 요약은 "오케스트레이터 상주(PID 94502)가 statusboard 자동
갱신"이라 서술해, 마치 그 오케스트레이터가 task_state를 오염시키는 것처럼 읽혔다. **실측
으로 반증**:

- PID 94502(`sh orchestrator.sh`)는 살아있으나(1:05AM 기동), `orchestrator.sh`는 forget을
  전혀 호출하지 않는다 — grep 결과 `record_task_state`/`task_id`/`devloop`/`record_context`
  0건. 유일한 forget-무관 호출은 `statusboard.py`이고, LongMemEval-V2 리포의 어떤 `.py`도
  `record_task_state`/`devloop`을 참조하지 않는다(grep 0건). 오케스트레이터는 **파일 폴링
  구동**(`runs/*/aggregated_metrics.json` 존재 여부로 단계 전이)이라 task_state를 읽지도
  쓰지도 않는다.
- 그렇다면 `task_id=devloop`의 LME-V2 요약(valid_from 2026-08-01T16:06:33Z=08-02 새벽 KST)은
  **goal:lmev2-credible-number를 작업한 devloop 세션(claude)**이 자기 손으로 쓴 것이다.
  1인칭 devloop 목소리("[devloop — 2026-08-02 새벽] 단계 1 RAG 재현 3차 발사")가 증거.

## 진짜 메커니즘: 공유 task_id 상의 목표-트랙 충돌

`task_id=devloop`은 `goal_id=goal:lmev2-credible-number`에 바인딩돼 있고(get_task_state가
반환), **두 종류의 세션이 같은 task_id에 record_task_state**한다:

1. 자기개선 루프 세션 (LOOP.md 지배, metrics.jsonl 번호 사이클 — F2/감사/회고).
2. LME-V2 벤치 목표 세션 (goal:lmev2-credible-number — RAG 재현·forget 대조런).

restore(get_task_state)는 **마지막 쓰기의 트랙**을 반환한다. 이번엔 마지막 쓰기가
LME-V2 트랙(08-02 새벽)이라 restore가 off-track에 착지했다. 사이클 21의 "유동층
포인터가 self-loop off-track" 서술은 이 충돌의 한 단면이었을 뿐, 근본은 **두 트랙이
하나의 task_id를 정당하게 공유**하는 구조다.

## 이미 만들어진 fix가 restore엔 무력함을 실측

episodic recall이 2026-08-01 세션 장면 2건을 표면화: 그날 **project 스코프 task_state**를
구현했다 — `record_task_state`가 `project` 파라미터를 받아 scope blob에 싣고, 읽기는
project로 필터. 당시 자기 서술: *"본문 오염은 예상된 잔재… 오늘까지의 모든 task 행이
무태그라서… 치유는 태그된 쓰기가 기존 행을 대체하는 순간부터 시작돼."*

이 fix가 restore를 고치는지 **직접 실측**(read-only):

| 조회 | 반환 행 |
|---|---|
| `get_task_state(devloop)` (project 생략, cross-project 뷰) | claim 1025f2dd, epoch e68ebe5d, LME-V2 |
| `get_task_state(devloop, project="forget")` | **동일** claim 1025f2dd, epoch e68ebe5d, LME-V2 |

**두 조회가 같은 무태그 LME-V2 행을 반환.** 읽기 규칙이 "project 스코프 읽기는 *다르게*
태그된 행만 숨기고 **무태그 행은 하위호환으로 항상 노출**"이라, LME-V2 행이 무태그인 한
project 필터는 restore를 고치지 못한다. **step 0에서 project를 넘겨도 소용없다.**

치유는 오직 **태그된 self-loop 쓰기가 무태그 행을 supersede**할 때 시작된다(task 연속성은
task_id 단위 — commit f35e3c3 "task continuity is per task, not per task×scope", 그러므로
task_id=devloop에 대한 더 신선한 쓰기는 이전 epoch를 대체). 사이클 21·22·23에서 이 대체가
일어나지 않았다 — 최신 행이 여전히 08-02 새벽 LME-V2다. 즉 **이 세 사이클 중 어느 것도
task_id=devloop에 self-loop 내용을 성공적으로 영속시키지 못했다.**

## 이번 사이클의 개입 = 자연 실험 (step 5 record_task_state)

step 5의 record_task_state는 어차피 매 사이클 실행된다. 이번엔 그것을 **project="forget" +
self-loop 우선 내용**으로 써서 무태그 LME-V2 행을 supersede 시도한다. 비파괴적이다:
LME-V2 오케스트레이터는 파일 구동이라 task_state를 읽지 않으므로 진행 중 체인에 무해하고,
LME-V2 병행 트랙 포인터(아침 대조 판정)는 소실 방지를 위해 next_actions에 명시 보존한다.

## 반증 테스트 (사이클 24 restore가 판정)

이번 사이클의 태그 쓰기 후, 다음 사이클 restore가 두 메커니즘 중 하나를 반증한다:

- **(a) 사이클 24 restore가 이 self-loop 행(cycle-23 내용, project=forget)을 반환** →
  "태그된 self-loop 쓰기가 무태그 행을 supersede하면 치유"가 성립. 잔여 갭은 단지 "루프가
  그동안 태그 쓰기를 영속 안 해온 것"뿐 → 처방: step 5에서 project=forget 쓰기 상시화.
- **(b) 사이클 24 restore가 LME-V2 행을 다시 반환(내 것보다 신규)** → LME-V2 세션이
  task_id=devloop을 재클로버 → 목표-트랙 충돌은 태그만으로 안 풀림, **task_id 분리 필요**
  → 회고 25 게이트: LME-V2 목표에 별도 task_id(예: task_id=lmev2) 부여, task_id=devloop은
  self-loop 전용.

양방향 반증 가능. 개입(step 5 쓰기)이 곧 실험 조작이므로 심기·대기·예측 카나리아 불요 —
매 사이클의 0단계가 그대로 표본(LOOP.md 백로그 #8 정신과 합치).

## 회고 25 안건 갱신

- 유형화: 이 마찰은 F4(스코프 오배송)의 인접이나 쓰기측 오배송과 다르다 — **읽기측
  트랙 선택 실패**. 새 유형(예: F7 트랙 충돌) 등록 여부는 회고 25(3회 재발로 귀납 요건 충족).
- 처방 결정: (사이클 24 반증 결과에 따라) project=forget 쓰기 상시화 vs task_id 분리.
- 캡슐 조립 층(사이클 22 관측 (b)): SessionStart 캡슐 헤드라인도 quant/LME-V2 편향 잔존 —
  task_state 행을 고쳐도 캡슐 조립이 goal 바인딩을 상단 노출하면 별도 잔재. 회고 25에서
  '이번 트랙'을 고르는 구성 정책(인격 모델) 안건과 묶음.
