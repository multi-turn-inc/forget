# 롤링 응고 1단계 — 선제 소화 설계 명세 (2026-07-31, 정훈 발안 / 백로그 7)

목표 재정의(하네스 제약 반영): Claude Code 훅은 살아 있는 컨텍스트를 치환할 수 없다.
따라서 1단계는 컴팩션의 **예방**이 아니라 (a) 컴팩션의 무손실화, (b) 컴팩션보다 나은
대안(재부팅+forget 복원)의 상시 준비. 오래된 턴의 실제 치환은 2단계(자체 하네스)의 몫.

## 부품

### ① forget_digest.py — Stop 훅 (신규)
- 입력: hook stdin의 transcript_path, session_id.
- 상태: ~/.forget/hooks/state/digest-<session_id>.json — {digested_upto: <line offset>, last_run: ts}.
- 동작: 최근 활성 창(RECENT_WINDOW_TURNS=30)을 제외한 미소화 구간이
  DIGEST_BATCH_TURNS(=20) 이상 쌓이면, 그 구간에서 결정·사실·미해결·정정을 추출해
  add_memories로 적립([digest] 접두어 금지 — 일반 기억과 동일 규율, 출처 메타데이터에
  session_id·turn range 기록). 게이트는 서버 쪽 기존 파이프라인이 수행.
- 비용 규율: 배치당 1회 호출, 실패 시 오프셋 비전진(다음 턴 재시도), fail-open exit 0.

### ② forget_precompact.py 승격 — 최종 플러시
- 기존: 마지막 사용자/어시스턴트 문장만 handoff.json으로.
- 추가: 컴팩션 직전 미소화 구간 전체를 ①과 같은 경로로 소화(플러시)한 뒤 handoff 기록.
- 결과: 컴팩션 발생 시에도 손실 0 — 증발분은 forget에 있고, SessionStart(source=compact)
  캡슐이 되돌린다.

### ③ 임계 감시 — 재부팅 권고
- ①이 트랜스크립트 크기로 컨텍스트 사용률을 추정(문자/3.2 근사 + 시스템 오버헤드 상수),
  ~70% 도달 시 state에 near_threshold=true.
- forget_turnrecall.py(UserPromptSubmit)가 이 플래그를 보고 주입에 한 줄 추가:
  "컨텍스트 임계 접근 — 오래된 구간은 forget에 소화 완료. 컴팩션보다 재부팅이 낫다."
- 강제하지 않는다 — 제안 규약(캡슐과 동일: 제안이며 명령이 아님).

## 검증 (구현 전 예측 등록 — predictions.md P4)
- P4: 선제 소화 배선 후 컴팩션을 통과한 세션에서 (a) 재설명 턴 0회 유지,
  (b) 직후 세션 restore_grade full. 대조군: 배선 이전의 컴팩션 통과 세션들(트랜스크립트 실측).
  5개 컴팩션 사건 관측 후 판정. 실패 시 훅 제거(롤백 비용 = settings.json 한 줄).

## 순서
1. 루프: ① 구현 + 단위 테스트(오프셋 전진·실패 비전진·활성 창 보호) — 코드 사이클 1개
2. 루프: ② 플러시 + ③ 플래그 — 코드 사이클 1개
3. 정훈 게이트: settings.json 훅 배선(사용자 전역 설정 변경이므로 릴리스 큐로)
4. 관측 5사건 → P4 판정 → 유지/롤백
5. Codex 트랙: 훅 없음 → Sol AGENTS.md에 주기적 자기 소화 규약 제안(다음 리포트 회신에 동봉)

## 2단계 (별도 발의)
컴팩션 이벤트 자체의 폐지 — 오래된 턴을 컴팩트 라인으로 실제 치환하는 런타임.
자체 하네스 또는 업스트림 제안. 1단계 P4 판정이 근거 데이터가 된다.
