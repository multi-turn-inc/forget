# 릴리스 큐 — 0.3.6 "the confidence release" (준비 완료, 게이트 대기)

목적: 신뢰 체크리스트(confidence-checklist.md)의 도구 항목 일괄 출하.
새 유저 3~4명 초대의 전제 조건.

## 체인지로그 초안

- **`forget-server doctor`** — 한 방 종합 판정: 서버·MCP 응답·스토어 무결성·
  스코프 오염(F4류)·훅 배선. 빨간 줄마다 처방 동봉. `--probe`(전용 스코프 왕복),
  `--report`(진단 번들 — 기억 내용 0, 유저가 읽고 직접 전송).
- **`forget-server weekly`** — 조용한 첫 주를 셀 수 있게: 이번 주 적립/정정(이력 보존)/
  게이트 거부(사유별). 숫자만, 내용 없음.
- **업데이트 알림** — doctor 안에서만, 알림까지만 (적용은 항상 유저 손. 개발 설치는 침묵).
- **install.sh 개편** — 설치가 doctor 판정으로 종료. 적색이면 exit 1 +
  "그 출력을 초대한 사람에게 보내라" (실패한 설치 = 진단 가능한 필드 리포트).
- **docs/first-week.md** — 콜드스타트 기대치 설정 (조용함은 설계, 재부팅 리추얼, 토큰 문답).

## 실행 순서 (⚠ 순서가 안전임)

1. PR #30 머지 (main-work → main)
2. `pyproject.toml` 버전 0.3.6 범프 + 태그 `v0.3.6` → Trusted Publishing이 PyPI 출하
3. PyPI 반영 확인 후 **그다음에** 사이트 배포 (install.sh가 doctor를 부르므로,
   역순이면 모든 신규 설치 실패)
4. 스모크: 새 venv에 `pip install forget-ai==0.3.6` → `forget-server doctor` 녹색 확인

## 함께 올리는 게이트: F4 정리안 (실DB — 백업 선행, 정훈 승인 필요)

역추적 결과(2026-07-31, 읽기 전용):
- `demo-redis×demo` 200건, `demo-fastapi×demo` 104건 — created_at이 2018·2025년으로
  **백데이트된 합성 픽스처** (데모 시드 스크립트가 라이브 DB에 유입)
- `demo-.×demo` 23건 — 7/9~7/20 실시간, Codex 데모 설정 유령(`…/demo`)과 일치
- `offreco×wire/registrar/scout/skeptic` 9건 — 7/27 11:51 OffReco 실험 버스트

제안: ① `cp ~/.forget/forget.sqlite3` 백업 → ② demo 3풀(327건) 삭제(합성이므로
마이그레이션 불필요), offreco 9건 삭제(실험 산출물, 전용 인스턴스 원칙 위반 유입)
→ ③ 영수증 기록 → ④ doctor 재실행으로 "scope clean" 녹색 확인.
승인 문구 예: "F4 정리 승인" 한 마디면 실행.

## 릴리스 후

- 체크리스트 ②가 녹색이 되면 남는 것: ⑥ Sol 재검증, ⑦ P1/P3 판정 (시간이 해결)
- first-week.md를 사이트로 승격할지 판단
