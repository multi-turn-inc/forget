"""평가셋 v1 — 지어낸 문항을 관측된 라벨로 갈아치운다. (2026-08-23)

왜 이 파일이 있는가. 조립기 평가가 n=8 자작 문항이었고, 그 8문항은 내가 쓴 것이라
내가 만든 조립기를 심판할 자격이 없었다(감사 항목 2). 원장을 뒤져보니 이유가 나왔다:

  기계(세션 재개) 질의  used_memory_ids gold 28건  ← 자율 박자가 스스로 라벨을 남긴다
  사람(정훈) 턴 질의    gold 0건 / 784건           ← 채널이 비어 있었다
                        라벨 있는 것 67건, 그중 51건이 selection_failure

사람 층에 양성 gold가 없다는 것은 결함이지 소음이 아니다. 그래서 층마다 다른 것을 잰다:

  A. machine_resume  검색력 — gold가 후보에 들어왔는가(천장) · 선택됐는가(랭킹)
  B. human_noise     회피력 — 소음으로 판정된 기억을 같은 질의에 또 넣는가
  C. human_helped    약한 양성 — 트레이스 단위로 '도움됐다'만 아는 12건 (weight 0.4)

B가 핵심이다: 양성 gold가 없어도 "이건 넣지 말았어야 했다"는 관측은 51건 있고,
재주입은 반박 불가한 회귀다. 천장(retrieval)과 랭킹 손실을 분리해 보고하는 것이
이 설계의 목적 — '못 가져왔다'와 '가져와서 버렸다'는 다른 병이고 처방도 다르다.

읽기 전용. 출력: research/eval/eval_set_v1.jsonl (+ .manifest.json)
사용: .venv/bin/python scripts/build_eval_set.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

DB = os.environ.get("MEM1_DB_PATH", str(Path.home() / ".forget/forget.sqlite3"))
REPO = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "research/eval/eval_set_v1.jsonl"

MIN_QUERY_CHARS = 6
TEST_FRACTION = 0.3      # 최근 30%는 시험용 — 시간 분할(과거로 고르고 미래로 시험)


def loads(value, default):
    try:
        parsed = json.loads(value) if value else default
        return parsed if isinstance(parsed, type(default)) else default
    except Exception:
        return default


def source_of(payload) -> str | None:
    return (loads(payload, {}) or {}).get("source")


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    alive = {
        str(r[0]) for r in con.execute("SELECT id FROM memories WHERE deleted = 0")
    }
    rows = con.execute(
        """
        SELECT t.trace_id, t.query, t.payload, t.filters, t.candidate_ids, t.selected_ids,
               o.used_memory_ids, o.harmful_memory_ids, o.failure_stage, t.created_at
        FROM context_traces t
        JOIN context_outcomes o ON o.trace_id = t.trace_id
        WHERE t.query IS NOT NULL AND t.query != ''
        ORDER BY t.created_at
        """
    ).fetchall()
    con.close()

    items: list[dict] = []
    dropped = {"short": 0, "no_label": 0, "all_dead": 0, "reasoning": 0}

    for tid, query, payload, filters, cand, sel, used, harmful, stage, created in rows:
        query = str(query).strip()
        if len(query) < MIN_QUERY_CHARS:
            dropped["short"] += 1
            continue
        if stage == "reasoning_failure":
            dropped["reasoning"] += 1      # 회상이 아니라 추론이 실패한 턴 — 조립기의 죄가 아니다
            continue
        keep = lambda ids: [i for i in (str(x) for x in loads(ids, [])) if i in alive]  # noqa: E731
        gold, forbid = keep(used), keep(harmful)
        selected = keep(sel)
        human = source_of(payload) == "turn_recall"

        if gold:
            stratum, weight = ("human_gold" if human else "machine_resume"), 1.0
        elif forbid:
            stratum, weight = ("human_noise" if human else "machine_noise"), 1.0
        elif stage == "selection_failure" and selected:
            stratum, weight, forbid = ("human_noise" if human else "machine_noise"), 1.0, selected
        elif stage == "none" and selected:
            stratum, weight, gold = ("human_helped" if human else "machine_helped"), 0.4, selected
        else:
            dropped["no_label"] += 1
            continue
        if not gold and not forbid:
            dropped["all_dead"] += 1        # 라벨이 가리킨 기억이 전부 삭제됨 — 채점 불가
            continue

        items.append({
            "id": hashlib.sha1(f"{tid}".encode()).hexdigest()[:12],
            "stratum": stratum,
            "human": human,
            "query": query,
            "filters": loads(filters, {}),
            "gold_ids": gold,
            "forbidden_ids": forbid,
            "n_candidates": len(loads(cand, [])),
            "n_selected_then": len(loads(sel, [])),
            "weight": weight,
            "created_at": str(created),
            "trace_id": str(tid),
        })

    split = int(len(items) * (1 - TEST_FRACTION))
    for i, it in enumerate(items):
        it["split"] = "dev" if i < split else "test"   # 시간 순 정렬이므로 앞이 과거

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    strata: dict[str, int] = {}
    for it in items:
        strata[it["stratum"]] = strata.get(it["stratum"], 0) + 1
    manifest = {
        "built_at_db": DB,
        "n_items": len(items),
        "strata": strata,
        "dev": sum(1 for i in items if i["split"] == "dev"),
        "test": sum(1 for i in items if i["split"] == "test"),
        "dropped": dropped,
        "gold_channel_note": (
            "사람 턴의 used_memory_ids는 원장에 0건이다 — 사람 층의 양성 gold는 "
            "관측되지 않았고 human_helped(트레이스 단위 약한 양성)로만 대리된다. "
            "사람 층 양성을 재려면 정훈이 서명한 문항이나 새 포착 채널이 필요하다."
        ),
        "label_bias_note": (
            "결과 라벨은 무작위 표본이 아니다 — 기록할 만한 턴에 편향된다. "
            "따라서 소음 비율은 기저율이 아니라 '라벨된 것 중의 비율'로만 읽는다."
        ),
    }
    (OUT.parent / (OUT.stem + ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"평가셋 {len(items)}문항 → {OUT}")
    for k, v in sorted(strata.items(), key=lambda kv: -kv[1]):
        print(f"  {k:16s} {v}")
    print(f"  분할: dev {manifest['dev']} / test {manifest['test']} (시간 순)")
    print(f"  탈락: {dropped}")


if __name__ == "__main__":
    main()
