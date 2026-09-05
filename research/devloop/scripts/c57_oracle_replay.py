#!/usr/bin/env python3
"""c57 — backlog #8 사이클-단위 oracle replay: c56 표본 (read-only, 2026-08-06).

backlog #8 확정 설계(LOOP.md): 사이클 종료 후 그 사이클의 **작업 선언문**으로 검색을
재생 → "스토어에 있었던 관련 기억" 대 "사이클이 실제 본 것(캡슐+훅 주입+검색 로그)"의
차집합을 뜬다. 차집합 중 **작업을 바꿨을** 항목만 silent_miss로 채점한다.
c36은 5개 특정 후보의 일회 판정이었고, 이 스크립트는 "매 사이클이 그대로 표본"의
첫 사이클-단위 집행이다.

표본 c56의 1차 증거 (트랜스크립트 b2bbf4f9, birth 2026-08-06 00:36:53):
  - c56이 실행한 forget 검색: get_task_state 1회뿐, search_memories **0회**
    → 회상 노출 전량 = 캡슐 + 훅 주입 3건 + get_task_state(전부 task_state 행)
  - 작업 선언문: c56 자신의 add_memory "[devloop] 사이클 56 선택+결정" 원문
    (아래 DECLARATION — 트랜스크립트에서 그대로 옮김, 스토어의 사본은 c56 산출물이므로
    시간여행 필터로 배제된다)

재생 경로: 설치본 훅(forget_turnrecall.py)의 _rpc — c52 재생과 동일한 read-only 채널.
  regime A (hook-faithful): top_k=5·recall=low·게이트 0.45·훅 필터 = "c56이 선언문으로
    물었다면 turnrecall이 표면화했을 것"
  regime B (oracle wide): top_k=15 동일 필터 = "스토어에 있었고 게이트를 넘는 관련 기억"

시간여행 필터: created_at >= c56 세션 birth(2026-08-06 00:36:53 KST)인 행은 후보에서
제외하고 별도 표시한다 — c56 시점 스토어에 없었으므로 silent_miss 분모가 아니다.

판정(작업을 바꿨을지)은 스크립트가 하지 않는다 — 출력을 노트에서 사람이(이 사이클 손이)
채점하고 근거를 남긴다. c36 전례와 동일.

    .venv/bin/python research/devloop/scripts/c57_oracle_replay.py
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

# c56 작업 선언문 — 트랜스크립트 b2bbf4f9의 add_memory 입력 원문 그대로.
DECLARATION = (
    "[devloop] 사이클 56 선택+결정 (2026-08-06, 일반 사이클 56%10=6·56%5=1, 영토 클린 → "
    "코드 사이클 허용): P11 처치 3(차원 거부)을 집행한다 — 예측 (c) 사전 등록 완료(c43), "
    "대조군 실측 존재(600/600 게이트 통과, min 0.4658). 설계 결정: ① memory_engine."
    "cosine_similarity는 len(left)!=len(right)면 0.0 반환((cos+1)/2 스케일에서 절단 잡음이 "
    "~0.5로 게이트 0.45를 넘던 것을 차단) ② 이웃 검사(c53 규율)에서 vector_adapters."
    "_cosine_similarity의 zip() 절단이 같은 결함류로 발견 — 동일 거부 처치를 사본 동기"
    "(P8 처치 1의 hooks/ 사본 동기 전례). 판정 시계는 배선(설치본 갱신+sha256) 후 "
    "+5사이클 — 코드 레벨 (c) 측정은 embedding_space_audit.py 재실행으로 이번 사이클에 "
    "남긴다."
)

C56_BIRTH = datetime.datetime(2026, 8, 6, 0, 36, 53)  # 트랜스크립트 st_birthtime, KST

# c56이 실제 본 것 — 훅 주입 3건의 식별 접두(트랜스크립트 1차 증거에서 옮김).
# 캡슐·get_task_state 노출분은 전부 task_state 행이라 훅 후보에서 구조적으로 제외됨.
SEEN_PREFIXES = [
    "[devloop] 사이클 43 발견 (2026-08-04, 일반 사이클, 관찰·측정): 도그푸드 :8000의",
    "[devloop] 사이클 42 결정+발견 (2026-08-04, 일반 사이클 42%10=2·42%5=2",
    "[devloop] 사이클 45 발견 (2026-08-04, 회고 사이클 45%5=0): 루프의 개정 채널은 셋",
]

CWD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def classify(item):
    """훅 main()의 필터 순서 재현(세션 ledger 제외) — c52 스크립트와 동일."""
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
               for p in SEEN_PREFIXES)


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
            "post_c56": (ca is not None and ca >= C56_BIRTH),
            "seen": seen(item.get("memory") or ""),
            "text": " ".join((item.get("memory") or "").split()),
        })
    return rows


def show(title, rows):
    print(f"\n=== {title} ===")
    misses = []
    for r in rows:
        flags = []
        if r["post_c56"]:
            flags.append("POST-c56(제외)")
        if r["seen"]:
            flags.append("SEEN")
        if r["verdict"] == "pass" and not r["post_c56"] and not r["seen"]:
            flags.append("**UNSEEN-PASS**")
            misses.append(r)
        print(f"{r['rank']:>3}. {r['score']:.4f} {r['verdict']:<8} {r['why']:<18} "
              f"{r['created']:<12} {' '.join(flags):<22} {r['text'][:110]}")
    return misses


def main():
    print(f"declaration[:80]: {DECLARATION[:80]}")
    print(f"hook constants: MAX_RECALLS={hook.MAX_RECALLS} gate={hook.SCORE_THRESHOLD}")
    print(f"time-travel cutoff (c56 birth): {C56_BIRTH}")

    q300 = DECLARATION[:300]  # 훅과 동일한 절단
    a = show("regime A — hook-faithful (top_k=5, prompt[:300])", replay(5, q300))
    b = show("regime B — oracle wide (top_k=15, prompt[:300])", replay(15, q300))
    # regime C — 선언문이 아니라 작업의 주제어로 묻는 강건성 프로브: 선언문의 "[devloop]
    # 사이클 N" 장르 접두가 다른 사이클 메모와 어휘 매칭되는 편향(C1)을 우회해, 코드
    # 영역 자체에 정렬된 기억이 스토어에 있었는지 본다.
    qc = "cosine_similarity 임베딩 차원 불일치 절단 truncation zip min len 거부 vector_adapters"
    c = show("regime C — topical probe (top_k=15, 코드 영역 질의)", replay(15, qc))

    print("\n=== 차집합 요약 (silent_miss 후보 = UNSEEN-PASS, 판정은 노트에서) ===")
    uniq = {}
    for r in a + b + c:
        uniq.setdefault(r["text"][:60], r)
    if not uniq:
        print("silent_miss 후보 0건 — c56이 본 것 + task_state 행 밖에 게이트 통과 관련 기억 없음")
    for t, r in uniq.items():
        print(f"  score={r['score']:.4f} created={r['created']}  {r['text'][:160]}")
    print("\nCAVEAT: ① 세션 ledger·캡슐 중복 억제는 재현 안 함(주입은 상한) ② 선언문은 "
          "c56 종료 후 재생이므로 현재-스토어 재생(시간여행 아님) — POST-c56 행은 분모에서 "
          "제외 표시 ③ '관련'의 오라클은 게이트 통과이지 사람 라벨이 아님 — 작업-변경 "
          "판정은 노트에서 항목별 근거와 함께.")


if __name__ == "__main__":
    main()
