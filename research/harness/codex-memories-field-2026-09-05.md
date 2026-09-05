# Codex Memories 실물 관찰 — 정훈 머신 `~/.codex/memories/` (2026-09-05 22:30 KST)

정훈: «지금 .codex/memories에 어떻게 쌓이고 있는지 조사해보면 되는 거 아냐?» 맞다. 문서(astra-study §A3)가 못 답한 것을 실물이 답했다. **읽기만 했다.** codex-cli 0.144.3, `[features] memories = true`.

## 1. 파이프라인 (실물로 확정)

```
sessions/**/rollout-*.jsonl  (648개, 8월 이후 101개)
        │  idle 6h 뒤, 백그라운드, 레이트리밋 잔량 ≥25%일 때
        ▼  Phase 1 — 채팅별 추출 (memories.extract_model)
rollout_summaries/<date>-<id>-<slug>.md   (12개)   ← 세션당 1파일
        ▼  Phase 2 — 전역 응고 (memories.consolidation_model)
raw_memories.md   (12 thread 블록, 313행)   «Merged stage-1 raw memories (stable ascending thread-id order)»
MEMORY.md         (38KB, cwd별 «Task Group» 단위로 재조직)
memory_summary.md (7.7KB, «v1», 주입용 요약본으로 추정)
        + .git (커밋 1개 «Initialize Codex git baseline» 2026-09-02)
        + extensions/{chronicle,ad_hoc}/instructions.md · .omx/ (다른 도구의 상태 — Codex 것 아님)
```

## 2. 선별률 — 가장 중요한 숫자

| | 수 |
|---|---|
| 전체 세션 | 648 |
| 8/1 이후 세션 | 101 |
| 기억이 된 세션 | **12** (1.9% · 8월 이후 기준 11.9%) |
| 7/9 ~ 9/1, 월 ~5개 | |

**대부분의 세션은 기억이 되지 않는다.** «활성·짧은 세션 스킵» + «MCP/웹검색 쓴 채팅 제외»(`disable_on_external_context`) + idle 6h 조건이 겹친 결과로 보인다. 정훈의 Codex 세션 대다수는 forget MCP를 쓰므로 **기본 설정이면 forget을 쓴 세션은 Codex 기억에서 빠진다** — 두 기억 층이 서로를 못 본다.

## 3. 기억 한 건의 형태 (raw_memories.md, thread 01a05b46)

프론트: `updated_at · cwd · rollout_path · rollout_summary_file` → `description · task · task_group · task_outcome(success|partial|uncertain) · keywords`
본문(Task별): **Preference signals** («사용자가 “…”라고 요청함 -> 앞으로 …이 적합함») · **Reusable knowledge** (경로·명령·검증 결과) · **Failures and how to do differently** (증상→원인→처방) · **References** (명령·경로).
MEMORY.md는 이를 cwd별 Task Group으로 묶고 `scope · applies_to(cwd=…; reuse_rule=…)`를 붙인다. memory_summary.md는 **User Profile · User preferences · General Tips · What's in Memory(cwd/날짜별 desc+learnings) · Older Memory Topics**.

task_outcome 분포: success 20 · partial 8 · uncertain 4 (Task 단위 32).

## 4. 있는 것 / 없는 것

| 있음 | 없음 |
|---|---|
| 세션→요약→응고 2단, 백그라운드, idle 게이트 | **출처 라벨** (누가 말했나: 사용자/도구/추론 구분 없음 — «Preference signals»만 사용자 발화 인용) |
| rollout_path·thread_id·updated_at (영수증의 반쪽) | **검증·정정·supersede** — 9/1 OpenCodex 제거가 8/28 설치 기억을 «supersedes any assumption» 문장으로만 처리(구조 아님) |
| cwd 범위(applies_to) + reuse_rule (재사용 조건 문장) | **만료 구조** (미사용 30일 폐기만) |
| 실패→처방 섹션 (우리 frictions와 같은 자리) | **도구 출력 색인** (요약에 명령·경로만, 출력은 없음) |
| 비밀 삭제 | **사람이 고치는 제어면** («generated state») |
| git baseline (이력 씨앗) | 커밋 1개 — 이력으로 안 쓰임 |
| | **forget MCP 쓴 세션 제외** → 두 층 단절 |

## 5. 주입 — 미확인

오늘(9/5) 세션 6개는 전부 auto-review 보조 세션(«The following is the Codex agent history whose request action you are assessing»)이라 memory_summary 주입 흔적이 없는 것이 정상일 수 있다. `world_state.agents_md`에는 **forget의 AGENTS.md 블록**이 실려 있음을 확인. Codex Memories가 실제 대화 세션 프롬프트 어디에 어떤 형태로 들어가는지는 **다음 실제 세션 1개를 열어 확인**해야 한다(사이클 1의 30분 항목).

## 6. forget에 대한 함의

1. **Codex는 이미 «에피소드→의미» 2단 응고를 로컬에서 돌린다.** 우리 일일 응고(05:23 launchd)와 같은 모양. 차이는 우리는 원장(구조)으로, 그들은 마크다운(문서)으로.
2. **그들이 버리는 세션이 우리 재료다.** MCP를 쓴 세션 = 외부 컨텍스트 = 오염 위험이라 통째로 제외. 우리는 0.5.0에서 origin·검역으로 그 위험을 **구조로** 다룬다. 이건 마케팅 문장이다: «Codex가 기억하지 않기로 한 세션을, forget은 출처를 붙여 기억한다.»
3. **«Failures and how to do differently»가 그들의 frictions다.** Astra 발표의 «과거 실패 원인 재검색»은 이 섹션을 검색하는 것일 가능성이 높다. 우리 H-3②(실패 색인)는 이 형식을 참고할 수 있다: 증상→원인→처방 3단.
4. **선별률 1.9%는 그들의 약점이자 우리의 벤치마크.** «이 세션이 기억될 가치가 있는가»를 idle·길이·외부컨텍스트 휴리스틱으로 정한다. 우리는 훅이 매 세션을 캡처하고 게이트가 걸러낸다. 어느 쪽이 나은지는 회수율로 잰다.
5. **rollout_path가 영수증의 반쪽이다.** 우리 에피소드 층(파일·줄·시각)과 같은 발상. 다만 그들은 줄 번호가 없고 정정 이력이 없다.

## 7. 다음
- 실제 Codex 대화 세션 1개 열어 주입 형식 확인(30분).
- `features.context_management.experimental_mode` 켜고 창 넘김 뒤 `~/.codex/` 변화 관찰 — «노트»가 memories/와 같은 파일인지 별개인지(Plus 로그인 필요, 정훈 계정).
- H-3② 실패 색인 스키마를 «증상→원인→처방 + 출처 + 세션 영수증»으로.
