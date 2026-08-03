# 사이클 38 — assemble 서버측 후보풀 필터 실분해: 경로별 회상도달 정량 완결 (2026-08-03)

일반 사이클(N=38, N%10=8·N%5=3). 영토 규약(foreign untracked `uv.lock` 잔존 +
정훈 처분 응답 부재) → 관찰·측정 폴백. 선택 = `get_task_state` next_actions[1]
= **사이클 37이 노트 line 104-107에 명시로 남긴 미검증 캐비앗 닫기**:

> "assemble 경로 제외 미확인: `prepare_context_autopilot`가 서버측에서
> hook/task_state를 제외하는지는 이 사이클에 미검증(훅 코드엔 제외 없음).
> 사이클 33 도달 집합에 auto_capture가 실제로 올랐음이 assemble 경로가
> 미제외임을 시사하나, 서버측 autopilot 내부 필터 확인은 향후 관측."

frictions 우선순위 점검: F1(시계형 해소)·F2(처치2=코드, 금지)·F4/F5(코드해소,
배포 게이트)·F6/F7(사람 게이트) — 관찰·측정 사이클에서 코드/게이트 없이 착수
가능한 미해소 마찰 0 → next_actions 폴백. 사이클 37은 **훅측**(`forget_turnrecall.py`)만
코드로 봤고 **서버측**(`assemble_context`)은 안 봤다. 이 사이클이 그 공백.

## 방법 — 서버측 코드 실분해 + read-only 상류 확인 ($0·코드 무변경)

1. `forget/store.py`의 `prepare_context_autopilot`(:9748)·`assemble_context`(:11187)를
   직접 읽어 후보풀이 어디서 오고 무엇으로 필터되는지 추적.
2. 공유 상류 `search_memories`(:4307)가 hook/task_state를 제외/강등하는지 확인 —
   격차가 진짜(상류가 미제외)인지 belt-and-suspenders(상류도 제외)인지 판별.
3. read-only `search_memories`(generic startup 쿼리, top_k=25, rerank=false)로 raw
   풀이 kind별로 pre-filter 없이 반환됨을 corroborate.

## 발견 — 후보풀 필터는 3층, 경로별로 갈린다 (코드 근거)

### 층 1 — `search_memories` (공유 상류, 두 경로 모두 호출)
`store.py:4307`. 스코어링 후 metadata 처리(`store.py:4388-4409`):
- `superseded_at` → `score × _superseded_score_multiplier()` **강등, 제거 아님**
  (4388-4394: "did X change? 질문이 옛 사실을 여전히 필요로 함").
- `metadata.hook`(auto_capture 세션-캡처) → `score × 0.5` **연화강등, 제거 아님**
  (4396-4403: "lexical match still surfaces them when the session itself is
  what's being hunted"). **풀에 잔존한다.**
- `assertion_kind == "task_state"` → **아무 처리 없음** = full score로 반환.
- ⇒ **상류는 어느 것도 후보에서 제거하지 않는다.** hook만 절반 벌점.

### 층 2 — turnrecall (`forget_turnrecall.py:133·135`)
- `metadata.hook` → `continue` (**하드 제외**, "rehydration용, recall 아님").
- `assertion_kind == "task_state"` → `continue` (**하드 제외**, F2 C2 처치1=사이클19).
- ⇒ 상류의 ×0.5 강등 **위에** 두 유형을 **완전 제거**.

### 층 3 — assemble/startup (`assemble_context` :11187 → `prepare_context_autopilot` 얇은 래퍼 :9748)
후보풀 = `search_memories` 출력 − 아래 셋. **hook/task_state 제외 코드 없음.**
- `_context_memory_is_superseded`(`store.py:6473`): `metadata.superseded_at`**만**
  하드 제거 — docstring: 검색은 superseded 유지하나 **조립된 ACTION 컨텍스트는
  금지**(취소선 사실 재진입이 supersede 계약 무력화, issue #3). 상류가 강등한 것을
  assemble는 더 나아가 제거.
- `_context_matches_requested_task`(`store.py:6272`): **`if not requested_task_id: return True`**
  — startup은 requested_task_id 없음 → **전부 통과**. task_id 있으면 매칭 `task_state`
  행을 오히려 **admit**(6280-6285, `_context_memory_task_state_id`로 매칭 유지) —
  turnrecall과 정반대.
- workspace 중복 memory id 1건 제거.
- ⇒ startup/assemble은 auto_capture(×0.5 강등하되 **잔존**)·task_state(**admit**)를
  후보풀에 **포함**한다.

## 판정 — CONFIRMED, 사이클 37 격차 기전 2(후보풀 필터) 양측 확증

| 유형 | search_memories(상류) | turnrecall | assemble/startup |
|---|---|---|---|
| `hook`(auto_capture) | ×0.5 강등, 잔존 | **하드 제외** | 잔존(×0.5 상속) |
| `assertion_kind=task_state` | full 반환 | **하드 제외** | **admit**(task-scope 시 우대) |
| `superseded_at` | ×mult 강등, 잔존 | (conflict-pair 별도 처리) | **하드 제거** |

1. **사이클 37 미검증 캐비앗 종결**: 서버측 assemble/autopilot은 hook·task_state를
   후보에서 제외하지 **않는다**(CONFIRMED). 격차 기전 2는 이제 훅측+서버측 양측 코드로
   확증 — turnrecall만 하드 배제, assemble는 미배제.
2. **사이클 33 재확증**: "저장 바이트 96.7% 미도달·dead-weight 90%=auto_capture"는
   assemble/startup 경로 상한 — auto_capture가 ×0.5 강등에도 2481행 볼륨으로 assemble
   후보의 28.9%(사이클 29)에 도달하는 것과 정합. turnrecall 분모엔 auto_capture가
   애초에 하드 제외되어 부재 → 격차의 후보풀 축이 실재.
3. **정밀화(모순 아닌 완결)**: 사이클 37/33의 이진 "assemble 미제외" 프레이밍은 방향은
   옳으나 정밀도 부족. 실제 = **상류 ×0.5 연화강등을 양 경로가 상속 + turnrecall만
   하드 제외를 얹음**. auto_capture는 assemble 풀에 "제거되지 않은 채 절반 벌점"으로
   들어온다(제거 0이 아님). 이 정밀화가 사이클 33 수치를 오히려 강화 — 절반 벌점에도
   볼륨으로 도달.
4. **두 제외 철학의 대칭**: assemble(action 컨텍스트)은 superseded를 하드 제거하되
   세션-캡처·task_state는 유지(캡슐 backbone) — turnrecall(turn recall)은 세션-캡처·
   task_state를 하드 제거하되(캡슐/get_task_state로만 여행) supersede는 conflict-pair로
   별도 취급. 같은 스토어, 목적별로 반대 필터.

## 정직성 캐비앗

- **판정 범위**: 필터 **존재/부재**의 코드 사실. 각 유형이 실제 순위에 미치는 크기
  (예: task_state가 startup 풀에서 몇 위인지)는 이 사이클이 재측정 안 함 — 사이클 36/37이
  5 substantive 후보로 잰 rank 1이 그 표본.
- **read-only 상류 확인의 한계**: generic startup 쿼리 top-25는 raw 풀이 kind별 pre-filter
  없이 이종 행(Quant action_report·LME-V2)을 반환함을 corroborate하나, 이 특정 쿼리의
  top-25에 가시적 `metadata.hook` 행은 안 떴다(그 쿼리엔 저점). auto_capture가 assemble
  풀에 도달한다는 것은 코드(×0.5 강등=잔존) + 사이클 33 측정이 근거이지 이 top-25가 아님.
- **레이스/시간여행 없음**: 코드 정적 분석 + 현재-스토어 read-only. 실DB 무변경.

## 거버넌스

거버넌스 동결(회고 25) 준수: **새 유형·새 스키마·새 amendment·새 A-항목 무제안.**
next_actions[1] 집행 = 관찰·측정이며, 기존 recall-reach/turnrecall 클러스터(frictions.md)에
경로 귀속을 **완결**(양측 확증)로 첨부할 뿐. "회상도달 계측 경로 명시" 규약 제안은 회고/정훈
게이트(누적 gate_pending, amendment-35 §6 단일 결정 패킷)로 유지.

## 산출

- `notes/cycle-38-assemble-server-side-filter.md` (이 파일; 3층 필터·코드 라인·대칭표)
- `frictions.md` recall-reach 클러스터에 사이클 38 서버측 완결 판정 첨부
