# patches/ — 게이트 대기 코드 청구의 릴리스 큐 (audit-290 R2 · c292 신설)

헌장 원칙 5 «릴리스 큐로 완성해 두고 게이트 대기»의 **코드 청구판**이다. 여기 놓인 diff는
**적용하지 않는다** — 적용은 정훈 게이트(gate-queue.md 해당 서열의 한 마디)다. 루프는 파일만
완성하고 «게이트 대기»로 보고한 뒤 다음 일로 넘어간다.

## 정의역 (audit-290 R2)

diff가 만지는 파일은 **HEAD 추적 파일 ∧ 봉쇄 집합(타 트랙 미커밋)과 교집합 0**이어야 한다.
피연산자는 c48 step 0 파트 A 인쇄다. 교집합이 생기면 그 diff는 정의역 밖으로 **표시**하고 남긴다
(삭제하지 않는다 — 1′ R2 `store.py`가 그 상태다: 교집합 1건이라 아직 여기 없다).

## 규약

1. 파일명 = `<청구>-<순번>-<한 줄>.diff` · `git diff` 서식(`--- a/` `+++ b/`) · `git apply --check`로 검산.
2. 매 감사(N%10=0) 직전 각 diff의 `git apply --check`를 재실행한다. HEAD 전진으로 깨지면 그
   사이클이 갱신하거나 «부패» 기재 — 침묵 이월 금지(P76 (b)).
3. 적용 후 기대 효과는 **적용 전에는 주장하지 않는다** — pytest는 적용 뒤에만 실측 가능.
4. 판정 = 다음 감사의 «게이트 대기 코드 청구 중 diff 보유 비율»(audit-290 R2 · P76).

## 목록

| diff | 청구 | 만지는 파일 | 정의역 | 영수증 |
|---|---|---|---|---|
| `obs-129-a-test-seal.diff` | 관측 129 (테스트 측 밀폐) | `tests/test_update_awareness.py` | HEAD 추적 · 봉쇄 교집합 0 | c292 `git apply --check` 통과 · 1세션 작성(14:28 KST) · 2세션 검산 채택 |
| `obs-129-b-bstate-forget-home.diff` | 관측 129 (제품 측 짝 · `FORGET_HOME` 우선) | `hooks/forget_bstate.py` | HEAD 추적 · 봉쇄 교집합 0 | c292 `git apply --check` 통과 · 1세션 작성 · 2세션 검산 채택 |
| `obs-137-partd-calendar-today.diff` | 관측 137 (c48 파트 D 달력 기한 **당일** `cal == today` → due 분기 · «★★ 오늘이 기한이다» 인쇄 · **c318 재생성**: 기한 분류를 순수 함수 `deadline_bucket(cyc, cal, n_now, today)`로 추출 — 인라인 분기는 회귀가 part_d 전체[실 대장·원장·계기 큐 직독]를 불러야 시험됐다[관측 129 부류] · 인쇄 문면·행 튜플 서식 불변) | `research/devloop/scripts/c48_step0_check.py` | HEAD 추적 · 봉쇄 교집합 0 · 계기 코드 +30 −9(c315본 +7 −2 대체) | c315 `git apply --check` 통과(초판) · **c318 재생성** `tmp/c318_make_patch.py`(원본 무접촉 · difflib) · c318 `git apply --check` 통과 · 격리 검산: 원본 테스트→변환 c48 10/10 · **part_d 실 대장 인쇄 원본 = 변환 1,996자 동일**(오늘 당일 기한 0건 → 리팩터 무변경 증명) |
| `obs-137-b-tests-calendar-today.diff` | 관측 137 (회귀 — 수용 기준 ② · `deadline_bucket` 5건: 달력 **당일** due · 전날 overdue/다음날 future · 사이클 축 3상태 불변 · 두 축 동시면 사이클 우선 · 기한 없음 = "none") | `tests/test_devloop_step0_deadlines.py` | HEAD 추적 · 봉쇄 교집합 0 · +31 −0 | c318 `git apply --check` 통과 · 같은 생성기 · 대조군: 변환 테스트→**원본** c48 = 5 실패(새 단언 전부 `AttributeError: deadline_bucket`) · 변환→변환 15/15 · **a와 짝** — b만 적용하면 그 5건이 실패한다 |
| `audit-300-r2-move-frame-docstring.diff` | audit-300 R2 (`queue_mover.move_frame` docstring — 큐 표 상대 이동 vs 상설 표 절대 재계산 비대칭 명시) | `research/devloop/scripts/queue_mover.py` | HEAD 추적 · 봉쇄 교집합 0 · docstring +5 −0 · 동작 변경 0 | c315 `git apply --check` 통과 · 같은 생성기 |
| `obs-126-a-parts-second-predicate.diff` | 관측 126 (c48 파트 S 사망 의심 눈 **제2 술어** — `predecessor_death_evidence`에 `weak` 키[devloop 소유 미커밋 ∧ 수확 이후 무접촉 = **약** · HEAD 신선도 불문] · `evidence`는 **강**으로 존치 · part_s 헤더 두 술어 병기 · «증거 0건»은 강·약 둘 다 0일 때만) | `research/devloop/scripts/c48_step0_check.py` | HEAD 추적 · 봉쇄 교집합 0 · 계기 코드 +24 −6 · 상수 발명 0 | c316 `git apply --check` 통과 · `tmp/c316_make_patch.py` 생성(원본 무접촉 · difflib) · **격리 검산**(pytest 호출 0): 원본 테스트→변환 c48 22/22 · 변환 테스트→변환 c48 25/25 — 적용 후 pytest의 대체 아님 |
| `obs-126-b-tests-weak-evidence.diff` | 관측 126 (회귀 — 기존 «무접촉 = 증거 아님» 단언 1건을 «강 아님·약임»으로 정정 + c208 재현[`blockade_rows` mtime < HEAD]·강·약·unknown 3칸 분리·빈 입력 키 존재 3건 신설) | `tests/test_devloop_step0_reverify.py` | HEAD 추적 · 봉쇄 교집합 0 · +40 −3 | c316 `git apply --check` 통과 · 같은 생성기 · 대조군: 변환 테스트→**원본** c48 = 4 실패(새 단언 전부 `KeyError: 'weak'`) · **a와 짝** — b만 적용하면 그 4건이 실패한다 |
| `obs-140-a-c48-state-cycle-head.diff` | 관측 140 (c48 파트 S·㉼ 세대 눈 — 순수 함수 `state_cycle_from_summary`: 문두 «cN 완료» → 첫 «사이클 N» 인용 → None · task_state_lag과 ㉼ 인라인의 **중복 정규식 두 자리를 한 함수로** · 반환 튜플·인쇄 불변 · audit-320 R2) | `research/devloop/scripts/c48_step0_check.py` | HEAD 추적 · 봉쇄 교집합 0 · 계기 코드 +22 −5 · 상수 발명 0 | c321 `git apply --check` 통과 · `tmp/c321_make_patch.py`(원본 무접촉 · difflib) · 격리 검산(pytest 호출 0): 원본 테스트→변환 c48 20/20 · 변환→변환 24/24 · **실 task_state summary(3,430자) 원본 «판정 불가» → 변환 «일치 320»** |
| `obs-140-b-tests-state-cycle-head.diff` | 관측 140 (회귀 4건 — 문두 우선 · 인용 후행 번호가 지연을 가리지 않음 · 인용 없는 c320 실 서식 · 폴백 순서) | `tests/test_devloop_step0_parsing.py` | HEAD 추적 · 봉쇄 교집합 0 · +33 −0 | c321 `git apply --check` 통과 · 같은 생성기 · 대조군: 변환 테스트→**원본** c48 = 4 실패(새 단언 전부 · `AttributeError: state_cycle_from_summary` 3 + AssertionError 1) · **a와 짝** — b만 적용하면 그 4건이 실패한다 |
| `audit-320-r4-part-f-label.diff` | audit-320 R4 (파트 F 인쇄 라벨 «재발 표본 계수» → «보강 헤더 계수(재발 아님 포함)» · 라벨≠술어 정정 · 동작 변경 0) | `research/devloop/scripts/c48_step0_check.py` | HEAD 추적 · 봉쇄 교집합 0 · 인쇄 1행 +1 −1 | c321 `git apply --check` 통과 · 같은 생성기 · obs-140-a와 같은 파일·다른 헝크(각각 HEAD 기준 검산 · 동시 적용 순서 **c324 전수 검산 = 순열 120/120 통과**) |
| `obs-139-a-c48-corider-last.diff` | 관측 139 ③ (c48 파트 F 색인 — 순수 함수 `header_coriders`: «보강» 헤더가 나르는 둘째 이후 «관측 N»(첫 번호 제외·중복 제거·등장 순) · parse_observations가 그 번호들의 `last`를 헤더 기재-사이클로 전파 · **기존 항목에만**(키 집합 불변) · tagged·exited·opened·title·reinforcement_counts 무접촉 · 한계 = 헤더 안 인용 과계상[실측 1건 «반대 관측 2건» · 항목 없어 전파 0]) | `research/devloop/scripts/c48_step0_check.py` | HEAD 추적 · 봉쇄 교집합 0 · 계기 코드 +31 −0 · 상수 발명 0 | c322 `git apply --check` 통과 · `tmp/c322_make_patch.py`(원본 무접촉 · difflib) · 격리 검산(pytest 호출 0): 원본 테스트→변환 c48 22/22 · 변환→변환 28/28 · **실 frictions.md: 키·open(80)·reinforcement_counts 동일 · last 갈림 4 = 31(137→138)·101(170→281)·136(315→321)·137(318→319)** · 동승 보강 헤더 전수 16(c138~) · **c48 diff 5본 연속 --check 통과**(obs-140-a→obs-139-a→audit-320-r4→obs-137→obs-126-a 순 · **c324 순열 120/120·순서쌍 20/20 = 순서 무관 증명**) |
| `obs-139-b-tests-corider-last.diff` | 관측 139 ③ (회귀 6건 — 판별 4: 둘째 이후 번호·등장 순 · 원본/처분/산문 [] · last 전파+opened·tagged 무접촉 · 실 대장 136 ≥ 318 / 불변 2: 무주 번호 항목 미생성·헤더 계수 1 · open 집합 불변) | `tests/test_devloop_step0_observations.py` | HEAD 추적 · 봉쇄 교집합 0 · +83 −0 | c322 `git apply --check` 통과 · 같은 생성기 · 대조군: 변환 테스트→**원본** c48 = 판별 4 실패(`AttributeError: header_coriders` 2 + AssertionError 2) · 불변 2 양쪽 통과(설계) · **a와 짝** — b만 적용하면 판별 4건이 실패한다 |
| `audit-320-r3-vocab-overdue-direction.diff` | audit-320 R3 («도과»를 «반증»과 가른다 — **정의역 정정**: 맨 «마감-기한도과»는 R10[c125]부터 VOCAB에 있었고 없던 것은 처분 조항[P24 «도과 무판정이면 반증 계상»]이 강제하는 방향 · P36 판정 c317 (a)(b) 맨 «반증»×2 · 처치 = `VOCAB_C323 = ("마감-기한도과(반증)",)` c136 «마감-조기(지지/반증)» 서식 · `_r10_base` 밑값 «마감-기한도과» · §1 tag 1행 · 맨 값 존치[강등 없음] · 지지 방향 미신설) | `research/devloop/scripts/c124_retro_prep.py` | HEAD 추적 · 봉쇄 교집합 0 · 계기 코드 +13 −2 · **값 신설 = 개헌 채널(A-160.x/R2b)이라 적용 = 게이트** | c323 `git apply --check` 통과(신규 2 + c48 5본 = 7본 한 번에) · `tmp/c323_make_patch.py`(원본 무접촉 · difflib) · 격리 검산(pytest 호출 0): 변환 테스트→변환 5/5 · **실 predictions.md: records·errors·arm_counts 원본 = 변환 동일(절 83 · 위반 1[P39 기지] · «반증» 팔 23 · 신규 값 팔 0)** — P36 상태줄 «(a) 반증 · (b) 반증» 정정은 적용 뒤 |
| `audit-320-r3-tests-vocab-overdue-direction.diff` | audit-320 R3 (회귀 5건 **신규 파일** — 판별 2: P36형 상태줄 어휘 안 · `_r10_base` 밑값 = P26 사상값 / 불변 3: 계수 키 «반증»과 분리 · 맨 «마감-기한도과» 무강등[마감-조기와 대비] · R10 ⊂ VOCAB·중복 0) | `tests/test_devloop_vocab_overdue_direction.py` (신규) | 신규 파일 · 봉쇄 교집합 0 · +51 −0 | c323 `git apply --check` 통과(단독 · 7본 묶음) · 같은 생성기 · 대조군: 변환 테스트→**원본** 모듈 = 판별 2 실패(AssertionError 2) · 불변 3 양쪽 통과(설계) · **a와 짝** — b만 적용하면 판별 2건이 실패한다 |

## 순서 전수 검산 (c324 · 규약 2의 «HEAD 전진» 검산과 별개 축)

c322~c323 영수증은 c48 5본(`obs-140-a` `obs-139-a` `audit-320-r4` `obs-137` `obs-126-a` — 전부
`research/devloop/scripts/c48_step0_check.py`)을 **한 순서**로만 검산했다. c324 `tmp/c324_patchcheck.py`
(`git apply --check`만 · 작업 트리 쓰기 0 · pytest 호출 0): 단독 5/5 · 순서쌍 20/20 · **순열 120/120** 통과 ·
7본 묶음(+`audit-320-r3-a·b`) 정순·역순·extra선행 3/3 · **patches/ 14본 전수 한 번에 통과**. 5본은 같은 파일의 서로
다른 헝크라 순서 무관이 증명됐다. 이 결과는 **HEAD 기준**이다 — 규약 2대로 HEAD가 전진하면 다시 돈다(다음 = c330 감사).

## A-241.1 — 기동 명령 + 수용 기준 ① 검증 (c293)

A-241.1(gate-queue.md 서열 30)의 처분 "기동 승인"이 나오면 실행할 명령과, 실행 후
수용 기준 ①(engine=LLM 복귀)을 확인할 검증 스크립트. **명령은 여기 적기만 하고
실행하지 않는다** — 실행은 원칙 3·4(도그푸드 실DB 런타임 개입)의 사람 게이트다.

- 기동 명령(정훈 승인 후 실행): `launchctl kickstart -k gui/$(id -u)/ai.forget.server`
  (forget/cli.py:659와 같은 관행 — 요약 엔진은 별도 launchd 라벨이 없고 서버 프로세스
  안에서 ollama를 호출하므로, 서버 재기동이 재시도 경로다).
- 검증 스크립트: `research/devloop/scripts/verify_a241_engine.py` — `~/.forget/bstate/forget.json`
  최신 캡처의 `engine` 필드가 `structural-fallback`이 아니면 통과(exit 0). c293 실측 =
  실패(exit 1, engine=structural-fallback, captured_at 2026-09-04T13:09:10+0900) — 기동 전
  베이스라인.

미완성 후보(다음 일반 사이클): 1′ R2 `store.py`(교집합 0 복원 시) · 관측 138 (ii) 캡슐 조립기 슬롯 최소 보장(P80 (b) 또는 슬롯
고정값 실측 뒤) · 파트 X «기지 은퇴 목록» 상수(4건).
