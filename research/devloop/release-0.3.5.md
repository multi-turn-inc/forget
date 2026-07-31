# 0.3.5 릴리스 체크리스트 — 게이트 산출물 (사이클 4, 2026-07-31)

상태: **게이트 대기 (정훈)**. 헌장 원칙 5 — 릴리스 태그·PyPI 배포·라이브 업그레이드는
사람 승인 후 실행한다. 이 문서는 실행자가 그대로 따라갈 수 있게 준비해 둔 것.

## 왜 지금인가

- 라이브(`~/.forget/venv`)는 `forget_ai 0.3.4` (dist-info로 확인, 2026-07-31).
- v0.3.4 이후 **패키지에 실리는 변경은 F1+F2 둘뿐** — `forget/store.py` +55줄,
  테스트 2파일 신규 (`git diff --stat v0.3.4..HEAD -- forget/ tests/`). 작고 깨끗한 릴리스.
- 예측 대장 P1·P3의 판정이 라이브 반영에 걸려 있다. 특히 P3(기한: 사이클 8)는
  릴리스가 늦어지면 판정 불가가 된다 — 사이클 4 세션 회상에서도 F2형 노출
  (heartbeat·stance)이 재확인됐는데, 이는 라이브가 구코드(0.3.4)이기 때문이다.
  코드 해소의 효과는 배포 전에는 측정되지 않는다.

## 실리는 것 (v0.3.4..HEAD, 패키지 경로만)

| 커밋 | 내용 | 필드노트 |
|---|---|---|
| 0667710 | 캡슐 상태에 나이 병기 + 24h stale 경고 (`_state_age_hours`/`_state_age_label`, `MEM1_CAPSULE_STALE_HOURS`) | #1 (F1 신선도) |
| aca67fe | task_state 검색의 무조건 +0.08 활성 보정 제거 — 활성도는 recency로만 | #2 (F2 관련성) |

사이트·연구·루프 문서 커밋들은 패키지에 실리지 않는다. CHANGELOG 0.3.5 절 초안은 준비됨.

## 실행 절차 (승인 후)

1. `pyproject.toml` version `0.3.4` → `0.3.5`, CHANGELOG의 `Unreleased` → 날짜 확정. 커밋.
2. 검증: `.venv/bin/python -m pytest -q` 전체 그린 (사이클 4 기준 192 passed).
3. 태그: `git tag v0.3.5 && git push origin v0.3.5` **[게이트]**
4. 빌드·배포: PyPI publish (기존 0.3.4 배포와 동일 경로) **[게이트]**
5. 라이브 업그레이드: `~/.forget/venv/bin/pip install -U forget_ai==0.3.5`
   → launchd 서비스 재시작 **[게이트 — 실DB 접점, 백업 선행: 헌장 원칙 4]**
6. 배포 후 검증 (P1·P3 판정 시계 시작):
   - 캡슐: 24h 넘은 task state에 stale 경고가 붙는가 (F1)
   - 세션 회상: 무관 활성 태스크(heartbeat·stance류)가 주제 무관 턴에 노출되지 않는가 (F2)
   - predictions.md P1·P3의 판정 기점을 배포 사이클로 기록

## 롤백

`~/.forget/venv/bin/pip install forget_ai==0.3.4` + 서비스 재시작. DB 마이그레이션 없음
(store.py 랭킹·표시 로직만) — 데이터 비가역 변경 없음.
