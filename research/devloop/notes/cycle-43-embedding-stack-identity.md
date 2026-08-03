# 사이클 43 — 이 인스턴스는 어떤 몸으로 돌고 있는가 (읽기 전용, $0)

2026-08-04 · 일반 사이클(43%10=3 · 43%5=3) · 관찰·측정 사이클
(영토 규약: `M forget/store.py` +231행 · `M forget/mcp.py` +5행 · `?? research/recall-eval/`
= 타 세션 활성 WIP, mtime 08-04 01:40/01:53 → **코드 사이클 금지**)

재현: `.venv/bin/python research/devloop/scripts/embedding_space_audit.py`
      `.venv/bin/python research/devloop/scripts/score_weight_replay.py 25`

## 왜 이것을 골랐나

양 채널 `next_actions`의 최우선은 P10(fetch-before-filter 처치)이나 코드 사이클이라 봉쇄.
최우선 **무-게이트·읽기 전용** 항목은 명시 등재된 P7 캐비앗 ②였다:

> "이 판정은 배포된 상태에서 겪은 것을 재는 것이지 재임베딩 벡터가 질의측과 같은 모델로
>  서빙되었는지는 확인하지 않았다(P7 처치 문면의 '서버 재시작' 실행 여부 미검증)"

이 질문은 P7보다 크다. LOOP.md 원칙 3은 "구성 스택을 **명시적으로 선언**"하라 요구하고,
그 계보가 "LME-V2 1차 풀런이 deterministic-128 폴백 위에서 돈 것을 사후에야 발견"이다.
스택이 선언되지 않으면 측정 자체가 무효 — 그렇다면 **선언이 틀렸을 때**는 무엇이 무효인가.

방법은 사이클 42의 ★★ 자기규율: 장부가 아니라 세계를 읽는다. 자기보고·health 응답을
믿지 않고 DB 바이트·파일 시각·제품 코드경로로 직접 확인했다.

## 1. P7 캐비앗 ② — 종결. 처치는 살아 있었다

`~/.forget/forget.sqlite3`(mode=ro) 라이브 3,149행을 제품의 `decode_embedding`으로 전수 디코드:

| 형식 | 차원 | 건수 | 비중 |
|---|---|---|---|
| JSON | 384 | 1,974 | 62.69% |
| MEB1 | 384 | 1,172 | 37.22% |
| MEB1 | 128 | 3 | **0.10%** |

- JSON-384 1,974건 = 재임베딩 영수증의 `reembedded: 1974`와 **정확히 일치**(영수증 대조 통과).
- 차원 전환 시각: 마지막 128d `2026-08-01T02:24:48Z` → 첫 384d `2026-08-01T02:24:59Z`.
  영수증 스탬프는 `022408`(=02:24:08Z). **전환이 재임베딩 창 안 11초 구간에서 일어났다.**
- 그 이후 08-03T16:38:08Z까지 **모든 쓰기가 384d**(1,172건), 128d 쓰기 0건.

→ "서버 재시작 실행 여부 미검증" 캐비앗 **닫힘**: 재시작(또는 임베더 승격)은 실제로 일어났고
시각이 재임베딩 시각과 정합한다. 질의측도 같은 `embed_text` 경로를 쓰므로 저장·질의가 같은
공간이다(bge-small은 `e5_prefixed`가 no-op이라 role 분기 없음). **사이클 41의 P7 판정
((a) 반증 / (b) 감소 미발생)은 유효한 기질 위에 서 있다** — 판정 자체는 바뀌지 않는다.

3건의 128d는 전환 직전 10초(02:24:38~48)에 들어온 세션 캡처이며, 전부 `user 1·assistant 2`
퇴화 세션(사이클 32가 분류한 복원가치≈0 에코)이다.

## 2. 선언 채널이 틀렸다 — health는 저장값, catalog만 실행값

같은 서버·같은 `proj_local`·같은 시각에 두 도구가 다른 답을 한다:

| 채널 | 임베딩 스택 |
|---|---|
| `get_provider_health` → `checks.embeddings` | `local` / **`deterministic-128`** |
| `get_provider_catalog` → `effective` | `fastembed` / **`BAAI/bge-small-en-v1.5`** |
| 저장 설정(`settings`) | `local` / `deterministic-128` |
| **DB 실측** | **384차원 99.90%** |

health가 보고한 3종(`rule-extractor` · `deterministic-128` · `lexical-v1`)은
`cli.py:340`의 `FALLBACK_STACK` 집합과 **정확히 일치**한다 — 즉 health는 폴백 스택을
선언한다. 코드는 이미 이 함정을 알고 있다:

```
forget/providers.py:925  def effective_embedding_stack(...):
    """What embed_text would actually use right now — not what settings store.
       Mirrors embed_text's resolution order so observers (doctor, catalog) can
       report the running truth."""
```
```
forget/provider_runtime.py:778-784
    # Effective stack may diverge from stored settings: semantic-by-default
    # silently upgrades an unconfigured "local" to fastembed when importable.
    # Doctor and any observer must see what actually runs, not what was stored
    # — the LME-V2 run-1 lesson, in the opposite direction.
    payload["effective"] = effective_embedding_stack(project_id)
```

**`effective_embedding_stack`의 호출처는 전 저장소에서 catalog 한 곳뿐이다.**
`provider_health_payload`(provider_runtime.py:894)는 `get_project_settings`만 읽는다.

원칙 3의 집행 도구가 원칙 3이 막으려던 실패를 재생산한다 — 부호만 반대다(폴백을 쓰면서
semantic이라 믿은 것이 LME-V2, semantic을 쓰면서 폴백이라 선언하는 것이 지금).

## 3. (핵심) semantic-by-default가 자기 짝인 가중치 재조정을 발동시키지 못한다

```
store.py:4747  def _semantic_embedding_active() -> bool:
                   provider = (os.getenv("MEM1_EMBEDDING_PROVIDER") or "").strip().lower()
                   return bool(provider) and provider not in {"local", "deterministic"}

store.py:4752  def _search_score_weights():
                   # The legacy 0.72/0.28 rule/vector split dates from the deterministic
                   # hash-bag fallback era, when the vector channel carried almost no
                   # meaning. With a real semantic model the vector becomes the stronger
                   # signal ... so rebalance toward it —
                   # but only when a semantic provider is actually active.
                   if _semantic_embedding_active():
                       return 0.45, 0.55
                   return 0.72, 0.28
```

`_semantic_embedding_active()`는 **환경변수**를 본다. 그런데 semantic-by-default
(providers.py:958, 2026-08-01 UX 결정 "users should not need to know these words")는
**환경변수 없이** 미설정 `local`을 fastembed로 승격한다. 두 코드가 "semantic이 켜졌는가"를
서로 다른 기준으로 판정한다.

**라이브 확정 증거**: catalog의 `resolution` 문자열이
`"auto-default (unconfigured + fastembed importable)"`이다. 이 분기는 `not env_choice`
일 때만 도달하므로, **서버 프로세스에서 `MEM1_EMBEDDING_PROVIDER`가 비어 있음이 확정**된다
(프로세스 env를 직접 읽지 않고 서버 자신의 응답으로 증명 — 샌드박스 무관).
따라서 라이브 가중치는 **(0.72 rule / 0.28 vector)** — 코드 주석이 "벡터 채널이 거의
의미를 못 싣던" 시절의 값이라 부르는 바로 그 split이다.

**설정을 아무것도 안 한 유저 = semantic-by-default의 수혜자만 이 벌점을 받는다.**
`MEM1_EMBEDDING_PROVIDER`를 명시한 유저는 0.55를 받는다. 기본값이 좋아질수록
가중치는 나빠지는 구조다.

### 대조 측정 (원칙 1 — 대조군 없는 숫자는 기록하지 않는다)

게임내성 지표(사이클 22 방법: 손수 관련성 라벨 배제, 랭크 역전·Kendall tau).
leave-one-out 프로브 25건(seed 43), 후보 풀 2,926행, 질의 = 기억 자기 텍스트[:300]
(`forget_turnrecall.py`가 보내는 `prompt[:300]`과 동형), 프로브 자신은 풀에서 제외:

| 지표 | 값 |
|---|---|
| top-1 변경 | **2/25 (8%)** |
| 평균 Kendall tau | **0.8829** (1.0=동일 순서) |
| 재순위 발생 | **16/25** |
| 평균 랭크 이동 | 0.41 위치 |

→ 미가중은 **실재하나 이 레짐에서 온건**하다. **정직 캐비앗(과소추정 방향)**: 프로브가
기억 자기 텍스트라 어휘 겹침이 높은 레짐이고, 거기서는 rule과 vector가 서로 동의하는
경향이 강하다. 두 채널이 가장 갈리는 것은 사이클 34·37이 보인 **주제 신호가 약한
generic startup 스트림**이므로 실제 격차는 이보다 클 수 있다. 이 표본으로 "8%"를
일반값으로 공표하지 않는다.

### F2와의 관계

F2(관련성)는 33+사이클 미해소이고 사이클 18이 지배 원인을 C1(phrase_bonus 무한 합산)으로
확정했다. phrase_bonus는 **rule 채널 안**에 있다. rule이 설계 의도(0.45)보다 **1.6배**
가중되어 있다면(0.72), C1의 발현 크기도 그만큼 구조적으로 증폭된다.
이것은 C1과 경쟁하는 가설이 아니라 **C1을 증폭하는 두 번째 독립 기전**이며,
43사이클 동안 어느 사이클도 지목하지 않았다. 단 본 사이클은 인과 기여도를 분리 측정하지
않았다 — 위 표는 가중치 단독 효과이지 F2 재발률에 대한 판정이 아니다.

## 4. 차원 불일치는 거부가 아니라 절단이다

```
memory_engine.py:774  def cosine_similarity(left, right):
                          size = min(len(left), len(right))   # ← 절단
```

`_batch_cosine_scores`(store.py:583)는 차원이 다른 행을 **제외**해 스칼라 경로로 넘기고,
스칼라 경로는 앞 128차원만 잘라 비교한다. 서로 무관한 두 공간의 앞부분을 비교하는 것이라
결과는 잡음이며, `(cos+1)/2` 재사상은 그 잡음을 **0.5 근방**에 놓는다.

제품 `cosine_similarity`로 실측(384d 실벡터 200개를 질의로 사용, seed 43):

| 쌍 | 평균 | 중앙값 | 최소 | 최대 | ≥ 게이트 0.45 |
|---|---|---|---|---|---|
| 교차공간 128d×384d (600쌍) | 0.5082 | 0.5046 | **0.4658** | 0.5836 | **600/600 (100%)** |
| 대조군 동일공간 384d (200쌍) | 0.9231 | 0.9587 | 0.7497 | 0.9971 | 200/200 (100%) |

교차공간 비교의 **최솟값(0.4658)조차 게이트(0.45)를 넘는다** — 차원이 어긋난 행은
의미 점수로는 결코 걸러질 수 없다. 오늘의 영향은 3행(0.10%)이라 실질 피해는 미미하지만
**기전은 일반적이다**: 임베더를 바꾸고 재임베딩하지 않으면 스토어 전체가 이 상태가 되고,
그때 회상은 조용히 잡음을 반환하면서 게이트는 전부 통과시킨다. 원칙 3이 재임베딩 영수증을
사람 게이트로 요구하는 이유가 코드 수준에서 확인된 셈이다.

## 처분

- 처치는 전부 **코드 사이클**이라 이번 사이클 금지(영토 규약). **P11 선등록**으로 갈음.
- 새 유형 등록 없음 — 귀납 원칙 + 거버넌스 동결(회고 25) 준수. 미분류 관측 1건 기재.
- 게이트 불요 항목(P11 처치 3종)은 영토 규약이 풀리는 즉시 착수 대상.
  **P10이 여전히 우선**이다(회상 채널이 지금 꺼져 있음 > 가중치가 기울어 있음).

## 캐비앗 (정직)

1. 가중치 측정은 leave-one-out 자기텍스트 레짐 1종뿐 — generic startup 레짐 미측정(과소추정 방향).
2. 서버 프로세스 env를 직접 읽지 못했다(샌드박스). 대신 서버 자신의 `resolution` 문자열로
   추론했다 — 그 분기는 `not env_choice`에서만 도달하므로 논리적으로 동치이나, 직접 관측은 아니다.
3. 3건의 128d 행이 실제 회상에서 무엇을 했는지는 추적하지 않았다(점수 기전만 실측).
4. 이 사이클은 제품 코드를 한 줄도 바꾸지 않았다. `268 passed`는 내 변경의 회귀 감시가 아니라
   타 세션 WIP(+236행) 위의 환경 green 확인이다 — 사이클 40~42와 동일 조건.
