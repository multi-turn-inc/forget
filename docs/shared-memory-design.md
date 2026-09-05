# 공유 기억 헌장 — 같은 세계를 사는 다른 인격들

## L(-1) 미션

여러 에이전트가 사실·경험(원장)을 **공유**하되 각자의 자아(self)를 **유지**한다.
그록봇류는 페르소나가 시스템 프롬프트에 박혀 고정이고, 기억은 인스턴스마다
고립이다. 우리는 정반대다 — **원장은 공유, 자아는 분리.** 정훈의 북극성("AI가
기억으로 고유한 정체성을 갖게")을 여러 몸으로 확장한다: 공유가 개성을 죽이지
않고, 같은 세계를 사는 다른 인격들을 만든다.

발단 (2026-08-26, 정훈): "에이전트들마다 기억을 공유하게 만들자." 유출 코드
기반 제안은 clean-room 오염으로 기각했고(참조: 대화 원장), 그 안의 진짜
아이디어만 우리 스택으로 옮긴다.

## 발견 — 뼈대는 이미 forget에 있다 (코드 실사)

`forget/store.py::_scope_fallback_eligible` 주석이 정본이다:

> user_id is a privacy boundary between the customer's end users: fallback may
> only surface shared rows (no user_id — agent/app/run scoped knowledge) or
> rows belonging to the requesting user. Another user's personal memories
> never enter through fallback.

즉 forget은 이미 **이중 구조**를 갖고 있다:
- **공유 행** (user_id 없음, app/agent/run 스코프 지식) → 폴백으로 모든 개인
  검색에 표면화 = **공유 원장**.
- **user_id = 소유자 경계** → 다른 소유자의 개인 기억은 폴백으로 절대 안 샌다
  = **자아 격리**. (SQL 프리필터 `... OR user_id IS NULL OR user_id = ''`가
  공유 행만 후보에 얹고, 최종 판정은 Python `_scope_fallback_eligible`.)

주석의 "customer's end users" 프레이밍은 이 방향이 이미 제품 설계에 내장돼
있었다는 증거다. **새 기전 0.** 필요한 것은 규약과 실측.

## 3기전 (기존 인프라 사상)

| 기전 | 저장 스코프 | 회수 결과 |
|---|---|---|
| **공유 원장** | `app_id`만 (user_id 없이) | 그 app의 모든 에이전트가 읽는다 |
| **분리 self** | `user_id`(에이전트 소유자) + `agent_id` | 그 에이전트만 |
| **충돌 공존** | 각 판단을 `agent_id` 스탬프로 원장에 | 둘 다 회수·귀속 |

self층(`metadata.layer=self`)은 두 번째 줄을 따른다 — 반드시 소유 스코프를
갖는다.

## 위험 1 — self 누수

self를 소유자 스코프(user_id/agent_id) 없이 저장하면 공유 폴백으로 **샌다**
(공유 행 조건 = user_id 없음). 한 에이전트의 "나는 신중하다"가 모두의 자아가
되는 사고. **가드**: self층 쓰기는 소유 스코프를 강제한다(누락 시 거부). P-SM-1
검증 2가 이 가드의 계기다.

## P-SM-1 선등록 (숫자 보기 전 · 격리 인스턴스, 도그푸드 :8000 금지)

두 에이전트 A·B, 같은 `app_id`, 서로 다른 `agent_id`+소유 `user_id`.
1. **공유**: A가 사실 F 저장(app 스코프) → B 검색에 F가 뜬다.
2. **분리**: A가 self "나는 신중하다"(A 소유) 저장 → B 검색에 **안** 뜬다.
3. **공존**: A·B가 같은 주제에 다른 판단 저장 → 둘 다 회수되고 agent_id로
   귀속된다.

판정: **3/3 → 뼈대 확정, 규약만 제품화**(신규 기전 없이 스코프 정책 + self
가드). 검증 2 실패(누수) → self 쓰기 가드 추가 후 재실측. 검증 1/3 실패 →
폴백 규칙 재독해(설계 오독).

## P-SM-1 판정 (2026-08-27, 격리 실측 — 3/3 PASS)

실측 스크립트: `scratchpad/p_sm1.py` (격리 임시 DB, forget.store 직접 호출).
1차 1/3 → 오독 발견 → 2차 3/3. **신규 기전 0줄, 규약만 제품화 확정.**

**오독·수리 (숫자와 함께 기록):** 1차에서 공유 원장·충돌 공존이 B 검색 0건으로
FAIL. 원인은 스코프 부재가 아니라 **검색 payload에 `scope_fallback=True`
미지정** — 폴백은 명시적으로 켜야 작동한다(`search_memories`의
`_scope_fallback_enabled(payload)` 게이트). 기본 격리가 안전 기본값이다: self가
실수로 새지 않는다. 플래그를 켜니 3/3.

**확정 규약 (기전별):**
1. **공유 원장** = `app_id` 스코프 저장(user_id 없이) + 검색 시 `scope_fallback=True`.
2. **분리 self** = `user_id`(에이전트 소유자) + `layer=self` 저장. **user_id 소유
   경계는 scope_fallback을 켜도 뚫리지 않는다** — `_scope_fallback_eligible`이
   `memory_user != requested_user`면 거부. 즉 self 격리는 옵션이 아니라 구조적.
3. **충돌 공존** = `agent_id` 스탬프. 상충 판단이 공존·귀속(실측 출력:
   `[agent-a] Postgres` vs `[agent-b] SQLite` 동시 회수).

**위험 1(self 누수) 재평가:** 구조적으로 닫혀 있음(소유 user_id가 폴백을 막음).
남는 가드는 "self 쓰기 시 소유 user_id 누락 거부" — 실수 방지용 방어선이지
누수 통로는 아니다.

## 개정 1 (2026-08-28, 계약 테스트가 잡은 누수) — 결합 스코프 행은 공유 원장이 아니다

기관 승격(forget/grants.py) 중 계약 테스트 ⑥(self층 비서빙)이 실패로 누수를
적발: self층 행이 `app_id`를 함께 달고 있으면(결합 스코프), 소유 경계는
**폴백 경로만** 지키고 순수 `{app_id}` 검색의 **1차 매칭**에는 걸린다.
P-SM-1이 통과했던 이유는 검색 필터에 요청자 user_id가 있었기 때문이고,
그랜트 서빙처럼 무소유 검색을 하는 경로에서는 뚫린다. 스파이크는 결합
스코프 행이 원장에 없어 못 봤다.

**수리 규칙(규약 승격):** 그랜트가 여는 것은 무소유 행(user_id 없음)뿐 —
서빙 경로가 소유 행을 명시 배제한다(grants.serve의 user_id 배제 줄).
공유 원장의 정의 자체를 "app_id만"에서 **"app_id만 + user_id 부재"**로
명문화한다. 봉인: tests/test_grants.py 계약 7 (7/7, 전체 회귀 727 통과).

## 다음 손

- P-SM-1 격리 실측 스크립트 (격리 포트·전용 DB, pilot.py의 격리 전례 재사용).
- 통과 시: self 가드 + 공유/self 저장 규약을 self-harness 확장(`.pi/extensions/
  forget.ts`)에 배선 — before_agent_start가 공유 원장은 app 스코프로, self는
  소유 스코프로 라우팅.
- 제품 서사: "한 팀의 에이전트들이 공유 지식 위에서 각자 전문성·인격 유지"
  (B2B) — BM 개정안 L1(연속성 풀스택)에 편입 검토.
