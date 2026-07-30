# devloop 사이클 지시서 (자동 박자 실행용)

이 파일은 예약 태스크가 매일 실행한다. 헌장은 LOOP.md — 충돌 시 LOOP.md가 우선한다.
이 지시서의 개정: 회고 사이클이 amendments/에 제안하고, 정훈이 승인해야 적용된다.

## 절차

**0. 회상 (restore 실측 — 매 런은 무기억으로 시작하므로 이 단계가 자연실험이다)**
- 저장소: /Users/junghunkim/orca/workspaces/forget/내-프롬프트를-공유하기-싫어 (main-work)
- LOOP.md를 읽는다 (헌장).
- forget MCP `get_task_state` (task_id=devloop). MCP 미연결이면
  `curl -X POST localhost:8000/mcp/forget/http/junghunkim` tools/call로 동일 조회.
- research/devloop/metrics.jsonl 마지막 줄에서 사이클 번호 N = 마지막+1.
- restore_grade 채점: full(요약+다음 행동만으로 즉시 착수 가능) / partial(일부 재구성 필요)
  / stale(구본을 현재로 제시받음) / miss(복원 실패). 자기 채점이며 근거를 한 줄 남긴다.

**1. 모드 결정**
- N % 10 == 0 → **적대 감사**: LOOP.md·백로그·과거 감사문을 읽지 말 것.
  metrics.jsonl + frictions.md + predictions.md + `git log --oneline -30`만 보고 심문한다:
  채점 기준이 물러졌는가, 지표가 실제 개선을 반영하는가, 회피 중인 마찰은 없는가.
  보고서를 research/devloop/audits/audit-N.md로 작성. 코드 변경 금지.
- N % 5 == 0 → **회고**: 대상은 LOOP.md와 이 지시서. 지표 추세·마찰 재발률·예측 대차대조를
  근거로 개정안을 research/devloop/amendments/amendment-N.md로 작성. 적용은 하지 않는다(정훈 게이트).
- 그 외 → **일반 사이클**.

**2. 선택 (일반 모드)**
- 먼저 `git status` — devloop 외의 미커밋 변경이 있으면 **코드 사이클 금지**,
  관찰·측정 사이클(마찰 재현, 지표 수집, 문서)로 전환한다 (세션 영토 규약).
- 우선순위: frictions.md 미해소 > task state의 next_actions > LOOP.md 백로그.
- 가장 작은 가치 단위 **하나만** 고른다.

**3. 수행**
- 결정·막힘·이유를 forget `add_memory`로 기록 ([devloop] 접두어).
- 설계 변경이면 predictions.md에 반증 가능한 예측을 **선행** 등록.
- 새 마찰을 느끼면 고치기 전에 필드노트로 기록하고 frictions.md 유형에 귀속.

**4. 검증**
- 코드 변경 시 `.venv/bin/python -m pytest -q` 전체 통과 필수. 실패 상태로 커밋 금지.
- 숫자 주장은 대조군 또는 직전 측정과의 비교 없이는 기록하지 않는다.

**5. 수확**
- metrics.jsonl에 한 줄 append (기존 스키마 유지: cycle, date, restore_*, recall_*, frictions_*, tests, work).
- 커밋 메시지는 `loop(cycle N): <한 일>` + Co-Authored-By 트레일러. push까지.
- forget `record_task_state`(task_id=devloop)로 상태 supersede — 요약, next_actions, 증거 파일.
- 마지막 메시지에 사이클 보고: 한 일 / 지표 / 다음 사이클 후보 / 게이트 대기 항목.

## 상시 금지 (LOOP.md 원칙 5·6)
릴리스 태그 · PyPI/사이트 배포 · 외부 발신(이슈 코멘트 포함 외부 계정 대상) ·
~/.forget 실DB 파괴적 조작 · 사이클당 외부 API $2 초과.
게이트가 필요한 산출물은 만들어두고 "게이트 대기"로 보고만 한다.
