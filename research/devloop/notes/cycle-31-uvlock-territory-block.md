# 사이클 31 — uv.lock 영토블록 재평가 (audit-30 권고3 집행)

일시: 2026-08-03 · 모드: 일반 사이클(N=31, N%5=1·N%10=1) · 코드사이클 금지(영토 규약)
선택 근거: audit-30 권고3 + task_state next_actions[2] — "untracked uv.lock 영토블록 9사이클
재평가, 코드 사이클 영구봉쇄 해소 검토(.gitignore/커밋 결정은 정훈 확인 가능)". 이는
audit-30이 지목한 세 '값싼 언블록' 중 **유일하게 loop-self 실행 가능**한 것(나머지 둘 —
self-loop task_id 분리, P8 훅 배선 — 은 protocol 변경/정훈 게이트).

## 필드노트 (Sol 규약)

**증상.** `git status`가 `?? uv.lock` 한 줄을 상시 반환하고, 절차 2의 영토 규약
("devloop 외의 미커밋 변경이 있으면 코드 사이클 금지")이 매 사이클 발동해 코드 사이클을
봉쇄한다. 이 단일 파일이 metrics 첫 언급(사이클 21) 이래 지금까지 코드 사이클을 영구
차단했고, audit-30이 지적한 "사이클 16 이후 13사이클 무-출하"의 **구조적 기전**이다.

**기대 동작.** 영토 규약의 *의도*는 병행 세션(연구 포크 vs 실행 세션, forget-session-division)의
**미커밋 작업(WIP)**을 밟지 않는 것이다. 규약은 "미커밋 foreign 파일 존재"를 "병행 세션이
활성"의 프록시로 쓴다. 정적 생성 아티팩트는 그 프록시의 오탐이어야 하지 않는다.

**수용 기준.** 정적 빌드 아티팩트(누가 편집 중인 WIP가 아닌, 도구가 결정론적으로 생성하는
파일)는 코드 사이클을 봉쇄하지 않는다. 구체 판정: uv.lock이 WIP인지 정적 아티팩트인지를
증거로 가른다.

## 증거 — uv.lock은 WIP가 아니라 정적 생성 아티팩트

| 사실 | 값 | 출처 |
|---|---|---|
| tracked 이력 | 없음 (`git log -- uv.lock` 공집합) | git |
| .gitignore 포함 | 아님 (`git check-ignore uv.lock` → NOT ignored) | git |
| mtime | 2026-08-01 13:06, 이후 2일 불변 | stat |
| metrics 첫 언급 | 사이클 21 | metrics.jsonl |
| 파일 성격 | 유효 uv 락파일(version=1, revision=3, requires-python>=3.11, 1212행) | head |
| 프로젝트 동기 | lock 내 `name = "forget-ai"` (line 300) = pyproject.toml name과 일치 | grep |

→ 편집 중인 병행 세션 WIP의 특징(최근 mtime·잦은 변동·미완결)이 전무. **2일 불변·도구
생성·프로젝트와 동기**된 정적 아티팩트다. 영토 규약이 이것을 WIP로 오탐해 코드 사이클을
영구 봉쇄 중.

**재귀속:** audit-30의 "13사이클 무-출하"는 "루프가 마찰을 회피 중"이 아니라(또는 그것에
더해) **단일 정적 아티팩트가 WIP-감지 휴리스틱을 매 사이클 오탐**시켜 온 구조적 봉쇄로
설명된다. 이 재귀속은 audit-30의 인과 진단을 정정·보강한다(감사 지표가 회피로만 읽었던 것에
구조적 대안 원인 제시).

## 처분 판단 (정훈 게이트) — 결정 레디

프로젝트는 **배포형 애플리케이션/패키지**다: pyproject.toml에 `name = "forget-ai"`,
`build-backend = "hatchling.build"`, `packages = ["forget"]`, tracked. uv 표준 관행은
**애플리케이션은 uv.lock을 커밋**(재현 가능한 의존성 해상), 라이브러리는 gitignore.
→ **권고 처분: commit uv.lock.**

근거·안전:
- .gitignore(tracked, Aug 2)는 큐레이팅된 정책(바이트코드·venv·DB·사적 데이터·세션 스크래치)이며
  **락파일 항목이 없다** — uv.lock 누락은 정책이 아니라 누락(오버사이트).
- 사적 데이터 아님: 안전검사 통과 — 비-PyPI 인덱스 URL 0건, 크레덴셜/토큰 0건(모든 URL
  pypi.org/files.pythonhosted.org).
- 커밋 시 코드 사이클 영구봉쇄가 **일회 해소**된다(모든 향후 사이클에 대해). audit-30의
  최고 레버리지 단일 언블록.
- 커밋 전 확인 권고: `uv lock --check` 통과(pyproject와 동기 확인).

대안(비권고): .gitignore에 `uv.lock` 추가 — 앱에 비표준(의존성 재현 불가)이고 봉쇄만 해소.
채택 시에도 F6 전례상 정훈 승인 필요.

**왜 이번 사이클에 직접 커밋/gitignore하지 않는가:**
1. 영토 규약상 이 사이클은 코드사이클 금지(foreign untracked 존재) — tracked-file 정책
   변경은 자기모순적으로 그 규약이 막는 행위.
2. **F6 전례**: 사이클 11 감사가 55709c1의 "feedback/을 .gitignore에 추가"를 amendment-5 A2
   위반의 **미승인 선적용**으로 적발. tracked-file 정책 무단변경은 정확히 그 안티패턴.
3. audit-30이 처분을 "정훈 확인 가능"으로 명시 유보.

## 회고 35 회부 (거버넌스 동결·회고25 준수, 이번 사이클 미적용)

절차 2 영토 규약에 **카브아웃 제안**: "정적 생성 아티팩트(uv.lock 등 도구 결정론 생성·
장기 mtime 불변·미tracked)는 WIP 프록시의 오탐이므로 코드 사이클을 봉쇄하지 않는다"
— 단, foreign 파일을 무단 커밋/삭제하지 않는 비파괴 원칙은 유지. 이는 절차서(cycle-prompt.md)
개정이라 회고 사이클이 amendments/에 제안하고 정훈 승인 필요.

## 산출
- 이 노트.
- frictions.md에 미분류 관측 추가(유형 등록은 거버넌스 동결상 회고/정훈 게이트).
- 검증: pytest 268 passed(회귀 green). 제품 코드·tracked 파일 정책 무변경.
