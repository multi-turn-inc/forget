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
