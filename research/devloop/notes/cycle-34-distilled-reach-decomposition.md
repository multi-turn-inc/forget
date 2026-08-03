# 사이클 34 — distilled 뇌의 80% 회상 미도달, 그 성질: 관련성이 아니라 길이 (2026-08-03)

일반 사이클(N=34, N%10=4·N%5=4). 영토 규약(foreign untracked `uv.lock` 잔존 +
정훈 처분 응답 부재) → 관찰·측정 폴백. 선택 = `get_task_state` next_actions[1]
잔여 후보 **(c)** = **"distilled 뇌 80% 회상 미도달의 성질 분해 — 어떤 distilled가
도달하나 (최근성·유형별)"**.

## 검정 대상 — 사이클 33의 중심 캐비앗

사이클 33은 "회상이 스토어를 거의 안 건드림(distilled 바이트 20.37%만 도달)"을
확정하면서, 판정보다 중요한 **정직 캐비앗**을 달았다: *dead-weight ≠ 무용 — 트레이스
쿼리 스트림이 devloop-startup 지배라, "미국 이주" 같은 off-topic 기억은 죽은 게
아니라 이 쿼리 분포 밖의 "보험 재고(insurance inventory)"로서 올바로 미표면화된다.*

그 캐비앗은 **반증 가능한 예측**을 함의한다: 도달 여부는 **주제-매치**로 설명돼야
한다 — loop-topic(devloop 쿼리 스트림에 관련)은 도달하고, off-topic substrate는 안
도달. 이 사이클은 581 distilled를 세 축으로 갈라 그 예측을 검정한다.

## 방법 ($0·로컬·read-only mode=ro, `scripts/distilled_reach_decomposition.py`)

- 스코프·회상도달 정의 = 사이클 33과 **동일**(load_store + scan_reach 재사용).
  **대조군 통과**: distilled 도달 78/581 = 13.43%를 정확 재현.
- **TOPIC**: loop-topic vs substrate. 게임내성 분류기(점수 독립) = metadata에
  `devloop_cycle|cycle|friction`, 또는 `track∈{devloop,self-loop,loop}`, 또는
  category `devloop`, 또는 본문 앞 60자에 `[devloop]`.
- **RECENCY**: created_at 월별 도달률.
- **LENGTH**: o200k 토큰 길이 구간별 도달률(F2 C1 기제 검정 — 사이클 18: 무한
  phrase_bonus × 장문 한국어가 길이에 바닥 점수를 준다 → 도달이 관련성 아닌 **길이
  아티팩트**일 가능성).

## 결과

### 1. RECENCY = 널 (도달은 최근성 구동 아님)

| 월 | store | reach | reach% |
|---|---|---|---|
| 2026-07 | 442 | 58 | 13.1% |
| 2026-08 | 139 | 20 | 14.4% |

노화 없음. 오래된 기억이 새 기억만큼 도달 = "기억이 회상에서 aging out" 서사 반증.

### 2. TOPIC = 반전 (사이클 33 캐비앗 예측의 역방향)

| 유형 | store | reach | reach% |
|---|---|---|---|
| loop-topic | 118 | 9 | **7.6%** |
| substrate | 463 | 69 | **14.9%** |

**substrate가 loop-topic의 ~2배 도달.** 사이클 33 캐비앗은 "off-topic은 미도달(보험
재고)"을 예측했으나, **off-topic substrate가 오히려 더 도달**한다. 도달하는 substrate는
장문 off-devloop 기억이 지배: 미국 이주 "다음 손에게"(577tok), 피봇 검증 지도(342tok),
저지 감사(289tok), pash 트윗(315tok), Codex azure(308tok). 즉 **도달 집합은 주제-매치로
설명되지 않는다** — 캐비앗의 "보험 재고" 프레이밍은 반증됐다.

### 3. LENGTH = 지배 축 (F2 C1과 정합)

| 길이(tok) | store | reach | reach% | loop-share |
|---|---|---|---|---|
| [0,20) | 60 | 5 | 8.3% | 22% |
| [20,50) | 215 | 17 | 7.9% | 21% |
| [50,120) | 178 | 21 | 11.8% | 28% |
| [120,300) | 101 | 29 | **28.7%** | 8% |
| [300,∞) | 27 | 6 | 22.2% | 4% |

도달률이 길이와 함께 **단조 상승**(8% → 29%). 길이 축에서 topic을 분리:

| 밴드 | 유형 | store | reach | reach% |
|---|---|---|---|---|
| <50tok | loop | 59 | 1 | 1.7% |
| <50tok | substrate | 216 | 21 | 9.7% |
| ≥50tok | loop | 59 | 8 | 13.6% |
| ≥50tok | substrate | 247 | 48 | 19.4% |

길이가 지배 축이나, 같은 길이 밴드 안에서도 substrate ≥ loop(topic 잔여 효과 존재 —
단 loop-topic이 파편적 마이크로-기억을 많이 포함하는 교란과 얽힘, 아래 캐비앗).

### 4. 루프 자신의 노트가 가장 덜 도달 — 침묵 미스 후보 109

loop-topic distilled 118 중 **109가 회상 미도달**(도달 7.6%). 정직한 분해:

- **45건(41%)이 <40tok 퍼-사이클 결정 파편** — "산출: scripts/…", "원칙 1 직결.",
  "$0·로컬·read-only." 같은 add_memory 스플릿 조각. 다음 사이클 task_state로 승계돼
  **복원가치 낮음**(silent-miss 아님).
- **5건의 substantive(≥120tok) 내구 루프 지식이 미도달** — 이게 진짜 침묵 미스 후보:
  - 필드노트 #1 (캡슐 신선도, 254tok)
  - 정훈의 설계 철학 (인격 = 컨텍스트 층위, 197tok)
  - 사이클 15 회고 결정 (amendment-15 recall 분리, 173tok)
  - 사이클 3 결정 (F2 기제 store.py, 141tok)
  - 사이클 18 원인 판별 (F2 지배원인 phrase_bonus, 127tok)

  루프가 **매번 재발견하는** 내구 지식이 회상엔 안 뜬다. (단 정직 캐비앗: 이들은
  frictions.md·notes/·task_state 등 **디스크 채널로는 컨텍스트에 진입** — "회상=무엇을,
  디스크=어떻게" 측정-사이클 패턴. 회상 미도달 ≠ 손실.)

## 판정

**사이클 33의 "보험 재고" 캐비앗은 절반만 맞고 귀속이 틀렸다.** distilled 80% 미도달은
"off-topic이 올바로 미표면화"로 설명되지 **않는다** — off-topic substrate가 오히려 더
도달하고(14.9% vs 7.6%), 최근성은 널이며, 도달을 지배하는 것은 **길이**(8%→29% 단조)다.
사이클 18 C1(무한 phrase_bonus × 장문)과 정합: **"회상도달"은 관련성이 아니라 기억
길이를 측정한다.**

함의(사이클 33 재구성):

1. **회상도달 압축비(0.067%)는 그 자체가 길이-편향 검색의 아티팩트** — 깨끗한 "워킹셋"이
   아니다. 도달 집합은 관련성 상위가 아니라 **길이 상위** + phrase_bonus 바닥점 수혜자다.
2. **F2 C1의 새 축**: 사이클 22는 phrase_bonus가 회상을 **오염**(junk 표면화)시킴을 봤고,
   이 사이클은 같은 기제가 **길이로 도달을 게이팅**함을 본다 — 짧고 온-토픽인 루프 노트는
   못 넘고, 길고 오프-토픽인 substrate는 바닥점으로 넘는다. F2와 이 사이클은 phrase_bonus의
   두 표현(오염 · 길이-게이팅).
3. **backlog #8(침묵 미스) 실표본**: 109 후보 중 **5건**이 substantive 침묵 미스 후보로
   특정됨(위). 45건 파편은 저가치로 배제. 단 디스크 채널 진입 캐비앗으로 "확정 침묵 미스"
   승격은 아님 — backlog #8 정의("작업을 바꿤을 항목")를 만족하는지는 회고 판정.

## 라이브 확인 — 파편화의 기제는 추출 파이프라인 (사이클 34 자기관측)

이 사이클의 결정을 **단일 substantive 기억**으로 기록(파편 대신 ≥120tok 도달률 ~29% 적용)하려
`add_memory` 1콜을 했으나, 추출 회계가 `facts_extracted: 8, memories_created: 8`을 반환 —
**파이프라인이 내 consolidated 노트를 8개 마이크로-기억으로 스플릿**했다. 즉 loop-topic 노트의
파편화(도달 7.6%, 45건 <40tok 파편)는 (내가 짧게 써서만이 아니라) **`add_memory`의 `infer=True`
기본값이 문장 단위로 사실을 쪼개는 데서 온다.** 이번 관측이 그 기제를 라이브로 확증. 잠재 처치
축이 하나 늘었다: 루프 결정은 `infer=False`로 단위 보존 기록(또는 파이프라인이 provenance-링크
사실을 검색 시 단위로 재조립) — F2 처치2(phrase_bonus 상한)와 별개 레버. 회고/정훈 게이트.

## 정직성 캐비앗

- 도달 = 로깅 트레이스에서 후보 관측 = devloop-startup 지배 쿼리 분포 하 경험적 **하한**
  (사이클 33 승계). off-topic substrate가 "이 스트림에서도" 도달한다는 사실이 오히려
  "길이가 topic을 압도"를 강화하나, 일반 쿼리 분포에서의 topic 효과는 미측정.
- loop-topic vs substrate는 topic 외에도 다르다: loop-topic은 파편적 마이크로-기억을
  많이 포함(스플릿 add_memory) → 밴드-내 topic 잔여 격차는 파편화와 교란. 길이 밴드가
  부분 분리하나 완전 분리는 아님.
- post-flood 단일 reembed regime(사이클 29·32·33 승계). pre/post 델타 귀속 불가.

## 거버넌스

거버넌스 동결(회고 25) 준수: **새 유형·새 스키마·새 amendment 무제안.** 사이클 33
회상도달 관측에 **성질 분해(topic·recency·length)**를 첨부할 뿐. 기존 처치안(퇴화 세션
캡처 억제·중복 요약 dedup)에 더해, **이번 발견이 시사하는 잠재 처치(phrase_bonus 상한/
정규화로 길이-게이팅 완화, 짧은 온-토픽 루프 노트의 회상 가시성 회복)는 F2 처치 2와 동일
레버**이나 새 처치·헤드라인 규약은 회고/정훈 게이트.

## 산출

- `scripts/distilled_reach_decomposition.py` (재현 가능, deps=tiktoken, read-only mode=ro,
  cycle-33 대조군 78/581 재현)
- `notes/cycle-34-distilled-reach-decomposition.md` (이 파일)
- `frictions.md` 자동캡처/회상도달 관측 클러스터 갱신(사이클 34 성질 분해 첨부)
- `compression-baseline.md` 회상도달 항목에 성질 분해 각주
