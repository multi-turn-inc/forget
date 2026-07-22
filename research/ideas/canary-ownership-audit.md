# 카나리 소유권 감사 — 필드 맵 & 실현 가능성 판정

> **아이디어**: 로컬-퍼스트 메모리 스토어의 사용자별 소유권 비콘 + "통과-LLM 카나리 감사" 프로토콜
> (사용자가 API provider에 보내는 트래픽에 카나리를 심어, provider의 "학습 안 함" 약속을 사후 블랙박스 검증)
>
> **출처**: deep-research 워크플로 `wf_b5f2ba52-52a` (2026-07-22, 에이전트 102개, 소스 20개, 클레임 100개 추출 → 25개 적대 검증 → 23 확정 / 2 기각 → 9 finding 병합). 모든 수치는 3-인 검증단 표결 통과분.
>
> **지위**: 10월 게이트 이후 연구 트랙 후보. 이번 주 작업 아님.

---

## TL;DR

2024년의 두 부정적 결과(Meeus: 트랩에 100토큰×1,000회 반복 필요 / Duan: 프리트레이닝 MIA 무력) 이후, 2025–26 필드는 세 방향으로 반격했다:

1. **dedup-생존형 설계** — fuzzy/mosaic 카나리(Nature Comms 2026), STAMP(ICML 2025: 반복 0회·코퍼스 0.001% 미만에서 탐지)
2. **순수 블랙박스화** — UCSD word-pair co-occurrence 워터마크(API 생성 텍스트만으로 p<0.01), Canary's Echo(ICML 2025: 합성 출력만으로 AUC 0.68–0.77)
3. **파인튜닝 국면 집중** — SPV-MIA(NeurIPS 2024): 파인튜닝 LLM에서 AUC ~0.9 vs 프리트레이닝 ≈0.5

**판정**: 2주 슬라이스는 **파인튜닝/RLHF 국면 타깃이면 문헌상 실현 가능 영역**. 프리트레이닝 타깃이면 즉사. "통과-API 학습 준수 감사"를 제품/프로토콜로 구현한 사례는 검증된 문헌에 **없음** — 부품 3개는 각각 선점됐지만 교집합은 빈 곳.

---

## 1. 필드 지형도 (검증 통과 finding 9개)

### 축1 기준선 — 원조 Copyright Traps (Meeus, ICML 2024) `high` `3-0×3`
- 1.3B CroissantLLM(3T 토큰 from-scratch): **100토큰×1,000회 반복 → AUC 0.748** (Ratio attack). 25토큰×1,000회 → 0.557, 100토큰×100회 → 0.639.
- 수 개~수십 개 삽입은 이 규모에서 탐지 임계 훨씬 아래. ~1B 모델은 자연 암기가 없어 document-level MIA도 무력.
- 방증: BLOOM-176B에서 SHA 해시 카나리도 ~90회 이상 출현해야 탐지 (Wei, ACL Findings 2024).
- https://arxiv.org/abs/2402.09363

### 축1+특별c — dedup 반론의 해법: Mosaic Memory `high` `3-0×3`
- 원조 트랩(verbatim 반복)은 표준 dedup에 "trivially removed" — **저자 그룹 스스로 인정**.
- 해법: 10% 토큰 치환한 fuzzy duplicate가 정확 중복 대비 **ρ=0.50–0.60** 암기 기여 유지 (Nature Comms 2026 게재본은 0.60–0.65로 상향). 4/100 토큰 치환 시 MIA AUC 0.90→0.87로만 하락.
- SlimPajama급 dedup 파이프라인은 fuzzy duplicate를 못 걸러냄 (시퀀스당 평균 ~2,500개 잔존).
- 한계: 1–3B continued pretraining 설정, frontier from-scratch 아님.
- https://arxiv.org/abs/2405.15523

### 축1 SOTA — STAMP (ICML 2025) `high` `3-0×3 + 2-1×1`
- 콘텐츠가 학습 데이터에 **단 1회 출현**(코퍼스 0.001% 미만)해도 collection-level 탐지: p=1.2e-4(TriviaQA)~6.6e-6(GSM8K). 같은 설정에서 표준 MIA 전부 AUROC≈0.5.
- 메커니즘: 공개본 1개 + 비밀키 워터마크된 비공개 rephrasing m개(기본 5) → perplexity 차이에 paired t-test.
- **경계**: ~1,000 문서 컬렉션 단위(p≈10⁻³에 ~600 문서), 단일 문서 아님. **로짓 접근(gray-box) 필요** → 텍스트 완성만 노출하는 폐쇄 API 감사엔 직접 적용 불가. 발행 전 사전 개입형.
- https://arxiv.org/abs/2504.13416

### 축4·특별b 최근접 — UCSD 폐쇄-LLM 워터마크 (2026 preprint) `medium` `3-0×3`
- 폐쇄 LLM(생성 텍스트만, 로짓 없음)에서 **provable·distribution-free FPR 보장**을 갖는 최초 데이터셋 워터마킹 주장.
- 방법: 무작위 word pair 250개의 동시출현 빈도를 rephrasing으로 상승 → 생성 출력의 co-occurrence 통계 검정.
- 파인튜닝 실측: LLaMA-3-8B/Gemma-2-2B에서 p<0.01(최저 1.34e-6). **파인튜닝 토큰의 1.1–1.3% 혼합에서 생존**, 0.5%에선 LLaMA-3-8B만 성공.
- 자원 레시피: 1,000 예제, word pair 250개, rephrasing 3라운드, 탐지 시 생성 샘플 20K, τ=0.03.
- 신뢰도 medium 사유: 비피어리뷰, 폐쇄 설정을 오픈웨이트로 시뮬레이션, 파인튜닝 국면만.
- https://arxiv.org/pdf/2605.06865

### 특별b 핵심 실측 — Canary's Echo (ICML 2025, Microsoft/Imperial) `high` `3-0×4`
- **모델 접근 전무, 합성 출력 텍스트만 관찰**하는 MIA: AUC 0.74(SST-2)/0.68(AG News)/0.77(SNLI) — Mistral-7B LoRA 파인튜닝, 카나리 **~12회 반복** 조건.
- 환산: 출력-전용 감사는 로짓 접근 대비 카나리 **8–16× 더 반복** 필요 (naive 설계 기준, 개선 설계로 갭 축소).
- 설계 교훈: ⓐ Carlini식 고퍼플렉시티 카나리는 출력-전용에서 AUC→0.5로 붕괴 (in-distribution 생성에 영향 못 미침). ⓑ 올바른 설계 = **in-distribution 저퍼플렉시티 prefix + 고퍼플렉시티 suffix** (SST-2: AUC 0.673→0.760).
- https://arxiv.org/pdf/2502.14921

### 축2 — Duan 2024 (COLM) 부정적 기준선 `high` `3-0×2 + 2-1×1`
- 5개 MIA × Pythia 160M–12B(Pile): 프리트레이닝 멤버십 추론 거의 무작위 (AUROC 0.48–0.58, GitHub 도메인 제외 0.6 미달).
- 원인: ⓐ 거대 데이터 × ~1 epoch, ⓑ 멤버/비멤버 경계 모호(비멤버 7-gram 중복 32–41%).
- **결정적 함의**: MIA 탐지력이 유효 epoch 수에 대략 선형 증가 → 샘플당 epoch 많은 **파인튜닝 국면이 훨씬 탐지 가능**함을 같은 논문이 명시.
- https://openreview.net/pdf?id=av0D19pSkU

### 축2 파인튜닝 파워 — SPV-MIA (NeurIPS 2024) `high` `3-0`
- 파인튜닝된 LLM 대상 MIA AUC **~0.7 → 평균 0.924** (GPT-2/GPT-J/Falcon-7B/LLaMA-7B × 3 데이터셋).
- "파인튜닝이 얼마나 더 잘 탐지되는가"의 현재 최선 정량 답: 무작위(≈0.5) vs 0.9대.
- 무작위 분할 사용 → Duan식 분포-이동 비판 미적용.
- https://openreview.net/forum?id=PAWQvrForJ

### ⚠️ 인용 함정 — SIGIL (2026 preprint) `기각 0-3 ×2`
- 블랙박스 AUC 0.892, dedup 생존 96%/73%, 패러프레이즈 생존("semantic leakage") 등 매력적 수치 **전량이 보정된 통계 시뮬레이터 산출물** — 실제 LLM 학습 실험 전무. "125M/1.3B/7B"도 시뮬레이터 파라미터.
- dedup·패러프레이즈 생존 클레임 2건은 본 검증에서 **0-3 기각**. 실현 가능성 근거로 인용 금지.
- https://arxiv.org/html/2606.06502

---

## 2. Novelty 위협 평가

| 최근접 이웃 | 선점한 부품 | 우리와의 차이 |
|---|---|---|
| **Canary's Echo** (ICML 2025) | 출력-전용 블랙박스 감사 | 데이터셋 소유자 관점, 통과-트래픽/개인 스토어 아님 |
| **UCSD co-occurrence** (2026 preprint) | 폐쇄모델 provable-FPR 탐지 | 벤치마크 오염 탐지 목적, 사용자 트래픽 아님 |
| **STAMP** (ICML 2025) | 반복-0 삽입 | gray-box(로짓) 필요, 컬렉션 단위, 사전 개입형 |
| **Behavioral Canaries** (arXiv 2604.22191) | RL 파인튜닝에서 retrieved-context 사용 감사 | 검증 단계 미통과 — 별도 정밀 확인 필요 |

**빈 곳 (검증된 문헌 기준)**:
1. "사용자→API 트래픽에 카나리 심어 provider 학습 준수를 사후 검증"하는 **제품/프로토콜** — 없음
2. **개인 메모리/노트 스토어 단위 소유권 비콘** — 다룬 연구 확인 안 됨 (특별확인 a 미해결)
3. **개인 단위 통계 파워 문제의 집단 협응 해법** (여러 사용자가 공유 비밀키/구조 분담 삽입) — 제안 없음

단, novelty 판정은 부재 증거 기반 — 비공개 상용 감사 도구 존재 가능성 배제 못함 (오픈 퀘스천 참조).

## 3. 2주 슬라이스 실현 가능성 판정

**판정: 조건부 GO (파인튜닝/RLHF 국면 타깃 한정)** — synthesis 교차 추론, confidence medium.

필요 조건 (문헌 실측 기반):
- 카나리당 **~12회 이상 반복** (출력-전용이면 로짓 대비 8–16×)
- **in-distribution prefix + 고퍼플렉시티 suffix** 설계 (Carlini식 무작위 문자열 금지)
- 개별 카나리 아닌 **집계 통계 검정** (paired t-test 또는 co-occurrence 검정)
- 탐지 쿼리 예산: 생성 샘플 **수천~20K**
- 예상 파워: 카나리당 AUC 0.68–0.77 (출력-전용) 또는 p<0.01 (분산형 co-occurrence, ~1% 혼합)

**치명적 반론 순위**:
1. **프리트레이닝 표적이면 즉사** — 100회 반복도 무탐지 (Meeus 2024)
2. **verbatim 반복은 dedup에 즉사** — 해법: fuzzy 변주 (ρ=0.5–0.6 유지, Mosaic Memory)
3. **로짓 미노출 API면 STAMP류 불가** — 해법: co-occurrence/합성출력 경로
4. **스케일 갭** — 실측 전부 ≤8B 모델·LoRA/continued-pretraining. frontier의 품질 필터+다단 dedup+RLHF 믹스 생존은 외삽
5. **RLHF 단계 자체에 대한 카나리 탐지 실측 부재**

## 4. 오픈 퀘스천

1. 특별확인(a): 개인 단위 카나리 + 집단 협응 프로토콜 — 별도 서베이 필요
2. 축3·축6 미커버: NYT v. OpenAI 등 소송에서 암기 증거의 법적 지위, 상용 지형(haveibeentrained류) — **비공개 상용 도구가 novelty 판정을 뒤집을 수 있음**
3. 8–16× 페널티와 ~1% 혼합 생존이 frontier 실제 학습 경로(대규모 SFT 믹스+RLHF+안전 필터)에서 유지되는가
4. fuzzy 카나리가 dedup 너머 품질 필터·LLM 기반 클리닝(rephrasing)까지 생존하는가 — dedup만 검증됨

## 5. 커버리지 공백 (부재 ≠ 없음)

축3(radioactive data 텍스트 이식·법적 증거력), 축5(텍스트판 Nightshade·unlearnable examples), 축6(제품·시장)은 검증 통과 클레임 전무. 후속 서베이 대상.

---

*원본 데이터: 워크플로 저널 `~/.claude/projects/.../subagents/workflows/wf_b5f2ba52-52a/journal.jsonl`, 전체 결과 `tasks/wu8f9urxv.output`*
