# Compress, but Keep the Receipts:
## Stratified Dual-Layer Memory for Conversational Agents, with Fully Local Construction

Status: outline v0.1 (2026-07-17). Target: arXiv 프리프린트 → ACL ARR 또는 ICLR 2027.
저자: 김정훈 (Multi-turn Inc.). 코드·데이터: forget 리포 research/ (재현 가능).

## Thesis (한 문장)

장기 대화 메모리에서 쓰기 시점 압축(관찰)과 원문 보존(영수증)은 **상보적이며 한 풀에서
경쟁시키면 서로를 파괴한다** — 레이어별 검색 예산을 보장하는 층화 듀얼 검색이 해법이고,
이 구조는 압축을 로컬 모델로 수행해도 (프라이버시 보존) 경쟁력을 유지한다.

## Contributions

1. **상보성 발견 + 층화 듀얼 검색**: 관찰 레이어는 시간추론·다중세션(temporal 100% 대
   raw 43%, n=42 사다리), 원문 레이어는 세부 회상(ss-assistant 100% 대 obs 43%)을 지배.
   단일 풀 혼합은 검색 경쟁으로 양쪽을 죽임(71.4%). 층화 예산이 해법 (full-500 81.8%).
2. **체계적 ablation, 공개 벤치마크**: LongMemEval-S full-500에서 64.4→81.8
   (McNemar p<1e-16), 단계별 격리: 날짜 노출(+10.4, p<1e-9), 듀얼 레이어(+6.0, p<4e-4),
   reader 균형화(+1.0, n.s. — 정직 보고). Oracle gpt-4o 천장(82.4)에 0.6pp.
3. **로컬 구축 격차 최초 측정 (H5)**: 메모리 구축(Observer)을 14B 온디바이스 모델로
   수행 시 격차 11.9pp(n=42; full-500 실측 진행 중) — 그럼에도 클라우드 원문-RAG 오픈
   베이스라인과 동률. E2EE 메모리 아키텍처의 성능 실증.
4. **정직 방법론 아티팩트**: 선등록 기준, dev/held-out 분리, held-out 소모 공개,
   lucky-draw 3회 적발 기록, 운영 바 이탈의 공개 결정. (부록)

## 실험 매트릭스 — 상태

| 셀 | 상태 | 비고 |
|---|---|---|
| naive RAG full-500 (64.4) | ✅ | |
| +date-fix full-500 (74.8) | ✅ | raw-only, top_k 20 |
| dual-v1 full-500 (80.8) | ✅ | obs42+raw42, v1 reader |
| dual-v3 full-500 (81.8) | ✅ | obs60+raw24, v3 reader |
| **raw-only@84 full-500** | 🔲 착수 | 예산 통제 ablation (dual과 동일 슬롯) |
| **obs-only@84 full-500** | 🔲 착수 | 〃 |
| O1 사다리 (n=42, 6 config) | ✅ | 발견 서사용 (본문은 full 수치가 주장) |
| **O2 로컬 full-500** | 🔲 장대 | 4090 Qwen-14B 관찰 생성 ~500인스턴스 |
| O2 로컬 32B (여력 시) | 🔲 | 로컬 스케일링 포인트 |
| Emergence 재현 full-500 | 🔲 검토 | 동일 judge 비교 강화 (~$50), n=42 재현(78.6)로 대체 가능 |
| McNemar 전 쌍 | ✅ | 본문 표 |
| E1 dirty-store | ✅(null) | 부록 or 별도 노트 — 본 논문 스코프 밖 |

## 구성 (섹션)

1. Intro — 저장-후-검색의 실패 양상, 압축이냐 보존이냐의 거짓 이분법
2. Related Work — MemGPT/Letta, Generative Agents, Mem0/Zep(Graphiti), HippoRAG,
   Mastra OM, Emergence SF, LongMemEval/LOCOMO; 위치: 쓰기시점 선택+수명주기+듀얼 서빙
3. Method — 관찰자(프롬프트 부록), 듀얼 스토어(스코프 격리), 층화 검색, 2단계 reader
4. Experiments — 매트릭스, 주표(full-500 6셀 + 타입별), 유의성, 사다리(발견 과정)
5. Local Construction — H5 격차, 프라이버시 논거(E2EE 요구와의 정렬), 비용(구축 $0)
6. Honest Methodology — 선등록·오염 공개·n.s. 보고 (이 분야 자기발표 수치 관행 비판)
7. Limitations — 벤치 1개, judge=gpt-4o 의존, preference 57% 미해결, multi-session 집계
   아키텍처 한계, held-out 소모

## 실행 순서 (오늘부터)

1. ✅ McNemar (완료, 위 수치)
2. 🔲 raw-only@84 + obs-only@84 full-500 발사 (관찰 캐시, ~$90, ~8h)
3. 🔲 4090 관찰 생성 파이프라인 (standalone 스크립트 → 4090에서 nohup, 병렬 4, ~15-20h)
4. 🔲 O2 full-500 채점 (관찰 완료 후, ~$50)
5. 🔲 본문 초고 (실험 도는 동안 §1-3, §6)
