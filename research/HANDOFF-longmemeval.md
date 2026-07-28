# LongMemEval 캠페인 — 연구 포크 인계 노트

작성: 2026-07-14, 실행 세션 → 연구 포크. 소유권: **연구 포크 단독**.
실행 세션은 이 시점부로 벤치마크에서 손 뗌 (분업 규약 [[forget-session-division]]).
판정 기준·티어: gtm/validation-criteria.md 실험 5 (선등록, 결과 보고 수정 금지).

## 이미 되어 있는 것 (실행 세션이 벌여놓은 것 인수)

- 벤치마크 리포 클론: scratchpad/longmemeval (xiaowu0162/LongMemEval, ICLR 2025)
- **oracle 데이터셋 확보**: research/longmemeval-data/longmemeval_oracle.json (15MB, 500문항)
- 스키마 분석 완료 (아래)

## 데이터셋 스키마 (oracle 기준, 인스턴스당)

- question_id, question_type, question, answer, question_date
- haystack_dates[], haystack_session_ids[], haystack_sessions[] (세션=메시지 리스트)
- answer_session_ids[] (정답 근거 세션 — oracle에만; 리트리벌 평가는 이걸로 채점)
- question_type 분포(500): temporal-reasoning 133, multi-session 133,
  knowledge-update 78, single-session-user 70, single-session-assistant 56,
  single-session-preference 30

## 우리 엔진의 강점이 겹치는 지점 (가설)

- **knowledge-update(78)** → supersede 계보의 홈그라운드
- **temporal-reasoning(133)** → temporal rerank의 홈그라운드
- 이 둘(211/500 = 42%)이 Zep이 Mem0를 이긴 급소. 여기서 벌면 점수가 크게 움직임.
- abstention은 관찰 게이트와 연결(모르면 모른다) — 확인 필요.

## 다음 스텝 (포크가 할 일)

1. **데이터 3종 완비**: oracle는 확보. longmemeval_s_cleaned.json,
   longmemeval_m_cleaned.json은 HF에서 추가 다운(스키마 동일, haystack이 더 김).
   실전 프로토콜은 S 구성 권장(oracle은 상한 참고용).
2. **하니스 어댑터**: 각 인스턴스에 대해 haystack_sessions를 forget에 인제스트
   (add_memory, user_id=인스턴스별 격리 스코프, created_at=haystack_dates 매핑) →
   question으로 search_memories/assemble_context → 검색된 컨텍스트로 reader LLM 호출
   → 답 생성. forget의 스코프 격리로 인스턴스 간 오염 차단(우리가 이번 주 고친 그 라우트).
3. **reader/채점**: LongMemEval src/evaluation/evaluate_qa.py 사용. reader는 공정
   비교 위해 공개 수치와 동일 계열(GPT-4o) 권장 — API 비용 발생(수십 달러 추정).
4. **baseline 먼저**: 현행 deterministic-128 + 휴리스틱 그대로의 숫자 = Tier 0.
   그 다음 임베딩 업그레이드(fastembed/bge = vault 스파이크 3과 동일작업)로 개선.
5. eval-gaming 금지: 튜닝은 held-out 분리. 나쁜 숫자도 방법론과 함께 기록.

## 참조점 (공정 비교는 우리 하니스에서 동일 reader로 재현)
Mem0 49.0% / Zep 63.8% (LongMemEval, GPT-4o reader). SOTA는 리더보드 확인.

## 실행 세션에 남기는 의존성
- 벤치마크 결과가 나오면 → 실행 세션이 Show HN v2(결과 문단 추가)·랜딩 배지·YC Winter
  덱에 반영. 포크는 add_memory로 "Tier N 달성, 숫자 X" 선언만 하면 됨.
