# 게이트 큐 — P4 순서 3: 도그푸드 Stop 훅 배선 (c79 적재, 게이트 대기)

사용자 전역 설정(`~/.claude/settings.json`)과 설치본(`~/.forget/hooks/`) 변경이므로
정훈 게이트(LOOP.md 원칙 5). 승인 문구 예: "P4 배선 승인" 한 마디면 실행.
**이 배선 시점부터 P4 시계가 가동된다** (컴팩션 5사건 관측 → 판정, 실패 시 롤백).

## 산출물 상태 (루프 몫 완료분)

- 순서 1 (c78): `hooks/forget_digest.py` — Stop 훅, 선제 소화. 테스트 6종.
- 순서 2 (c79): ② PreCompact 최종 플러시(`forget_capture.py` → `forget_digest.flush`,
  활성 창 보호 해제, FLUSH_MAX_BATCHES=4, 오프셋은 전송분까지만·기준선은 사건 기록) +
  ③ 임계 감시(`forget_digest`가 문자/3.2 근사로 near_threshold 추정 →
  `forget_turnrecall`이 에피소드당 1회 재부팅 권고 1줄). 테스트 7종 추가, 전체 352 passed.
- packages/forget-connect/assets 사본 동기 완료 (capture·turnrecall).
  자산에 forget_digest.py는 아직 없음 — capture의 임포트는 가드되어 있어 배포본 무해.

## 집행 절차 (승인 후)

1. 훅 스크립트 갱신 — repo → 설치본 복사 3건:
   ```bash
   cp hooks/forget_digest.py     ~/.forget/hooks/forget_digest.py
   cp hooks/forget_capture.py    ~/.forget/hooks/forget_capture.py
   cp hooks/forget_turnrecall.py ~/.forget/hooks/forget_turnrecall.py
   chmod 755 ~/.forget/hooks/forget_digest.py
   ```
2. `~/.claude/settings.json`의 `hooks`에 Stop 항목 추가 (기존 forget 항목과 동일 형식):
   ```json
   "Stop": [
     {
       "hooks": [
         {
           "type": "command",
           "command": "FORGET_MCP_URL='http://localhost:8000/mcp/forget/http/junghunkim' python3 '/Users/junghunkim/.forget/hooks/forget_digest.py'",
           "timeout": 40,
           "statusMessage": "forget: digesting aged turns"
         }
       ]
     }
   ]
   ```
3. 같은 파일에서 PreCompact 항목의 `"timeout": 10` → `"timeout": 60`
   (플러시 최악 케이스: 배치 4회 RPC — 10초로는 잘린다).
4. 스모크: 아무 세션에서 30턴+ 진행 후 `~/.forget/hooks/state/digest-<sid>.json` 생성 확인
   + `add_memory` 이벤트에 `metadata.digest='rolling-stage1'` 행 확인(소화 기억 표지 —
   `metadata.hook` 키가 **없어야** 정상: 있으면 회상 스킵 + ×0.5 강등으로 역할이 죽는다).

## 롤백 (P4 판정 실패 시)

settings.json의 Stop 항목 삭제 + PreCompact timeout 원복(10) — 두 줄.
소화된 기억은 일반 기억이므로 별도 청소 불요(서버 게이트가 이미 통과시킨 것).

## 제품 트랙 후속 (이 게이트 범위 밖, 다음 릴리스에)

forget-connect가 Stop 훅을 표준 배선에 포함하려면: `HOOK_SCRIPTS`에
forget_digest.py 추가 + `hookEntries()`에 Stop 항목 + assets에 파일 동봉 +
PreCompact timeout 기본값 상향. P4 판정 통과가 선행 조건.
