# 저자 리뷰 (2026-07-20) — 개정 계획

| # | 지적 | 조치 | 상태 |
|---|---|---|---|
| 1 | organic 무해함 = 번역 아티팩트 가능 | 유사도를 주장→측정으로: 계열별 기질 대비 임베딩 유사도 분포 + per-query harm~similarity 회귀 | **즉시 실행** (w1_similarity.py) |
| 2 | crosstalk 14.7pp는 상한 (동일 생성기) | 용량-반응 곡선: donor 유사도 층화(near/mid/far) 스윕 → harm vs similarity 연속 법칙 | **백그라운드 발사** (w2_dose_response.py) |
| 3 | confirmatory 기록 약함 (C2 사후 분할) | §5.3 서술 교체: "방향 전 셀 일관·등록 효과크기 미달·분할은 탐색적, held-out 확인 대기". W2에 OR/AND held-out 확인(제2 임베더 서브샘플 + Tier-2 셀) 편입 | 문구 수정 완료, W2 설계 반영 |
| 4 | k 간 pp 비교의 headroom 교란 | M(0,k) 기저 공개 + logit/상대 harm 병기 | 분석 추가 |
| 5 | Tier-2 전 헤드라인은 검색 지표 / C5 자리만 있음 | hit=0 → 답 실패 하한 논리 명시. C5를 기여 목록에서 조건부로 강등. 브리지 = W2 최우선 | 문구 수정 완료 |
| 6 | dedup 원인 회계 부재 | dedup 삭제분 중 증거 사본 비율(evidence FP rate) 텔레메트리 재실행 + 대표성 방어 문단 | W2 큐 |
| 7 | 정체성: D&B가 안전 경로 | **D&B 확정.** W1(라벨링·datasheet·라이선스·호스팅) 을 W2와 동순위 승격. 이론은 검증된 만큼만 | 방침 확정 |
| 8 | 제목-발견 충돌 + abstract 숫자 과다 | 제목 후보: "It's Not the Junk: ..." (저자 결정 대기). abstract 4박자 다이어트 | 초안 반영, 제목은 보류 |
| 소 | 타임스탬프 재샘플 한계 / sign test 명시 | §3.6 + §5.4 한 줄씩 | 완료 |
