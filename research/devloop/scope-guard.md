# 쓰기 시점 스코프 가드 — F4 재발 방지 설계 메모

2026-07-31. F4 정리(339건, 영수증 `~/.forget/migrations/f4-cleanup-20260731.json`)의
재발 방지책. devloop next_action "데모/실험 유입 경로에 가드" 집행.

## 사후 부검: F4는 왜 가능했나

세 가지 유입 모두 같은 구멍을 지났다 — **쓰기 경로에 스코프 검증이 전혀 없다.**

- `POST /mcp/{app_id}/http/{user_id}`(server.py:92)가 URL 그대로 스코프를 만들고,
  body의 `user_id`/`app_id`가 그것마저 덮는다(mcp.py `_openmemory_scope`).
- `store.add_memories`(store.py:3557)는 "엔티티 ID 하나 이상" 외엔 검증 없이
  임의의 (user_id, app_id) 쌍으로 INSERT — 새 풀이 조용히 태어난다.
- 데모 런북들(gtm/token-overhead.md:24, demoday-runbook.md 등)이 도그푸드 서버
  :8000을 그대로 가리킨다. `demo-corp×jiwoo.lee` 한 방이면 새 오염.
- doctor의 "scope clean"(cli.py `foreign_pools`)은 **사후 탐지**다. 예방이 없다.

## 설계 원칙

스코프 격리는 이 제품의 기능이다(유저 1호의 회사별 격리 요구). 따라서
"canonical 외 전부 금지"를 기본값으로 박으면 제품을 부순다. 가드는 **모드**다:

| 모드 | 동작 |
|---|---|
| `off` | 현행 유지 |
| `warn` (기본) | 쓰기는 통과. foreign이면 ①응답에 경고 문구 ②`metadata.scope_guard="foreign"` 스탬프 (정리를 1쿼리로) |
| `enforce` | foreign 쓰기를 400으로 거부, 처방 동봉 (allowlist 또는 전용 인스턴스 `FORGET_HOME`) |

- **canonical** = (`MEM1_MCP_DEFAULT_USER_ID` 또는 OS 유저명) × `forget` —
  doctor의 `foreign_pools`와 같은 정의를 **한 곳에서** 공유한다 (드리프트 방지).
- **allowlist**: `FORGET_ALLOWED_SCOPES="user:app,user2:app2"` (`*` 와일드카드 허용).
  allowlist에 든 풀은 warn/enforce 모두 통과하고 doctor도 foreign으로 안 센다.
- 환경변수: `FORGET_SCOPE_GUARD` (`FORGET_*`→`MEM1_*` 자동 매핑은 기존 관례).

## 삽입 지점

- **엔진 경계** `store.add_memories` — MCP·REST(/v1/memories) 전 경로의 수렴점.
  enforce 거부와 warn 스탬프는 여기서 (한 곳, 우회 불가).
- **MCP 경계** `add_memory`/`add_memories` 핸들러 — warn 모드의 인밴드 경고 문구는
  여기서 (에이전트가 읽는 표면. codex×codex 유령 풀 경고와 같은 관례).

## 도그푸드 적용 (릴리스 후, 별도 스텝)

이 코드가 릴리스에 실린 뒤 launchd plist에 `FORGET_SCOPE_GUARD=enforce` 추가
→ kickstart → doctor 녹색 확인. 데모는 전용 인스턴스
(`FORGET_HOME=~/demo-forget forget-server …`, 다른 포트)로 — 런북 4곳 수정 필요.

## 반증 가능한 예측 (devloop 관례)

가드 배포+enforce 후 90일간 도그푸드 DB에 새 foreign 풀 0건.
warn 기본값에서 신규 유저 설치의 doctor "scope clean"은 계속 녹색
(가드가 정상 경로를 막지 않는다는 증거).
