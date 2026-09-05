#!/usr/bin/env python3
"""c58 — backlog #8 사이클-단위 oracle replay 표본 2호: c57 (read-only, 2026-08-06).

c57 규약 첫 적용: 선언문 재생(B)과 주제어 재생(C)을 병기하고 **분모는 C 우선**으로
읽는다 — c57 실측에서 게이트-통과 오라클이 "[devloop] 사이클 N" 장르 접두 어휘
매칭(C1 기전)으로 분자를 ~8배 과생성했기 때문(frictions 미분류 22건째).

c57 스크립트와의 차이: 표본 메타데이터를 SAMPLE dict로 파라미터화 — 표본 3호부터는
이 dict만 교체하면 된다(일반화 검토 = c57 next_actions 후보 ①의 후반부).

표본 c57의 1차 증거 (두 런 — c55 관측 "죽은 런 비가시성" 재발 2회차 사이클):
  - 1차 런 2ee9f37d (birth 08-06 01:08:27, 01:17 사망): get_task_state 1회,
    search_memories 0회, add_memory 0건. 훅 주입 3건(c43·c42·c45).
  - 2차 런 639c34a6 (birth 08-06 02:32:21, 완주): get_task_state 1회,
    search_memories 1회("[devloop] 사이클 57 선택 결정 oracle replay", top_k=5)
    → 5건(c31·c32·c33·c38·c39 선택결정 계열). 훅 주입 3건(1차와 동일).
  - SEEN = 두 런 훅 주입 합집합(3건) + 2차 런 검색 결과 5건 = 8건.
    캡슐·get_task_state 노출분은 전부 task_state 행 — turnrecall 구조 제외 층.
  - 작업 선언문: 2차 런 add_memory "[devloop] 사이클 57 선택+결정+검증" 원문
    (트랜스크립트에서 채취 — 스토어 사본은 c57 산출물이라 시간여행 필터로 배제).

시간여행 컷오프 = 1차 런 birth(사이클 개시). 두-런 사이클의 컷오프 규약: 사이클의
관련-기억 분모는 "사이클이 시작될 때 스토어에 있던 것"이므로 이른 쪽 birth를 쓴다.

판정(작업을 바꿨을지)은 스크립트가 하지 않는다 — 노트에서 사람이(이 사이클 손이)
항목별 근거와 함께 채점한다. c36·c57 전례와 동일.

    .venv/bin/python research/devloop/scripts/c58_oracle_replay.py
"""
import datetime
import importlib.util
import os
import sys

HOOK_DIR = os.path.expanduser("~/.forget/hooks")
sys.path.insert(0, HOOK_DIR)

spec = importlib.util.spec_from_file_location(
    "forget_turnrecall", os.path.join(HOOK_DIR, "forget_turnrecall.py"))
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402

SAMPLE = {
    "cycle": 57,
    # 2차 런(639c34a6) add_memory 입력 원문 그대로 — 954자.
    "declaration": (
        "[devloop] 사이클 57 선택+결정+검증 (2026-08-06, 일반 사이클 57%10=7·57%5=2, "
        "N·모드는 c48_step0_check.py 첫 줄 — metrics 무접촉, F-절차0 (A) 마지막 표본 준수): "
        "git status 고아 대조(c56 next_actions 지시)로 죽은 1차 런의 완성 산출물 2건 발견 — "
        "notes/cycle-57-oracle-replay-c56.md + scripts/c57_oracle_replay.py (backlog #8 "
        "사이클-단위 oracle replay 첫 집행, 표본 c56). 결정: 신뢰 채택이 아니라 재실행 검증 후 "
        "채택 — read-only 스크립트를 2차 런이 직접 재실행, 3개 regime 전부 노트 표와 일치(A: "
        "게이트 통과 2·전부 SEEN·UNSEEN-PASS 0 / B: pre-c56 통과 11·SEEN 3·UNSEEN-PASS 8, "
        "항목·점수 ±0.0001 동일 / C 주제어: 통과 1=c43 SEEN). silent_miss(c56)=0 판정 유지. "
        "발견 2건: ① 게이트-통과 오라클은 \"[devloop] 사이클 N\" 장르 접두 어휘 매칭(C1 기전)으로 "
        "분자를 ~8배 과생성 — regime B 통과 8건이 주제어 질의에서 전원 게이트 아래(예 "
        "0.8114→0.3698), 사람 작업-변경 판정이 필수 성분임을 실측(frictions 미분류 22건째 기재). "
        "② 죽은 런 비가시성 재발 2회차(c55 관측): 1차 런은 add_memory·record_task_state 0건 — "
        "기억 채널엔 완전 무흔적, 단 이번엔 next_actions가 고아 대조를 명시 지시해 수용 기준"
        "(\"중복 생성 없이 이어받기\") 첫 표본 성공(n=1, 처치 후보 (b) 복원 규약 명문화의 "
        "기억-채널 판본이 작동). 1차 런의 노트 내 \"frictions 기재\" 주장은 미집행이었음(F6형) — "
        "2차 런이 실제 기재로 닫음."
    ),
    # 시간여행 컷오프 — 1차 런 트랜스크립트 st_birthtime, KST.
    "birth": datetime.datetime(2026, 8, 6, 1, 8, 27),
    # c57이 실제 본 것: 훅 주입 3건(두 런 동일) + 2차 런 검색 결과 5건. 식별 접두는
    # 트랜스크립트 1차 증거에서 옮김(c57 전례와 동일한 40자-접두 매칭).
    "seen_prefixes": [
        # 훅 주입 (attachment line 7, 두 런 동일)
        "[devloop] 사이클 43 발견 (2026-08-04, 일반 사이클, 관찰·측정): 도그푸드 :8000의",
        "[devloop] 사이클 42 결정+발견 (2026-08-04, 일반 사이클 42%10=2·42%5=2",
        "[devloop] 사이클 45 발견 (2026-08-04, 회고 사이클 45%5=0): 루프의 개정 채널은 셋",
        # 2차 런 search_memories 결과 5건 (toolu_0139SuN7…)
        "[devloop] 사이클38 선택 결정: 일반 사이클(38%10=8·38%5=3)",
        "[devloop] 사이클 39 결정+발견 (2026-08-03, 일반 사이클, N%10=9·N%5=4",
        "[devloop] 사이클 33 (2026-08-03, 일반 사이클 N%5=3·N%10=3) 선택 결정",
        "[devloop] 사이클 32 (일반 사이클, 2026-08-03) 선택 결정",
        "[devloop] 사이클 31 (2026-08-03, 일반 사이클) 선택·결정",
    ],
    # regime C — 작업의 실제 영역(방법론: 재생·검증·죽은 런)에 정렬된 주제어.
    # 선언문의 장르 접두("[devloop] 사이클 N")를 우회하는 것이 목적이므로 접두 미포함.
    "topical_query": (
        "oracle replay 재생 silent_miss 침묵 미스 판정 죽은 런 고아 산출물 재실행 검증 채택 "
        "게이트 통과 오라클 과생성 작업 선언문"
    ),
}

CWD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def classify(item):
    """훅 main()의 필터 순서 재현(세션 ledger 제외) — c52·c57 스크립트와 동일."""
    md = item.get("metadata") or {}
    score = float(item.get("score") or 0.0)
    if md.get("hook"):
        return "drop", "hook-pointer"
    if md.get("assertion_kind") == "task_state":
        return "drop", "task_state"
    if md.get("superseded_by") or (isinstance(md.get("supersedes"), list) and md.get("supersedes")):
        return "conflict", "conflict-pair"
    if score < hook.SCORE_THRESHOLD:
        return "drop", f"below-gate({hook.SCORE_THRESHOLD})"
    return "pass", "-"


def created_at_of(item):
    for key in ("created_at", "createdAt"):
        v = item.get(key) or (item.get("metadata") or {}).get(key)
        if v:
            try:
                return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")) \
                    .astimezone().replace(tzinfo=None)
            except ValueError:
                pass
    return None


def seen(text):
    t = " ".join(text.split())
    return any(t.startswith(" ".join(p.split())[:40]) or " ".join(p.split())[:40] in t
               for p in SAMPLE["seen_prefixes"])


def replay(top_k, query):
    project = None if scope_disabled() else project_key_for_path(CWD)
    args = {"query": query, "top_k": top_k, "recall": "low"}
    if project:
        args["filters"] = layered_filter(project)
    res = hook._rpc("search_memories", args)
    rows = []
    for rank, item in enumerate(res.get("results") or [], 1):
        verdict, why = classify(item)
        ca = created_at_of(item)
        rows.append({
            "rank": rank,
            "score": round(float(item.get("score") or 0.0), 4),
            "verdict": verdict, "why": why,
            "created": ca.strftime("%m-%d %H:%M") if ca else "?",
            "post": (ca is not None and ca >= SAMPLE["birth"]),
            "seen": seen(item.get("memory") or ""),
            "text": " ".join((item.get("memory") or "").split()),
        })
    return rows


def show(title, rows):
    print(f"\n=== {title} ===")
    misses = []
    for r in rows:
        flags = []
        if r["post"]:
            flags.append(f"POST-c{SAMPLE['cycle']}(제외)")
        if r["seen"]:
            flags.append("SEEN")
        if r["verdict"] == "pass" and not r["post"] and not r["seen"]:
            flags.append("**UNSEEN-PASS**")
            misses.append(r)
        print(f"{r['rank']:>3}. {r['score']:.4f} {r['verdict']:<8} {r['why']:<18} "
              f"{r['created']:<12} {' '.join(flags):<22} {r['text'][:110]}")
    return misses


def main():
    n = SAMPLE["cycle"]
    print(f"sample cycle: c{n}")
    print(f"declaration[:80]: {SAMPLE['declaration'][:80]}")
    print(f"hook constants: MAX_RECALLS={hook.MAX_RECALLS} gate={hook.SCORE_THRESHOLD}")
    print(f"time-travel cutoff (c{n} 1차 런 birth): {SAMPLE['birth']}")

    q300 = SAMPLE["declaration"][:300]  # 훅과 동일한 절단
    a = show(f"regime A — hook-faithful (top_k=5, prompt[:300])", replay(5, q300))
    b = show(f"regime B — oracle wide (top_k=15, prompt[:300])", replay(15, q300))
    c = show(f"regime C — topical probe (top_k=15, 주제어 질의)", replay(15, SAMPLE["topical_query"]))

    print(f"\n=== 차집합 요약 — c57 규약: B+C 병기, 분모는 C 우선 (판정은 노트에서) ===")
    print(f"  regime C UNSEEN-PASS (1차 분모): {len(c)}건")
    print(f"  regime B UNSEEN-PASS (장르 매칭 상한, 참고 분모): {len(b)}건")
    print(f"  regime A UNSEEN-PASS (hook-faithful): {len(a)}건")
    uniq = {}
    for r in c + b + a:  # C 우선 순서로 dedup — 같은 항목이면 C의 점수가 남는다
        uniq.setdefault(r["text"][:60], r)
    if not uniq:
        print(f"  silent_miss 후보 0건 — c{n}이 본 것 + task_state 행 밖에 게이트 통과 관련 기억 없음")
    for t, r in uniq.items():
        print(f"  score={r['score']:.4f} created={r['created']}  {r['text'][:160]}")
    print("\nCAVEAT: ① 세션 ledger·캡슐 중복 억제는 재현 안 함(주입은 상한) ② 현재-스토어 "
          "재생(시간여행 아님) — POST 행은 분모에서 제외 표시 ③ '관련'의 오라클은 게이트 "
          "통과이지 사람 라벨이 아님 — 작업-변경 판정은 노트에서 항목별 근거와 함께 "
          "④ 두-런 표본의 컷오프는 이른 쪽(1차 런) birth.")


if __name__ == "__main__":
    main()
