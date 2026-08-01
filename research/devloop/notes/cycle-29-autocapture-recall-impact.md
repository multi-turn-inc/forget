# 사이클 29 — 자동캡처 레이어의 실제 회상 선택 영향 (F2 가설 검정, 2026-08-02)

일반 사이클(N%10=9·N%5=4). 영토 규약(foreign untracked `uv.lock` 잔존 → 코드 사이클
금지) + frictions-first이나 F2·F7 견고 fix 전부 정훈 게이트 → 관찰·측정 폴백. 선택 =
`get_task_state` next_actions[0] 후보 (b') **자동캡처 F2영향 실측**.

## 검정 대상 (사이클 28이 남긴 미검증 가설)

사이클 28은 도그푸드 스토어가 536→3030으로 급증했고 그 82%(2492)가 SessionEnd/
PreCompact 자동 캡처임을 발견하고, `frictions.md`에 **미검증 가설**을 남겼다:

> (b) **회상 풀에 저신호 세션 요약 2492건을 추가해 F2 관련성을 악화**시킬 수 있음
> (가설, 미검증) — 자동 캡처가 distilled 관련 기억을 밀어낸다(crowd-out).

이 사이클은 그 가설을 **실제 회상 파이프라인 출력**으로 검정한다 — 사이클 21의 퇴화
재생(projection)보다 강한 관측.

## 데이터 ($0·로컬·읽기전용 mode=ro, 스크립트: `scripts/autocapture_recall_impact.py`)

`context_traces` 테이블(3295행, `selector-policy-v1.1`, 2026-07-22~08-01). 각 행 =
실제 recall/assemble 1회의 `candidate_ids`/`selected_ids`/`rejected_ids`/`scores`(dict)/
`roles`(dict). `filters`가 스코프를 junghunkim×forget으로 고정. 후보를 role별로 분류:
role=task_state(claims 소속) / role=general → 사이클 28과 **동일 classify**(metadata.hook
∈ {SessionEnd,PreCompact} 또는 텍스트 "세션 캡처" 시작 = auto_capture, 나머지 distilled).
자동캡처 유입 경계(2026-07-31T00:00Z)로 pre/post 세그먼트.

## 결과 — 핵심 표 (post-flood 세그먼트, 2406 traces, 단일 정책/스케일 regime)

| layer | cand% | sel% | sel_rate | cand_median | sel_median |
|---|---|---|---|---|---|
| auto_capture | 28.9% | 24.3% | 58.3% | **0.4456** | 0.4462 |
| distilled | 70.0% | 74.9% | **74.2%** | **0.5214** | 0.5308 |
| task_state | 1.1% | 0.8% | 53.0% | 0.5106 | 0.5371 |

- **자동캡처는 회상 파이프라인에 실제로 도달한다** — post-flood 후보 풀의 28.9%,
  1365/2406(57%) 트레이스에 후보로 등장. 가설의 전반부(대량 유입이 풀에 들어온다)는 참.
- **그러나 선택 레이어가 체계적으로 강등한다**: 자동캡처 median 0.4456 vs distilled 0.5214
  (거의 임계 위), 선택률 58.3% vs 74.2%, 후보 지분(28.9%)보다 선택 지분(24.3%)이 **낮음**
  (de-selection), distilled는 반대로 70.0%→74.9%로 **증폭**.
- **crowd-out 대칭 검정**(post-flood): 자동캡처 SELECTED가 distilled REJECTED를 점수로
  이긴 쌍 = **3,576** vs 그 역(distilled SELECTED가 자동캡처 REJECTED를 이김) = **11,657**.
  순 변위가 distilled 편으로 **약 3.3:1** — 밀어내기는 반대 방향으로 일어난다.

## 일별 강건성 (단일-일 인공물 배제)

| day | auto_n | auto_med | auto_selr | dist_n | dist_med | dist_selr |
|---|---|---|---|---|---|---|
| 2026-07-31 | 6111 | 0.4457 | 59.5% | 6353 | 0.4930 | 79.0% |
| 2026-08-01 | 858 | 0.4448 | 49.3% | 10518 | 0.5256 | 71.4% |

두 유입일 모두(각각 수천 후보) distilled가 자동캡처를 median·선택률에서 일관 압도 —
발견은 **일 단위로 안정**(단일 트레이스/단일 일 몰림 아님).

## 판정

1. **가설 b(자동캡처가 distilled를 crowd-out해 F2 악화)는 선택 레이어에서 반증된다**
   (일 단위 안정). 자동캡처는 풀에 들어오나 distilled 아래로 랭크되고 de-select되며, 순
   변위는 distilled 편 3.3:1. 셀렉터는 유입에 밀리는 게 아니라 유입을 강등한다.
2. **잔여 관측(정직):** 그럼에도 post-flood 회상 **출력의 24.3%가 여전히 자동캡처**(4061건
   선택 인스턴스), 선택 임계에 밀착(sel_median 0.4462). "crowd-out"은 아니나 회상 슬롯의
   ~1/4를 저신뢰 자동캡처가 점유 = 출력 조성의 실질적 희석. 그 marginal 자동캡처가
   주제 관련인지는 **점수만으로 판별 불가**(내용 읽기/관련성 라벨 필요 — 향후 측정).
3. **교란 명시:** pre/post 경계가 점수 스케일 이동(distilled cand_median 0.3762→0.5214,
   reembed/regime)과 겹침 → pre/post 델타(예: distilled 선택률 53.5%→74.2%)는 유입에
   깨끗이 귀속 불가. 깨끗한 증거는 **post-flood 내부/일 단위** 비교뿐.
4. **F2 방향 재조정:** 자동캡처 **볼륨은 F2 레버가 아니다** — 사이클 18 확정 원인(C1
   phrase_bonus × 고정 devloop 프롬프트 토큰 프로필)과 정합. 사이클 28의 "유입이 F2 악화"
   우려는 **강등**된다(볼륨 아닌 특정 junk 임계 초과가 F2의 기전).

## 정직성 캐비앗

- context_traces는 `session startup`/autopilot 조립 경로 중심(query 필드 확인) —
  forget_turnrecall(턴 회상)과 완전 동일 경로가 아닐 수 있음. 단 둘 다 동일 셀렉터
  (`selector-policy-v1.1`)를 통과하므로 랭킹 성질은 공유. 경로별 분해는 향후 측정.
- "distilled"에 이 사이클 add_memory 6건 + 07-31 이후 [devloop] 노트가 포함 —
  distilled 지분을 미세 상향(비율 영향 무시 가능, 사이클 28과 동일 근사).
- 판정은 **랭킹/선택**에 관한 것 — 선택된 자동캡처의 **내용 관련성**은 미측정(잔여 2).

## 산출

- `scripts/autocapture_recall_impact.py` (재현 가능, 표준 라이브러리만; read-only mode=ro)
- `notes/cycle-29-autocapture-recall-impact.md` (이 파일)
- `frictions.md` 자동캡처 유입 관측 갱신(가설 b 선택-레이어 반증 + 잔여 희석 실측)

## 거버넌스

거버넌스 동결(회고 25) 준수: 새 amendment·새 스키마 필드·새 유형 등록 **무제안**.
기존 미분류 관측(자동캡처 유입)에 증거를 붙여 가설을 강등할 뿐 — 유형화·처치는 회고/정훈 게이트.
