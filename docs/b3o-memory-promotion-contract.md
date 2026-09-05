# B3O 기억 레인 제품 승격 계약 — 초안 v0 (forget 측)

2026-08-29, gpt-live 부분 수용 결정의 HOLD 해제 조건 5개에 대한 forget 측
제안. 상태: **초안 — 합의 원장 왕복 + 정훈 게이트(기존 경계 «로컬 연결은
테스트용» 해제) 전까지 효력 없음.** B3O 파일은 건드리지 않는다.

## gpt-live 요구 조건 ↔ forget 측 답

| 조건 | forget 측 제공 |
|---|---|
| ①전용 B3O principal | `b3o-desktop` principal의 자격-결합 키를 소유자가 발급 (api_keys.agent_principal — 사칭 구조 차단). 워크스페이스 구분은 principal이 아니라 scope_app으로: `b3o.<workspace_id>` |
| ②main-process 전용 credential broker | 키는 환경/키체인 → Electron main만 보유. forget은 키를 HTTP Bearer로만 받으므로 renderer 비노출은 B3O 내부 불변식 — forget 측 협력: 키 회전 API(구키 유예 창) 제공 가능, v1은 수동 회전 |
| ③renderer 비노출 | 상동 (B3O 영토). forget 측 보조: 영수증·그랜트 조회는 읽기 전용 엔드포인트로 분리돼 있어 조회용 저권한 키 발급 가능(scopes) |
| ④native 사람 승인 | 쓰기 경로는 forget 측도 이중 게이트: 서버가 `human_approved: true` 필드를 요구하는 쓰기 모드(신규, 소액 작업) + 에코 차단기 통과. B3O의 native 승인 UI가 이 필드의 유일한 공급자 |
| ⑤영수증 감사 UX | 이미 있는 API로 충분: `GET /v1/receipts/access/`(목록) + `POST /v1/receipts/verify/`(3중 검증) + `GET /v1/receipts/public_key/`(자가 검증). UX는 B3O 영토 |

## 기본값 제안 (협상 대상)

- 그랜트 기본: quota 명시 필수 · deny_pii 4종 전부 · answer_mode=passage ·
  만료 필수(expires_at) — 무기한 그랜트 금지.
- scope_app 규약: `b3o.<workspace_id>` — 워크스페이스 간 교차 서빙은
  그랜트 단위로만 (오늘 봉쇄한 교차-앱 누수 원칙의 연장).
- 회수: 소유자 즉시 회수(`/revoke`) + B3O 설정 화면은 조회 전용 투영.
- 감사: 거절 포함 전 서빙이 영수증 — B3O가 주기 폴링으로 로컬 투영.

## 게이트 처분 (2026-08-29 정훈: «테스트용 경계 해제하자»)

1. 경계 해제 — **승인** (합의 원장 decision + 소유자 확인 영수증).
2. `b3o-desktop` 키 — **발급됨** (`~/.forget/keys/b3o-desktop.key`, 자격 결합
   principal=b3o-desktop). B3O 진입은 credential broker(B3O 영토)가 환경
   변수로 나른다 — 제안 명: `FORGET_B3O_TOKEN`. renderer 비노출은 B3O 불변식.
3. 쓰기 게이트 — **구현·라이브** (`/v1/memories/` b3o.* 스코프는
   human_approved=true 명시 필수, 참-유사값 불허 — 계약 테스트 5종,
   에코 차단기는 add 경로 상주). 813 passed.

계약 상태: forget 측 의무 전부 이행 — gpt-live의 조항별 검토·broker/UI
착수만 남음 (그쪽 페이스대로, 비차단).
