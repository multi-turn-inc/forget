# 사이클 37 — turnrecall 경로 실분해: startup↔turnrecall 도달 격차 = 두 기전 (2026-08-03)

일반 사이클(N=37, N%10=7·N%5=2). 영토 규약(foreign untracked `uv.lock` 잔존 +
정훈 처분 응답 부재) → 관찰·측정 폴백. 선택 = `get_task_state` next_actions[1] 후보
**(a)** = **"turnrecall(턴중 회상) 경로 실분해 — 사이클36 oracle replay가 'topic-recall이
substantive 기억을 rank 1–2로 낸다'를 실측(=turnrecall 프록시)했으니, 이제 실제
UserPromptSubmit 훅 경로(`forget_turnrecall.py`)를 직접 분해해 startup vs turnrecall 도달
격차를 확증"**.

frictions 우선순위 점검: F1(시계형 해소)·F2(처치2=코드, 금지)·F4/F5(코드해소, 배포 게이트)·
F6/F7(사람 게이트) — 관찰·측정 사이클에서 코드/게이트 없이 착수 가능한 미해소 마찰 0 →
next_actions 폴백. 사이클 32·33·34는 **startup/autopilot 조립 경로만** 봤다(이 사이클이 그 공백).

## 방법 — 두 훅의 코드 대조 분해 + 실제-훅-params 재생 ($0·read-only)

1. `hooks/forget_turnrecall.py`(UserPromptSubmit)와 `hooks/forget_sessionstart.py`(SessionStart)를
   직접 읽어 쿼리 구성·후보 필터·게이트를 대조.
2. 사이클 36의 5 substantive 후보를 **실제 turnrecall 훅 파라미터**(`top_k=5`, rerank 미전달,
   gate 0.45)로 재생 — 사이클 36은 `rerank=on, top_k=8`(더 관대)로 쟀고, 그것을 "미확인 캐비앗"으로
   남겼다. 이 사이클이 그 캐비앗을 닫는다. 대조군 = generic startup 쿼리.

## 발견 A — startup↔turnrecall 도달 격차 = TWO orthogonal 기전 (코드 근거)

두 훅을 나란히 읽으면 격차가 단일 기전이 아니라 **직교하는 둘**임이 드러난다:

### 기전 1 — 쿼리 레짐 (사이클 34/36 축, 이제 소스 라인에 고정)
- **startup** (`forget_sessionstart.py:103`): 쿼리 = 고정 generic 문자열
  `session {source} in {cwd} — active tasks, open loops, recent decisions`.
  작업-주제 신호 **0**. `prepare_context_autopilot` 호출.
- **turnrecall** (`forget_turnrecall.py:121`): 쿼리 = `prompt[:300]` = **실제 유저 프롬프트**.
  주제-정렬 by construction. `search_memories` 호출.

### 기전 2 — 후보풀 필터 (신규 축, 코드에서만 보임)
- **turnrecall**은 후보에서 명시 제외:
  - `metadata.hook` = auto_capture 세션-캡처 포인터 (`turnrecall.py:133`, "rehydration용, recall 아님")
  - `metadata.assertion_kind == "task_state"` = 유동층 task 원장 (`turnrecall.py:135`, F2 C2 처치1=사이클19)
- **startup/assemble** 경로(`prepare_context_autopilot` + `layered_filter` scope만)는 이 제외를 훅에서 안 함.
- **함의**: 사이클 33 "저장 바이트 96.7% 회상 미도달·dead-weight 90%=auto_capture"는
  **assemble/startup 경로 측정**이다. turnrecall 경로엔 auto_capture가 **애초에 후보가 아니므로**
  도달될 수도, crowd-out할 수도 없다. turnrecall 후보 모집단은 startup 미도달 수치를 지배하는 바로
  그 dead-weight를 이미 배제하고 시작한다.

### 기전 3 — 게이트·구조 차이 (부수, 그러나 "startup+좋은쿼리"가 아님을 확정)
- top_k = `MAX_RECALLS+2 = 5`(≠8), cap `MAX_RECALLS=3`, `MEMORY_CHAR_LIMIT=160`(전문 아닌 160자 스텁 OFFER).
- gate `SCORE_THRESHOLD=0.45`; **충돌지대(supersede-pair) 멤버는 더 느슨한 `0.32`**
  (안전: incident #1 — 정정본 놓침이 평범한 회상 놓침보다 비쌈). startup 경로엔 없는 관련성-vs-안전 게이트.
- 가드: `MIN_PROMPT_LEN=8`, `/ ! < #` 시작 프롬프트 스킵(슬래시-커맨드/단문엔 turnrecall 없음),
  세션 단위 반복억제 원장 + 캡슐-dedup(startup이 이미 낸 것 재-오퍼 안 함).

⇒ turnrecall은 "startup에 좋은 쿼리 끼운 것"이 아니라 **구조적으로 다른 회상 경로**:
주제-정렬 쿼리 + dead-weight-배제 후보풀 + 엄격하되 안전-인지 게이트 + 캡슐 dedup.

## 발견 B — 실제-훅-params 재생: 5/5 rank 1, 사이클 36 rerank 캐비앗 닫힘

각 후보의 주제-매치 쿼리(사이클 36 것 재사용)를 `top_k=5`·`rerank=false`(=훅 기본)로 재생:

| # | 후보 | raw rank | score(rerank=off) | 사이클36(rerank=on) | 게이트 0.45 |
|---|---|---|---|---|---|
| 1 | 필드노트 #1 캡슐 신선도 (`91a9facc`) | 1 | 0.632 | 0.538 | 통과 |
| 2 | 정훈 설계철학 (`07ad010a`) | 1 | 0.644 | 0.753 | 통과 |
| 3 | 사이클15 amdt-15 recall분리 (`cec31dc4`) | 2 raw → **1 hook-eligible** | 0.656 | 0.631 | 통과 |
| 4 | 사이클3 F2 store.py (`0fee478e`) | 1 | 0.748 | 0.794 | 통과 |
| 5 | 사이클18 phrase_bonus C1 (`9674b10a`) | 1 | 0.899 | 0.920 | 통과 |
| — | **대조군: generic startup 쿼리** | 5건 중 **0건** top-5 | — | — | — |

- **5/5 전부 hook-eligible rank 1** (3번은 raw rank 2가 `task_state` claim `1944f735`(0.715)이라
  `turnrecall.py:135`에서 훅이 드롭 → 잔여 최상위 = `cec31dc4`). **훅의 후보 제외 기전이 측정 중
  실제로 발화** — 코드 대조가 실측으로 확증됨.
- score(rerank=off) 전부 **≥0.45**. rerank 제거 + top_k 8→5로 낮춰도 게이트·순위 불변 →
  **사이클 36의 "rerank=on이 실제 훅보다 관대할 수 있다" 캐비앗 닫힘**. 훅은 base score로 게이트하며
  (사이클36 노트), off/on 델타는 모든 후보에서 게이트로부터 멀다(최저 0.632).
- **대조군**: generic startup 쿼리는 5 후보 중 **0건 도달**(top-5 = 긴 Quant/릴리스 행 3개 +
  cwd-경로 literal 매치 노트 `225066aa` + devloop cycle-32 selection 노트). startup 경로 도달 격차
  재현 — 같은 스토어·같은 스코어러, 쿼리만 바꿔 도달이 뒤집힌다.

캐비앗(정직): query 2에 오타(`인gran트`↔`인격`)가 있었으나 타깃이 여전히 rank 1·0.644 —
주제-정렬 쿼리는 오타에도 강건(발견 방향 강화, 그러나 재현 시 오타 명시).

## 판정 — 회상도달 계열(사이클 32·33·34)의 경로 귀속 정정

회상도달 계측 연작은 **전부 startup/assemble 경로**를 쟀다. turnrecall 경로에선 격차가 **두 방향으로
동시에 무너진다**: (i) 나쁜 probe(generic 쿼리)가 실제 프롬프트로 교체되고, (ii) 미도달을 지배하던
dead-weight(auto_capture)가 후보풀에서 아예 배제된다. 따라서:

1. 사이클 33 "저장 바이트 96.7% 미도달"·34 "distilled 80% 미도달"은 **startup/assemble 경로 상한**이지
   유저-대면 turnrecall 도달의 척도가 아니다. turnrecall 후보풀은 auto_capture·task_state를 제외하므로
   분모 자체가 다르다.
2. 사이클 36 가설("'회상이 스토어 안 건드림'은 startup 진실이지 turnrecall 진실 아닐 수 있음")을
   **코드 + 실제-훅-params 측정 수준에서 확증**. 디스크 없는 유저-대면 forget에서도 turnrecall(실제
   프롬프트 → 주제-정렬)은 실제 훅 파라미터로 substantive 기억을 rank 1·게이트 통과로 낸다.
3. 길이-게이팅(사이클 34)·phrase_bonus C1(F2)은 **주제 신호가 약한 startup 스트림에서만 지배**
   (대조군이 재확인: generic 쿼리 top-5가 전부 장문). 실제 프롬프트가 오면 짧은 온-토픽 루프 노트도
   rank 1(사이클36·37 일관). 모순 아님 — 같은 기전, 다른 쿼리 레짐.

## 정직성 캐비앗

- **판정 범위**: 이 5건(사이클 34 특정 substantive 후보)에 한정. "turnrecall이 모든 관련 기억을
  낸다"는 일반 주장 아님. 진짜 침묵미스는 실제 프롬프트로도 안 뜨는 지식일 것.
- **rerank 기본값 미확정**: 훅은 rerank 키를 안 보내므로 서버 기본을 받는다. 이 측정은 `rerank=false`
  명시 → 훅이 서버 기본으로 rerank=on을 받는다면 사이클 36 컬럼이 그 조건. 두 조건 모두 게이트 통과라
  판정 불변(어느 쪽이든 5/5 rank 1, ≥0.45).
- **현재-스토어 재생**: 오늘 스토어(홍수 후). 5건 전부 홍수 이전 생성인데 여전히 rank 1 = crowd-out
  반증 정합(사이클 29·32·36).
- **assemble 경로 제외 미확인**: `prepare_context_autopilot`가 서버측에서 hook/task_state를
  제외하는지는 이 사이클에 미검증(훅 코드엔 제외 없음). 사이클 33 도달 집합에 auto_capture가 실제로
  올랐음(사이클 33 "dead-weight 90%=auto_capture")이 assemble 경로가 미제외임을 시사하나, 서버측
  autopilot 내부 필터 확인은 향후 관측(next_actions).

## 거버넌스

거버넌스 동결(회고 25) 준수: **새 유형·새 스키마·새 amendment·새 A-항목 무제안.** 이 사이클은
next_actions 후보 (a) 집행 = 관찰·측정이며, 기존 recall-reach/turnrecall 클러스터(frictions.md)에
경로 귀속 정정을 첨부할 뿐이다.

## 산출

- `notes/cycle-37-turnrecall-path-decomposition.md` (이 파일; 5 쿼리·순위·점수·대조군 재현 기재)
- `frictions.md` recall-reach 클러스터에 사이클 37 경로 분해 판정 첨부
