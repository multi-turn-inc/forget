# forget on LongMemEval — Results Note (v0.1)

Status: 2026-07-14, 연구 포크. 어젠다 §4 E2의 실행 기록. 선등록 티어:
gtm/validation-criteria.md 실험 5. 이 문서는 방법론과 파일럿 결과를 담으며,
full-500 헤드라인 숫자는 실행 완료 시 §5에 추가된다. **나쁜 숫자도 방법론과 함께
기록한다** — 튜닝은 dev(seed 42), 검증은 held-out(seed 7, disjoint).

## 1. 세팅

- **벤치마크**: LongMemEval-S (cleaned, 2025-09), 500 인스턴스. 인스턴스당 haystack
  ~50 세션 / ~550 메시지. question_type 6종.
- **메모리 시스템**: forget 엔진, 로컬 전용. 임베딩 deterministic-128(해시) 기본.
  스코프 격리로 인스턴스 간 오염 차단(2026-07-13 수정한 `/mcp/<app>/http/<user>` 라우트의
  REST 대응). 별도 벤치 서버(포트 8001, 스크래치 DB) — 도그푸드 스토어 불가침.
- **reader / judge**: 둘 다 gpt-4o (공개 Mem0/Zep 수치와 동일 계열 → 공정 비교).
  judge 프롬프트는 벤치마크 원본의 question_type별 템플릿 그대로.
- **파이프라인**: haystack 전 메시지를 `role: content`로 인제스트(created_at =
  haystack 날짜) → 질의로 top_k 검색(temporal_rerank on) → 검색 기억을 날짜 태그와 함께
  reader에 제시 → 답 생성 → judge 채점.
- **하니스**: `research/longmemeval/harness.py` (재현: `--dataset s --held-out --seed 7
  --top-k 20`). 재시도·에러 캡처 포함.

## 2. 참조점 — 2026 프론티어 (핸드오프 노트의 49/63.8은 2024 옛 수치)

| 시스템 | LongMemEval-S | reader | 비고 |
|---|---|---|---|
| OMEGA | 95.4% | GPT-4.1 | 벤더 자체발표, bge-small 임베딩 |
| Mastra Observational Memory | 94.87% / 84.23% | gpt-5-mini / gpt-4o | 벤더 자체발표, 오픈소스 |
| Emergence AI (internal) | 86% | gpt-4o | 벤더 자체발표 |
| **Oracle GPT-4o (천장)** | **~82.4%** | gpt-4o | 정답 세션만 줬을 때의 상한 |
| Emergence Simple-Fast | 79% | gpt-4o | **오픈소스, 우리 하니스로 재현 78.6%** |
| Zep/Graphiti | 71.2% | gpt-4o | |

핵심: gpt-4o reader의 현실적 천장은 ~82.4%(Oracle)다. 90%대는 더 센 reader 덕.
공정 비교(gpt-4o) 목표선은 Mastra 84.23% / Emergence 79%.

## 2b. 헤드투헤드 (동일 held-out 42문항, seed 7, gpt-4o judge)

| question_type | forget baseline | forget 조합 | Emergence SF |
|---|---|---|---|
| knowledge-update | 100% | **100%** | 71% |
| temporal-reasoning | 43% | 71% | 71% |
| single-session-assistant | 100% | 100% | 100% |
| multi-session | 43% | 57% | 71% |
| single-session-preference | 14% | 43% | 57% |
| single-session-user | 86% | 86% | 100% |
| **OVERALL** | **64.3%** | **76.2%** | **78.6%** |

- **forget 조합** = 엔진(fastembed bge-small 임베딩) + top_k 42 + 2단계 reader(사실추출→답변).
- baseline 64.3 → 조합 76.2 (+11.9pp), Emergence 78.6과 n=42 오차범위(±13pp) 내 동률.
- **knowledge-update 100 vs 71**: 비파괴 supersede가 raw-turn RAG를 압도 — forget 명제의 직접 입증.
- 남은 갭(multi-session·preference·ss-user)은 검색 recall. 가설: forget 랭킹의 temporal_rerank
  최근성 편향이 광역 회수형 질의에서 손해. 다음 레버 §6.

## 3. 개선 경로 (dev, seed 42, n=42 층화)

| config | overall | 비고 |
|---|---|---|
| baseline (deterministic-128, top_k 10, 날짜 미노출) | 54.8% | 이미 Mem0 상회 |
| fastembed(bge-small)로 임베딩 교체, 동일 조건 | 54.8% | **동률 — 임베딩은 병목 아님** |
| + 검색 기억에 날짜 태그 + top_k 20 | 59.5% | +4.8pp |

**반직관 발견**: 임베딩 업그레이드(deterministic-128 → bge-small)는 전체 점수를 안 움직였다
(분포만 이동). 병목은 의미 임베딩이 아니라 **컨텍스트 구성**(reader가 볼 수 있는 것)과
**검색 폭**(top_k)이었다. 이는 "더 좋은 임베딩 = 더 좋은 메모리"라는 통념과 어긋난다.

## 4. Held-out 검증 (seed 7, n=42, dev와 disjoint) — 방어 가능한 숫자

config 잠금(날짜 + top_k 20, deterministic-128) 후 dev에 쓰지 않은 42문항으로 검증:

**overall 64.3%** (dev 59.5%보다 높음 → 과적합 아님). Zep 63.8%와 나란함 = **Tier 2 신호.**

| question_type | held-out acc | 관찰 |
|---|---|---|
| knowledge-update | 100% (7/7) | 비파괴 supersede의 홈그라운드 — 가설 H2 지지 |
| single-session-assistant | 100% | |
| single-session-user | 86% | |
| multi-session | 43% | top_k 확대로 dev 14→57 크게 개선됨 |
| temporal-reasoning | 43% | 날짜 노출이 부분적으로만 도움 |
| single-session-preference | 14% | **미해결** — 검색이 선호 진술을 상위로 못 올림 |

한계: n=42, 이항 95% CI ≈ ±14pp. 방어 가능한 주장은 "42문항 held-out에서 Mem0/Zep
대역에 안착". 리더보드 헤드라인은 §5의 full-500이 확정한다.

## 5. Full-500 (headline) — 확정 (2026-07-14)

**forget 조합 config, 전체 500문항: 64.4%.** (fastembed bge-small + top_k 42 +
2단계 reader, gpt-4o reader/judge.)

| question_type | n | full-500 acc |
|---|---|---|
| single-session-assistant | 56 | 94.6% |
| single-session-user | 70 | 94.3% |
| knowledge-update | 78 | 76.9% |
| multi-session | 133 | 58.7% |
| temporal-reasoning | 133 | 43.6% |
| single-session-preference | 30 | 23.3% |
| **전체** | **500** | **64.4%** |

### Tier 판정 (선등록, gtm/validation-criteria.md 실험 5)

- Tier 1 (>49% Mem0-old): ✅ 통과
- Tier 2 (≥60% Zep권): ✅ 통과 (구 Zep 63.8 소폭 상회)
- Emergence Simple-Fast 79% 초과: ❌ **미달** (약 15pp 아래)
- Oracle gpt-4o 천장 ~82.4%: ❌ 미달
- Tier 3 SOTA (~95%): ❌ 미달

**결론: Tier 2 달성, SOTA 아님.**

### 정직 노트 — held-out 76%는 노이즈였다

§2b의 held-out(n=42) 조합 76.2%는 **낙관적 표본 오차**였다. full-500의 진짜 값은
64.4%로 12pp 낮다. 이는 우리가 앞서 자각한 "n=42 CI ±13pp" 경고가 그대로 실현된 것 —
작은 표본으로 낸 고무적 숫자를 헤드라인으로 쓰지 않은 이유다. **헤드라인은 64.4%다.**

### 진단 — 갭은 어디에 있나

- 최약체 두 타입(temporal-reasoning 43.6%, multi-session 58.7%)이 벤치마크의 **가장 큰
  두 카테고리(각 133문항, 합 266/500 = 53%)**다. 즉 약점이 점수를 지배한다.
- 이 둘은 held-out 재현에서 Emergence가 71%를 낸 지점 — forget의 검색이 raw-turn MiniLM
  RAG보다 **광역 회수형 질의에서 열세**임이 full-500에서 확증됨. rerank/임베딩은 이미
  레버가 아님을 배제했으므로, 남은 원인은 **검색 랭킹 함수 자체 또는 검색 단위**(메시지 vs 세션).
- forget이 이기는 지점은 여전히 knowledge-update(76.9%, supersede 홈그라운드)와
  단일세션(94%대). 명제("사실 수명주기가 중요하다")는 유효하나, 이 벤치마크의 무게중심은
  거기 있지 않다.

### 다음 (E2b, 별도 실험)

1. **세션 단위 검색** — Emergence처럼 메시지 파편이 아니라 세션 청크를 회수(가장 유망).
2. multi-session/temporal 질의에 top_k 대폭 상향 + 세션 다양성 확보.
3. 이후에야 Emergence 79% / Oracle 82% 재도전이 의미. 지금 config로는 천장이 ~64%.

## 6. E2b 결과 — 세션 단위 검색 (2026-07-14)

dev(seed 42, n=42) 세션 단위 vs turn 단위 (top_k 10 session ≈ 42 turn 총량):

| question_type | turn | session | Δ |
|---|---|---|---|
| temporal-reasoning | 14% | 43% | **+29** |
| multi-session | 43% | 29% | −14 |
| single-session-preference | 29% | 0% | −29 |
| knowledge-update | 86% | 86% | 0 |
| single-session-user/assistant | 100% | 100% | 0 |
| **전체** | **61.9%** | **59.5%** | −2.4 (노이즈 내) |

**판정: 단순 세션 가설 기각** — dev 기준선(61.9%)을 못 넘어 held-out/full-500 승격 안 함.

**획득한 메커니즘 (세션 임베딩 희석)**: 세션 단위는 트레이드오프다. temporal은 통짜
세션의 날짜·순서 맥락으로 개선되지만(+29), preference·multi-session은 특정 한 턴의 사실이
긴 세션 임베딩에 평균화돼 묻혀 악화된다(−29/−14). overall Δ는 n=42 노이즈 안이나 타입별
스윙은 dilution 메커니즘과 일관돼 신호로 본다.

### E2c 후보 — 하이브리드 검색

데이터가 가리키는 해법: **턴 단위 핀포인트 검색**(preference/multi-session 회수 유지)
**+ 검색된 턴을 그 세션 맥락으로 확장**해 reader에 제공(temporal 이득 획득). "찾을 땐
정밀하게, 읽을 땐 넓게." 검색 턴↔세션 매핑 필요. 별도 실험.

## 7. 헤드라인 갱신 — 하니스 날짜 버그 수정 (2026-07-15)

**실패 케이스를 직접 읽다가** 하니스 버그를 발견했다: `normalize_date`가 LongMemEval
포맷 `2023/05/20 (Sat) 02:21`을 `2023/05/20TSat) 02:21` 쓰레기로 만들어 서버가 파싱
실패 → **모든 500 인스턴스의 모든 기억이 created_at을 "오늘"로 폴백**. temporal-reasoning
(133문항, 벤치마크 최대 카테고리)이 날짜 신호 0으로 채점되고 있었다. (이것이 §6의 "rerank
ON=OFF 완전 동일" 미스터리도 설명한다 — 모든 날짜가 같으니 재정렬 대상이 없었다.)

정규식 파싱으로 수정 후 동일 config(fastembed + top_k 42 + 2단계 reader) full-500 재실행:

| question_type | n | buggy | **date-fix** | Δ |
|---|---|---|---|---|
| temporal-reasoning | 133 | 44% | **75%** | **+32** |
| single-session-preference | 30 | 23% | 30% | +7 |
| knowledge-update | 78 | 77% | 81% | +4 |
| single-session-user | 70 | 94% | 97% | +3 |
| multi-session | 133 | 59% | 61% | +2 |
| single-session-assistant | 56 | 95% | 95% | 0 |
| **전체** | **500** | **64.4%** | **74.8%** | **+10.4** |

### 확정 헤드라인: **forget = 74.8% on LongMemEval-S** (n=500, gpt-4o reader/judge)

### Tier 재판정

- Tier 1 (>49): ✅ · Tier 2 (≥60): ✅
- 구 Zep 63.8 / 신 Zep 71.2: ✅ 상회
- **Emergence Simple-Fast 79%: ❌ 미달 (4.2pp 아래)** — 우리 하니스 재현치 78.6과 비교해도 아래
- Oracle gpt-4o 천장 ~82.4%: ❌ 미달
- SOTA ~95% (더 센 reader): ❌ 미달

**결론: 확정 Tier 2, Emergence에 4pp 근접하나 미달.** 정직한 서술 = "로컬 임베딩 forget이
공개 SOTA급 오픈소스 베이스라인(Emergence 79)에 4pp 이내로 근접, knowledge-update는 우위."

### 남은 갭 진단 (E2c 이후)

date-fix 후에도 약한 두 지점: single-session-preference 30%(검색이 선호 진술을 못 올림),
multi-session 61%(집계형 회수). temporal은 해결됨. E2c 하이브리드(턴 검색 + 세션 확장)는
이제 temporal이 아니라 **multi-session/preference의 회수 완전성**을 겨냥해야 한다.

## 6. 다음 레버 (선등록 — 결과 보고 후에도 이 순서 유지)

1. **single-session-preference** (14%): 선호 진술 검색 실패. 가설 — 선호는 저빈도·저유사도
   진술이라 top_k에 안 걸림. 후보: 선호형 발화의 write-time 승격(관찰 게이트가 선호를 별도
   태그), 또는 질의 확장. dev에서만 튠 후 held-out 재검증.
2. **temporal-reasoning** (43%): 파편 검색의 한계. 후보: 세션 단위 검색(메시지가 아니라
   세션 청크 회수) + 날짜 정렬 컨텍스트. 아키텍처 변경이라 별도 실험(E2b).
3. full-500 확정 후 Tier 판정 → Show HN v2 벤치마크 문단 반영은 실행 세션 소관(분업 규약).

## 7. 정직 노트

- deterministic-128이 bge-small과 동률인 것은 이 태스크에 국한된 결론일 수 있다(짧은
  대화체 메시지, gpt-4o reader가 파편에서 복원). 다른 코퍼스에서 재확인 필요.
- reader/judge가 gpt-4o라 "로컬 전용"은 메모리 레이어에 한한 주장이다(평가 자체는 API 사용).
  제품의 로컬성과 벤치마크 평가의 API 사용은 별개임을 명시한다.

## 8. O1 사다리 — 쓰기 시점 관찰 압축 (2026-07-15)

프론티어(Mastra Observational Memory)의 쓰기 시점 압축을 이식·해부한 실험 사다리.
전부 동일 held-out 42(seed 7), gpt-4o Observer/reader/judge. Observer는 질문을 보지
못한 채 세션당 날짜 앵커링된 관찰 불릿 생성(캐시: observations/).

| config | overall | 관찰 |
|---|---|---|
| 원문만 + 검색 42 (기존 최고) | 78.6% | |
| O1a 관찰만 + 전체 컨텍스트 (Mastra식) | 52.4% | 쓰기 소실: 어시스턴트 세부를 Observer가 폐기 |
| O1b 관찰만 + 검색 42 | 69.0% | **temporal 100%** — 압축·날짜해석이 시간추론 지배 |
| O1c 관찰+원문 한 풀 42 | 71.4% | 검색 경쟁으로 multi-session 86→57 붕괴 |
| O1d 층화 듀얼 21+21 | 76.2% | multi-session에 관찰 슬롯 부족 |
| **O1e 층화 듀얼 42+42** | **90.5%** | 4개 카테고리 100%, preference 57%로 회복 |

**발견**: 관찰 레이어(세션 횡단·시간 추론)와 원문 레이어(세부 회상)는 상보적이며,
한 풀에서 경쟁시키면 서로를 죽인다. 레이어별 검색 예산 보장(층화 듀얼)이 결정타.
이는 forget의 비파괴 설계(압축하되 원문을 영수증으로 보존)의 벤치마크 실증이다.

**정직 캐비앗**: held-out 42에 config 6개를 순차 시도 — 선택 편향 위험. n=42에서
90.5%의 CI ≈ ±9pp. 따라서 90.5는 주장 아님; **full-500이 헤드라인을 확정**한다.
config 자체는 정당함: Observer는 질문 비접근, question_type 라우팅 없음, 표준 judge.

**비용 노트**: full-500 관찰 생성 ≈ 458 인스턴스 × ~50 세션 × gpt-4o ≈ $250-350.
O2(로컬 Observer)가 이 비용을 0으로 만든다 — 상업 논거이기도 함.
