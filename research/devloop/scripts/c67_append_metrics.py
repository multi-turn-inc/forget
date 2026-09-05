#!/usr/bin/env python3
"""사이클 67 원장 append (c64~c66 전례 승계 — 한글 산문을 셸 인용에 맡기지 않는다).

멱등: cycle=67 행이 이미 있으면 아무것도 하지 않는다.
"""

from __future__ import annotations

import json
import os

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
LEDGER = os.path.join(REPO, "research", "devloop", "metrics.jsonl")

ROW = {
    "cycle": 67,
    "date": "2026-08-07",
    "restore_turns": 3,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, **일반 사이클**(67%10=7·67%5=2). 턴 원장: **턴1 LOOP.md+cycle-prompt.md Read "
        "+ ToolSearch 묶음** / 턴2 get_task_state + c48_step0_check.py + git status 병렬 / "
        "**턴3 = 첫 유효 행동**(작업 단위 P21 배선 확정 + 대상·공여 코드 정독). 포함 계상 **3**. "
        "**P20 (a) 표본 2/4, 지지 방향** — floor **3**, 초과분 **0**. c65의 4에서 내려온 c66의 3이 "
        "재현됐다. A-65.1 미승인이라 원장에 floor 필드가 없으므로 절대값 3을 대리 지표로 쓰며 "
        "그 대리 사용을 P20 규정대로 이 줄에 명기한다. 자[尺] 공지(방향 중립 의무): 계상 규약은 "
        "c61 이후의 **포함**이며 이 사이클에서 바꾸지 않았다. "
        "grade full 근거: 캡슐 next_actions[0](턴 계획)·[1](P21 배선 = 1순위, **공여 코드 위치까지 지정**)·"
        "[2](계수 의무)만으로 재구성 0턴에 착수 — 원장의 '채취 코드는 이미 있다: c66_body_identity.py와 "
        "c66_denominator_probe.py에서 옮기면 된다'가 그대로 맞았다. "
        "**★ F-절차0 14회차 — 이 손이 위반했다(정직 기재).** 턴2 영토 검사 명령에 "
        "`tail -2 research/devloop/metrics.jsonl`을 덧붙였다. 금지문은 두 채널(캡슐·스크립트 배너)로 "
        "도착했고 같은 턴에 출력받았다. **번호는 스크립트에서 얻었으므로 목적 (a)는 위반되지 않았으나 "
        "목적 (b)(26KB 컨텍스트 비용)는 전액 지불됐다** — '번호에 안 썼으니 무해'는 성립하지 않는다. "
        "**이 위반이 c61의 예고 실험을 완성한다**: 절단 불가 채널은 작동했는데도(N을 스크립트에서 획득) "
        "위반이 일어났으므로 **남은 원인은 지시서 절차 0 문면('마지막 줄에서 N') 단독으로 확정된다** — "
        "턴1에 그 문면을 읽고 턴2에 실행했다. → **A-55.1의 근거가 '약화'에서 '실측 표본 1건'으로 승격.** "
        "c66의 P16 (a) 5/5 판정(창 c62~c66)은 소급 변경하지 않으나, 거기서 파생된 "
        "'그림자 처치가 작동하므로 문면 교체는 덜 급하다'는 해석은 c67이 반증한다. "
        "계열: c49 관측('도착한 규약을 손에 쥐고 위반')의 직계이며 차이는 원인이 문면으로 좁혀진 것."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A(audit-60 R1 확정) **7행째** — 성분 분해 병기(P15 (b) 이행). "
        "**능동 검색 0회**(search_memories 직접 호출 0 — 작업이 디스크·프로세스·라이브 서버 1차 증거 감사였다). "
        "**주입 4건 = 캡슐 hit 1 + 훅 주입 3건 miss.** "
        "**캡슐 hit 1**: next_actions[0](턴 계획)·[1](P21 배선 = 1순위 + 공여 코드 파일명 2개 + '출력 3줄 이내' "
        "상한 + 근거 위치)이 작업 단위와 턴 배치를 함께 결정했다 — 캡슐 hit **4행째**. "
        "**훅 주입 3건 miss**: c43 발견·c42 결정+발견·c45 발견. 전부 [devloop] 온토픽이고 "
        "**c43은 이번 작업과 주제가 정면으로 겹쳤다**(도그푸드 :8000 임베딩 스택 감사, 3149행 중 3146이 384차원) — "
        "그런데도 miss로 계상한다: 스토어 차원은 이 사이클이 embedding_space_audit.py로 **직접 실측**했고"
        "(384 n=3619), 주입은 그 부분집합이며 행동을 바꾸지 않았다. c21 엄격 규칙 유지. "
        "**주목 — 2사이클 연속 헤드라인이 기억 채널로 도달 불가한 사실이었다.** c66은 몸의 교체(스토어에 "
        "기록된 적 없음), c67은 라이브 서버의 자기 보고 모순(관측 31, `get_provider_health` 응답에만 존재). "
        "회상 품질을 아무리 올려도 도달할 수 없는 부류이고, 이것이 관측 30·31의 수용 기준이 모두 "
        "'기억'이 아니라 **'계기가 매 사이클 말하게 하라'**인 이유다."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "**관측 31 신규 등재 (관측 30의 하위 기전)**: 몸의 자기 보고가 임베딩 스택을 **두 개로** 말한다 — "
        "`checks.embeddings` = {local, **deterministic-128**, status:\"ok\"} 대 "
        "`effective` = {fastembed, BAAI/bge-small-en-v1.5, resolution:\"auto-default (unconfigured + "
        "fastembed importable)\"}. **진실은 effective**(1차 증거: 스토어 dim=384 n=3619, dim=128은 3행뿐 — "
        "bge-small=384, deterministic-128=128. 독립 채널 2개 일치: embedding_space_audit 전행 디코드 + "
        "step 0의 length(embedding) 집계 MEB1:384). **버그가 아니라 설계이고 그래서 더 위험하다** — "
        "checks는 저장된 설정의 거울(providers.py:43 기본값)이고 provider_runtime.py:779-784에 의도가 "
        "주석으로 남아 있다('what actually runs, not what was stored — the LME-V2 run-1 lesson'). "
        "진실 채널은 이미 있으나 **추가 필드**로 붙었고, 'health' 응답에서 checks를 읽는 자연스러운 독법은 "
        "**LME-V2 1차 풀런을 무효화한 그 이름을 무경고로 반환**한다. 원칙 3의 '스택 병기'를 이 응답에서 뽑으면 "
        "틀린 스택을 성실하게 병기한다. **상위/하위 관계**: resolution='auto-default'는 임베딩 공간이 설정이 "
        "아니라 **fastembed import 가능성**으로 결정된다는 뜻 → **설정 변경 0·재임베딩 0·커밋 0으로도 공간이 "
        "뒤집힌다**(의존성 설치/제거만으로). 관측 30이 '몸이 바뀐 걸 원장이 몰랐다'면 31은 '왜 몸의 정체를 "
        "묻기 어려운가'다. **c66 귀속을 대체하지 않는다** — 두 경로(fd30a68 질의측 수리 / resolution 전환)가 "
        "모두 열려 있다는 것이 발견이고 어느 쪽이 c66 사건의 원인이었는지는 판정하지 않았다. "
        "**frictions_fixed 0 — 판단을 노출한다**: 관측 30의 수용 기준(지문 3종 출력 + 재교정 표시)은 "
        "기계적으로 충족됐고 테스트로 고정됐다. 그러나 등록 기준의 ②'프로세스 기동 시각'을 내가 "
        "**의도적으로 대체**했으므로, 내 대체를 내가 '충족'으로 채점하는 것은 LOOP.md가 경고하는 순환이다. "
        "따라서 fixed를 올리지 않고 c70 감사/다음 손에게 남긴다. 관측 31은 계기에만 반영(두 필드 병기 + "
        "resolution을 지문 1급 항목으로), **제품 미수정**(관찰 우선 + 작업 단위 하나)."
    ),
    "tests": (
        "**301 passed**, 1 warning in 10.17s — 294 → 301(**신규 7건**). "
        "**제품 코드 0행**: 변경은 계측기(research/devloop/scripts/c48_step0_check.py) + "
        "신규 테스트(tests/test_devloop_body_fingerprint.py) + baseline(body-fingerprint.json) + 문서. "
        "294는 c63~c66 4사이클 동수였고 이번에 처음 올랐다 — **c64가 c65 후보로 남긴 '계측기 파싱 로직을 "
        "순수 함수로 떼어 테스트'(c65·c66 재이월)의 부분 이행**이다: `compare_fingerprint`를 순수 함수로 "
        "분리해 7건으로 감시한다. 다만 **부분**임을 명기한다 — part_n/part_a/part_b의 파싱 로직은 여전히 "
        "미커버이므로 그 항목은 c68 이후 후보로 남는다(4회 재이월). "
        "7건의 절반 이상(4건)이 단일 성질만 지킨다: **채취 실패를 '일치'로 보고하지 않는다**(3값 판정 — "
        "일치/재교정 필요/**판정 불가**). 계측기 거짓 음성 8종 전례에 대한 사전 방어다. "
        "baseline 비결정성 유지(c24 계측 0.114% 확률적 flaky, 결정화 처치 **43사이클째** 게이트 큐)."
    ),
    "work": (
        "**P21 처치 배선 (c66 선등록, 무게이트, 원장 1순위)** — step 0이 매 사이클 도그푸드 :8000의 "
        "**몸 지문**을 채취해 git 추적 baseline과 대조하고, 다르면 게이트 상수 의존 계기를 "
        "**'재교정 필요'**로 표시한다. 산출: `c48_step0_check.py:part_body()` + 순수 함수 "
        "`compare_fingerprint()` + `research/devloop/body-fingerprint.json`(baseline, 필드별 주석) + "
        "`tests/test_devloop_body_fingerprint.py`(7건) + `scripts/c67_identity_channels.py`(채널 조사) + "
        "notes/cycle-67-body-fingerprint-wired-and-two-stacks.md. 실측 출력 3줄 고정: "
        "`forget_ai-0.4.0 inst_vs_repo=22/22 eff=fastembed:BAAI/bge-small-en-v1.5 res=auto-default "
        "checks=local:deterministic-128 store=MEB1:384` / `대조: 일치`. "
        "**설계 결정 3개**: ① baseline을 **자기 갱신 캐시로 만들지 않았다** — 변경을 조용히 흡수하는 것이 "
        "관측 30의 병리 자체다. 갱신은 커밋으로만, 그 커밋이 감사 흔적이며 `_how_to_update`에 순서를 "
        "못 박았다(원인 확정 → 의존 계기 표시 → 노트 → **그 다음** baseline). ② **미채취를 '일치'로 접지 "
        "않는다**(3값 판정, baseline에 없는 신규 키도 미채취 취급 — 지문 확장은 자[尺] 변경이므로 커밋 승인 필요). "
        "③ **등록본 이탈 1건(선언)**: 등록 ②'프로세스 기동 시각'을 빼고 `effective` 스택 + `resolution`을 넣었다. "
        "사유 = lsof/ps가 이 샌드박스에서 **승인 없이 실행되지 않음을 실측**(lsof -ti / lsof -nP -iTCP / "
        "ps -Ao 모두 차단) → 지문이 승인에 의존하면 승인 없는 런에서 조용히 미지로 내려앉아 "
        "**거짓 음성 기계 9종째를 자진 제작**하는 셈. 대체 채널은 살아 있는 몸에게 HTTP 직접 질의이고 "
        "디스크가 아니라 **적재된 런타임**을 반영하므로 원리상 더 강하다. **대가 정직 기재**: '같은 코드로 "
        "재시작'은 이제 검출 안 되고, P21 (b) 위양성 상한의 반증력도 함께 약해진다(기동 시각이 원래 위양성 "
        "원천이었으므로 오발 0은 **약한 지지**일 뿐) — 이 약화를 predictions.md에 선등재했다. "
        "**발견 (예정 외) = 관측 31, 몸이 자기 스택을 두 개로 말한다** (frictions_note 참조). "
        "**배선 첫 런이 자기 결함을 잡았다**: store_vec 매직 비교가 `substr(...)='MEB1'`이었고 SQLite에서 "
        "BLOB은 TEXT 리터럴과 절대 같지 않아 항상 거짓 → 1540바이트(=4+384×4) MEB1 행을 `JSON:len1540`으로 "
        "보고했다. baseline 대조가 같은 턴에 `재교정 필요`를 띄워 잡았고 x'4D454231'로 수리. "
        "**이 표본은 P21 (a)의 증거가 아니다**(바뀐 건 몸이 아니라 계기) — 그러나 대조 장치가 실제로 무언가를 "
        "잡는다는 것과, 이 계열 결함(형식 비교가 조용히 항상 거짓 = '항상 이상 없음' 기계)이 c48 .git/HEAD · "
        "c64 porcelain 첫 행 절단에 이어 **3번째**임을 보여준다. "
        "**부수 실측(원칙 1 대조군, 게이트 재교정용 신규 대조군)**: embedding_space_audit.py가 실제 저장 벡터 "
        "200개를 질의로 써서 동일 공간 코사인 mean **0.9040**·median 0.8783·**200/200이 게이트 0.45 통과**를 냈다 — "
        "c66의 '신 스택에서 게이트 판별력 0'을 **독립 채널로 재확인**(c66은 질의 텍스트 기반, 이쪽은 저장 벡터 기반). "
        "**미이행 2건 정직 기재**: P18 (b) c63_depth_invariance 재실행은 **재이월**(게이트/점수 의존이라 "
        "상수 재교정 전 재실행은 판정이 아니라 소음 — c66 경고 승계), P10 재서술은 **5사이클 이월**(선행 조건 미충족)."
    ),
    "gate_pending": (
        "① **A-65.1** restore_turns 계상 정의 성문화 + floor 분해 + 방향 중립 공지(amendment-65 §3) — 2사이클 "
        "② **A-65.2** 거버넌스 동결 부분 해제(amendment-65 §4) — **관측 31이 다섯 번째 근거로 추가**, "
        "미분류 관측이 26·27·29·30·31 다섯으로 늘었다 "
        "③ **A-55.1 지시서 절차 0 문면 교체 — 12사이클. ★ 근거가 뒤집혔다**: c66까지 '두 채널 5연속 작동으로 "
        "근거 약화'로 보고돼 있었으나 **c67이 문면 단독 인과의 실측 표본을 냈다**(F-절차0 14회차, 절단 불가 "
        "채널은 작동했는데도 문면이 위반을 생산). **게이트 목록에서 우선순위를 올릴 것을 권고한다.** "
        "④ 개헌 채널 처분(큐 5건) — **62사이클 0/4**, 현상 유지 기각 권고 유지 "
        "⑤ 부채 캐리어 항구 소재(audit-60 R2) — 7사이클 "
        "⑥ 케이던스 전환 + 조건 (a)(b)(audit-60 R4) — 7사이클, 관측 30의 선행 조건(게이트 재교정) 유지 "
        "⑦ 그림자 규약 10건 처분 ⑧ frictions_note 사후 승인/기각 "
        "⑨ F4 픽스처 · F6 feedback/ · **flaky 결정화(43사이클째)** · launchd enforce · Sol 재검증 "
        "⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계 "
        "⑪ **게이트 상수 0.45 재교정 (c66 등재, 최우선 후보)** — 이제 **독립 대조군 2개** 보유: "
        "c66의 평탄도 게이트 spread 분포(ON 0.0109~0.0575 / OFF 0.0111~0.0272) + "
        "**c67 신규 저장 벡터 자기 질의 분포(mean 0.9040, 200/200 통과)**. 후자가 '관련 있는 것끼리의 점수 상한'을 "
        "주므로 0.45가 얼마나 낮은지를 정량화한다. 재교정 없이는 oracle replay 계열·gate_audit·score_weight_* 판정 불가. "
        "⑫ **신규 — 관측 31 제품 처치**(게이트 아님, 다음 사이클 후보): checks와 effective가 다르면 issues에 "
        "실리고 status != 'ok'. 대조군 = 둘이 같을 때 issues 빈 배열 유지(위양성 0). 제품 코드 변경이므로 영토 검사 선행. "
        "**해소 1건**: 전 사이클 ①(P11 배선)은 c66이 거짓으로 판정해 목록에서 내렸다. "
        "**무게이트: P21 배선 = c67 집행 완료. 다음 무게이트 = 게이트 상수 0.45 재교정.** "
        "정산 1줄(audit-40 R6, **22회차**): 신규 1건(⑫) 추가, 해소 1건(P11), 근거 역전 1건(A-55.1)."
    ),
}


def main() -> None:
    with open(LEDGER, encoding="utf-8") as fh:
        cycles = {json.loads(ln)["cycle"] for ln in fh if ln.strip()}
    if ROW["cycle"] in cycles:
        print(f"[skip] cycle={ROW['cycle']} 이미 존재")
        return
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(ROW, ensure_ascii=False) + "\n")
    print(f"[ok] cycle={ROW['cycle']} append, keys={len(ROW)}")


if __name__ == "__main__":
    main()
