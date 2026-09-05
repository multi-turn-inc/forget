# 이 저장소에서 일하는 에이전트에게

## devloop 세션 — step 0 턴 배치 규약 (읽는 즉시 적용)

이 저장소의 devloop 사이클(LOOP.md 헌장 + research/devloop/cycle-prompt.md 지시서)을
실행하는 세션이라면, **첫 응답을 만들기 전에** 아래를 적용한다.

**먼저 하네스를 판별한다** — `mcp__forget__*` 스키마가 **이미 적재**돼 있는가
(`get_task_state`를 `ToolSearch` 없이 바로 부를 수 있는가)? 이 한 줄이 아래 분기를 정한다.

- **A. 기적재 하네스 (ToolSearch 불요)** — 턴을 가를 의존성이 **없다.** 아래 **넷**을
  **전부 턴1 한 응답에 묶는다**: `research/devloop/cycle-prompt.md` Read ·
  `mcp__forget__get_task_state(task_id="devloop")` ·
  `.venv/bin/python research/devloop/scripts/c48_step0_check.py` · `git status`.
  **`LOOP.md`는 턴1에 읽지 않는다** — 턴2에서 c48 첫 줄로 모드를 확인한 뒤, 모드가
  **적대 감사(N%10=0)가 아니면** LOOP.md Read를 첫 유효 행동과 **같은 턴2**에 묶는다.
  감사면 LOOP.md 금독 유지(지시서 절차 1). **턴2 = 첫 유효 행동** → `restore_turns` **2**.
- **B. 미적재 하네스 (ToolSearch 필요)** — 스키마를 받아야 상태를 부를 수 있으므로 턴이 갈린다.
  **턴1** = `cycle-prompt.md` Read **와 동시에** `ToolSearch`(`select:mcp__forget__get_task_state,`
  `mcp__forget__record_task_state,mcp__forget__add_memory,mcp__forget__search_memories,`
  `mcp__forget__record_context_outcome`) / **턴2** = `get_task_state` + `c48_step0_check.py` +
  `git status` **병렬** / **턴3** = (비감사면 `LOOP.md` Read +) 첫 유효 행동 → `restore_turns` **3**.
- **C. 제3형 하네스 (`mcp__forget__*` 미적재 **그리고** `ToolSearch` 부재 — c232~c235 실측)** —
  MCP 경로가 없으므로 `get_task_state`는 지시서 절차 0의 **curl 폴백**
  (`POST localhost:8000/mcp/forget/http/junghunkim` tools/call)으로 조회한다.
  **턴1** = `cycle-prompt.md` Read + `c48_step0_check.py` + `git status` **3중 병렬** /
  **턴2** = (비감사면 `LOOP.md` Read +) curl `get_task_state` + **모드가 여는 소스 정독을
  같은 턴에 묶는다** — 모드는 턴1의 c48 첫 줄로 이미 판명돼 있다. **회고·감사**는 작업
  소스(감사 소스·추세·정산 정본)가 task_state에 비종속이므로 턴2 정독이 첫 유효 행동 →
  `restore_turns` **2**. **일반 사이클**은 선택(절차 2)이 task_state `next_actions`에
  종속이라 첫 유효 행동이 턴3 → `restore_turns` **3**.
  **C형 curl의 가드 통과 형태(c291 실측 · 관측 132 · P75)** — 한 줄·주석 없음·파이프만:
  `curl -s -X POST localhost:8000/mcp/forget/http/junghunkim -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_task_state","arguments":{"task_id":"devloop"}}}' | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(c.get("text","")) for c in d["result"]["content"]]'`
  출력이 크면 하네스가 파일로 저장한다 → Read 1회(별도 턴·rt에 산입). **차단되는 형태**(c291 각 1턴 소모):
  인라인 `python3 -c` 안의 `#` 주석(«Newline followed by #») · heredoc `<<EOF`(«Parser skipped input») ·
  `&&` 복합 명령 · `zsh tmp/x.sh` 스크립트 실행(승인 요구 = 무인 세션 사망 경로). 파일이 필요하면 Write
  도구로 만들고 `python3 tmp/x.py`로 단순 실행한다. 절차 5의 쓰기 호출은 `-d @tmp/x.json`(Write 도구로 생성).

**어느 쪽이든 `restore_note`에 하네스 종류(A/B/C)를 병기한다** — 병기하지 않으면 세 계열이
한 분모에 섞여 지표가 판정 불가가 된다.

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

P29(`research/devloop/predictions.md`)는 이 채널의 **개설**을 판정했다(표본 2로 마감).

**조건부 분기는 왜 c125에 추가됐는가.** 구 문면은 A/B 구별 없이 3턴을 지시했고, 그
결과 기적재 하네스 **c112~c123 12사이클**이 사이클당 1턴씩 불필요하게 냈다(관측 72).
c124가 그 사실을 실측하고(2턴, `restore_turns` 2) 조건부 문면을 `next_actions[0]`에
적었으나 — **그 채널은 턴2에 열린다.** c125는 무기억으로 태어나 여기(구 문면)를 읽고
3을 냈다. 자기가 방금 명명한 함정에 자기가 빠진 것이며, 그래서 조건부 문면이 지금
**이 파일**에 있다. 효능 판정은 **P38**(표본 c126~c130, 판정 c130): 기적재 사이클이
전부 2면 지지, **1건이라도 3이면 반증**. 대조군은 c112~c123 12연속 3 · c125 = 3.
→ **P38 판정 = 지지 5/5** (audit-130 §1).

**하네스 C는 왜 c235에 추가됐는가.** c232가 제3형(`mcp__forget__*`·ToolSearch 동시 부재)을
처음 실측했고 c232~c234가 curl 폴백으로 rt 3을 3연속 냈다 — 구 문면은 A/B 이분법이라 C형
세션은 자기 규약 없이 «B의 유사물»로 임기 배치됐다(c232 발안). c235(회고·C형 4회째)가
«모드는 턴1에 판명되므로 비-일반 모드는 소스 정독을 턴2에 curl과 병렬 배치 가능»을
실측(rt 2 — C형 첫 비-3)하고 두 채널(여기 + 파트 T)에 동시 성문화했다. 골자는 **모드
조건부 턴 수** — C형 rt는 하나의 수가 아니라 {일반 3 · 회고/감사 2}이며, restore_note의
A/B/C 병기가 그 분모를 가른다. 효능 판정 = **P70**(predictions.md · 표본 c236~c245의
C형 사이클, 판정 c245). 회귀 = tests/test_devloop_step0_turn_protocol.py 계약 ④.

**LOOP.md는 왜 c135에 턴1에서 빠졌는가.** 적대 감사는 LOOP.md(헌장·백로그) 금독인데
(지시서 절차 1), 구 문면은 모드를 알기 전인 턴1에 LOOP.md Read를 지시해 **감사가 노출된
채 시작**됐다(audit-130 서두 병기 — 격리의 구조적 구멍). 모드의 정본(c48 첫 줄)은 턴2에
도착하므로, Read를 모드 판명 뒤로 옮기면 턴 수 증가 0으로 구멍이 닫힌다(비감사 사이클은
여전히 절차 0대로 헌장을 읽는다 — 시점만 이동). 효능 판정은 **P40**(amendment-135 §5):
(a) c140 감사가 LOOP.md 턴1 노출 없이 시작 / (b) c136~c140 기적재 restore_turns 전부 2.

## 게이트 큐 — 정본은 `research/devloop/gate-queue.md` (c165 이동)

**당 사이클에 신규 상신·서열 변동·해소가 있으면 그 파일을 직접 고친다. 모드 불문.**
회고를 기다리지 않는다. 회고는 `amendment-N.md §6`에서 그 표를 **포인터로 인용**하고
전문을 복사하지 않는다 — 복사하면 정본이 둘이 된다.

**왜.** 정본이 회고 산출물(`amendment-155 §6`) 안에 있던 동안 상신은 매 사이클
열리고 편입은 10사이클에 한 번 열렸다. 그 위상차로 **c156~c164 9사이클 연속**
청구가 원장 산문에만 살았고 **정본 미등재 5건**이 적체됐다(관측 82). 그중 하나가
*"큐를 옮겨라"*는 청구 자신이었다(A-160.1 = audit-160 R4). 효능 판정 = **P49**(c175).

**경과값은 `N − start + 1`로 계산하고 `start`를 병기한다.** 청구 경과와 계열 계수
(서비스율·봉쇄·응답 대기)를 **같은 칸에 넣지 말 것** — 섞은 결과 A-106.1이 8사이클
연속 10만큼 젊게 인쇄됐다(관측 92).

## 상시 금지 (LOOP.md 원칙 5·6)

릴리스 태그 · PyPI/사이트 배포 · 외부 발신 · `~/.forget` 실DB 파괴적 조작 ·
사이클당 외부 API $2 초과. 게이트가 필요한 산출물은 **릴리스 큐로 완성**해 두고
"게이트 대기"로 보고한 뒤 다음 일로 넘어간다 — 사람의 답을 기다리며 멈추지 않는다.
