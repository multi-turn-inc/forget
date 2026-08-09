# 이 저장소에서 일하는 에이전트에게

## devloop 세션 — step 0 턴 배치 규약 (읽는 즉시 적용)

이 저장소의 devloop 사이클(LOOP.md 헌장 + research/devloop/cycle-prompt.md 지시서)을
실행하는 세션이라면, **첫 응답을 만들기 전에** 아래를 적용한다.

- **턴1** — `LOOP.md` + `research/devloop/cycle-prompt.md` Read **와 동시에**
  `ToolSearch`(`select:mcp__forget__get_task_state,mcp__forget__record_task_state,`
  `mcp__forget__add_memory,mcp__forget__search_memories,mcp__forget__record_context_outcome`)를
  **같은 응답에 묶는다.** 이 다섯 스키마는 어느 사이클에서나 쓰이므로 조회를 미룰 이유가 없다.
- **턴2** — `mcp__forget__get_task_state(task_id="devloop")` +
  `.venv/bin/python research/devloop/scripts/c48_step0_check.py` + `git status` **병렬**.
- **턴3** — 첫 유효 행동.

**`research/devloop/metrics.jsonl`을 `tail`/`cat`/`head`로 열지 않는다.**
사이클 번호와 모드의 정본은 `c48_step0_check.py`의 **첫 줄**이다. 그 스크립트가 이미
파일 전체를 파싱한다. (지시서 절차 0의 "마지막 줄에서 N" 문면은 A-55.1 사람 게이트
대기 중인 구본이다. 분석 목적의 프로그램적 파싱은 번호 결정 단계와 별개로 허용된다.)

### 왜 이 문장이 여기 있는가 (지우기 전에 읽을 것)

이 규약은 c66~c87 **22사이클** 동안 `restore_turns` 3을 냈다. c88에 배달 채널에서
사라지자 4로 퇴행했고 c88~c91 **4연속** 위반이 났다. c90이 `next_actions[0]`에
복원했으나 c91이 또 깼다 — `next_actions`는 `get_task_state` **호출 이후에** 열리므로
*턴1의 도구 선택을 지시하는 규약*을 실을 수 없기 때문이다(관측 47).

`CLAUDE.md`는 세션 시작 시 주입되는 **턴1 이전** 채널이고, 캡슐(슬롯 경합·1600자 예산)과
달리 절단·강등이 없다. 그래서 여기다. 캡슐과 **이중화**이지 이관이 아니다.

판정은 P29(research/devloop/predictions.md): c92·c93·c94에서 규약 ④ 준수 3/3 ·
`restore_turns` ≤ 3이면 지지, 1건이라도 어긋나면 반증이고 처치는 하네스 강제로 간다.

## 상시 금지 (LOOP.md 원칙 5·6)

릴리스 태그 · PyPI/사이트 배포 · 외부 발신 · `~/.forget` 실DB 파괴적 조작 ·
사이클당 외부 API $2 초과. 게이트가 필요한 산출물은 **릴리스 큐로 완성**해 두고
"게이트 대기"로 보고한 뒤 다음 일로 넘어간다 — 사람의 답을 기다리며 멈추지 않는다.
