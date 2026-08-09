#!/usr/bin/env python3
"""c89 원장 행 append — 절차 5 (기존 스키마 유지, 마지막 줄만 추가)."""
from __future__ import annotations

import json
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "metrics.jsonl"

ROW = {
    "cycle": 89,
    "date": "2026-08-10",
    "restore_turns": 4,
    "restore_grade": "full",
    "restore_note": (
        "무기억 세션, 일반 사이클(89%10=9·89%5=4, 스크립트 정본). **c89는 한 사이클을 "
        "4세션에 걸쳐 완주** (1세션: 선등록 eef5a06 직후 사망 / 2세션: 관찰 4b11b8c 후 "
        "스윕 5/42에서 사망 / 3세션: 스윕 재개·완주 + J1·J2·J3 판독 + 정정 집행까지 하고 "
        "**커밋 0으로 사망** / 4세션=이 세션: 독립 검시 후 수확). 턴 원장: 턴1 LOOP.md+"
        "cycle-prompt.md Read / 턴2 ToolSearch(5스키마)+**metrics tail(규약 위반, 관측 42 "
        "재발 4호)**+git status / 턴3 get_task_state+c48_step0_check / 턴4 첫 유효 행동"
        "(JSON 구조 검시 = 판독 착수) = floor **4**. ★ 경고 **배달** 21연속 / 준수 실패 "
        "**4연속**(c88부터 시작한 준수 카운터 0/4). **grade full**: task_state가 c89 중간 "
        "체크포인트 #2를 서빙했고 그 안의 **자기 무효화 조건**(\"c89_dual_payload.json이 "
        "존재하면 이 체크포인트는 무효 — 남은 일은 판독·정정·수확\")이 그대로 발화했다 — "
        "파일 존재 확인 1회로 blockers의 '스윕 진행 중'이 무해하게 폐기됐고, 남은 "
        "next_actions 6개가 전부 현재·정확·즉시 착수 가능이었다. **P26 (a) 처치(자기 "
        "무효화 조건 명기)의 두 번째 표본이자 첫 완전 발화** — c88·c89 2세션은 stale을 "
        "1턴 내 '검출'했지만 이 세션은 검출조차 불필요했다(조건문이 미리 판정을 내려둠). "
        "정직 병기: 3세션이 판독·정정까지 마쳐 두었으므로 이 세션의 복원 난이도는 낮았다 "
        "— full 채점의 관대함 여부를 감사 90에 자기 지정한다. [Body] 대조: 20/22 "
        "**일치**(기대값, 제품 코드 무변경)."
    ),
    "recall_hits": 1,
    "recall_misses": 3,
    "recall_note": (
        "정의 A 29행째, 정본 형식: **능동 0회(hit 0·miss 0) / 주입 4건(hit 1·miss 3)**. "
        "능동 0 정직 근거: 이 세션의 need(스윕 완료 판정 · J1·J2·J3 수치 · 정정 집행 "
        "여부)는 전부 **1차 증거 정독**으로 충족됐다 — 산출물 JSON rows 42행, c88 원자료, "
        "git diff, 공표 사이트 4곳. 검색을 쓸 결핍이 없었다(오히려 이 사이클의 규율은 "
        "'전언 대신 원자료'였으므로 검색은 부적절한 도구였다). 다중 세션 이중계상 방지: "
        "주입은 **완주 세션 것만** 계상(3세션 주입은 행 append 전 사망으로 소멸 — 그 "
        "세션의 계상 계획을 이 행이 흡수). 주입: 캡슐/task_state **hit 1** — 자기 무효화 "
        "조건이 첫 행동을 결정했다(스윕 재실행이 아니라 판독으로 직행). 훅 3건"
        "(c43·c42·c45) miss — 동일 트리오 **25행째** 회전(record_context_outcome 기록, "
        "selection_failure). §5-2 이분법 성분: 훅 miss 3 = 채널 선택 실패; 능동 팔 표본 "
        "0이라 이분법 비해당. R4 포화 표지: (1·5)→(1·3)은 능동 팔 미가동에 의한 조성 "
        "변화이지 포화 이탈이 아니다. part_recall 검산(step0): 직전 행 c88 fields(1·5) vs "
        "성분(0·2/1·3) **일치**(기대값). 다음 행(c90=적대 감사) 검산 기대값: "
        "fields(1·3) vs 성분(0·0/1·3)."
    ),
    "frictions_logged": 2,
    "frictions_fixed": 1,
    "frictions_note": (
        "logged 2(4세션 몫) — ① **관측 45 신규**: 공표한 수의 정의가 기록되지 않았다. "
        "정정으로 올린 수염 p10 9,687 / p90 14,988이 `statistics.quantiles(n=10)` "
        "기본값(exclusive) 산출물인데 관례가 산출물·노트·차트 어디에도 없어, 4세션의 "
        "독립 재계산(nearest-rank)이 9,698 / 14,926으로 어긋났다(11.2 / 62.3 tok). "
        "관측 40('숫자를 낳은 파라미터가 숫자 옆에 없다')의 통계판 — **정정 사이클이 "
        "'측정된 적 없는 추정'을 폐기하면서 그 자리에 '정의가 안 적힌 수' 둘을 올렸다**. "
        "② 관측 41 재발 2건 추가(cd 포함 복합 명령 · python -c 힙독 오탐 차단, 우회로 "
        "존재·손실 0) → **n=5**. fixed 1 — 관측 45 수용 기준 ① 즉시 집행: 공표 사이트 "
        "2곳(compression-baseline.md 2개소 · rate_distortion_chart.py docstring+SVG 각주)에 "
        "관례 명기, 차트 캔버스 505→520으로 확장해 6번째 각주 줄 잘림 방지, 재생성 검증"
        "(마지막 줄 y=509 < 520). 검시 계기가 두 관례를 나란히 출력하므로 다음 사이클은 "
        "어긋남을 드리프트로 오진하지 않는다. **3세션 몫은 이 행에 흡수하되 재계상하지 "
        "않는다**(관측 42 재발 3호·관측 44·P27은 커밋 d743607로 이미 등재 완료). "
        "관측 42 재발 4호는 restore_note에 기재하되 logged 미계상(동일 관측의 4번째 "
        "재발이며 3호에서 무처치 대조군을 이미 닫았다 — 중복 계상 방지). 거버넌스 동결 "
        "준수: 신규 유형 미등록, 관측 45 유형 판정 회부."
    ),
    "tests": (
        "**373 passed**, 1 warning in 11.79s — 제품 322 + 계기 51(R2 병기). c88 대비 증감 "
        "0(제품·테스트 코드 무변경 — 신규 파일은 검시 계기 c89_verdict_recheck.py와 이 "
        "append 스크립트, 나머지는 노트·frictions·공표 사이트 문면). 기존 단언 완화 0건. "
        "소요 11.79s는 c88의 35.94s와 달리 스윕 미실행 상태의 값(c87 7.79s와 동류) — "
        "c88의 지연이 CPU 경합이었다는 사후 확인."
    ),
    "work": (
        "**일반 사이클 — 측정 ②-b 완주: dual 경로 회상 페이로드 실측으로 공표 숫자 "
        "1.2–2k tok을 폐기하고 12,363 tok으로 정정.** 4세션 분업: 1세션 선등록 / 2·3세션 "
        "스윕·판독·정정 / **4세션 = 독립 검시 + 수확**. ① **J1 out-of-range 확정** — dual "
        "중앙값 **12,363 tok**(p10 9,687 · p90 14,988 · min 6,303 · max 20,180 · mean "
        "12,358.6), 공표 상한 2,000의 **6.18배**. 분해: obs층 2,331 + raw층 9,960 — "
        "**페이로드의 80.6%가 원시 턴층**인데 옛 추정은 압축 진술층만 상상했다(틀린 것은 "
        "계수가 아니라 구성). ② **J2 out-of-range** — obs층 항목당 38.85 tok vs c88이 "
        "유도해 둔 반증 조건 11.8–19.6(2.0–3.3배 초과). J1과 다른 층·다른 정규화인데 같은 "
        "방향 → 단일 지표 오류 가능성 배제. ③ **J3 예측보다 강하게 통과** — raw42 중앙값이 "
        "c88 k=42와 9,960.5로 일치했을 뿐 아니라 **42/42 문항별 전수 일치(delta 0)**. 서로 "
        "다른 DB에 독립 재인제스트·독립 검색인데 동일 42건을 동일 순서로 회수 = 계기 "
        "드리프트 0·검색 결정론성 확인. 이것이 J1의 6.2배를 계기 결함이 아니라 실체로 읽을 "
        "자격을 줬다(**선등록의 값은 규율이 아니라 해석력**). 가산성 42/42·앵커 항등식 "
        "이탈 0. ④ **정정 집행**(저장소 내부, 무게이트): compression-baseline.md · "
        "token-overhead.md(유저용 한 줄 포함) · rate_distortion_chart.py · rate-distortion.svg "
        "재생성 — '2%를 남기고'→**~11%**(12,363/115,000=10.75%), '1/57'→**1/9**, 압축비 "
        "9.3배. **결론의 방향은 생존**: 토큰 1/9로 +17.8pp. 죽은 것은 자릿수이지 '압축은 "
        "손실이 아니라 증류'가 아니다. 사이트·README 미승격 상태에서 잡아 **외부 정정 부채 "
        "0** — 게이트가 실제로 값을 한 지점. ⑤ **4세션 독립 검시**(신규 계기 "
        "c89_verdict_recheck.py, 읽기 전용): 3세션의 verdicts 블록을 무시하고 rows 42행에서 "
        "A~F 7항목 전부 재계산 → **ALL PASS**. 판정자=검산자 순환을 서로 다른 무기억 세션 "
        "둘로 끊었다(독립성 충분 여부는 감사 90에 자기 지정). ⑥ **관측 45 신규**: 그 검시가 "
        "유일하게 잡아낸 어긋남 — 공표 수염의 분위수 관례 미기록(exclusive vs nearest-rank "
        "62 tok 차). 즉시 처치 완료. ⑦ 관측 44 계기 개정 반영 확인: 산출물 meta.body에 "
        "`store_vec_first_instance: \"not-run(resumed)\"` 명시 기록됨(공백을 공백으로 "
        "기록 — 수용 기준 ③ 집행). 몸(원칙 3): fastembed:BAAI/bge-small-en-v1.5 · "
        "신척도(c72+c81) · 전용 DB tmp/c89_bench_dual.sqlite3 · **스토어 벡터 MEB1:384 "
        "live 117행**(3세션이 런 중 대역 외 읽기전용 프로세스로 회수 — 런 종료 후엔 스코프 "
        "DELETE로 복구 불가능했던 증거) · :8000·8600·8601 무접촉 · repo_head 4b11b8c. "
        "**LLM 호출 0 · 외부 비용 $0**(observations/ 캐시 전용) · 실DB 무접촉 · elapsed "
        "3,136s · 라이브 접촉 = 규약 쓰기(add_memory·task_state·record_context_outcome)뿐."
    ),
    "gate_pending": (
        "① A-65.1 restore_turns 계상 성문화 — 16사이클(floor 4 연속 2행; 관측 42가 턴 "
        "최소화 유인의 부작용 표본으로 누적 n=4) ② A-65.2 거버넌스 동결 부분 해제 — "
        "16사이클·재상신 대기 ③ A-55.1 지시서 절차 0 문면 교체 — 26사이클 · **위반 4건 "
        "생산**(c89 3세션이 무처치 대조군을 n=3에서 닫았고 4세션이 4호를 추가). P27이 "
        "판정 규칙을 선등록해 두었으므로 승인 즉시 시계 가동 — **문면 한 줄 교체로 "
        "닫히는 최저비용 항목** ④ 개헌 채널 처분 — 76사이클 0/4 ⑤ 부채 캐리어 — "
        "21사이클 ⑥ 케이던스 전환 — 21사이클 ⑦ 그림자 규약 10+1건 ⑧ frictions_note "
        "사후 승인/기각 ⑨ F4 픽스처 · F6 feedback/ · launchd enforce · Sol 재검증 "
        "⑩ 라이브 배포 1건 → P6·P3b·P7b 3시계(72·70·65사이클) + ⑮ 배포 영수증 + 관측 33 "
        "라이브 재측정 — 단일 최대 레버 ⑫ 관측 31 ⑭ 평탄도 margin 처치 설계 ⑱ 예측 처분 "
        "규약 성문화 ⑲ 관측 36 제품 처치 · 관측 37 trace 마스킹 ⑳ A-75.1·A-75.2·A-75.3 · "
        "A-85.1(블라인드 복원 프로브) ㉑ P4 순서 3 settings.json Stop 훅 배선 — 산출물 "
        "완성, 게이트 대기 ㉒ 처치 2(자격 필터) 벤치 판정 — LongMemEval 풀런 승인 필요 "
        "㉓ 관측 41 하네스 경로 검사 오탐 업스트림 보고 — 외부 발신 금지이므로 게이트 "
        "대기(**n=5로 누적**) **㉔ 신규 등재: rate–distortion y축을 같은 몸에서 재측정 — "
        "현재 차트는 신척도 x + 구척도 y 혼합이며 캐비앗으로만 병기된 상태. dev-42 dual "
        "정확도 측정에 reader=gpt-4o 호출 필요 → 원칙 6 비용 게이트(42문항 견적 선행). "
        "이것이 차트에 남은 최대 부채** · 정산 1줄(audit-40 R6, 44회차): 신규 1건(㉔), "
        "해소 0건, 이관 0건 — 관측 45 등재·처치와 정정 집행은 무게이트 루프 몫. 묶음 "
        "재편 = amendment-85 §6-2(우선순위 권고 A배포>B문면>C거버넌스 — 단 c89는 ③이 "
        "B문면군의 최저비용·최고실적 항목임을 4번째 위반으로 입증)."
    ),
}


def main() -> int:
    text = LEDGER.read_text()
    existing = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    if any(r.get("cycle") == ROW["cycle"] for r in existing):
        print(f"[abort] cycle {ROW['cycle']} 행이 이미 있다 — 중복 append 방지")
        return 1
    last = existing[-1]["cycle"]
    if last != ROW["cycle"] - 1:
        print(f"[abort] 마지막 cycle={last}, 기대 {ROW['cycle'] - 1} — 순서 불일치")
        return 1
    keys_prev, keys_new = set(existing[-1]), set(ROW)
    if keys_prev != keys_new:
        print(f"[abort] 스키마 불일치 — 누락 {keys_prev - keys_new} / 추가 {keys_new - keys_prev}")
        return 1
    sep = "" if text.endswith("\n") else "\n"
    with LEDGER.open("a") as fh:
        fh.write(sep + json.dumps(ROW, ensure_ascii=False) + "\n")
    print(f"[ok] cycle {ROW['cycle']} append 완료 (직전 {last}, 스키마 {len(keys_new)}필드 일치)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
