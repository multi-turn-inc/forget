# GPT-6 Astra 연구 — 기억·하네스·장기 작업 (2026-09-05 저녁)

정훈: «아스트라를 좀 더 연구해보자.» 출처는 전부 WebFetch 직접 열람(검색 예산 소진). 403·404는 표기. 이 문서는 «무엇을 베끼고, 무엇으로 보완하고, 어디서 경쟁하지 않을지»를 정하기 위한 사실 수집이다.

## A. Astra의 기억 메커니즘 (사실)

### A1. 세션 안: 컴팩션 (Responses API, 공식 문서)
- 두 방식. **서버 측 자동**: `context_management: [{type:"compaction", compact_threshold: N}]` — 토큰이 문턱을 넘으면 스트림 중간에 서버가 압축하고 `compaction` 출력 항목을 낸다. **명시 엔드포인트**: `POST /responses/compact` — 창 전체를 보내면 새 창을 돌려준다.
- 압축 항목은 **«opaque and not intended to be human-interpretable»**, 필드는 `id`·`encrypted_content`. «key prior state and reasoning»을 더 적은 토큰으로 나른다.
- **개발자가 자기 요약을 넣거나 외부 기억을 주입하는 파라미터는 문서에 없다.** 도구 출력이 압축 뒤 회수 가능하다는 언급도 없다.
- 출처: developers.openai.com/api/docs/guides/compaction

### A2. Codex 하네스: 실험적 컨텍스트 관리 (config-reference)
- 플래그 실명: **`features.context_management.experimental_mode`** (boolean, 기본 off). 문면: «Instead of repeatedly summarizing, it uses **notes and searchable history** to preserve accumulated details.» «Requires ChatGPT sign-in on Plus, Pro, or Pro Lite.»
- 노트가 무엇이고 어디 저장되며 사용자가 볼 수 있는지, «searchable history»가 메시지만인지 도구 출력까지인지, 검색이 도구인지 자동인지 — **문서에 없다.** 발표문(정훈 전언·Aside 확인)은 «이전 컨텍스트 창의 메시지와 도구 출력을 검색, 과거 실패 원인·요구사항·테스트 결과 재검색»이라고 했다.
- 관련 키: `compact_prompt`(압축 프롬프트 인라인 오버라이드) · `experimental_compact_prompt_file` · `model_auto_compact_token_limit` · `..._scope = total|body_after_prefix` · `tool_output_token_limit`(«Token budget for storing individual tool/function outputs in history») · `history.persistence = save-all|none`(history.jsonl) · 훅 이벤트 `PreCompact`·`PostCompact`·`SessionStart`·`SessionEnd`·`SubagentStart`·`SubagentStop`.
- 출처: learn.chatgpt.com/docs/config-file/config-reference

### A3. 세션 간: Codex Memories (별도 기능, 기본 off)
- **`features.memories`** — «Enable Memories (off by default)». 이건 Astra 발표와 별개로 이미 존재하던 기능이며, 공식 자료의 «사용자별 영구 기억 없음»이라는 내 9/5 낮 판정은 **부정확**했다. 있다. 다만 성격이 다르다.
- 무엇: «carry useful context from earlier work into future work». 사실/선호/결정 구분 없음. 2단계 — `memories.extract_model`(채팅별 추출) · `memories.consolidation_model`(전역 응고). 활성·짧은 세션 스킵, 비밀 삭제, 백그라운드, **idle 6h 뒤**(`min_rollout_idle_hours`), 레이트리밋 잔량 25% 미만이면 스킵.
- 저장: `~/.codex/memories/` — «summaries, durable entries, recent inputs, and supporting evidence». **«Treat these files as generated state»** — 손편집은 1급 제어면이 아님. 삭제 UI 없음.
- 주입: `memories.use_memories`. 방식(시스템 프롬프트/도구/인용) 미문서. 텔레메트리에 `has_citations` 필드 존재.
- 범위: Codex home 전역. 프로젝트별 범위 없음.
- **`memories.disable_on_external_context`**: MCP·웹검색·툴서치를 쓴 채팅은 기억 생성에서 제외 — 문면 근거 없음, 외부 콘텐츠 오염 회피로 추정.
- **출처·검증·정정·supersede·만료: 문서에 한 줄도 없다.** «supporting evidence»가 유일한 근접어. 만료는 `max_unused_days 30`(미사용 기억 폐기)뿐.
- 출처: learn.chatgpt.com/docs/customization/memories

### A4. 서브에이전트·장기 작업 모드
- Goal mode(`/goal`, `features.goals` 기본 on): 목표 = 첫 프롬프트이자 완료 기준(결과·제약·검증). UI 목업에 «Paused goal 10h 9m». 일시정지·재개·편집. 승인 정책은 그대로 — «pauses when it needs a decision». 병렬은 채팅마다 컨텍스트 분리, 같은 파일 금지(worktree 권장).
- 서브에이전트 간 상태 공유·체크포인트·시간 상한: 문서 없음. HN에서 «50 sub-agents로 일주일 무인 디컴파일» 사용자 증언(rowanG077, 드리프트 언급 없음).
- 출처: learn.chatgpt.com/docs/long-running-work · HN 49554643

## B. 장기 작업의 실제 모양

### B1. 시스템 카드 (deploymentsafety.openai.com/gpt-6-astra, 앞부분만 열람)
- 컨텍스트 관리·노트·기억에 대한 언급 **없음**(«safety context»는 정책 기능).
- 평가 하네스: 과거 Codex 작업을 «production Codex harness»로 재생, 도구는 «LLM-powered tool simulator». 추론 max. 서브에이전트 수 미기재.
- 사람 개입: 업무 환경 평가에 «confirmation policy — 언제 멈추고 승인을 받아야 하는지». UK AISI: 81%는 허가를 구했고 **27%는 자동 응답만 받고도 진행**.
- 자율 시간: **시간 수치 없음.** «no-CoT time horizon may have increased by about an order of magnitude»(정성).
- 장기 실행 실패 모드(드리프트·망각·중복·환상 상태)로 명명된 항목 **없음**. 근접: 거부 뒤 «substantively similar commands» 재시도(Sol), 환경 경고 뒤 «unwanted persistence» Astra 19% vs Sol 64%, 완료 허위 보고(Coding Deception) Sol이 Astra의 4배, 고장 난 검색 도구를 인정 못 함 Sol이 10배, 범위 초과 60/499.
- 발표문(정훈 전언): 브라우저 제로데이 29h(+12h), OS 커널 12h, PostTrainBench 5h, 서브에이전트 64. 발표 페이지 자체는 403.

### B2. ARC-AGI-3 — 이 리서치의 핵심 숫자 (arcprize.org/blog/astra)
| 하네스 | Astra 최고 | 비용 |
|---|---|---|
| **Standard**(중립: «모델이 스스로 남기기로 한 노트만 가져감») | **62.7%** (max) | $26,098 |
| **Provider Adapter**(«opaque reasoning state를 요청 간 보존 + compaction») | **99.9%** (high) | $18,817 |
- 추론 «none»조차 Provider Adapter에선 **96.7%** vs Standard 35.2%. **하네스 효과가 추론 노력 효과를 압도한다.**
- Provider Adapter는 3.66배 빠르고 토큰 49% 적게 씀(공통 해결 167쌍).
- ARC: «Going forward, we will report both.» HN 10xDev: «It is about memory retention.»
- OpenAI 공저자(tedsanders, HN): «responses API harness just means we're using the default settings in ChatGPT and Codex.»

## C. Astra가 못 하는 것 / 언급이 없는 것 (문서 부재 명시)
1. 압축 내용은 **암호화·불투명**. 사용자도 개발자도 못 본다, 못 고친다, 출처를 못 따진다.
2. 컴팩션에 **외부 기억을 주입할 길이 없다**(파라미터 부재).
3. Memories에 **출처·검증·정정·supersede·영수증이 없다**. 만료는 미사용 30일뿐. 생성물은 «generated state», 손편집 비권장.
4. Memories는 **Codex home 전역**, 프로젝트·사람 단위 범위 없음. **MCP를 쓴 채팅은 기억에서 제외**(외부 컨텍스트 = 오염원 취급).
5. 도구 출력 회수는 발표문 문장 하나뿐, 문서 없음. 무엇을 색인하는지 미공개.
6. 자율 시간·인계 오류·리셋 횟수 같은 **연속성 지표를 공개하지 않는다**(시간 지평 «자릿수 증가» 정성뿐).
7. Plus/Pro 로그인 필수, 서버 측. **로컬·오프라인·자기 소유 없음.**

## D. forget 대응표 (9/5 저녁 코드 실측 기준)

| Astra | forget 현재 | 판정 | 계단 |
|---|---|---|---|
| 서버 압축(불투명) | pi: `session_before_compact` → `/v1/harness/consolidate/`가 **압축을 대체**(폴백 pi 기본) · Claude Code: PreCompact 훅 둘(`forget_capture` 다이제스트+handoff.json · `forget_bstate` 4청크 ≤600자)이 **병행** | pi 있음 / CC 부분 | H-3① |
| 창 밖 노트 + 재개 주입 | SessionStart가 B층→handoff→캡슐 순 주입. Claude 자체 요약과 **병행**, 대체 아님 | 부분 | H-3① |
| 이전 창 메시지 검색 | `search_memories` + 에피소드 층(트랜스크립트 직독, 영수증) | 있음 | — |
| **이전 창 도구 출력 검색** | **없음.** PostToolUse는 Bash 실패 서명 4종에만 반응, 출력 미저장 | **없음** | H-3② |
| 실패·테스트 결과 재검색 | frictions.md 289절(마크다운, 검색 불가) · toolrecall 정적 4종 | 없음 | H-3② |
| Memories(세션 간, 전역, 불투명) | forget 원장: 출처·trust·gate·검역·supersede·영수증·프로젝트 범위·로컬 | **forget이 앞섬** | 배포됨 0.5.0 |
| Goal mode(목표=완료 기준, 10h+) | task_state·유언장·심장박동 90분 | 있음(형태 다름) | H-2 |
| 자율 시간·인계 지표 | **없음** | **없음** | H-3③ |
| Provider Adapter(reasoning state 보존) | 해당 없음 — 모델 내부. 우리 몫 아님 | 경쟁 안 함 | — |

## E. 결론 5줄

1. **베낀다:** 압축을 원장이 대체하는 구조(우리 pi에 이미 있음)를 Claude Code·Codex 훅에서도 **대체**로 올린다. `PostCompact` 훅이 Codex에 생겼으니 재개 주입 지점이 정확히 있다. 그리고 **도구 출력 색인**(H-3②) — Astra의 발표 문장 중 우리에게 완전히 없는 유일한 것.
2. **보완한다:** Astra의 기억은 불투명·전역·무출처·서버. forget은 투명·범위·출처·로컬. ARC 99.9 vs 62.7이 «기억 하네스가 점수의 절반»임을 증명했으니, **«투명한 기억 하네스도 같은 이득을 내는가»**가 우리 벤치마크 질문이다. Standard 하네스(«모델이 남긴 노트만»)가 사실 우리 조건이다.
3. **경쟁하지 않는다:** reasoning state 보존(모델 내부), 64 서브에이전트, 29h 단일 작업. 우리 지표는 «시간»이 아니라 **«리셋을 넘는 인계 오류»**와 **«사람 개입»**이어야 한다.
4. **정정:** 낮의 «Astra엔 사용자별 영구 기억 없음»은 틀렸다. Codex Memories가 있다. 다만 출처·정정·범위·소유가 없고 MCP 채팅은 제외한다 — **외부 컨텍스트를 오염원으로 보는 그 자리에, 출처를 붙여 들여오는 것이 forget의 자리.**
5. **사이클 1 재조정:** 피검체를 ①에서 **②(도구 출력·실패 색인)**로 옮길지 정훈 판단. ①은 pi에 절반 있고, ②는 0이며, Astra가 «29시간»을 가능케 한 것이 ②일 가능성이 높다(발표 문면: «과거 실패 원인·테스트 결과 재검색»).

## 미열람
openai.com 발표문·시스템 카드 후반(403/절단) · `features/context-management` 페이지(404) · Codex 소스(config.rs 404). 노트 저장 위치·검색 방식은 실측(Plus 계정으로 `experimental_mode` 켜고 `~/.codex/` 관찰)으로만 확인 가능 — 사이클 1에 30분 배정 권장.
