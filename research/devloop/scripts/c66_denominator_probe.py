#!/usr/bin/env python3
"""c66 — regime C 분모 비재현(2 → 11)의 원인 규명 프로브 (read-only, 2026-08-07).

관측(c66이 커밋본 c59_oracle_replay.py를 무수정 재실행):
  regime A  UNSEEN-PASS 0  = c59 노트 0   ✔ 재현
  regime B  UNSEEN-PASS 7  = c59 노트 7   ✔ 재현 (질의 = 선언문[:300], 장르 접두 리터럴)
  regime C  UNSEEN-PASS 11 ≠ c59 노트 2   ✘ **비재현** (질의 = 주제어, 리터럴 겹침 없음)

경합 가설 둘:
  H1 벡터 채널 이동 — c59(08-06 03:38) 이후 벡터 성분이 바뀌어 벡터-지배 regime만 이동.
     B는 리터럴 매칭이 점수를 지배(노트 0.8036~0.9213)하므로 불변, C는 벡터 지배라 이동.
     예측: 신규 통과행의 score_breakdown이 vector 지배적이고, B 통과행은 rule 지배적.
  H2 소급 생성행 — 신규 통과행이 c59 이후 기록됐으나 created_at이 원본 날짜를 물려받아
     시간여행 컷오프(created_at 기준)를 통과. 예측: created_at ≪ updated_at, 또는
     id 발급 순서가 created_at 순서와 불일치.

두 가설은 배타가 아니다 — 둘 다 성립할 수 있고, 각각 다른 처방을 요구한다.
H1이면 오라클 점수는 시점 간 비교 불가(자[尺] 문제), H2면 컷오프 술어 자체가 틀렸다.

    .venv/bin/python research/devloop/scripts/c66_denominator_probe.py
"""
import datetime
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

spec = importlib.util.spec_from_file_location(
    "c59_oracle_replay", os.path.join(HERE, "c59_oracle_replay.py"))
c59 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c59)

SAMPLE = c59.SAMPLE
GATE = c59.hook.SCORE_THRESHOLD
CWD = c59.CWD

from forget_project import layered_filter, project_key_for_path, scope_disabled  # noqa: E402


def raw(query, top_k):
    project = None if scope_disabled() else project_key_for_path(CWD)
    args = {"query": query, "top_k": top_k, "recall": "low", "score_breakdown": True}
    if project:
        args["filters"] = layered_filter(project)
    return c59.hook._rpc("search_memories", args).get("results") or []


def ts(item, *keys):
    md = item.get("metadata") or {}
    for k in keys:
        v = item.get(k) or md.get(k)
        if v:
            return str(v)
    return ""


def parse(v):
    if not v:
        return None
    try:
        return datetime.datetime.fromisoformat(v.replace("Z", "+00:00")) \
            .astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def dump(title, query, top_k):
    print(f"\n{'=' * 78}\n=== {title} ===")
    rows = raw(query, top_k)
    print(f"질의[:90]: {query[:90]}")
    print(f"결과 {len(rows)}건 | gate={GATE} | 컷오프={SAMPLE['birth']}\n")
    keyset = set()
    for i, it in enumerate(rows, 1):
        score = float(it.get("score") or 0.0)
        ca, ua = parse(ts(it, "created_at", "createdAt")), parse(ts(it, "updated_at", "updatedAt"))
        bd = it.get("score_breakdown") or (it.get("metadata") or {}).get("score_breakdown") or {}
        if isinstance(bd, dict):
            keyset |= set(bd.keys())
        bds = " ".join(f"{k}={v:.3f}" if isinstance(v, (int, float)) else f"{k}={v}"
                       for k, v in (bd.items() if isinstance(bd, dict) else []))
        post = ca is not None and ca >= SAMPLE["birth"]
        lag = ""
        if ca and ua:
            d = (ua - ca).total_seconds()
            lag = f" upd_lag={d / 3600:+.1f}h" if abs(d) > 60 else " upd_lag~0"
        mark = "PASS" if score >= GATE else "    "
        print(f"{i:>3}. {score:.4f} {mark} {'POST' if post else 'pre '} "
              f"id={str(it.get('id'))[:8]} ca={ca.strftime('%m-%d %H:%M') if ca else '?':<11}"
              f"{lag:<14} {bds}")
        print(f"      {' '.join((it.get('memory') or '').split())[:120]}")
    print(f"\nscore_breakdown 키 관측: {sorted(keyset) or '(없음 — 서버가 분해를 반환하지 않음)'}")
    return rows


def main():
    print("c66 — regime C 분모 비재현 원인 프로브")
    print(f"c59 노트 기록: A pass=1/UNSEEN=0, B pass=9/UNSEEN=7, C pass=3/UNSEEN=2")
    print(f"c66 재실행값:  A UNSEEN=0(재현), B UNSEEN=7(재현), C UNSEEN=11(비재현)")

    c_rows = dump("regime C — 주제어 질의 (비재현 regime), top_k=25",
                  SAMPLE["topical_query"], 25)
    b_rows = dump("regime B — 선언문[:300] (재현 regime, 대조), top_k=15",
                  SAMPLE["declaration"][:300], 15)

    print(f"\n{'=' * 78}\n=== H1/H2 판정 재료 ===")
    for nm, rows in (("C", c_rows), ("B", b_rows)):
        ps = [r for r in rows if float(r.get("score") or 0) >= GATE]
        scores = [float(r.get("score") or 0) for r in ps]
        print(f"  regime {nm}: 통과 {len(ps)}건, 점수 {min(scores, default=0):.4f}"
              f"~{max(scores, default=0):.4f}")

    # H2 — 소급 생성 검사: pre-컷오프인데 updated_at이 컷오프 이후인 행
    late = []
    for r in c_rows:
        ca, ua = parse(ts(r, "created_at", "createdAt")), parse(ts(r, "updated_at", "updatedAt"))
        if ca and ca < SAMPLE["birth"] and ua and ua >= SAMPLE["birth"]:
            late.append((r, ca, ua))
    print(f"\n  H2 검사 — created_at<컷오프 이면서 updated_at>=컷오프: {len(late)}건")
    for r, ca, ua in late:
        print(f"    id={str(r.get('id'))[:8]} ca={ca} ua={ua} "
              f"{' '.join((r.get('memory') or '').split())[:80]}")
    if not late:
        print("    → 이 채널로는 H2 미지지 (단, updated_at이 재기록 시 갱신되지 않으면 위음성)")

    print("\nCAVEAT: ① read-only, 스토어 무변경 ② score_breakdown은 서버 지원 시에만 채워짐 — "
          "빈 값이면 H1은 이 채널로 판정 불가이고 별도 채널(임베딩 스택 동일성)이 필요 "
          "③ updated_at 부재/미갱신 시 H2는 위음성 가능 — 부재는 반증이 아니다.")


if __name__ == "__main__":
    main()
