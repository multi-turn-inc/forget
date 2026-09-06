# HaluMem-Medium · forget 파일럿 (2026-09-07 04:1x KST)

설정: 1 user(Martin Mark, 65 세션, 14,948 중 2,110 기억점, QA 164) · forget 인프로세스(규칙 추출·활성 재순위 검색 top20) · 답변·판정 gpt-4o(논문과 동일) · 격리 DB.
러너 `scripts/bench_halumem.sh 1 pilot` · 어댑터 `research/eval/halumem_adapter/eval_forget.py` · 수집 65세션 ≈ 5.5분 · 판정 423초.

| 지표 | forget(1 user) | 논문 Medium 참고(20 user) |
|---|---|---|
| 추출 recall(가중) | 0.71 (0.85) | — |
| 추출 F1 | 0.79 | — |
| target accuracy / interference accuracy | 0.89 / 0.53 | — |
| 갱신 correct / hallucination / omission | 0.34 / **0.00** / 0.66 | — |
| QA correct | **66.5** | MemOS 67.2 · Zep 55.5 · Mem0-Graph 54.7 · Supermemory 54.1 |
| QA hallucination | **14.0** | MemOS 15.2 · Mem0 19.2 · Zep 21.9 · Supermemory 22.2 · Memobase 30.0 |
| QA omission | 19.5 | — |

읽기(n=1, 판정 아님):
- QA 정답·환각은 첫 판에서 이미 표의 상단 근처. 검색·출처 게이트가 하는 일이다.
- 갱신은 환각 0이지만 누락 66% — 규칙 추출이 «바뀐 사실»을 supersede로 잇지 못한다. 채용 P0(두 시간축·needs_recheck)이 정확히 이 칸이다.
- interference accuracy 0.53 — 산만 문장을 기억으로 저장한다(«Hi, I'm Martin» 같은 문장). 저장 게이트(중간 루프 로컬 모델) 자리.
- 비용 미측정 — 다음 사용자 1명은 토큰 로그를 켜고 돌려 20명 총액을 추정한 뒤 전체 실행 여부를 정한다(총액 상한 $40).
