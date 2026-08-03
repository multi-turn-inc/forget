# 사이클 36 — backlog #8 oracle replay: 5 substantive 침묵-미스 후보 판정 (2026-08-03)

일반 사이클(N=36, N%10=6·N%5=1). 영토 규약(foreign untracked `uv.lock` 잔존 +
정훈 처분 응답 부재) → 관찰·측정 폴백. 선택 = `get_task_state` next_actions[1] 후보
**(b)** = **"backlog #8 침묵미스 5건 substantive '작업 바꿨을 항목' 판정 재생 —
회고35가 승격 판정 보류(동결), 일반 사이클에서 oracle replay로 실측 가능"**.

## 검정 대상 — 사이클 34의 침묵-미스 후보 5건

사이클 34는 loop-topic distilled 118 중 109가 회상 미도달임을 보고하며, 그 중
**5건의 substantive(≥120tok) 내구 루프 지식**을 침묵-미스 후보로 특정했다:

1. 필드노트 #1 (캡슐 신선도, 254tok) — `91a9facc`
2. 정훈의 설계 철학 (인격 = 컨텍스트 층위, 197tok) — `07ad010a`
3. 사이클 15 회고 결정 (amendment-15 recall 분리, 173tok) — `cec31dc4`
4. 사이클 3 결정 (F2 기제 store.py, 141tok) — `0fee478e`
5. 사이클 18 원인 판별 (F2 지배원인 phrase_bonus, 127tok) — `9674b10a`

단 사이클 34는 이 5건을 **회상도달**(도달=devloop-startup 쿼리 스트림 하 후보 관측)
기준으로 잡았고, backlog #8 정의("작업을 바꿨을 항목")를 만족하는지의 **판정은 보류**
(회고 35가 거버넌스 동결로 승격 보류, "일반 사이클 oracle replay로 실측 가능"). 이 사이클이
그 판정을 집행한다.

## 방법 — 실제 회상 경로(`search_memories`) 재생, $0·read-only

backlog #8의 방법은 "그 사이클의 **작업 선언문으로 검색을 재생** → 스토어에 있었던 관련
기억 대 사이클이 실제 본 것의 차집합". 로컬 스크립트 재구현 대신 **제품의 실제 recall
파이프라인(`search_memories` MCP, rerank=on, top_k=8)** 을 직접 호출 = 가장 충실한 oracle
replay(셀렉터를 재구현하지 않고 실물을 친다) + forget 도그푸딩(원칙: forget으로 forget 개발).

각 후보에 대해 그 지식이 중심이 되는 **주제-매치 작업 선언문**을 쿼리로 재생하고,
후보가 top-k에 뜨는 순위·점수를 기록. 사이클 34가 잰 것은 **generic startup 쿼리**
("session startup in `<cwd>`") 하 도달 — 이 사이클은 **need-aligned 쿼리** 하 도달을 잰다.

## 결과 — 5/5 전부 rank 1–2, 0.45 게이트 통과

| # | 후보 | 주제-매치 쿼리(요지) | best rank | score | 게이트 0.45 |
|---|---|---|---|---|---|
| 1 | 필드노트 #1 캡슐 신선도 | "캡슐 신선도 stale 유동층 굳음 현재로 제시 마찰" | **1** | 0.538 | 통과 |
| 2 | 정훈 설계 철학 인격층위 | "인격 모델 컨텍스트 층위 불변/완만/유동 캡슐 조립 정책" | **1** | 0.753 | 통과 |
| 3 | 사이클15 amendment-15 recall분리 | "amendment-15 recall 분리 task_state 검색풀 회고 결정" | **2** | 0.631 | 통과 |
| 4 | 사이클3 F2 기제 store.py | "F2 회상오염 phrase_bonus store.py score_memory 사이클3" | **1** | 0.794 | 통과 |
| 5 | 사이클18 phrase_bonus C1 | "F2 지배원인 phrase_bonus 무한합산 단문자/숫자 매칭 임계 비구속" | **1** | 0.920 | 통과 |

**5건 전부 need-aligned 쿼리에서 rank 1–2로 표면화**하며, 전부 턴-회상 게이트(0.45,
F2 노트 기준)를 넘는다. 사이클 34가 "회상 미도달"로 잡은 바로 그 기억들이, 필요-정렬
쿼리에서는 최상위로 돌아온다. (교차 확인: 후보 4·5는 서로의 쿼리에도 rank 1–2로 동반
표면화 = F2-기제 클러스터가 일관 검색됨; 후보 2는 후보 1 쿼리에도 rank 2 = 관련성 순서 재현.)

## 판정 — 작업-바꿨을 침묵미스 = 0 (이중 보상)

backlog #8의 silent_miss는 세 조건의 곱: (a) 그 사이클에 **관련**, (b) 사이클이 **못 봄**,
(c) 봤으면 **작업이 바뀜**. 5건 전부 (b)에서 탈락 — **이중으로**:

- **회상 채널**: need-aligned 쿼리에서 rank 1–2·게이트 통과(위 표). 사이클이 필요-정렬
  검색을 냈다면(=oracle replay가 바로 그것) 최상위로 받았다. 미도달은 **retrieval 실패가
  아니라 startup 쿼리의 주제-generic 성질**이었다.
- **디스크 채널**: 5건 전부 매 사이클 직독되는 문서에 상주 —
  필드노트#1=LOOP.md ll.36 + frictions.md F1행 / 인격철학=LOOP.md ll.22–38(인격 모델 절) /
  amendment-15=amendments/amendment-15.md + 매 gate_pending "A5 recall 분리" / 사이클3·18=
  frictions.md F2행 + notes/cycle-18-f2-root-cause.md. 회상 없이도 컨텍스트 진입.

⇒ **이 5건은 작업-바꿨을 침묵미스가 아니다(silent_misses=0).** 회상 미도달이 손실이
아님을 사이클 34가 "디스크 채널 진입"으로 이미 캐비앗했고, 이 사이클은 **회상 채널 자체도
필요-정렬 시 이들을 최상위로 낸다**를 실측으로 더한다.

## 함의 — 회상도달 계열(사이클 33·34)의 귀속 정정

이 사이클의 발견은 recall-reach 연작을 **한 축 더** 정정한다:

1. **"미도달 ≠ 미검색가능(non-retrievable)".** 사이클 33 "저장 바이트 96.7% 회상 미도달"·
   사이클 34 "distilled 80% 미도달"은 전부 **generic startup 쿼리 하** 측정이다. 같은
   기억이 need-aligned 쿼리에서 rank 1–2다. 미도달의 기전은 (사이클 34가 지목한 길이-게이팅에
   더해) **probe 자체의 주제-generic 성질** — startup 쿼리는 나쁜 탐침이다.
2. **회상도달 압축비 0.067%(사이클 33)는 startup-probe 아티팩트**임이 강화됨 —
   사이클 34 "워킹셋 아님" 결론을 유지하되 *왜*를 sharpen: 길이만이 아니라 **탐침 부정합**.
3. **길이-게이팅(사이클 34)은 startup 스트림에서만 지배** — 주제 매치가 오면 짧은 온-토픽
   루프 노트(필드노트#1 254·사이클18 127tok)도 rank 1로 올라온다. phrase_bonus 길이-편향은
   주제 신호가 약할 때(generic 쿼리)만 결정적. F2 C1과 모순 아님(같은 기전, 다른 쿼리 레짐).
4. **제품 함의(정직)**: devloop의 **startup 캡슐이 generic 쿼리를 쓰는 것**이 5건 미표면화의
   실인(實因). 일반 유저의 **turnrecall은 실제 프롬프트(=주제-정렬)로 검색**하므로 이 5건류를
   rank 1–2로 받는다 — 즉 이 oracle replay는 next_actions 후보 **(a) turnrecall 경로**의
   프록시이기도 하다(turnrecall ≈ 주제 쿼리, startup ≈ generic 쿼리). "회상이 스토어를 거의
   안 건드림"은 startup 경로의 진실이지 turnrecall 경로의 진실이 아닐 수 있음.

## 정직성 캐비앗

- **rerank=on**: startup 캡슐 조립이 rerank를 쓰는지 미확인 — 이 측정은 "원리상 검색가능"을
  보이는 것(retrievability-in-principle). rank는 rerank 후. 게이트 통과는 base score 기준이라
  덜 취약(1·2·4·5는 0.53+, 3은 0.63).
- **현재-스토어 재생**: 각 후보의 home 사이클 당시 스토어가 아니라 **오늘 스토어**(자동캡처
  홍수 후)에서 재생 — 완전한 시간여행 replay 아님. 단 5건 전부 홍수 이전 생성이고 여전히
  rank 1–2 = 성장이 이들을 묻지 않음(오히려 반증: 홍수가 관련 기억을 밀어냈다면 순위가
  내려갔어야). 사이클 29·32의 crowd-out 반증과 정합.
- **판정 범위**: 이 5건(사이클 34가 특정한 substantive 후보)에 한정. "침묵미스는 없다"는
  일반 주장 아님 — 진짜 침묵미스는 디스크 채널에도 없고 need-aligned 쿼리에도 안 뜨는
  지식일 것(devloop 디스크-중심 아키텍처에선 루프-내부 지식에 드묾; **디스크 없는 유저-대면
  forget에선 회상 채널 단독이 유일**하고, 거기서 결과는 안심: 주제-정렬 turnrecall이 rank 1–2).
- oracle replay 방법(주제-매치 search_memories) 재사용 가능 — 이 사이클이 실연.

## 거버넌스

거버넌스 동결(회고 25) 준수: **새 유형·새 스키마·새 amendment·새 A-항목 무제안.**
backlog #8은 헌장(승인)이 명시한 측정이고, 이 사이클은 그 **판정을 집행**할 뿐이다.
단 backlog #8 문구의 "metrics에 silent_misses 필드 추가"는 스키마 변경이므로 **동결 하
보류** — silent_misses=0을 metrics `work`/`gate_pending`에 인라인 보고하고, 전용 JSON
필드 신설은 회고/정훈 게이트(회고 35 "metrics fixed_verified 분리"와 동일 처분). 기존
recall-reach/backlog#8 클러스터(frictions.md)에 판정 첨부.

## 산출

- `notes/cycle-36-oracle-replay-silent-miss.md` (이 파일; 5 쿼리·순위·점수 재현 기재)
- `frictions.md` recall-reach 클러스터에 사이클 36 판정 첨부(backlog#8 5건 = silent_miss 0)
</content>
</invoke>
