# OpenAI ToS 준수 조사 — MemoryArena forget 어댑터 (2026-07-30)

질문: MemoryArena에서 forget을 gpt-5-mini(에이전트+판정) 위에서 돌리고 결과를 공개하는 게
OpenAI 이용약관상 안전한가.

## 결론: 안전함. 단, 아래 체크리스트를 지킬 것.

## 근거 조항

**OpenAI Services Agreement (2026-01-01 발효) §3.3(e)**
> except for a Permitted Exception, use Output to develop artificial intelligence
> models that compete with OpenAI's products and services

**§17 정의 — "Permitted Exception"**
> using Output to: (a) develop AI models primarily intended to categorize,
> classify, or organize data (embeddings, classifiers), if not distributed/sold
> to third parties; (b) fine-tune via OpenAI's own fine-tuning service.

**적용 안 되는 이유:**
1. forget 엔진(게이트·SQLite·트러스트 모델)은 GPT 출력을 증류한 파운데이션 모델이 아님 — 독자 알고리즘, 관측자 모델 교체 가능.
2. gpt-5-mini는 벤치마크에서 에이전트/판정자 역할일 뿐, 산출물은 "훈련된 모델"이 아니라 비교 리포트.
3. 실증: MemoryArena 코드베이스 자체가 mem0/letta/zep 등 경쟁 메모리 제품 어댑터에 동일하게 gpt-5-mini를 백엔드로 씀 — 업계 표준 관행이며, 이 조항이 이런 용례에 적용된다면 API 위에 제품을 짓는 것 자체가 금지되는 모순.

**실제 적용되는 조항:**
- §3.3(h) 레이트리밋 우회 금지 (표준 사용은 무관)
- §3.3(g) API 키 재판매/양도 금지
- [Sharing & Publication Policy](https://openai.com/policies/sharing-publication-policy) — 공개 시: 이름/회사 귀속, AI 생성 사실 명시, 콘텐츠 정책 준수. "Research" 섹션에서 벤치마크 공개 연구를 명시적으로 환영함.
- 벤치마크 비교 수치 공개를 금지하는 조항은 존재하지 않음. OpenAI 스스로도 비교 벤치마크를 공개함.

## 실무 참조 사례 (GitHub)
`Harmix/pam-benchmark` — 경쟁 메모리 제품(Pam) vs gpt-4-turbo 베이스라인을 겨루는 실제 벤치마크가
`ethics-and-licensing/licensing-and-data-handling.md`에 벤더별 ToS 체크 테이블과 "External-claim policy"를
공개해둠. 패턴을 인용해 아래 체크리스트로 흡수.

## forget 적용 체크리스트 (공개 전)
1. **모델 스냅샷 고정 기록**: 정확한 model id(예: `gpt-5-mini-2026-xx-xx`)를 config·리포트에 남길 것 — 드리프트 대비.
2. **개인 API 키 사용**, 재판매·양도 없음.
3. **레이트리밋 준수**, 백오프로 우회 안 함.
4. **공개 시 고지 3종**: forget/multi-turn 귀속 · "GPT-5-mini를 에이전트/판정 백엔드로 사용" 명시 · OpenAI 콘텐츠 정책 위반 콘텐츠 없음 확인.
5. **결과 해석 정직성**: 시드·구성·날짜·판정 모델을 №0003처럼 공시 (OffReco 원칙과 동일선).
6. **경쟁사 비교 시**: mem0/letta 등 각 벤더 자체 ToS도 개별 확인 — 일부는 벤치마크 공개를 금지할 수 있음(pam-benchmark 테이블의 "TBD per vendor" 패턴). forget↔OpenAI 관계와 별개로, forget↔각 경쟁사 관계도 체크.

## 참고 링크
- https://openai.com/policies/business-terms (Services Agreement, 2026-01-01)
- https://openai.com/policies/usage-policies
- https://openai.com/policies/sharing-publication-policy
- https://github.com/Harmix/pam-benchmark (실무 패턴 참조)
