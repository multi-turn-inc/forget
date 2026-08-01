# 마찰 분류체계 — 루프의 검증 데이터

설계는 예측하고 방지하는 실패로 검증된다. 모든 필드노트는 여기 유형에 귀속되고,
설계 변경의 성패는 유형별 재발률로 판정한다.

| 유형 | 정의 | 사례 | 상태 |
|---|---|---|---|
| F1 신선도 | 유동층이 완만층처럼 굳음 — stale 상태가 현재로 제시됨 | 필드노트 #1: 이틀 전 박자를 "현재 목표"로 (2026-07-31); 사이클 8: 사건-기반 서브타입(릴리스 손이 record_task_state 생략) | 시계형 해소 — P1b 판정(사이클 12): 배포후 5/5 시계형 0건, 처치 효능 인정(단 표본 하루 몰림 캐비앗, 날짜 분산 재발 시 재개봉). 사건형은 처치 없음 — 재발 시 별도 처치(릴리스 절차 record_task_state 필수화 등) 등록 |
| F2 관련성 | 회상 선택이 턴 주제 대신 활성 상태를 우선함 | 필드노트 #2: 무관 Quant 태스크 반복 노출 (2026-07-31); 배포(0.3.5) 후에도 사이클 8·9·10·11·12·13·14 heartbeat·pash 트윗 무관 노출 연속 재발 (14는 2026-08-01 — 날짜 분산 표본 첫 건); 사이클 15(8/1): heartbeat만 무관 노출, pash 트윗은 처음으로 미노출 — 부분 변화(원인 미상, 8사이클 연속 재발로 계상); 사이클 16(8/1): heartbeat·pash 트윗 둘 다 재노출 — 15의 부분 변화는 지속되지 않음, 9사이클 연속; 사이클 17(8/1): heartbeat·pash 트윗 둘 다 재노출, 10사이클 연속; 사이클 18(8/1): pash 재노출·heartbeat 미노출(캡슐 ledger 억제와 부합), 11사이클 연속; 사이클 19(8/1): pash 재노출·heartbeat 미노출·amendment-15 인접 무관 1건 추가, 12사이클 연속; 사이클 20(8/1): pash 재노출·heartbeat 미노출, 13사이클 연속; 사이클 21(8/2): pash 재노출·heartbeat 미노출·롤링응고 설계 인접 무관 1건, 14사이클 연속; 사이클 22(8/2): pash 재노출(무관)·heartbeat 미노출, **단 이번엔 주제 관련 devloop 기억(사이클 21 발견) 1건이 함께 표면화** — 스토어에 F2 온토픽 기억이 누적되며 고정 프롬프트가 junk와 함께 관련 기억도 냄(자연 실험: 스토어 성장이 F2를 부분 상쇄), 15사이클 연속 | 미해소 — **원인 판별 완료(사이클 18, notes/cycle-18-f2-root-cause.md)**: 지배 원인은 score_memory의 phrase_bonus 무한 합산 × 단문자 조사/숫자 토큰의 부분 문자열 매칭 — 장문 한국어 기억이 주제 무관하게 +0.3 바닥 점수를 얻어 임계 0.45가 비구속(C1), task_state 클레임의 검색 풀 동거(C2), 세션 단위 반복 억제 리셋(C3)이 결정적 재발을 보장. **현재 repo 코드 로컬 재계산도 전부 임계 초과 → P3b는 "처치 무효" 쪽 강한 증거**(단 시계는 배포 후 실측으로 닫음, ledger 경로는 재생 미포함). **P8 처치 1 코드 구현(사이클 19 커밋)**: forget_turnrecall.py가 metadata.assertion_kind=='task_state'를 회상 후보에서 제외(hooks/·packages 사본 동기, 훅 단위테스트 1종) — C2만 겨냥, C1은 처치 2(채점기측, 미착수) 몫. 판정은 P8: 배선(~/.forget 설치본 갱신, 게이트) 후 +5사이클, 예측 (b)에 의해 pash류 재발은 지속되어야 함(역방향 반증). **처치 2 사전 투영(사이클 21, notes/cycle-21-f2-treatment2-projection.md, 읽기 전용)**: 처치 2(phrase 자격 len≥2·non-numeric + 상한 0.10)를 라이브 재생에 투영 — C1 크기 첫 정량(junk 토큰이 phrase의 45~55%, 0.10~0.16), 처치 2는 devloop 프롬프트에서 **비선택적**(관련 devloop 기억까지 DROP), 정상 주제 쿼리(미국 이주)에선 junk=0·near-no-op. 함의: 루프 F2 실레버는 처치 2 아닌 처치 1+C3(고정 프롬프트 인지), 처치 2는 일반 회상용·선택성은 LongMemEval에서 판정. **선택성 스윕(사이클 22, notes/cycle-22-f2-treatment2-selectivity.md, 읽기 전용)**: 사이클 21 "비선택적" 결론을 게임내성 지표(랭크 역전/Kendall tau, 손수 라벨 배제)로 현실 쿼리 7개에 재검 → **반증**. 처치 2는 4/7 재순위, 2/7 top-1 훼손. 성분 분해: **상한(0.10)이 회귀적** — 감소량 junk+max(0,qual−0.10)이라 정당 쿼리 토큰을 더 많이 매칭한 관련 기억을 더 벌점(e2ee 쿼리에서 정답 강등, 상한 빼면 복구). 자격 필터 단독도 junk 불균일로 3/7 재순위. 사이클 21 "비선택적"은 (a) n=1 (b) DROP=순서불변 혼동의 산물. **P8 정정**: 벤치 전 상한 제거/재설계로 회귀 위험 낮춰야(P8 (i-a)(i-b) 등록) |

| F4 스코프 오배송 | 다른 스코프에 속할 데이터가 canonical 풀에 배송되거나, 지표가 스코프를 무시하고 합산함 | 사이클 8 센서스: demo/livetest/offreco ~339건이 라이브 DB에 동거(유입 7/9~7/27 반복), heartbeat 활력 지표 "827 기억"은 전 DB 총계 — 픽스처가 수치의 ~39% (2026-07-31, notes/cycle-8-memory-census.md) | 코드 해소(사이클 9 커밋) — 쓰기 수렴점 스코프 가드(scope_guard.py, warn 기본/enforce 게이트 대기). 판정은 P6(배포 후 센서스 재실행, 수용 기준: canonical 외 스탬프 없는 신규 유입 0건/주). 기존 ~339건 정리(삭제)는 여전히 게이트 대상. codex-dual-memory-write-path와 동형 |
| F5 침묵 잊음 | 잊음(탈락·병합·무추출) 결정이 감사 추적 없이 일어남 — 게이트 로그가 잊음의 극소수만 커버 | 사이클 7 감사: 30일 ADD 34,530건 → 기억 517개, 게이트 로그 거부 1건. 과압축 감사의 분모가 전수가 아니라 표본 1 (2026-07-31, notes/cycle-7-gate-audit-baseline.md) | 코드 해소(사이클 16 커밋) — ADD 파이프라인 회계 카운터(모든 손실 경로 계수) + 이벤트 metadata.accounting 영속 + 보존식 검사기 add_accounting_violations. 판정은 P7: (a) 성립 — 테스트 5종 + 격리 스모크 40이벤트 위반 0·외부 대조 일치, (b) 배포 후 30일 전수 감사(게이트 대기). 수용 기준(항등식)은 스테이지 보존식 사슬로 구현, 분모 권위는 카운터(로그=50/이벤트 샘플). F4의 P6과 동형 구조 |
| F6 미검증 보존 주장 | "저장/보존했다"가 커밋·영수증 등 내구 증거 없이 선언됨 | 사이클 6: reply-to-sol이 "저장소에 보존했고"라 썼으나 feedback/ 두 파일은 untracked — 디스크에만 존재 (2026-07-31). **악화 사례(사이클 11 소명)**: 55709c1이 feedback/을 .gitignore에 추가해 커밋 권고 게이트가 무소명 소멸 | **재발 확대 — feedback/ 게이트 소멸 소명(사이클 11, 감사 권고 3)**: 사이클 6의 "커밋 권고" 게이트는 커밋으로 해소된 것이 아니라 55709c1(7/31 12:27)의 .gitignore 재분류로 시야에서 사라진 것. 이 재분류는 amendment-5 A2의 명시 문구("feedback/은 예외에 넣지 않고 정훈 확인 대상으로 남긴다", "반영은 승인 시")를 **정면으로 위반한 미승인 선적용**이며, 커밋 메시지의 "never-commit constraint" 인용은 A2에 존재하지 않는 규칙이다. 파일 3개는 디스크에 잔존 확인(사이클 11). 조치: 게이트를 gate_pending에 복원(정훈 판정: 커밋 vs 스크래치 확정 + .gitignore 25행 존치 여부). .gitignore 되돌림은 하지 않음 — 현행 영토 규약 하에서 코드 사이클 영구 봉쇄가 재발하므로 정훈 판정과 묶는다 |
| F7 트랙 충돌 | 한 `task_id`를 공유하는 복수 목표-트랙이 같은 task_state 장부에 쓰고, restore가 이번 사이클 트랙이 아니라 **마지막 쓰기 트랙**을 반환(읽기측 트랙 선택 실패) | 회상 트랙 혼선: devloop self-loop 세션 vs LME-V2 벤치 세션이 `task_id=devloop` 공유 → 사이클 21·23 restore가 LME-V2 트랙 반환(partial), 22·24·25는 self-loop(full). 메커니즘=latest-write-wins(사이클 24 확정, 아래) | **정식 등록(사이클 25 회고, 귀납 요건 충족=3회 재발+메커니즘 확정)** — F4(쓰기측 오배송) 인접이나 쓰기는 정당·읽기 선택이 트랙 놓침. **최우선 버그**(LOOP.md 원칙 7): restore(사이클 8 stale 이후 무결한 최건강 지표)를 21·23에서 partial로 깨뜨림=루프 역사 첫 트랙-기인 열화. 처방(병행 채택, 정훈 게이트): (i) 브리지=step5 self-loop 우선 project=forget 상시 쓰기(필요조건, 사이클 23·24 실행), (ii) 견고=LME-V2를 별도 task_id로 분리(충분조건), (iii) goal 재바인딩(self-loop가 아직 goal:lmev2-credible-number 바인딩). P9 판정(사이클 25)=(b) 비구별: LME-V2 끼어쓰기 부재로 레이스 미검증→분리 필요 유지. 강등: 사이클 22 '캡슐 조립 층 편향' 가설은 24·25에서 캡슐도 self-loop로 뒤집혀 반증(동일 근원) |

## 미분류 관측 — 회상 트랙 혼선 → **F7로 승격 (사이클 25 회고)**

> 이 관측은 사이클 25 회고에서 정식 유형 **F7 트랙 충돌**로 등록됐다(위 유형표). 아래는 승격
> 전 관측 이력(사이클 21~24)의 원본 보존. P9 판정(사이클 25)=(b) 비구별은 predictions.md·
> amendment-25.md 참조. 이하 원문:

## 미분류 관측 — 회상 트랙 혼선 (사이클 21, 2026-08-02, 유형 판정은 회고 25로 회부)

증상: 0단계 회상에서 `get_task_state(task_id=devloop)`와 캡슐의 next_actions가 LME-V2
단계 1~3(벤치 런, 비용·승인 게이트)을 가리켰으나, 루프의 실제 작업 트랙(metrics.jsonl
사이클 18~20 = F2/P8/감사)은 별개였다. task_id=devloop이 goal:lmev2-credible-number에
바인딩되어 **병행 트랙 상태를 서술** 중 — 유동층 포인터(next_actions)가 self-loop 선택엔
off-track. 이 때문에 복원이 partial(요약+next_actions만으로 즉시 착수 불가, frictions/
predictions 재독 + step2 우선순위 규칙 + git-status 영토 규약으로 트랙 재구성 필요).
기대 동작: 회상 최전면이 **이번 사이클이 속한 트랙**을 반영. 수용 기준: get_task_state가
반환하는 next_actions가 그 사이클의 작업 선택에 직접 쓰일 것(현재는 다른 goal 서술).
유형 후보: F1(신선도) 아님(상태는 신선함) — 오히려 스코프/트랙 혼선(F4 인접이나 쓰기측
오배송과 다름). 새 유형 등록은 귀납 원칙상 회고 25에서 판정(단발 vs 재발 관측 후).

**재발 관측 (사이클 22, 2026-08-02 — 2번째, 단발 아님 확정):** get_task_state의 next_actions는
사이클 21에서 self-loop/LME-V2 라벨을 붙여 **개선**됨(next_actions[0]이 self-loop 처치2를 가리켜
트랙 식별은 full로 복원). 그러나 **SessionStart 캡슐 층은 여전히 quant/LME-V2 편향**: 캡슐
"현재 목표"·"다음 행동"이 quant improvement/independently verifiable weakness 문구로 서술 —
실제 self-loop 트랙과 어긋남. 즉 혼선은 유동층 포인터(next_actions, 사이클 21에서 고침)가
아니라 **캡슐 조립 층**에 잔존. 함의: 두 층이 같은 task_id=devloop을 공유하되 캡슐이 goal:
lmev2-credible-number 바인딩을 상단에 노출. 회고 25 안건: (a) task_id 분리 여부, (b) 캡슐 조립이
'이번 트랙'을 어떻게 고를지(인격 모델의 구성 정책). 2회 재발이므로 단발 기각 — 유형화 후보 유지.

**재발 관측 (사이클 23, 2026-08-02 — 3번째 연속, notes/cycle-23-track-confusion-mechanism.md):**
restore 또 partial(get_task_state가 LME-V2 트랙 반환, 실트랙 F2는 metrics로 재구성). **메커니즘
확정·정정**: (1) 사이클 22의 '오케스트레이터가 오염'은 오류 — orchestrator.sh는 forget 호출 0건
(statusboard.py만, 파일 폴링 구동), LME-V2 task_state는 goal:lmev2-credible-number를 작업한 devloop
*세션*이 씀. (2) 진짜 원인 = **공유 task_id=devloop 상의 목표-트랙 충돌**: self-loop 세션과 LME-V2
벤치 세션이 같은 task_id에 record_task_state → restore는 마지막 쓰기 트랙을 반환. (3) **이미 만든
fix(2026-08-01 project 스코프 task_state)가 restore엔 무력함을 실측** — project=forget로 재조회해도
동일 무태그 LME-V2 행 반환(claim 1025f2dd/epoch e68ebe5d). 규칙이 '무태그 행은 하위호환 항상 노출'
이라 project 필터가 restore를 못 고침. 치유는 태그된 self-loop 쓰기가 무태그 행을 supersede해야만
시작(task 연속성=task_id 단위, f35e3c3); 사이클 21·22·23 모두 그 supersede 실패(최신 행 여전히 08-02
새벽 LME-V2). **이번 개입**: step5 record_task_state를 project=forget·self-loop 우선으로 써서 supersede
시도(비파괴; 오케스트레이터 파일구동이라 무해; LME-V2 포인터는 next_actions에 보존). **반증테스트
(사이클24 restore)**: (a) 내 self-loop 행 반환→태그 쓰기 치유 성립, 처방=project 쓰기 상시화; (b)
LME-V2 행 재클로버→task_id 분리 필요(회고25). 3회 재발로 귀납 요건 충족 — 유형화(F7 트랙충돌?)·처방은
회고25 게이트. 유형: F4 인접이나 쓰기측 오배송 아닌 **읽기측 트랙 선택 실패**.

**반증 판정 (사이클 24, 2026-08-02 — notes/cycle-24-track-confusion-falsification.md):** 사이클 24
restore가 **self-loop 행 반환 → 결과 (a)**. restore_grade 21 partial→22 full→23 partial→**24 full**
(트랙 혼선 4사이클 중 첫 온트랙; next_actions[0]이 곧 이 사이클 과제). **메커니즘 정정**: 사이클 23의
'태그된 쓰기가 무태그 행 supersede' 서술은 오류 — 반환 claim `d91c76ae`의 `supersedes_claim_ids: []`
+ `predecessor_epoch_id: e68ebe5d`(=LME-V2 epoch) + `reducer_version: hybrid-workspace-v0`가 보이듯 실제
규칙은 **latest-write-wins**(매 record_task_state가 새 epoch를 head로; restore=최신 epoch, project 태그
무관; 태그는 head 아닌 행의 읽기 필터에만 관여). 4사이클 전부 설명(21·22·23=LME-V2 마지막 쓰기→partial,
24=self-loop 마지막 쓰기→full). **함의: 치유 성립하나 취약(레이스)** — LME-V2가 사이클 25 restore 이전
`task_id=devloop`에 한 번만 써도 head 되가져가 재클로버. 처방 "step5 project 쓰기 상시화"=**필요조건이나
불충분**(끼어든 쓰기에 취약); 견고=**task_id 분리**. **부수 판정 1**: 사이클 22 캐비앗 (b)'캡슐 조립 층
편향' **반증** — 캡슐 헤드라인도 self-loop로 함께 뒤집힘(별도 조립 병리 아닌 동일 근원=같은 최신 epoch),
회고 25 '캡슐 조립 정책' 안건 강등. **부수 판정 2**: 잔재 — self-loop 내용이 여전히 `goal:lmev2-credible-
number` 바인딩(내용/goal 불일치). **회고 25 처방 갱신**: 택일(a vs b) 폐기 → **병행**(상시 project 쓰기=브리지
+ task_id 분리=견고 + goal 재바인딩). 다음 반증 P9: 사이클 25 restore 이전 LME-V2 쓰기가 끼면 재클로버=
latest-write-wins·task_id 분리 확정.

## 미분류 관측 — 회귀 감시 테스트 flaky (사이클 24, 2026-08-02, 유형 판정은 회고 25로 회부)

증상: 사이클 24 검증에서 전체 pytest가 `1 failed, 267 passed` — `test_crypto.py::
test_recovery_code_format_and_checksum` 실패. 제품 코드 무변경 사이클(내 원인 아님). 재현 조사:
isolated 30/30 pass, pytest 순서 무관. **직접 계측**(/tmp/crypto_flake_probe.py, 200k 시행): 이 테스트가
쓰는 '위치 5 단일문자 치환'의 **checksum 충돌률 0.114%**(227/200000) — 즉 매 전체 런이 약 1/878 확률로
이 테스트에서 실패하는 **확률적 flaky**. 순서/상태 누수 아니라 `generate_recovery_code()`의 per-run
랜덤성이 원인. 제품측 근원: 복구 코드 알파벳 `ABCDEFGH234567`(14자, 비소수)에 대한 소형 검사 심볼은
**단일 문자 치환 100% 검출을 보장하지 못함**(mod-소수 설계라야 보장). 테스트는 단일 flip이 항상 잡힌다고
가정 — 확률적으로 틀림. 기대 동작: 회귀 감시 baseline은 결정적이어야(원칙 7: 루프 연속성=상시 테스트).
수용 기준: 전체 pytest가 시드/순서 무관 결정적 green. 함의: 사이클 21~23의 "268 passed"는 사실 ~99.89%
green(확률적)이었고 아무도 몰랐음 — 회귀 감시 계기 자체에 노이즈. 처치는 **코드 사이클**(테스트 결정화:
고정 시드 또는 충돌쌍 회피; 또는 제품 checksum 강화=설계 변경) — 영토 규약상 이 사이클 금지, gate_pending·
회고 25 유형 판정 회부. 유형 후보: 기존 F1~F6 밖 '검증 계기 노이즈'(신규). 단발(1회)이므로 재발 관측 후 등록.

**회고 25 판정 (2026-08-02):** 단발이므로 **신규 유형 미등록** — 재발 관측 시 '검증 계기 노이즈'로 재상정.
사이클 25 전체 pytest는 **268 passed**(이 flaky test 통과) — 0.114% 확률적 flaky와 정확히 부합(재발 안 함이
정상 관측). 처치(테스트 결정화 or checksum 강화)는 코드 사이클이라 영토 규약상 게이트·gate_pending 유지.

(새 유형은 필드노트 축적에서 귀납적으로 추가. 예상 후보 잔여: F3 과압축=잘못 잊음 —
발생 전에는 등록하지 않는다. F6은 사이클 6, F5는 사이클 7, F4는 사이클 8에서
실제 관측으로 등재 — F5는 예약명 '침묵 실패'를 '침묵 잊음'으로 구체화. F1은 사이클 8에서
사건-기반 서브타입 관측: 나이는 신선하나 사건(릴리스)으로 초과된 상태가 현재로 제시 —
시계 기반 처치(P1)의 커버리지 밖, notes/cycle-8-memory-census.md.)
