"""어텐션 실험용 컨텍스트 내보내기. (2026-08-23)

평가셋 v1의 gold 보유 질의마다 조립기를 건식으로 돌려, 실제 후보 좌석과
gold 라벨을 실험 장치(4090 attn-lab)가 먹을 수 있는 JSONL로 만든다.

각 항목:
  {qid, query, stratum, seats: [{id, text, gold}], n_gold}

좌석 구성: 조립기가 실제로 고려한 후보(debug.raw_candidate_ids)를 텍스트로
복원하되, gold가 후보에 없으면(검색이 못 데려온 경우) 그 항목은 건너뛴다 —
이 실험은 '주입된 것 중 무엇을 읽었나'를 재므로 gold가 주입 안 되면 잴 것이 없다.
음성 대조용 무관 좌석 1석은 다른 층의 무작위 기억에서 뽑아 gold=False로 섞는다.

사용: MEM1_DB_PATH=<사본> .venv/bin/python scripts/export_attn_contexts.py [출력.jsonl]
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SET = REPO / "research/eval/eval_set_v1.jsonl"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "research/eval/attn_contexts_v0.jsonl"

MAX_SEATS = 10          # 좌석 수 상한 — 27B 4bit @ 4090의 컨텍스트 여유 안
SEAT_CHARS = 400        # 좌석 텍스트 절단 — 토큰 예산 통제
RNG = random.Random(20260823)   # 재현 가능한 셔플·표집


def main() -> None:
    from forget.db import get_db
    from forget.store import assemble_context

    items = [json.loads(l) for l in SET.open()]
    with_gold = [i for i in items if i["gold_ids"]]

    def text_of(ids: list[str]) -> dict[str, str]:
        if not ids:
            return {}
        with get_db() as conn:
            q = "SELECT id, memory FROM memories WHERE id IN (%s) AND deleted = 0" % ",".join("?" * len(ids))
            return {str(r[0]): str(r[1]) for r in conn.execute(q, ids)}

    # 음성 대조 풀: gold 질의들과 무관한 기억 (아무 gold/후보에도 안 나온 것)
    used_everywhere: set[str] = set()
    for it in items:
        used_everywhere.update(it["gold_ids"])
        used_everywhere.update(it["forbidden_ids"])
    with get_db() as conn:
        pool = [
            (str(r[0]), str(r[1])) for r in conn.execute(
                "SELECT id, memory FROM memories WHERE deleted = 0 "
                "AND length(memory) BETWEEN 40 AND 400 ORDER BY random() LIMIT 500")
            if str(r[0]) not in used_everywhere
        ]

    exported, skipped_gold_not_retrieved = [], 0
    for it in with_gold:
        res = assemble_context({"query": it["query"], "filters": it["filters"], "record_trace": False})
        cand_ids = [str(x) for x in (res.get("debug") or {}).get("raw_candidate_ids") or []]
        gold = set(it["gold_ids"])
        if not gold & set(cand_ids):
            skipped_gold_not_retrieved += 1     # 검색이 gold를 못 데려옴 — 이 실험의 관할 밖
            continue
        texts = text_of(cand_ids)
        seats = [{"id": cid, "text": texts[cid][:SEAT_CHARS], "gold": cid in gold}
                 for cid in cand_ids if texts.get(cid)][:MAX_SEATS]
        if sum(s["gold"] for s in seats) == 0 or len(seats) < 4:
            continue
        distractor = RNG.choice(pool)
        seats.append({"id": distractor[0], "text": distractor[1][:SEAT_CHARS],
                      "gold": False, "distractor": True})
        RNG.shuffle(seats)
        exported.append({
            "qid": it["id"], "query": it["query"], "stratum": it["stratum"],
            "seats": seats, "n_gold": sum(s["gold"] for s in seats),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for row in exported:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    n_seats = sum(len(r["seats"]) for r in exported)
    print(f"질의 {len(exported)}건 (gold 보유 {len(with_gold)} 중, 미인출 제외 {skipped_gold_not_retrieved})")
    print(f"좌석 {n_seats}석 · 질의당 평균 {n_seats / max(1, len(exported)):.1f}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
