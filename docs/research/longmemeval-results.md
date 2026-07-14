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

## 2. 참조점 (공개 수치, GPT-4o reader)

| 시스템 | LongMemEval-S |
|---|---|
| Mem0 | 49.0% |
| Zep | 63.8% |
| **forget (목표)** | Tier1 >49 · Tier2 ≥60 · Tier3 SOTA |

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

## 5. Full-500 (headline) — 실행 중, 완료 시 기입

_(pending: `research/longmemeval/runs/full-s-500.summary.json`)_

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
