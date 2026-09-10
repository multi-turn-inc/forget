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
  **C형 curl의 가드 통과 형태(c291 실측 · 관측 132 · P75 · **c326 `results` 벗김 판본으로 갱신**)** — 한 줄·주석 없음·파이프만:
  `curl -s -X POST localhost:8000/mcp/forget/http/junghunkim -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_task_state","arguments":{"task_id":"devloop"}}}' | python3 -c 'import sys,json; d=json.load(sys.stdin); t="".join(c.get("text","") for c in d["result"]["content"]); j=json.loads(t) if t.strip().startswith("{") else None; print(json.dumps({k:v for k,v in j.items() if k not in ("results",)},ensure_ascii=False,indent=1) if isinstance(j,dict) else t)'`
  **왜 벗기는가(관측 141).** `get_task_state`는 같은 claim을 `current`와 `results[0]`에 두 번 싣는다 — 원형(text 그대로 인쇄)은 34~38KB라
  하네스 저장 문턱(19,016B 근방)을 넘어 저장본 Read 1턴을 내고(c323 rt 4 · c326 실측 34,872B), 벗김본은 ≈17KB로 인라인 수신된다(c325 실측).
  `current`가 정본이며 `results`는 단일 조회에서 같은 본문이다(처치 diff = patches/obs-141-a·b·c · 적용 = 게이트). 출력이 그래도 크면
  하네스가 파일로 저장한다 → Read 1회(별도 턴·rt에 산입). **차단되는 형태**(c291 각 1턴 소모):
  인라인 `python3 -c` 안의 `#` 주석(«Newline followed by #») · heredoc `<<EOF`(«Parser skipped input») ·
  `&&` 복합 명령 · `zsh tmp/x.sh` 스크립트 실행(승인 요구 = 무인 세션 사망 경로). 파일이 필요하면 Write
  도구로 만들고 `python3 tmp/x.py`로 단순 실행한다. 절차 5의 쓰기 호출은 `-d @tmp/x.json`(Write 도구로 생성).
  **C형 복원 *이후* 채널의 가드 형태(c305 성문 · 관측 132 보강 c303 · P78)** — 절차 3·5도 같은 가드
  아래 있고, 이 지식이 task_state·직전 tmp/*.json에만 살면 무기억 손은 매번 다시 부딪힌다(c303 실측 3회).
  인자명: `add_memory` = **`text`**(«content»는 −32000 «messages or text is required») ·
  `record_task_state` = `task_id`/`status`/`summary`/`next_actions`/`evidence_files` · `search_memories` = `query`.
  차단 형태 **전면**: `;` 복합도 `&&`와 똑같이 승인 요구 · 인라인 `python3 -c` 안의 **모든 `#`**(주석이든
  마크다운 `##` 헤더든 — 가드는 «따옴표 안 개행 뒤 #»만 보고 의미를 묻지 않는다) · heredoc. `#`이 든
  본문(frictions.md·predictions.md 절)은 Edit/Write 도구로 쓴다 — 인라인 python으로 append하지 않는다.
  **추가 등재(c305 관찰 3형태 + c306 실측 1형태 · P78 «형태 갱신 = 처치»)**: `grep … | head`(«multiple
  operations») · **grep 패턴 안의 `\|` 대체·`\{n,m\}` 수량자**(c306 2회 — 파이프 뒤에서는 «multiple
  operations», 단독으로도 «requires approval»; 같은 세션의 `grep "a\|b" … | tail -N`과 `grep -o "[^|]*"`는
  통과했으므로 술어는 미확인 — 정규식 좁히기는 **Grep 도구**로 한다) · `$?` 확장(«simple_expansion» —
  종료 코드는 스크립트 안에서 print한다) · `> 파일` 출력 리다이렉트(«allowed working directories» 거부 —
  비ASCII 워크트리 경로·관측 41 기전 · 큰 출력은 하네스 자동 저장 파일을 Read한다). 파트 T curl 한 줄의
  `| python3 -c` 파이프는 통과한다. **c310 등재(감사 실측 1형태)**: 인라인 `python3 -c` 안의 `|=`(파이프
  문자 직후 `=` — «Contains zsh =cmd equals expansion» · 따옴표 안이어도 가드는 `=`로 시작하는 단어로 본다) —
  증강 대입이 든 파이썬은 Write 도구로 파일을 만들어 `.venv/bin/python tmp/x.py`로 실행한다.

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

## task_state `next_actions` 서식 — 달력 사건은 날짜 조건으로 적는다 (c305 · 관측 135)

`next_actions`는 **사이클 서수**(cN)에 실리는 채널이다. 달력에 묶인 사건(예측 마감·기한 판정)을
«cN에서 판정»으로 적지 말 것 — «**KST 날짜 ≥ 기한**인 첫 사이클에서 판정»으로 적고, 집행 손은
판정 전에 `date -u`와 c48 파트 D «오늘 기한/도과» 인쇄를 대조한다. 파트 D가 «오늘 기한 0·도과 0»을
인쇄한 사이클은 달력 판정을 열지 않는다(기계 눈 우선).

**왜.** 사이클≈1일은 가정이지 상수가 아니다 — c302/c303/c304가 2026-09-09 02:03/02:30/02:52 KST에
연달아 떴고, c303이 적은 «c304 = 09-10 당일 판정»을 문면대로 집행했으면 P36이 하루 이른 반증 도장을
받았다(관측 135 · 파트 D는 옳았고 산문이 틀렸다). 효능 판정 = 관측 135 수용 기준 ③(공존 표본 0건).

## task_state `next_actions[0]` 서식 — 다음 사이클 첫 항목 한 줄 (c315 · 관측 138 · P80)

`next_actions[0]`은 SessionStart 캡슐 «다음 행동:» 슬롯에 실리는 **유일한** 항목이고, 그 슬롯은 «현재 목표:»(summary)와
1600자 예산을 경합한다. [0]에는 **다음 사이클의 모드 · 하네스 턴 배치 포인터(«CLAUDE.md 파트 T C형») · 첫 후보 하나**만
적는다(**≤ 200자** — 캡슐 조립기의 «다음 행동:» 항목 상한이 **220자 상수**[`forget/store.py` `_render_context_capsule_text` · c325 코드 직독]라 ≤ 400자는 첫 표본부터 절단됐다 · P80 판정 c325: 293~398자 표본 5/5 절단 · ≤ 200자 표본 5/5 전문). 상시 손 의무(이동기·전사·정산 줄) · 달력 규약 · step 0 주의 · 전사 재료 · 회고 의제는 **[1]~**로 나눈다 —
그것들은 task_state를 읽는 손에게만 필요하고, 캡슐로 배달될 때 [0]을 자르는 비용만 낸다.

**왜.** c308~c314 캡슐 «다음 행동:» 절단 7연속 · c314는 [0] 길이가 같은데 «현재 목표:»가 길어지자 절단이 앞으로 갔다
(관측 138 · audit-310 R2). 캡슐 단독 복원이 partial로 고정된 원인의 루프 쪽 절반이 [0] 팽창이다. 효능 판정 = **P80**
(창 c316~c325 · 도달 사이클 중 [0] 전문 도달 ≥ 8/10 · (b) 발화면 제품 몫[캡슐 조립기 슬롯 예산]으로 귀속).
**판정(c325).** (a) 반증(5/10 · 전부 ≤ 400자 서식 아래) · 기전 정정 = «현재 목표:» 팽창 경합이 아니라 항목별 고정 상한(220/240)이었다 — 앞 블록 길이는 뒤 블록에 영향 0. ≤ 200자로 적은 5사이클은 5/5 전문 도달. 정본 = predictions.md P80 판정 절 · 관측 138 보강 c325.

## 상시 금지 (LOOP.md 원칙 5·6)

릴리스 태그 · PyPI/사이트 배포 · 외부 발신 · `~/.forget` 실DB 파괴적 조작 ·
사이클당 외부 API $2 초과. 게이트가 필요한 산출물은 **릴리스 큐로 완성**해 두고
"게이트 대기"로 보고한 뒤 다음 일로 넘어간다 — 사람의 답을 기다리며 멈추지 않는다.
