#!/usr/bin/env python
"""c96 원장 행 append (관측 사이클, 2세션 — 후속 세션이 작성).

이 파일 자체가 관측 55의 일부다: 선행 세션이 evidence_files에 이 경로를 기재하고
사망했을 때 파일은 존재하지 않았다(유령 증거). 후속 세션이 실물화한다 —
행의 내용은 후속 세션의 실측 기준이고, 선행 세션 몫은 출처(task_state 자기 보고)를 병기한다.

관측 36 규약: 질의 원문은 원장·필드노트가 아니라 이 헤더에만 둔다.
- 능동 검색 1회 (계상 hit): trace=devloop_c97_recall (트레이스 라벨은 착수 시점의
  가번호 c97 기준 — 번호 확정 전 명명, 실제 사이클은 96)
  질의: "[devloop] 절차 5 수확 커밋 미완주 원장 정정 백필 규약"
  결과: c44 선례 기억(89e2bbed — "장부는 절차 5에 도달하지 못한 사이클을 담지 못한다",
  후속이 번호 승계·백필 없음) 표면화 → 번호 결정을 뒤집음(백필 신설안 폐기, 96 승계).

중복 방지: cycle 96 행이 이미 있으면 아무것도 하지 않는다 (원장 무중복 불변식).
"""
import json, os, sys

LEDGER = os.path.join(os.path.dirname(__file__), "..", "metrics.jsonl")

ROW = {
    "cycle": 96,
    "date": "2026-08-11",
    "restore_turns": 3,
    "restore_turns_sessions": [3, 3],
    "restore_grade": "partial",
    "restore_grade_capsule": "miss",
    "restore_grade_task_state": "partial",
    "restore_note": (
        "무기억 세션 2개가 한 사이클을 이뤘다(같은 날·같은 번호 — 비독립 표본, conventions.md 4항). "
        "세션1(선행, 01:03 관측 커밋 2c1f632 후 절차 5 중 사망): 자기 보고 restore_turns 3·grade full — "
        "원장 미기재로 원장 검증 불가, task_state 지표 문면에서 사후 전재(액면 할인). "
        "세션2(후속, 이 행의 작성자): 복원 근거 claim 1f0a1d26 · epoch 6f8b4f8e · valid_from "
        "2026-08-10T16:04:30Z. 턴 원장: 턴1 = LOOP.md+cycle-prompt.md Read + ToolSearch(5스키마) 묶음 / "
        "턴2 = get_task_state + c48_step0_check.py + git status 병렬 — 파트 S ledger_last=95/"
        "task_state_cycle=96 판정=앞섬(원장 미기재 — 절차 5 미완주 의심) **앞섬 분기 실전 첫 발화**, "
        "freshness fresh·stale=false·age 0.34h / 턴3 = 첫 유효 행동(c96 증거 검증 병렬: "
        "c96_append_metrics.py 부재 확인·2c1f632 stat·branch -avv·능동 검색 1회) = restore_turns 3, "
        "규약 ④ 준수(c92~ 세션 기준 7세션 중 6/7 — 편차율 축적 기재). 규약 ③ 준수 — 위반 0건: "
        "metrics.jsonl 접촉은 프로그램적 파싱(스키마 확인 1회)과 이 스크립트뿐, tail/cat/head 0회. "
        "★ grade partial 근거 한 줄: task_state가 사이클 상태 전체(모드·선결 조건·게이트 장부·판정 잔여)를 "
        "배달했으나 요약의 '완주'·blockers의 '부채 0건'·유령 증거 파일이 허위였다 — 원장 c96 행·수확 "
        "커밋·push 부재를 파트 S와 git 검증으로 재구성해야 했다(관측 55). full 불가 사유는 채널 지연이 "
        "아니라 **내용 선기재**: 신선한 세대가 틀린 완료 주장을 실었고 freshness는 fresh라 말했다"
        "(P33 (c) 한계 실물). 채널 분해: task_state 단독 partial / 캡슐 단독 miss — 심장박동 슬롯 점유 "
        "세션 기준 7연속(사이클 기준 c90·91·93·94·95·96 2세션), 점유 내용(_open_loop_postits 이관) 실작업 무교차."
    ),
    "recall_hits": 2,
    "recall_misses": 1,
    "recall_note": (
        "정의 A: 능동 1회(hit 1·miss 0) / 주입 2건(hit 1·miss 1) → fields hits=2·misses=1. "
        "능동 hit: c44 선례 기억(89e2bbed)이 번호 결정을 뒤집음 — 백필 신설안을 폐기하고 96 승계 확정"
        "(행동을 바꾼 신규 정보의 전형). 주입: ① task_state = hit — 사이클 전체 상태·모드·선결 조건 배달, "
        "이 세션 계획의 원천(완주 선기재 허위 성분은 관측 55·restore partial로 별도 계상 — hit 판정은 "
        "'행동을 바꾼 신규 정보' 정의에 따르며 허위 검출 자체도 이 주입이 있어야 가능했다). "
        "② 캡슐 = miss — 심장박동 슬롯 점유, 실작업 무교차(세션 기준 7연속). ③ 훅 = 0건(채널 부재 — "
        "세션 기준 3연속, 관측 53 수용 기준 ③ 이행 계속). ★ misses 산술 주의(audit-90 N5) 유지: "
        "훅 침묵 중의 misses 숫자는 회상 품질 신호가 아니다. 계기 검색 0회. 질의 원문은 이 스크립트 "
        "헤더에만(관측 36). 검산: 직전 행 c95 fields(3·0) = 성분(능동 1·0/주입 2·0) 일치(파트 R 인쇄 "
        "확인). 다음 행(c97) 검산 기대값: fields(2·1) vs 성분(능동 1·0 / 주입 1·1)."
    ),
    "frictions_logged": 1,
    "frictions_fixed": 0,
    "frictions_note": (
        "logged 1 = 관측 55(완주 선기재·절차 5 역순 쓰기 + 세션 사망 — 파트 S 앞섬 분기 실전 첫 발화가 "
        "검출, 관측 49의 경상 대칭, A-95.2 실물 증거 병기). fixed 0 — 관측 55 수용 기준 ①(원장 행·수확 "
        "커밋·push 부채)은 이 커밋으로 충족되지만 ②(쓰기 순서 관행/문면화 3사이클) ③(재발 검출 재확인) "
        "미충족: 부분을 해소로 계상하지 않는다(c96 세션1의 관측 54 계상 관행 유지). 관측 54는 ① 해소 "
        "상태 유지·③ 소유권 관행은 이 세션도 준수했으나 같은 사이클이므로 표본 2로 세지 않는다"
        "(독립 사이클 표본은 c97부터). 관측 53 침묵은 세션 기준 3연속으로 지속."
    ),
    "tests": (
        "**2 failed·377 passed** (tests/ 스코프, 후속 세션 재실측 10.41s) — 세션1 실측과 동일: "
        "test_hooks repeat-suppression · test_project_layer 턴 회상 스코프. 귀속은 세션1이 확정한 대로 "
        "미커밋 훅 WIP 단독(관측 54 ①, HEAD 379/379 녹색 — 임시 워크트리 재생). 이 사이클 코드 변경 "
        "0이라 절차 4 커밋 게이트 비발동, regression_watch 계상(A8). 녹색 복귀는 WIP 소유 세션 몫으로 "
        "존속, c97 코드 사이클의 선결 조건 유지."
    ),
    "product_code_unchanged_streak": 2,
    "gate_pending": (
        "유지: ㉖ 관측 47 수용 기준 성문화 · ㉗ F8 유형 신설 · ㉙ 규약 ④ 하네스 강제안(세션1이 근거 갱신 "
        "상신 — 몫은 잔여 편차 1/6 제거, 문면 채널이 5/6 달성; 세션2 표본 추가로 7세션 6/7). 문면안 대기: "
        "A-95.1(조망 상수화) · A-95.2(절차 3 쓰기 앞당김 — **관측 55가 실물 증거 추가**: 절차 5 이전 "
        "커밋은 생존, 절차 5로 미룬 것은 유실) · A-95.3(모드 판정 순서) · A-55.1 4차. 소멸: A-85.1 확정"
        "(c96 미승인 도과, 다음 표본 기회 c106). 시계: P33 (b) c100 판정(자연 표본 2 축적) · P30 c102 "
        "시한 · P27 c99 만료 예고 · P2 2026-08-31 기한. 묶음 B 정훈 게이트 대기. c97 후보 1순위: 배포 "
        "영수증 사이클(c63 재실행·oracle replay 재교정·P6/P3b/P7b·P4 시계 재검·관측 33 라이브 재측정) — "
        "선결: git status로 훅 WIP 정리 확인(잔존 시 관찰 전환·관측 54 ③ 독립 표본 2 기재). 신규 검토: "
        "관측 55 수용 기준 ②(record_task_state 후치 순서)의 A-95.2 합류. 원칙 5 준수 — 전부 큐, 무정지."
    ),
    "step5_write_reverified": True,
    "work": (
        "**관측 사이클 c96 완주 — 2세션 합산: 세션1(관측 커밋 2c1f632)이 실질을, 세션2(이 행·검시 커밋 "
        "df3255d)가 절차 5를 완결.** 세션1: 관측 54 ① 귀속(훅 WIP 단독·HEAD 379/379 녹색·스코프 함정 "
        "해소) · P31 표본 3 (b) 반증 확정 → P29·P31 재개봉(잔여 팔 P31 (c)) · P32 (a) 무판정 마감 · "
        "㉙ 근거 갱신 · A-85.1 소멸 · 관측 53 보강(침묵 n=2·고장 방향 1차 증거). 세션2: 절차 5 미완주 "
        "검출(파트 S 앞섬 분기 실전 첫 발화 — 선기재된 '완주'를 턴2 기계 판정으로 정정) → 관측 55 기재 "
        "후 부채 상환(원장 행·수확 커밋·push) · P32 (b) 지지 표본 3/3 창 마감(세대 확인은 교차 세션 "
        "재조회 — 정직 병기 2종: 자기 이행 증거 부재·재조회는 존재를 증명하지 진실을 증명하지 않음) · "
        "P33 (b) 자연 표본 2 + (c) 한계 실물 첫 발생(fresh가 선기재 허위를 담음) · P33 헤딩 파손 기계 "
        "수리 · 유령 증거 파일(c96_append_metrics.py) 실물화. 영토 규약 준수 지속(훅 WIP 무접촉). "
        "c44 선례 적용: 백필·이중 행 없이 후속 세션이 번호 96을 승계 완결."
    ),
}


def main() -> None:
    with open(LEDGER, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    if any(r.get("cycle") == ROW["cycle"] for r in rows):
        print(f"cycle {ROW['cycle']} 행이 이미 있다 — 아무것도 하지 않음 (원장 무중복 불변식)")
        return
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(ROW, ensure_ascii=False) + "\n")
    print(f"appended: cycle {ROW['cycle']} ({ROW['date']}) — 행 수 {len(rows)} → {len(rows)+1}")


if __name__ == "__main__":
    sys.exit(main())
