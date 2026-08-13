#!/usr/bin/env python3
"""정훈-예측기 v0 — 되기(becoming) 통일 계기 (태스크 #10).

한 가지 질문에 하나의 곡선으로 답한다: **"얼마나 그가 되었나"** —
어떤 쌍둥이 변형(프롬프트-온리 / +기억 / 어댑터 / 미래 버전)이든
같은 원장(shadow_scores.jsonl)에서 같은 방법으로 채점된 곡선 위에 선다.

하는 일:
1. 소급 오염 필터 — 데몬 NOISE가 놓쳤던 자동화 표면([SUGGESTION MODE] 등)을
   실발화로 채점한 행을 표식(원장은 append-only이므로 삭제하지 않는다).
2. 변형×일 단위 곡선 집계 → curve_v0.jsonl.
3. W-트랙 A/B 표면: 방향 분포에서 교정률·승인률(어댑터 on/off 2주 크럭스의
   계기 — weights-and-context-first 선등록 "first-try 성공률·교정 횟수" v0 대용).

출처 규율: 원장의 어떤 행도 수정·삭제하지 않는다. 오염 판정은 이 스크립트의
CONTAM 정규식이 정본이고, 곡선은 매 실행 시 원장 전체에서 재파생된다.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCORES = Path.home() / ".forget/twin/shadow_scores.jsonl"
CURVE = Path.home() / ".forget/twin/curve_v0.jsonl"

# 데몬 NOISE의 소급 판(2026-08-13 확장분 포함): 실발화가 아닌 자동화 표면.
CONTAM = re.compile(
    r"\[SUGGESTION MODE|Suggest what the user might naturally type"
    r"|\[forget 회상|\[forget 캡슐|<command-|<local-command|<bash-input"
    r"|<system-reminder|Caveat:|\[SYSTEM NOTIFICATION|<task-notification"
    r"|The user (stepped away|sent a new message)|Recap in under"
    r"|This is how Claude Code surfaces",
    re.I,
)


def load_rows() -> list[dict]:
    rows = []
    for line in SCORES.open():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def main() -> None:
    if not SCORES.exists():
        sys.exit("원장 없음: " + str(SCORES))
    rows = load_rows()
    clean, dirty = [], []
    for r in rows:
        (dirty if CONTAM.search(str(r.get("actual") or "")[:300]) else clean).append(r)

    # 변형×일 곡선 (변형 필드가 없는 구행은 engine으로 소급 식별)
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in clean:
        variant = r.get("variant") or f"prompt-only/{r.get('engine', '?')}"
        day = str(r.get("ts") or r.get("scored_at") or "")[:10]
        buckets[(variant, day)].append(r)

    CURVE.write_text("")
    with CURVE.open("a") as fh:
        for (variant, day), items in sorted(buckets.items()):
            sims = [i["sim"] for i in items if i.get("sim", -1) >= 0]
            dirm = [i["dir_match"] for i in items if "dir_match" in i]
            dirs = [i.get("dir_actual") for i in items]
            n = len(items)
            fh.write(json.dumps({
                "variant": variant, "day": day, "n": n,
                "sim_mean": round(sum(sims) / max(1, len(sims)), 4),
                "dir_acc": round(sum(dirm) / max(1, len(dirm)), 4),
                # W-트랙 A/B 표면 v0: 정훈 실발화의 방향 분포 —
                # 교정률(어시스턴트 산출이 교정을 유발한 비율)·승인률.
                "correct_rate": round(dirs.count("correct") / max(1, n), 4),
                "approve_rate": round(dirs.count("approve") / max(1, n), 4),
            }, ensure_ascii=False) + "\n")

    sims = [r["sim"] for r in clean if r.get("sim", -1) >= 0]
    dirm = [r["dir_match"] for r in clean if "dir_match" in r]
    dirs = [r.get("dir_actual") for r in clean]
    print(json.dumps({
        "total_rows": len(rows),
        "contaminated": len(dirty),
        "contamination_rate": round(len(dirty) / max(1, len(rows)), 4),
        "clean_n": len(clean),
        "clean_sim_mean": round(sum(sims) / max(1, len(sims)), 4),
        "clean_dir_acc": round(sum(dirm) / max(1, len(dirm)), 4),
        "correct_rate": round(dirs.count("correct") / max(1, len(clean)), 4),
        "approve_rate": round(dirs.count("approve") / max(1, len(clean)), 4),
        "curve": str(CURVE),
    }, ensure_ascii=False, indent=2))
    if dirty:
        print("\n오염 표본 (최대 3):", file=sys.stderr)
        for r in dirty[:3]:
            print("  -", str(r.get("actual"))[:80].replace("\n", " "), file=sys.stderr)


if __name__ == "__main__":
    main()
