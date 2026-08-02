# 사이클 39 — supersede-contract 런타임 관찰: 두 채널 비대칭 + 이중 집행 (2026-08-03)

일반 사이클(N=39, N%10=9·N%5=4 — 감사 전 마지막 일반). 영토 규약(foreign untracked
`uv.lock` 잔존 + 정훈 처분 응답 부재) → 관찰·측정 폴백. 선택 = `get_task_state`
next_actions[2] = **사이클 38이 파생시킨 신규 스레드**(recall-reach 계열은 next_actions[1]★로
동결·재개봉 금지):

> "관찰 후보 (사이클38 파생): search_memories는 superseded를 ×mult 강등(잔존)하나
> assemble는 하드 제거(store.py:6473, issue#3). 현재 스토어에서 supersede된 기억이
> 이력 쿼리로는 표면화되나 action 캡슐에선 제거되는지 read-only로 확인 — F1/supersede-
> contract 인접, $0. 단발이면 등록 안 함(귀납+동결)."

사이클 38은 이 비대칭을 **코드 사실**로 확정("필터 존재/부재의 코드 사실이지 순위 크기
재측정 아님"). 이 사이클의 공백 = **런타임 확인**: 현재 스토어에서 실제로 두 채널이
갈리는가. read-only($0), 제품 코드 무변경.

## 방법 — 동일 기억을 두 채널에 통과 ($0·read-only·실DB 무변경)

1. `search_memories`(filter `metadata.superseded_at:*`)로 현재 스토어의 실 superseded
   episodic 기억 1건 확보 → **`e815c1aa`** "도그푸딩 전환 완료 (2026-07-13)", 
   `superseded_at 2026-07-23T15:11:42Z`, `superseded_by 5b5bd07c`.
2. **이력/검색 채널**: 그 기억이 search_memories에 표면화되는지 + trust 라벨 확인.
3. **action 캡슐 채널**: `prepare_context_autopilot`(주제-매치 쿼리, top_k25, debug on)의
   `raw_candidate_ids`/`selected_ids`에 그 기억이 있는지 vs 정정본 `5b5bd07c`가 있는지.
4. **혼동 격리**: 동일 주제-쿼리로 plain search_memories top-25를 떠서 `e815c1aa`의
   실제 순위/점수를 확인 — 캡슐 부재가 (a)하드제거인지 (b)단순 점수 컷오프인지 판별.

## 발견 — 두 채널 비대칭 런타임 확증, 단 배제 기전은 이중·본 쿼리선 하위층이 이미 충분

### 채널 1 — 검색/이력 (search_memories)
`e815c1aa`가 **표면화됨**: score **0.1977**, `trust {"light":"red","note":"superseded —
reference only, prefer the newer fact"}`. 코드 근거 store.py:4388-4394(×mult 강등, 
"never remove")+4415-4416(red 라벨 부착) 런타임 확증. 이력 채널은 struck-through 사실을
**찾을 수 있게 유지**하되 붉게 표시.

### 채널 2 — action 캡슐 (prepare_context_autopilot → assemble)
주제-매치 쿼리("도그푸딩 전환 완료 — Claude Code Codex Claude Desktop 로컬 forget 연결
이주") 하:
- `raw_candidate_ids`(25) 중 **`e815c1aa` 부재** — 후보 풀에 애초 진입 못 함.
- 정정본 **`5b5bd07c`**("7/13 '모든 클라이언트 연결'은 오염 — Codex 미연결이었음, 07-23
  실연결 완료", metadata.supersedes=[e815c1aa]) = **`selected_ids`(7)에 선택됨**(캡슐 진입).
- 비-superseded 형제 `c6ef9ad6`("도그푸딩 시작") = 함께 선택.
- ⇒ **런타임 end-state 확증**: 캡슐은 **stale 사실을 억제하고 정정본을 표면화**. 
  supersede-contract(issue#3) end-to-end 성립.

### 격리 — 배제는 over-determined, 하위층(강등)이 본 쿼리선 이미 충분 (정직 핵심)
동일 주제-쿼리 plain search_memories top-25는 하한 **0.4058**(1d50ab87)에서 끊김.
**`e815c1aa`는 이 top-25에도 부재** = 이 쿼리 하 그 점수 < 0.4058. 즉 `_superseded_
score_multiplier()=0.45`(store.py:4553) 강등 **하나만으로** 이미 풀 컷오프 아래로 떨어짐.
따라서:
- assemble 하드 제거(`_context_memory_is_superseded`, 6473)는 이 기억·이 쿼리선
  **결정적 필터가 아니라 잉여 backstop** — 상류 ×0.45 강등이 먼저 배제.
- 두 기전은 **혼동(confounded)**되어 있고, 본 표본은 **더 약한 층(강등)의 충분성만**
  행사. 하드제거의 결정성을 read-only로 격리하려면 raw×0.45가 top-25에 살아남을 만큼
  **원점수 높은 superseded 기억**이 필요한데 표본에 부재(supersession이 정확히 그걸
  강등하므로 구조적으로 드묾).

## 판정 — supersede-contract는 action 채널을 **2층**으로 집행 (관찰, 버그 아님)

| 채널 | superseded 취급 | 근거 | 목적 |
|---|---|---|---|
| search/이력 | ×0.45 강등 + red 라벨, **잔존** | store.py:4388-4416 | "무엇이 바뀌었나"·감사 쿼리 |
| action 캡슐 | **부재**(정정본으로 대체) | 4388(강등)→풀컷 + 6473(하드제거 backstop) | 취소선 사실 재진입 금지(issue#3) |

1. **런타임 확증**: 사이클 38 코드 비대칭이 실제 스토어에서 관측되는 end-state로 성립 —
   같은 `e815c1aa`가 검색엔 뜨고(붉게) 캡슐엔 없고, 정정본 `5b5bd07c`가 캡슐에 든다.
2. **정밀화(사이클38 확장)**: action 채널 배제는 단일 기전이 아니라 **직교 2층** —
   (L1) 상류 ×0.45 강등(확률적·점수 의존, search와 공유) + (L2) assemble 하드 제거
   (결정적·점수 무관 backstop, assemble 전용). 대부분 쿼리는 L1이 이미 충분(본 표본),
   L2는 raw 점수가 ×0.45를 뚫고 풀에 살아남는 희귀 superseded를 잡는 belt-and-suspenders.
3. **강건성 함의**: 누가 `MEM1_SUPERSEDED_SCORE_MULT`를 1.0 근처로 올려 L1을 무력화해도
   L2가 여전히 struck-through 사실을 acting prompt 밖에 유지 — contract가 단일 파라미터에
   종속되지 않음. 이력 채널이 **더 약한 강등(0.45)만** 받는 것은 의도(찾을 수 있어야).

## 정직성 캐비앗
- **격리 실패 명시**: 이 표본은 L2(하드제거)의 **결정성을 격리 못 함** — L1 강등이 본
  쿼리서 이미 배제. "캡슐에 없음"은 관측 사실이나 "하드제거 때문에 없음"은 이 표본이
  증명 못 함(코드로는 L2 존재 확정, 사이클38+본 사이클 재독). L2 결정성 격리는 향후
  고-원점수 superseded 표본 필요.
- **표본 범위**: superseded episodic 기억 **1건**(`e815c1aa`) 한정. `metadata.superseded_at:*`
  필터는 대부분 task_state claim을 반환(claim ledger 경로), 실 episodic superseded는 소수.
- **레이스/시간여행 없음**: 정적 코드 + 현재-스토어 read-only, 실DB 무변경. LLM 미호출
  (debug `llm_action_hint_status: missing_api_key` → 외부 API $0).

## 거버넌스
거버넌스 동결(회고 25) 준수: **새 유형·새 스키마·새 amendment·새 A-항목 무제안.**
이 관찰은 **supersede-contract 스레드의 1회차**(단발) — next_actions 지침("단발이면 등록
안 함, 귀납+동결")대로 **신규 유형 미등록**. frictions.md에 F1-인접 관찰로 첨부하고 스레드는
재발 관측 대기로 열어둠. 처치·규약 제안 없음(버그 아닌 정상 동작 확증).

## 산출
- `notes/cycle-39-supersede-contract-runtime.md` (이 파일; 2채널·이중집행·격리표)
- `frictions.md`에 supersede-contract 런타임 관찰 첨부(F1 인접, 단발 미등록)
