# 사이클 24 — 회상 트랙 혼선: 반증 테스트 판정 + 메커니즘 정정 (2026-08-02)

관찰·측정 사이클(영토 규약: foreign untracked `uv.lock` → 코드 사이클 금지). read-only.
제품 코드 무변경. 이 사이클의 0단계 restore가 곧 자연 실험의 판독값이다.

## 판정: 사이클 23 반증 테스트 → 결과 (a)

사이클 23은 step5에서 `record_task_state`를 `project=forget`·self-loop 우선 내용으로 써서
공유 `task_id=devloop`의 마지막 쓰기를 self-loop 트랙으로 만들고, 사이클 24 restore가
어느 트랙을 반환하는지로 두 가설을 반증하도록 등록했다:

- (a) self-loop 행 반환 → "태그된 self-loop 쓰기가 무태그 행을 대체하면 치유" 성립.
- (b) LME-V2 행 재클로버 → task_id 분리 필요.

**사이클 24 restore는 self-loop 행을 반환했다 → 결과 (a).** 실측:

| 필드 | 값 |
|---|---|
| `get_task_state(devloop)` 요약 | "[devloop self-loop — 2026-08-02 사이클 23] … 회상 트랙 혼선 마찰 3번째 연속 관측…" (self-loop 트랙) |
| `next_actions[0]` | "[self-loop 반증테스트] 사이클 24 restore가 이 project=forget 행을 반환하는지 판정…" (이 사이클의 과제 그 자체) |
| claim_id | `d91c76ae-1049-4488-aaa4-1a839712371d` |
| epoch | `8337a688-…` (predecessor `e68ebe5d`) |
| scope | `{app_id:forget, project:forget, user_id:junghunkim}` |
| valid_from | `2026-08-01T16:26:50Z` (=사이클 23 step5 쓰기) |

restore_grade = **full** (사이클 21·22·23 대비: 21 partial → 22 full → 23 partial → **24 full**).
요약+next_actions만으로 즉시 착수 가능했고, next_actions[0]이 곧 이 사이클의 과제였다.
이 개선은 사이클 23 개입의 직접 결과다 — 트랙 혼선 4사이클 중 첫 **온트랙** restore.

## 메커니즘 정정: 대체가 아니라 "마지막 쓰기가 epoch head"

사이클 23은 치유를 "**태그된** self-loop 쓰기가 무태그 행을 supersede"로 서술했다. 반환된
claim 객체가 이를 **정정**한다 — 태그가 원인이 아니다:

- `supersedes_claim_ids: []` — self-loop 쓰기는 어떤 claim도 **명시적으로 대체하지 않았다.**
- `predecessor_epoch_id: e68ebe5d` — 현재 epoch의 부모가 바로 그 LME-V2 epoch이다.
- `reducer_version: hybrid-workspace-v0`, `state_source: workspace_epoch` — task_state는
  **workspace-epoch 리듀서**: 매 `record_task_state`가 이전 epoch를 부모로 하는 새 epoch를
  만들고, `current` = **최신 epoch head**.
- 타임라인: LME-V2 쓰기 `16:06:33Z` → self-loop 쓰기 `16:26:50Z`(20분 뒤). head = 나중 쓰기.

즉 restore가 반환하는 것은 **`task_id=devloop`에 대한 가장 최근 `record_task_state`**이며,
project 태그와 무관하다. 태그(project=forget)는 head가 **아닌** 다른 행의 읽기 필터링에만
관여하고, head는 "마지막에 쓴 세션"이 소유한다. 이것이 4사이클을 전부 설명한다:

| 사이클 | 마지막 쓰기 | restore |
|---|---|---|
| 21·22·23 | LME-V2 (08-02 새벽) | partial (off-track) |
| 24 | self-loop (사이클 23 step5) | **full (on-track)** |

## 함의: 치유는 성립하나 **취약**하다 (레이스)

결과 (a)는 성립하되, 그 원인이 태그 우선이 아니라 **latest-write-wins**이므로 치유는
경합적이다: self-loop 트랙이 head인 것은 사이클 23 step5 이후 **LME-V2 쓰기가 끼어들지
않았기** 때문일 뿐이다. LME-V2 세션이 사이클 25 restore 이전에 `task_id=devloop`에 한 번만
써도 head를 도로 가져가 restore가 재클로버(partial)한다.

- 사이클 23 처방 "step5 project=forget 쓰기 상시화"는 **필요조건**이다 — 매 사이클 self-loop를
  head로 재설정. 그러나 **충분조건이 아니다** — 사이클 사이(다음 restore 이전) LME-V2 쓰기가
  끼면 그 시점 head는 LME-V2다.
- 견고한 처방은 여전히 **task_id 분리**: LME-V2 목표에 별도 task_id(예: `task_id=lmev2`)를
  주면 두 트랙이 epoch 사슬을 공유하지 않아 레이스 자체가 사라진다.
- 따라서 회고 25 권고는 "(a) 또는 (b)" 택일이 아니라 **둘 다**: 상시 project 쓰기(값싸고 즉효,
  단 취약) + task_id 분리(구조적·견고). 전자는 후자 배선 전까지의 브리지.

## 부수 판정 1: 사이클 22 캐비앗 (b) "캡슐 조립 층 편향" 반증

사이클 22·23은 SessionStart 캡슐 헤드라인이 quant/LME-V2 편향인 것을 **별도의 '캡슐 조립
층' 잔재**로 서술했다. 이번엔 캡슐 헤드라인('현재 목표'·'다음 행동')도 **self-loop 트랙**을
보였다(트랙 혼선 내용·self-loop 반증테스트 next_action). **두 표면(get_task_state·캡슐)이
함께 뒤집혔다** → 캡슐 편향은 별도의 조립-층 병리가 아니라 **동일 근원**(캡슐도 같은 최신
task_state epoch에서 헤드라인을 뽑음)이었다. 사이클 22 캐비앗 (b)는 반증 — 회고 25에서
'별도 캡슐 조립 정책' 안건은 강등(같은 latest-write-wins 처방이 두 표면을 함께 고침).

## 부수 판정 2: 잔재 — self-loop 내용이 lmev2 goal에 바인딩

정정에도 남는 것: 반환 claim `d91c76ae`는 self-loop 내용이지만 `goal_id:
goal:lmev2-credible-number`에 바인딩돼 있다. 그래서 캡슐의 '상위 목표'·'병행 트랙' 필드는
여전히 lmev2/quant를 노출한다(내용/goal 불일치). latest-write가 요약·next_actions는
가져오되 goal_id는 이전 epoch에서 승계했기 때문. task_id 분리(또는 self-loop 쓰기 시
goal 재바인딩)가 이 잔재도 해소한다 — 회고 25 처방에 포함.

## 이번 사이클의 개입 = 다음 반증 (연속)

step5 record_task_state는 다시 project=forget·self-loop 우선으로 쓴다(상시화 시험 계속,
LME-V2 포인터는 next_actions 보존). 이는 self-loop를 다시 head로 만든다. 하지만 latest-write-
wins 하에서 이것만으로는 "태그가 견고히 이긴다"와 "그냥 마지막 쓰기라 이긴다"를 못 가른다 —
**구별자는 오직 끼어든 LME-V2 쓰기**다. predictions.md에 전방 예측 등록(P9): 사이클 25
restore 이전 LME-V2가 `task_id=devloop`에 쓰면 사이클 25 restore는 재클로버(partial) →
latest-write-wins·task_id 분리 필요 확정. 쓰지 않으면 계속 full(치유 지속하나 비구별).

## 회고 25 안건 갱신 (사이클 23 대비 델타)

- 유형화(F7 트랙 충돌?): 3회 재발 + 이번 사이클 정정으로 메커니즘 확정(공유 task_id의
  latest-write-wins) → 귀납 요건 충족, 신규 유형 등록 근거 완비.
- 처방: **택일 폐기 → 병행 채택** — 상시 project 쓰기(브리지) + task_id 분리(견고) + goal 재바인딩.
- 캡슐 조립 정책 안건: **강등**(부수 판정 1) — 별도 병리 아님, 같은 처방이 두 표면을 함께 고침.
