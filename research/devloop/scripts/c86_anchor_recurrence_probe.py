#!/usr/bin/env python3
"""c86 — 관측 36 재발 카운터 첫 집행: 앵커 재측정 + 반전 원인 검시 (읽기 전용).

관측 36 수용 기준 ②: "앵커 재측정 시 반전 원인이 루프 유래 기억이면 이 관측의
카운터를 증분한다." 등재(c74) 이후 집행 표본이 0이었다 — audit-80 §3-(c)가 무집행을
지적했고, amendment-85 §7 Q3가 "다음 감사까지 표본 0이면 회피로 재분류"를 예고했다.
이 스크립트가 표본 1호를 만든다.

판정 규칙 (선등록 — c86 add_memory에 측정 전 기록):
  (a) 자[尺] 전부 고정: margin=0.03 · min_samples=4 · window=5 · top_k=5 (c74와 동일,
      c48 규율 — 재기만 하고 바꾸지 않는다). spread = top1 − median(top-5 eligible).
  (b) flat verdict가 c74 판정 대비 **반전**된 앵커만 카운터 후보다. 반전 앵커는 top-5
      검시로 원인 기억을 식별하고, 루프 유래(1차 자동 판정: 기억 텍스트에 'devloop'
      마커; 최종 판정은 노트에 created_at·내용 근거와 함께)이면 카운터 +1 (앵커당 1).
  (c) c74에서 이미 반전된 앵커 2건(A3·A4)의 봉우리 **지속**은 신규 증분이 아니다 —
      카운터는 '새 반전'만 센다. 지속 여부(top-1이 여전히 c63 노트 2026-08-06T16:58
      인가)는 별도 병기: c74의 "영구 발화로 바꾼다" 주장의 첫 종단 검증이다.
  (d) 이 사이클의 작업 선택 기억(측정 전 add_memory, 원문 무인용)이 앵커 top-5에
      개입했는지 검사한다 (c74 선례 — 08-09 devloop 기억의 top-5 등장 여부).

측정 몸 선언 (원칙 3): 살아 있는 :8000 = 구척도 아핀 합성(score = 0.275 + rule*0.45
+ 0.275*cos). 저장소 신척도(c72, 미배포 ⑮)와 혼용 금지. 스택은 실행 시
get_provider_health `effective`로 인쇄한다(관측 31: checks는 폴백 이름).

원장 접촉 (관측 37 ③ 병기): context_traces에서 앵커 4건의 filters 컬럼만 질의
동등 매칭으로 읽는다(4행 한정, 정독 아님) — c74 측정이 trace의 filters를 그대로
재실행했으므로 수치 비교 가능성을 위해 복제한다. 비밀 스캔 대상 원문 정독 없음.

관측 36 ① 자기 이행: 앵커 질의 원문은 이 계기 파일에만 있다(c74 계기 2본에 이미
커밋된 동일 문자열). 노트·기억·metrics에는 trace 시각/해시로만 지칭한다.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import urllib.request

DB = os.path.expanduser("~/.forget/forget.sqlite3")
FORGET_URL = os.environ.get("FORGET_MCP_URL", "http://127.0.0.1:8000/mcp")
SHALLOW = 5          # 현행 top_k (MAX_RECALLS + 2) — 훅 패리티
WINDOW = 5           # 평탄도 창
MIN_SAMPLES = 4      # 자[尺] 미변경
MARGIN = 0.03        # 자[尺] 미변경
C63_NOTE_CREATED = "2026-08-06T16:58:13"   # 반전 원인으로 확정된 c63 필드 노트 (관측 36)

# 앵커 4건 — c63 당시 값과 c74 재측정 값(notes/cycle-74-flatness-length-profile.md 표).
# A1·A2 = 대조군(c74에서 소수 4자리 재현), A3·A4 = c74에서 평지→봉우리 반전(원인: c63 노트).
ANCHORS = [
    {"key": "A1", "trace": "2026-08-06T15:23", "flip_c74": False,
     "query": "그런데 그러고 보니 잊은 것들의 목록은 후보에서 제외했네?",
     "c63": (0.0264, 0.0233), "c74": 0.0263, "c74_flat": True},
    {"key": "A2", "trace": "2026-08-06T13:08", "flip_c74": False,
     "query": "응 c14는 잘 되고 있어? 언제 끝나?",
     "c63": (0.0120,), "c74": 0.0119, "c74_flat": True},
    {"key": "A3", "trace": "2026-08-06T15:10", "flip_c74": True,
     "query": "c15 eta를 알려줘",
     "c63": (0.0113,), "c74": 0.3371, "c74_flat": False},
    {"key": "A4", "trace": "2026-08-06T09:32", "flip_c74": True,
     "query": "에러가 발생했나?",
     "c63": (0.0192,), "c74": 0.3184, "c74_flat": False},
]


def rpc(name: str, arguments: dict) -> dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(
        FORGET_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    body = json.loads(urllib.request.urlopen(request, timeout=30).read())
    return json.loads(body["result"]["content"][0]["text"])


def eligible(item: dict) -> bool:
    """훅 `_injection_eligible` 판정 복제 (c63·c74와 동일한 구조적 배제)."""
    md = item.get("metadata") or {}
    if md.get("hook"):
        return False
    if md.get("assertion_kind") == "task_state":
        return False
    if md.get("superseded_by"):
        return False
    supersedes = md.get("supersedes")
    if isinstance(supersedes, list) and supersedes:
        return False
    return True


def loop_origin(item: dict) -> bool:
    """1차 자동 판정 — 루프 유래 기억인가. 최종 판정은 노트에서 근거와 함께."""
    text = str(item.get("memory") or "")
    return "devloop" in text.lower()


def flat_verdict(scores: list[float]) -> tuple[bool, float, int]:
    if len(scores) < MIN_SAMPLES:
        return (False, float("nan"), len(scores))   # 게이트 미적용 = 전량 통과
    spread = scores[0] - scores[len(scores) // 2]
    return (spread < MARGIN, spread, len(scores))


def ledger_lookup(query: str) -> tuple[str, dict | None, str]:
    """앵커 질의의 원장 전체 질의+filters — 4행 한정 접촉 (관측 37 ③ 병기는 헤더 참조).

    c74 계기의 ANCHORS 일부는 접두였다(원문 주석 "접두, 당시 spread") — exact 실패 시
    접두 LIKE 폴백으로 원장의 전체 질의를 복원한다. c74 측정은 원장 전체 질의+filters로
    돌았으므로, 이 복원 없이는 수치 비교 가능성이 깨진다(1차 실행에서 A1이 실증).
    """
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT query, filters FROM context_traces "
        "WHERE query = ? AND payload LIKE '%turn_recall%' "
        "ORDER BY created_at DESC LIMIT 1", (query,)).fetchone()
    source = "exact"
    if row is None:
        row = conn.execute(
            "SELECT query, filters FROM context_traces "
            "WHERE query LIKE ? AND payload LIKE '%turn_recall%' "
            "ORDER BY created_at DESC LIMIT 1", (query[:20] + "%",)).fetchone()
        source = "prefix" if row else "constant"
    conn.close()
    if row is None:
        return query, None, source
    try:
        filters = json.loads(row["filters"] or "null")
    except Exception:
        filters = None
    return (row["query"] or query).strip(), (filters if isinstance(filters, dict) else None), source


def stack_header() -> str:
    try:
        health = rpc("get_provider_health", {})
    except Exception:
        return "몸: :8000 응답 없음 — 측정 불가"
    eff = health.get("effective") or {}
    chk = (health.get("checks") or {}).get("embeddings") or {}
    return (f"몸: :8000 구척도(0.275+rule*0.45+0.275*cos) · "
            f"effective={eff.get('embedding_provider')}:{eff.get('embedding_model')} "
            f"res={eff.get('resolution')} · checks(폴백 거울)={chk.get('provider')}:{chk.get('model')}")


def main() -> None:
    print(stack_header())
    print(f"자[尺] 고정: margin={MARGIN} min_samples={MIN_SAMPLES} window={WINDOW} "
          f"top_k={SHALLOW} — c74와 동일\n")

    counter_increments = 0
    persistence = {}
    sanitized_rows = []
    self_intervention = []

    for anchor in ANCHORS:
        query, filters, query_source = ledger_lookup(anchor["query"])
        args = {"query": query, "recall": "low",
                "score_breakdown": True, "top_k": SHALLOW}
        if filters:
            args["filters"] = filters
        results = rpc("search_memories", args).get("results") or []
        elig = [i for i in results if eligible(i)]
        scores = sorted((float(i.get("score") or 0) for i in elig), reverse=True)[:WINDOW]
        flat, spread, n = flat_verdict(scores)

        then = "/".join(f"{v:.4f}" for v in anchor["c63"])
        sp = "n/a" if math.isnan(spread) else f"{spread:.4f}"
        flipped_vs_c74 = (n >= MIN_SAMPLES) and (flat != anchor["c74_flat"])
        print(f"=== {anchor['key']} (trace {anchor['trace']}, {len(query)}자, "
              f"질의 출처={query_source}) filters={'예' if filters else '무'}")
        print(f"    c63 {then} → c74 {anchor['c74']:.4f} → c86 {sp} (자격 {n}) · "
              f"평지 c74={anchor['c74_flat']} c86={flat} · 반전(c74 대비)={flipped_vs_c74}")

        top = sorted(elig, key=lambda i: float(i.get("score") or 0), reverse=True)
        for rank, item in enumerate(top[:WINDOW], 1):
            sb = item.get("score_breakdown") or {}
            created = str(item.get("created_at") or "")[:19]
            marker = " LOOP" if loop_origin(item) else ""
            print(f"    top{rank} score={float(item.get('score') or 0):.4f} "
                  f"rule={sb.get('rule')} vec={sb.get('vector')} created={created}{marker}")

        top1 = top[0] if top else None
        top1_created = str(top1.get("created_at") or "")[:19] if top1 else ""

        if anchor["flip_c74"]:
            # (c) 지속성 검사 — 신규 증분 아님
            persists = top1 is not None and top1_created.startswith(C63_NOTE_CREATED[:16])
            persistence[anchor["key"]] = persists
            print(f"    [지속성] top-1이 c63 노트({C63_NOTE_CREATED})인가: {persists}")
        elif flipped_vs_c74:
            # (b) 새 반전 — 원인 검시. c74가 대조군 창 검시를 남기지 않아 단일 기억
            # 귀속이 불가능할 수 있다 — top-10을 배제 항목까지 펼쳐 창 이웃을 기록한다
            # (다음 재측정부터는 이 창이 대조 창이 된다).
            cause_is_loop = top1 is not None and loop_origin(top1)
            print(f"    [새 반전] 원인 top-1 created={top1_created} "
                  f"루프 유래(자동 1차)={cause_is_loop}")
            if cause_is_loop:
                counter_increments += 1
            deep = rpc("search_memories", {**args, "top_k": 10}).get("results") or []
            deep = sorted(deep, key=lambda i: float(i.get("score") or 0), reverse=True)
            print("    [창 검시 — top-10, 배제 포함]")
            for rank, item in enumerate(deep, 1):
                md = item.get("metadata") or {}
                sb = item.get("score_breakdown") or {}
                created = str(item.get("created_at") or "")[:19]
                flags = []
                if not eligible(item):
                    if md.get("hook"):
                        flags.append("excl:hook")
                    if md.get("assertion_kind") == "task_state":
                        flags.append("excl:task_state")
                    if md.get("superseded_by"):
                        flags.append("excl:superseded")
                    if isinstance(md.get("supersedes"), list) and md.get("supersedes"):
                        flags.append("excl:supersedes")
                if loop_origin(item):
                    flags.append("LOOP")
                print(f"      #{rank} score={float(item.get('score') or 0):.4f} "
                      f"rule={sb.get('rule')} vec={sb.get('vector')} "
                      f"created={created} {' '.join(flags)}")

        # (d) 이 사이클 작업 선택 기억의 개입 검사 — 08-09 생성 devloop 기억
        for item in top[:WINDOW]:
            created = str(item.get("created_at") or "")
            if created.startswith("2026-08-09") and loop_origin(item):
                self_intervention.append((anchor["key"], created[:19]))

        sanitized_rows.append({
            "key": anchor["key"], "trace": anchor["trace"],
            "chars": len(query), "query_source": query_source,
            "c63": list(anchor["c63"]), "c74": anchor["c74"],
            "c86_spread": None if math.isnan(spread) else round(spread, 4),
            "n": n, "c74_flat": anchor["c74_flat"], "c86_flat": flat,
            "flipped_vs_c74": flipped_vs_c74,
            "top1_created": top1_created,
            "top1_loop_origin": bool(top1 and loop_origin(top1)),
        })
        print()

    print(f"[관측 36 카운터 판정] 새 반전 중 루프 유래 = {counter_increments}건 → "
          f"카운터 {'+' + str(counter_increments) if counter_increments else '증분 없음 (0 유지)'}")
    print(f"[지속성 판정] c74 반전 2건의 봉우리 지속: "
          f"{ {k: v for k, v in persistence.items()} }")
    print(f"[자기 개입 검사] 이 사이클 작업 선택 기억(08-09)의 앵커 top-5 등장: "
          f"{self_intervention if self_intervention else '없음'}")

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "notes", "c86_anchor_rows.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(sanitized_rows, fh, ensure_ascii=False, indent=1)
    print(f"[원자료] {len(sanitized_rows)}행 → {out} (질의 원문 무포함 — 관측 36 ①)")


if __name__ == "__main__":
    main()
