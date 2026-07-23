---
name: goal
description: View and manage the goal layer in forget — the "why" above tasks. Use when the user says /goal, asks "지금 목표가 뭐지", wants to set/close a goal, or link a task to a goal.
---

# /goal — 목표 원장

목표는 forget 태스크 원장의 task_state 중 **task_id가 `goal:`로 시작하는 것**이다.
태스크는 `goal_id`로 목표에 연결된다. 목표는 캡슐의 "상위 목표" 줄로 자동 표면화된다.

## /goal (인자 없음) — 트리 보기

1. `get_task_state` (limit 20) 호출.
2. `goal:*` 항목을 상위로, 각 목표 아래에 `goal_id`가 일치하는 태스크를 들여쓰기로 묶어 렌더:

```
◎ yc-fall-2026 — YC Fall 2026 합격 (in_progress)
  다음 이정표: 7/27 제출
  ├─ yc-fall-2026-application (in_progress) — [금] 영상 촬영
  └─ site-beta-refresh (done)
◎ beta-launch — Show HN 베타 (in_progress)
  └─ memory-productization (done) — npm publish 대기
(무소속 태스크가 있으면 "목표 미연결:" 섹션으로 표시 — 연결 제안)
```

3. done 목표는 요청 시에만 표시.

## /goal set <slug> "<목표 문장>" [이정표...]

`record_task_state`: task_id=`goal:<slug>`, status=`in_progress`, summary=목표 문장(한 문장, 측정 가능하게), next_actions=이정표들(날짜 포함 권장 — 캡슐 첫 이정표가 노출됨).
상위 목표가 있으면 parent_goal_id=`goal:<상위slug>`.

## /goal done <slug> [증거]

목표 달성 = 완료 주장. **증거 없이 done 금지** (원장 규율): status=`done` + summary에 달성 증거 1줄. 증거가 애매하면 사용자에게 물을 것.

## /goal link <task_id> <slug>

해당 태스크의 최신 상태를 읽고, 동일 내용으로 `record_task_state` 재기록하되 goal_id=`goal:<slug>` 추가.

## 규율

- 목표 문장은 결과-형태(달성 판정 가능)로: "YC 합격" ✓ / "열심히 하기" ✗
- 활성 목표는 2~3개 상한 — 넘으면 사용자에게 통합/보류 제안
- 목표 변경·폐기는 supersede가 아니라 status 변경 (목표는 사실이 아니라 의도)
