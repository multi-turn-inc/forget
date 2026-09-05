"""억제 간선 계약 시험 — supersede 쌍의 행동 계약. (본선 3, 2026-08-23)

뇌 사양: 새 학습은 옛 기억을 지우지도 딱지 붙이지도 않는다 — 인출 시점에
**경쟁**한다. 대체본이 함께 인출되면 이기고(억압), 대체본이 그 맥락에 없으면
구본이 표면화하며(renewal), 시점 질의("7월엔 뭐라고 믿었지")는 옛 상태를 되살린다.

통계가 아니라 계약이다: 원장의 실제 supersede 쌍(구본·대체본 모두 생존 18쌍
실측)을 전건 검사한다. 질의는 두 텍스트의 공유 내용어에서 기계적으로 유도한다
(어느 쪽에도 유리하지 않게).

## 사전 등록 판정 (숫자를 보기 전에 고정)

  C-A (질서): 공유-주제 질의 결과에 둘 다 들면 대체본이 구본 위. 실패 0 목표,
      1건 이하 허용(쌍의 의미가 애매할 수 있음 — 실패는 개별 첨부).
  C-B (동반): 구본이 결과에 드는 질의에서 대체본도 함께, 그리고 위에 보인다.
      현행은 간선을 안 쓰므로 기준선이 낮을 것으로 예상 — 구현 후 상승이 판정.
  C-C (재부상): memory_as_of = supersede 하루 전 질의에서 구본이 회수된다.
      현행 예상: 전멸 (supersede가 updated_at을 올려 as_of 필터가 행을 제외 —
      코드 확인 완료). 구현 후 회복이 판정.
  C-D (고립 비강등): 대체본이 후보권 밖인 질의에서 구본이 ×0.45 강등 없이
      선다 — 주제의 유일한 담지자를 누르면 주제가 통째로 사라진다.

  측정 창 정정 (1차 실행 후 공개 기록): 처음 창은 top-10이었고 그 창에서는
  구본이 아예 안 보여 A·B·D의 측정 가능 쌍이 0이었다 — 계약이 공허했다.
  질서 의미론은 그대로 두고 관측 창만 top-50으로 넓힌다. 사용자 노출은 여전히
  조립기 top-k가 정하므로, 이 창은 '기전이 발화할 때 옳게 발화하는가'를 본다.

적용 규칙: 구현 후 C-A 유지 & C-B·C-C 상승이면 채택. C-A가 깨지면(구본이
대체본을 이기기 시작) 기각 — 억압이 경쟁의 본질이다.

읽기 전용 의도 — 반드시 사본 DB에 걸 것 (search가 SEARCH 이벤트·트레이스를 쓴다).
사용: MEM1_DB_PATH=<사본> .venv/bin/python scripts/contract_inhibition.py [--asof-only]
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta

DB = os.environ.get("MEM1_DB_PATH", "")
_STOP = set("the a an is are was were of to in for and or on at with by from user said tool observed "
            "그리고 그러나 있다 없다 한다 했다 됐다 것 수 등 및 이 그 저 은 는 이них 가 을 를 의 에 로 와 과".split())


def content_words(text: str) -> list[str]:
    words = re.split(r"[^\w가-힣.%-]+", text.lower())
    return [w for w in words if len(w) >= 2 and w not in _STOP and not w.isdigit()]


def shared_query(old: str, new: str, k: int = 6) -> str:
    """두 텍스트의 공유 내용어 상위 k개 — 어느 쪽에도 유리하지 않은 주제 질의."""
    o, n = Counter(content_words(old)), Counter(content_words(new))
    shared = [(min(o[w], n[w]) * (o[w] + n[w]), w) for w in set(o) & set(n)]
    return " ".join(w for _, w in sorted(shared, reverse=True)[:k])


def main() -> None:
    if not DB:
        sys.exit("MEM1_DB_PATH 필요 (사본!)")
    from forget.store import search_memories

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    pairs = []
    for mid, meta, mem, uid in con.execute(
        "SELECT id, metadata, memory, user_id FROM memories "
        "WHERE deleted=0 AND metadata LIKE '%superseded_by%'"
    ):
        m = json.loads(meta or "{}") or {}
        new_id = m.get("superseded_by")
        if not new_id:
            continue
        row = con.execute("SELECT memory, user_id, deleted FROM memories WHERE id=?", (str(new_id),)).fetchone()
        if row and row[2] == 0:
            pairs.append({"old_id": str(mid), "new_id": str(new_id), "old": str(mem),
                          "new": str(row[0]), "uid": str(uid or row[1] or "junghunkim"),
                          "superseded_at": str(m.get("superseded_at") or "")})
    con.close()
    print(f"시험 가능 쌍 {len(pairs)}\n")

    res = {"A_pass": 0, "A_fail": 0, "A_na": 0, "B_pass": 0, "B_total": 0,
           "C_pass": 0, "C_total": 0, "D_undemoted": 0, "D_total": 0}
    fails = []
    for p in pairs:
        q = shared_query(p["old"], p["new"])
        if len(q) < 6:
            res["A_na"] += 1
            continue
        r = search_memories({"query": q, "filters": {"user_id": p["uid"]}, "top_k": 50,
                             "score_breakdown": True})
        ranks = {str(m.get("id")): i for i, m in enumerate(r.get("results") or [])}
        ro, rn = ranks.get(p["old_id"]), ranks.get(p["new_id"])

        if ro is not None and rn is not None:                      # C-A 질서
            if rn < ro:
                res["A_pass"] += 1
            else:
                res["A_fail"] += 1
                fails.append(("A", q[:40], p["old"][:44]))
        else:
            res["A_na"] += 1
        if ro is not None:                                          # C-B 동반
            res["B_total"] += 1
            res["B_pass"] += rn is not None
            # C-D 고립 비강등 — 구본이 떴는데 대체본이 없을 때 강등 배수가 적용됐나
            if rn is None:
                res["D_total"] += 1
                hit = next(m for m in r["results"] if str(m.get("id")) == p["old_id"])
                res["D_undemoted"] += not (m2 := (hit.get("score_breakdown") or {})).get("superseded")

        if p["superseded_at"]:                                      # C-C 재부상
            try:
                asof = (datetime.fromisoformat(p["superseded_at"].replace("Z", "+00:00"))
                        - timedelta(days=1)).isoformat()
            except ValueError:
                continue
            res["C_total"] += 1
            r2 = search_memories({"query": q, "filters": {"user_id": p["uid"]},
                                  "top_k": 50, "memory_as_of": asof})
            res["C_pass"] += any(str(m.get("id")) == p["old_id"] for m in r2.get("results") or [])

    print(f"C-A 질서   : 통과 {res['A_pass']} · 실패 {res['A_fail']} · 판정불가 {res['A_na']}")
    print(f"C-B 동반   : {res['B_pass']}/{res['B_total']} (구본 노출 시 대체본 동반율)")
    print(f"C-C 재부상 : {res['C_pass']}/{res['C_total']} (as_of=supersede 전날, 구본 회수율)")
    print(f"C-D 비강등 : {res['D_undemoted']}/{res['D_total']} (대체본 부재 시 구본 비강등율)")
    for tag, q, t in fails[:5]:
        print(f"  ✗{tag} q={q} old={t}")


if __name__ == "__main__":
    main()
