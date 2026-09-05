# Pass 1 설계 문서 — 수렴 로드맵 · 소유자 감사 UX · consult 계약 초안

2026-08-28, claude-exec. Pass1 소유권 규약에 따른 신규 단독 파일 —
공유 스펙(MEMORY_ECONOMY.md·GRANTS_API.md 등)은 증거 인계 전 불가침.
consult 절은 **계약 초안**이며 동결은 gpt-live 리뷰 후(Pass2 착수 조건).

## 1. 수렴 로드맵 (원장 a611d2b3 + 확정 decision의 기록본)

**합의**: thin live UI slice가 Tranche 4(vault)보다 먼저 — 통합 위험 조기 노출
+ 실물 자산 창출. 단 권한 불확대(비밀은 브로커 경유 env·렌더러 불반입,
자격 결합 serve만, 공개 배포·패키징 금지, pre-E2EE 배너).

| Pass | gpt-live | claude-exec | 게이트 |
|---|---|---|---|
| P0 | Bot 레포 WIP 기록 | forget 좁은 커밋 4건 ✓ (3174ca0…b01c221) | 기록 영수증 |
| 1 | thin live slice (App.tsx·composition·통합테스트) | 본 문서 + 데모 런북 ✓ | **L1**: 실프로바이더 1회전 · Forget 캡슐 주입 · 검증된 접근 미러 · **kill/reopen 복구(중복 효과 0)** · 자격 카나리아 UI/journal/log/export 부재 · 전체 테스트 그린 |
| 2 | Tranche 4 vault + macOS Keychain | consult endpoint (동결 계약 하) | **L2**: vault 왕복·잠금/거부/부재/회전/삭제·크래시 마이그레이션/롤백 → UI가 env 고지에서 네이티브 자격으로 전환 |
| 후순 | Tranche 5·sync·자동화 | — | 빌링·Paddle은 **최후** (정훈 결정 2300011f) |

## 2. 소유자 감사 UX 명세 (Pass1은 명세만 — 구현은 gpt-live 로드맵 (5))

목적: "허락한 만큼인지 **확인할 수 있게**"(창업자 원문)의 화면화.
서버 재료는 전부 존재: 그랜트 목록(사용량·모드), 접근 영수증(허용·거부·
가림 수·서명), 공개키. UX 원칙 4:

1. **원장 우선**: 기본 화면 = 시간역순 접근 영수증 스트림. 각 행에
   누가(grantee) · 무엇을(scope, 검색 지문) · 결과(served/redactions/거부
   사유) · 서명 상태(✓ = Ed25519+HMAC 검증).
2. **거부도 1급 시민**: allowed=false 행을 숨기지 않는다 — "안 나간 것"이
   신뢰의 절반이다.
3. **그랜트 = 계약 카드**: 각 그랜트를 카드로(대상·범위·PII 정책·쿼터
   게이지·answer_mode), 카드에서 즉시 폐기(revoke) — 폐기는 되묻기 1회.
4. **검증 가능성 노출**: 화면 하단에 공개키 지문 + "이 원장은 서버 없이도
   검증됩니다" 링크(검증 절차 문서). 신뢰를 주장하지 말고 검증 경로를 준다.

비목표(Pass1·2 공통): 원격 접근, 알림 푸시, 과금 표시.

## 3. consult 계약 초안 v0 — verdict / summary (동결 대상)

배경: 외부 판매의 정보 위계는 `pointer < verdict < summary < passage`.
pointer·passage는 기존 serve가 제공. consult는 가운데 두 단을 별도 문으로.

### 3.1 Endpoint (초안)

```
POST /v1/memories/consult/
{ "grantee": <생략 — 인증 principal에서 유도, 인자 거부>,
  "scope_app": "...", "query": "...",
  "mode": "verdict" | "summary",
  "request_id": "..." (멱등, serve와 동일 규약) }
→ { "allowed": bool, "reason": str,
    "answer": {"mode": "verdict", "text": "yes|no|unknown + 한 문장 근거"}
           | {"mode": "summary", "text": "≤400자 요약"},
    "receipt": { ...접근 영수증 공통 필드...,
                 "mode": "verdict|summary",
                 "answer_commitment": HMAC(key, "answer:"+text) } }
```

### 3.2 불변식 (serve와 공유 + 신규 3)

- 기존 전부 승계: 인증 principal 유도(호출자 선택 불가) · 원자 입장 ·
  영수증 선기록 · 무소유 행만 · 출구 검문(요약 생성 **후** 재검문 — 생성이
  PII를 재조립할 수 있으므로 검문은 항상 마지막) · request_id 멱등.
- **신규 ① 판정은 로컬 전용**: verdict/summary 생성 LLM은 소유자 기기의
  로컬 모델만(E2EE 테제 — 기억이 판정을 위해 외부로 나가면 전부 무효).
  로컬 모델 부재 시 consult는 503으로 정직하게 거부(대체 경로 없음).
- **신규 ② answer_commitment**: 나간 답의 키드 지문이 영수증에 남는다 —
  분쟁 시 "그 답이 이 답이었다"를 소유자가 증명.
- **신규 ③ 모드별 쿼터 가중 훅**: 그랜트에 `mode_weights` 예약 필드
  (기본 {passage:1, summary:1, verdict:1}) — 과금 아님, 유출 면적 차등의
  자리만 판다. 값 설계는 빌링 단계(최후)로 이연.

### 3.3 계약 동결 v1 (2026-08-28 — gpt-live 리뷰 반영, Pass2 구현 기준)

열린 질문 3건 전부 gpt-live 판정 수용:

1. **summary 상한**: 400자 폐기 → **≤4096 UTF-8 bytes AND ≤1200 유니코드
   스칼라** 이중 상한 (한국어·절차 지식 유용성 유지, passage 미만 보장).
2. **verdict는 인식론 3치 유지** (yes|no|unknown). 거부는 `allowed=false` +
   reason — 권한 결과와 인식 결과를 한 축에 섞지 않는다.
3. **영수증은 access_receipts 합류**: `mode` 컬럼 + CHECK 제약, verdict/
   summary에만 nullable `answer_commitment`.

**수정 조항 (gpt-live amendment, 수용 — 초안보다 강함):**

- `answer_commitment` = HMAC('answer:'+text)가 아니라 **도메인 분리 canonical
  결합**: `HMAC(key, canonical("consult-answer-v1", receipt_id, grantee,
  scope_app, mode, request_id, query_commitment, sha256(answer_bytes)))` —
  다른 문맥의 커밋먼트를 재생·이식할 수 없다.
- **`source_set_commitment` 추가**: 파생 답이 어느 증거 집합에서 나왔는지
  결합 — `HMAC(key, canonical("consult-sources-v1", receipt_id,
  sorted(served_memory_ids)))`. "그 답이 그 증거에서 나왔다"까지 소유자가
  검증 가능.

이 절이 동결 계약이다 — Pass2의 claude-exec 구현은 이 문면과 다르면 안 되고,
변경은 원장 decision으로만.
