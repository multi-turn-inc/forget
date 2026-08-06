#!/usr/bin/env python3
"""c68 보조 — ON 팔의 표적 미반환 10/12의 원인 진단 (read-only).

가설 A: 스코프. 훅과 같은 layered_filter로 검색하는데 표본은 DB 전체에서 뽑았으므로
        다른 스코프(user/app/run)의 기억은 애초에 후보에 없다 → 계측기 결함.
가설 B: 랭킹. 스코프 안에 있는데 top_15 밖으로 밀렸다 → 실제 회상 실패(제품 발견).
두 가설은 스코프 컬럼과 필터 통과 여부로 갈린다. 귀속 전에 배제한다.
"""
from __future__ import annotations

import importlib.util
import os
import random
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    "c59_oracle_replay", os.path.join(HERE, "c59_oracle_replay.py"))
c59 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c59)

DB = os.environ.get("FORGET_DB", os.path.expanduser("~/.forget/forget.sqlite3"))
SEED = 68
N_SELF = 12

MISS = {"8af1a31b", "cdad16e1", "e42c8171", "c2e5cd8a", "e2edaf50",
        "5a91c327", "b298c952", "4a6594df", "8a448763", "28921b0e"}
HIT = {"d15c454f", "c348dd6f"}


def main() -> None:
    con = sqlite3.connect("file:" + DB + "?mode=ro", uri=True)
    cur = con.cursor()
    cur.execute("select id, memory from memories where deleted=0 and length(memory) >= 80")
    rows = [(str(i), str(m)) for i, m in cur.fetchall()]
    rng = random.Random(SEED)
    rng.shuffle(rows)
    picked = [r[0] for r in rows[:N_SELF]]

    cur.execute("pragma table_info(memories)")
    cols = [c[1] for c in cur.fetchall()]
    scope_cols = [c for c in cols
                  if c in ("user_id", "agent_id", "app_id", "run_id", "project_id")]
    print("스코프 컬럼:", scope_cols)

    from forget_project import layered_filter, project_key_for_path, scope_disabled
    project = None if scope_disabled() else project_key_for_path(c59.CWD)
    print("훅이 쓰는 project =", project)
    print("layered_filter    =", layered_filter(project) if project else None)
    print()

    for mid in picked:
        cur.execute("select " + ",".join(scope_cols) + " from memories where id=?", (mid,))
        r = cur.fetchone()
        tag = "MISS" if mid[:8] in MISS else ("HIT " if mid[:8] in HIT else "?   ")
        print("  " + tag + " " + mid[:8] + "  " +
              "  ".join(c + "=" + repr(v) for c, v in zip(scope_cols, r)))
    con.close()


if __name__ == "__main__":
    main()
