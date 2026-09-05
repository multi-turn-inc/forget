#!/usr/bin/env python3
"""c59 — backlog #8 사이클-단위 oracle replay 표본 3호: c58 (read-only, 2026-08-06).

c58 스크립트의 SAMPLE dict 교체(설계대로 표본 3호부터 dict만 교체) + 1개 계측 추가:
**near-miss ±0.05 병기 관행 첫 적용** — c58 발견(게이트-아래 위음성: A10 캐비앗이
주제-정렬 질의에서 0.4216 = 게이트 0.45−0.028로 분모 밖)의 계측기화. regime C에서
게이트 [gate−0.05, gate) 대역 행을 분모 아님·관측만으로 표에 병기한다. 대역 커버리지를
위해 C의 top_k를 15→25로 넓힌다 — 결과는 점수 내림차순이므로 **게이트-통과 분모는
top_k=15와 동일 집합**(pass는 랭킹의 접두)이라 c57·c58 표본과의 비교성이 유지된다.
B는 15 유지(장르 팽창 상한의 표본 간 비교축).

표본 c58의 1차 증거 (한 런 — c56·c57과 달리 죽은 선행 런 없음):
  - 런 5413ca9e (birth 08-06 02:59:55, 03:11 완주): get_task_state 1회,
    **search_memories 0회**(c56과 같은 무검색 사이클), add_memory 2건.
    훅 주입 3건(c43·c42·c57 — c58 노트의 창 회전 기록과 일치).
  - SEEN = 훅 주입 3건이 전부. 캡슐·get_task_state 노출분은 task_state 행(구조 제외 층).
  - 작업 선언문: c58 add_memory 1호 "[devloop] 사이클 58 선택+결정" 원문 725자
    (트랜스크립트에서 채취 — 스토어 사본은 POST-c58이라 시간여행 필터로 배제).
    캐비앗: c58은 선언을 두 기억(선택+결정 / 발견+검증)으로 분할했다. 재생 질의는
    작업 선언 성격의 1호를 쓴다 — 2호(결과 보고)의 어휘는 regime C 주제어가 커버.

시간여행 컷오프 = 런 birth 02:59:55 (한-런 사이클이므로 규약상 그 birth).

판정(작업을 바꿨을지)은 스크립트가 하지 않는다 — 노트에서 사람이(이 사이클 손이)
항목별 근거와 함께 채점한다. c36·c57·c58 전례와 동일.

    .venv/bin/python research/devloop/scripts/c59_oracle_replay.py
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

NEAR_MISS_BAND = 0.05  # c58 수용 기준 확장 후보 — 게이트 아래 이 폭은 관측 병기

SAMPLE = {
    "cycle": 58,
    # c58 add_memory 1호(선택+결정) 입력 원문 그대로 — 725자.
    "declaration": (
        "[devloop] 사이클 58 선택+결정 (2026-08-06, 일반 사이클 58%10=8·58%5=3, "
        "N·모드는 c48_step0_check.py 첫 줄 — metrics 무접촉): 영토 클린, frictions "
        "미해소 전건 게이트 종속 → next_actions[0] 후보 ① 집행 = backlog #8 oracle "
        "replay 사이클-단위 표본 2호, 대상 c57. c57 규약(B+C 병기, 분모 C 우선) 첫 "
        "적용이자 스크립트 일반화(SAMPLE dict 파라미터화, c58_oracle_replay.py). "
        "1차 증거 채취 완료: c57은 두 런(1차 2ee9f37d birth 01:08:27 사망 / 2차 "
        "639c34a6 birth 02:32:21 완주), SEEN = 훅 주입 3건(c43·c42·c45 — c56과 동일 "
        "3건, P10 만석 10연속) + 2차 런 search_memories 1회 결과 5건(c31·c32·c33·"
        "c38·c39 선택결정 계열) + task_state 행(구조 제외). 선언문 = 2차 런 "
        "add_memory \"[devloop] 사이클 57 선택+결정+검증\" 원문 954자(트랜스크립트에서 "
        "채취, 스토어 사본은 POST-c57 제외 대상). 시간여행 컷오프 = 1차 런 birth "
        "01:08:27. 부수 판정 예정: 포인터 경로 축약 수용 기준(c56~c58 1차 실행 오류 0) "
        "— c58 step0 스크립트 1차 실행 성공으로 3/3 충족."
    ),
    # 시간여행 컷오프 — c58 런 트랜스크립트 st_birthtime, KST.
    "birth": datetime.datetime(2026, 8, 6, 2, 59, 55),
    # c58이 실제 본 것: 훅 주입 3건이 전부(search_memories 0회). 식별 접두는
    # 트랜스크립트 1차 증거에서 옮김(c57·c58 전례와 동일한 40자-접두 매칭).
    "seen_prefixes": [
        # 훅 주입 (f2_ledger 규약 추출, 세 항목)
        "[devloop] 사이클 43 발견 (2026-08-04, 일반 사이클, 관찰·측정): 도그푸드 :8000의",
        "[devloop] 사이클 42 결정+발견 (2026-08-04, 일반 사이클 42%10=2·42%5=2",
        "[devloop] 사이클 57 선택+결정+검증 (2026-08-06, 일반 사이클 57%10=7·57%5=2",
    ],
    # regime C — c58 작업의 실제 영역(재생 방법론 + c58 고유 발견 축)에 정렬된 주제어.
    # 선언문의 장르 접두("[devloop] 사이클 N")를 우회하는 것이 목적이므로 접두 미포함.
    # c58 2호 기억(발견+검증)의 어휘 축(위음성·near-miss·장르 팽창)을 포함한다.
    "topical_query": (
        "oracle replay 선언문 재생 표본 일반화 SAMPLE dict 파라미터화 장르 팽창 "
        "게이트 아래 위음성 near-miss 임계 직하 판별력 약함 silent_miss 판정 분모"
    ),
}

CWD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def classify(item):
    """훅 main()의 필터 순서 재현(세션 ledger 제외) — c52·c57·c58 스크립트와 동일."""
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


def near_misses(rows):
    """게이트 [gate−0.05, gate) 대역 — 분모 아님, 관측 병기(c58 확장 후보 첫 적용)."""
    lo = hook.SCORE_THRESHOLD - NEAR_MISS_BAND
    return [r for r in rows
            if lo <= r["score"] < hook.SCORE_THRESHOLD and not r["post"]]


def main():
    n = SAMPLE["cycle"]
    print(f"sample cycle: c{n}")
    print(f"declaration[:80]: {SAMPLE['declaration'][:80]}")
    print(f"hook constants: MAX_RECALLS={hook.MAX_RECALLS} gate={hook.SCORE_THRESHOLD}")
    print(f"time-travel cutoff (c{n} 런 birth): {SAMPLE['birth']}")

    q300 = SAMPLE["declaration"][:300]  # 훅과 동일한 절단
    a = show(f"regime A — hook-faithful (top_k=5, prompt[:300])", replay(5, q300))
    b = show(f"regime B — oracle wide (top_k=15, prompt[:300])", replay(15, q300))
    c_rows = replay(25, SAMPLE["topical_query"])
    c = show(f"regime C — topical probe (top_k=25, 주제어 질의; pass 분모는 top_k=15와 동일 집합)", c_rows)

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

    nm = near_misses(c_rows)
    print(f"\n=== near-miss 대역 [gate−{NEAR_MISS_BAND}, gate) — regime C, 분모 아님·관측만 "
          f"(c58 확장 후보 첫 적용) ===")
    if not nm:
        print("  대역 내 0건 (top_k=25 창 안에서)")
    for r in nm:
        flags = "SEEN" if r["seen"] else ""
        print(f"  rank={r['rank']:>2} score={r['score']:.4f} (gate−{hook.SCORE_THRESHOLD - r['score']:.4f}) "
              f"created={r['created']} {flags:<5} {r['text'][:140]}")

    print("\nCAVEAT: ① 세션 ledger·캡슐 중복 억제는 재현 안 함(주입은 상한) ② 현재-스토어 "
          "재생(시간여행 아님) — POST 행은 분모에서 제외 표시 ③ '관련'의 오라클은 게이트 "
          "통과이지 사람 라벨이 아님 — 작업-변경 판정은 노트에서 항목별 근거와 함께 "
          "④ near-miss 대역은 top_k=25 창으로 절단된 하한 관측 ⑤ c58 선언은 두 기억으로 "
          "분할 — A/B 질의는 1호(선택+결정)만 사용, 2호(발견+검증) 어휘는 C 주제어가 커버.")


if __name__ == "__main__":
    main()
