# cycle-197 — 몸 재교정 3차: 처음으로 «승인된 몸 교체»를 재교정한다

**계기.** c48 파트 Body가 «재교정 필요»를 인쇄한다 — 변경 3키
(`checks_embedding` · `effective_embedding` · `store_vec`) + 미채취 1키
(`installed_vs_repo`). baseline은 c111본(2026-08-13: bge-small-en-v1.5 · 384d ·
checks=deterministic-128 폴백). c196이 이연했고(사유: ㉶+㉬ 병합 기한 벌칙)
c197 1순위 재지명 — 2사이클 연속 이연 금지 권고 이행.

## ① 왜 바뀐 몸인가 — 1차 증거 (재교정 순서 규약 1항)

**임베딩 전환 = 사람 게이트를 거친 승인 집행이다.** 계보상 처음이다 —
c95·c111의 재교정 사유는 둘 다 **무공지 배포**였다.

- **승인 증거** (forget 능동 회상, 기억 `74adee62` · trust=**green** · source=**user**):
  다국어 임베딩 전환 + 앵커 소급 실DB 집행, 2026-08-23 저녁, **정훈 승인 2단계**
  («다국어 임베딩 전환을 승인할게» → 판정 보고 후 «적용하자»). 생존 기억 **6,119건**을
  앵커 소급(6,070건 유도, 결합 입력 2,323건)과 함께
  `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`(**768차원**)로 재임베딩.
- **재임베딩 영수증** (원칙 3 요건): 커밋 **5c8760f** (2026-08-23 18:49:07 KST,
  *«게이트 집행: 앵커 소급 + 다국어 임베딩 전환 — 실DB 적용 (정훈 승인)»*) —
  `scripts/migrate_embeddings_v2.py` + `research/eval/mig/eval_before_mig.json` ·
  `eval_after_mig.json`(전/후 평가 913행씩) + `research/eval/echo_pairs.jsonl`.
- **동반 재보정** (기억 `0eef022b`, green): 훅 상수 — turnrecall `SCORE_THRESHOLD`
  0.45→**0.33**(새 점수 대역: 관련 0.40~0.46 · 무관 바닥 0.28), capture
  `SEMANTIC_THETA` **0.613**. 게이트 상수 의존 계기가 참조할 것.
- `checks_embedding`(저장 설정의 거울)이 폴백 이름(deterministic-128)에서 mpnet으로
  바뀐 것도 같은 사건이다 — 저장 설정이 명시됐고, c111 노트가 지적한
  «checks↔effective 불일치» 자체가 해소됐다.

**`installed_vs_repo` 미채취의 원인 = 배포 방식 변화다.**
`~/.forget/venv/lib/python3.14/site-packages/`에 `forget/` 복사본이 없다 —
`_editable_impl_forget_ai.pth`가 있고, `forget_ai-0.4.0.dist-info/direct_url.json`이
`{"dir_info": {"editable": true}, "url": "file:///…/내-프롬프트를-공유하기-싫어"}`로
**이 워크트리 자체**를 가리킨다. 구 프로브(최상위 `.py` 해시 대조)는 대상 디렉토리가
없어 UNKNOWN을 낸다. 함의 둘:

1. **디스크 기준 «설치본 vs 저장소본» 구분이 구조적으로 소멸했다** — 설치본이 곧
   워크트리다. 무공지 배포 감시의 축이 «파일 해시 편차»에서 **«프로세스 적재 시점
   편차»**로 이동한다: 적재된 데몬은 재기동 전까지 구 모듈을 든다(A-192.1 «데몬 배포
   편차»가 그 실측 — c192에서 pid 48382가 디스크에 없는 코드로 죽었다).
2. editable **대상 경로 자체가 지문이다** — 대상이 다른 체크아웃으로 바뀌거나
   복사본 설치로 회귀하면 그것이 몸 교체다.

## ② 게이트 상수 의존 계기의 재교정 표시 (순서 규약 2항)

**oracle replay 계열 · gate_audit · score_weight_\* — 구몸(384d bge-small-en)
공간에서 잰 상수·거리·라벨을 신몸(768d mpnet) 산출과 산술 비교하는 것 금지.**
같은 날 스토어에 남은 교훈(기억 `b0239fc3`, green): *«임베딩 공간을 갈면 그 공간이
만든 라벨로 채점하는 모든 자가 순환으로 무효가 된다 — 자를 먼저 의심할 것.»*
**신몸 기준선 런 전까지 이 계열 판정 없음.** baseline 일치 복귀는 지문 대조의
재개이지 구몸 상수의 복권이 아니다(c111 문면 승계). 백로그 #8(oracle replay)
공전의 해제는 신몸 기준선 런이 선결이며, 그 런은 후속 사이클 몫이다.

## ③ 프로브 확장 — editable 몸을 «미지»가 아니라 «다른 종류의 몸»으로 채취

`_installed_vs_repo`에 editable 분기를 추가한다: 복사본 디렉토리가 없고
`direct_url.json`이 editable을 선언하면 `editable:<대상 경로>`를 지문 값으로 반환.
근거: 미채취를 영구 «판정 불가»로 두면 **아는 것을 모름으로 접는** 것이고(관측 30의
거울상 — 조용한 흡수의 반대쪽 병), editable 대상 경로는 위 2의 이유로 지문 자격이
있다. 파싱은 순수 헬퍼 `editable_target()`로 갈라 회귀 테스트를 단다
(`tests/test_devloop_body_fingerprint.py`). 채취 실패 시 여전히 UNKNOWN —
«모르는 것을 일치로 보고하지 않는다» 성질은 불변.

## ④ 갱신 순서 (규약 3항)

이 노트 → `body-fingerprint.json` 갱신(`_recorded_cycle: 197` — 커밋이 감사 흔적)
→ `part_body()` 재실행으로 «일치» 확인. 갱신 후에도 위 ②의 판정 금지는
**신몸 기준선 런까지 유지된다.**
