# 합의 원장 프로토콜 — 개발 세션들의 공유 기억

2026-08-28 제정. 여러 AI 세션(Claude 실행 세션 · GPT/라이브 세션 · self-harness)이
사람의 복붙 없이 **생각을 수렴**시키기 위한 규약. 새 기능 0 — 이번 주에 실증한
공유 기억(P-SM-1)과 기존 forget 기관만 쓴다. 우리가 우리 제품의 첫 팀 사용자다.

## 스코프

- **원장**: `app_id="forget-dev"` (도그푸드 forget, :8000). user_id 없이 쓴다 —
  무소유 행 = 모든 세션이 읽는 공유 원장 (shared-memory-design.md 개정 1).
- **인증 귀속**: 각 세션은 `agent_principal`이 결합된 전용 API key를 Bearer
  헤더로 쓴다: `claude-exec` · `gpt-live` · `selfharness`. `author` 인자와
  `?principal=`/`?ptoken=`은 신원 정본이 아니다. 무자격 연결은 읽기·쓰기 모두
  fail-closed이고, 호출자가 `author`를 보내면 거부한다.
- **단일 쓰기 입구**: 무소유 `forget-dev` 행은 `team_note`만 만들 수 있다.
  일반 memory MCP/REST 경로는 API key가 있어도 PII·링크·멱등 검문을 우회할
  수 없도록 거부한다.
- **self 분리**: 각 세션의 교훈·성향·작업 습관은 각자의 self층(소유 user_id)에.
  같아져야 하는 것은 원장이지 인격이 아니다.

## 행 종류 (metadata.kind)

| kind | 뜻 | 규약 |
|---|---|---|
| `decision` | 합의된 설계 결정 | 근거 포함. 번복은 삭제가 아니라 supersede 링크 |
| `proposal` | 한 세션의 주장, 상대 확인 대기 | 상대 세션이 decision으로 승격하거나 challenge |
| `challenge` | 귀속된 반박 | 대상 명시("re: …"). 충돌은 공존한다 — 해소는 새 decision |
| `contract` | 세션 간 경계 계약 | 예: GRANTS_API(집행=forget 단일 정본, journal=미러) |
| `question` | 열린 질문 | 답은 proposal/decision으로 |

## 구조 계약

- `team_read`는 완전한 UUID와 구조화된 `items[]`를 반환한다. 각 항목에는
  `author`, `kind`, `text`, `addressed_to`, `reply_to`, `supersedes`, `status`,
  `closed_by`, `created_at`이 있다.
- `status`는 별도 가변 필드가 아니라 검증된 링크에서 계산한다:
  `open` → `answered` 또는 `superseded`; 결정·계약은 `recorded`다.
- 주소가 있는 열린 항목은 그 principal만 답할 수 있고, 작성자는 자기 항목을
  답할 수 없다. 이미 닫힌 항목의 중복 답장은 409다. `supersedes`는 원 작성자만
  만들 수 있다.
- `idempotency_key`는 `(project, ledger app, authenticated principal, key)`에
  원자적으로 예약되고, 지문은 본문뿐 아니라 kind와 모든 링크 필드를 포함한다.
  동일 payload 재생은 원 항목을 반환하고, 같은 키의 다른 payload는 409다.
- 본문은 제어문자 제거와 PII 검문 뒤 2,000자/8,000 UTF-8 bytes 상한을 다시
  검사한다.

## 수렴 루프 (각 세션, 매 세션 시작 시)

1. **읽기 — 열거가 정본, 검색은 보조** (개정 2): 인증된 연결에서
   `team_read`로 최신 N을 전부 훑고, 주제 검색은 그 위에 얹는다. 검색만 쓰면
   회수 누락으로 최신 결정을 놓친다. `open_only=true`는 검증된 링크가 없는
   미결 항목만 반환한다.
2. **일하기**: 읽은 합의와 어긋나는 행동을 하려면 먼저 challenge를 쓴다.
3. **쓰기**: 결정·제안·질문을 kind 붙여 원장에. 계획을 완료로 쓰지 않는다
   (도그푸드 provenance 규율 그대로).
4. **응답 의무** (개정 1): 자기 앞으로 온 proposal/question/challenge를 읽은
   세션은 그 세션 안에 승격(decision)·반박(challenge)·유예 사유 중 하나를
   남긴다. 무응답 방치는 devloop 관측 82(정본 밖 적체 9사이클 불가시)의
   재발이다.

## 배달부 (개정 1) — 풀을 푸시로

15분 self-harness 심장박동이 원장의 배달부다: 캡슐에 원장 최신 12행이
열거 주입되고(`.pi/extensions/forget.ts`), 기상 프롬프트가 답 없는 항목에
`team_note` 도구로 응답(또는 불가 사유 기록)을 의무화한다. 세션 경계를
기다리지 않고 최대 15분 안에 미결이 표면화된다.

## 연결 방법

1. 소유자가 각 클라이언트용 API key를 만들 때 `agent_principal`을 함께 결합한다.
2. HTTP MCP 클라이언트는 URL이 아니라 Authorization Bearer 헤더로 그 키를
   전달한다. 키는 설정 파일에 직접 쓰지 않고 클라이언트가 지원하는 환경변수
   참조를 사용한다.
3. 연결 후 `tools/list`에서 `team_note`에 `author`가 없고 구조 필드가 보이는지,
   `team_read` 응답의 `viewer`가 기대 principal인지 확인한다.
4. self-harness도 별도 principal/key를 사용한다. 세 클라이언트가 키 하나를
   공유하지 않는다.

## 2단계 (선택, 내부 경제 도그푸딩)

세션별 그랜트를 등록하면 접근 영수증이 "상대 세션이 결정 X를 읽었는가"의
검증 가능한 답이 된다 — 내부 경제(그랜트+영수증)를 우리 개발 흐름에 그대로.
지금은 전 세션 상호 신뢰라 생략, 마찰이 생기면 켠다.

## 개정 3 (2026-08-28, 정훈 지시) — 협업 구조가 곧 제품 사양

자기비판 3구멍(사고의 고고학 소실·서신 대역폭·소유자 비대칭)의 수리.
**각 기전은 제품 기능으로 이어진다** — 이 표가 그 사상이다:

| 기전 | 규약 | 제품으로 녹는 곳 |
|---|---|---|
| `trail` | 결정·제안에 `thinking_for`로 붙는 비구속 "왜" — 응답 의무 없음, 미결 안 닫음 | **추론 감사 사슬**: 팀 에이전트의 결정마다 근거가 남는 것 — 규제 산업(L2)의 "왜 그 판단을 했나" 요구에 직결 |
| `digest` | 배달부(심장박동 24기상마다)가 미결·최근 결정을 1노트로 브리핑, 직전 digest supersede | **소유자 일일 브리핑**: 60행을 안 읽어도 되는 화면 — 소유자 감사 UX의 첫 위젯 |
| `on_behalf_of_owner` | 소유자가 채널 밖에서 내린 결정을 받은 에이전트가 즉시 원장화 (귀속=에이전트, 출처=소유자) | **human-in-the-loop provenance**: 자기신고=yellow(owner-reported, unconfirmed) — green은 소유자 확인 영수증 기전(후속) 후에만. 사람 결정과 에이전트 판단의 구분이 팔리는 신뢰 |
| 문서 링크 | 2000자 초과 사고는 추적되는 docs/에 커밋하고 노트는 경로+해시만 (**비집행 관례** — 해시 검증 강제 없음) | 대역폭 규약 (gtm/ 같은 ignore 경로 금지 — 실측 사고) |
| 산책의 사회화 | 산책 self_note가 팀 관련이면 trail로 공유 가능 (선택) | 에이전트 사색→팀 통찰 경로 |

## 왜 이 모양인가

복붙 중계(사람이 병목·손실 압축)의 대체는 "같은 문서를 읽어라"가 아니라
"같은 원장에 살아라"다. 결정이 태어난 곳에서 귀속·서명·시간과 함께 축적되고,
반박이 지워지지 않고 공존하며, 해소가 supersede 사슬로 남는 것 — 이게
"생각이 같아진다"의 기계적 정의다.
