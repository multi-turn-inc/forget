"""평가셋 v1로 조립기를 채점한다. (2026-08-23)

두 병을 분리해 보고하는 것이 이 채점기의 존재 이유다:

  천장(ceiling)  gold가 후보에 들어왔는가 — 검색의 책임
  랭킹(ranking)  후보에 있던 gold가 선택됐는가 — 순위·예산의 책임

이 둘을 합쳐 한 숫자로 보고하면 처방을 못 고른다. 실제로 recency 가중치를 0.05→0.60으로
훑어도 결과가 꼼짝 안 했던 것은(2026-08-23) 병이 랭킹이 아니라 천장이었기 때문이다.
랭킹은 검색이 데려오지 않은 후보를 구제할 수 없다.

회피(avoidance)는 사람 층의 유일한 채점 가능 축이다: 소음으로 판정된 기억을 같은
질의에 다시 넣으면 재주입이고, 그건 반박 불가한 회귀다.

원장 보호: record_trace=False로 건식 실행한다. 사본 DB를 쓰려면 MEM1_DB_PATH를 넘긴다.
사용: .venv/bin/python scripts/run_eval.py [--split test|dev|all] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SET = REPO / "research/eval/eval_set_v1.jsonl"


def pct(num: float, den: float) -> str:
    return f"{100.0 * num / den:5.1f}%" if den else "    –"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["test", "dev", "all"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from forget.store import assemble_context  # DB 경로 확정 후 import

    items = [json.loads(l) for l in SET.open()]
    if args.split != "all":
        items = [i for i in items if i["split"] == args.split]
    if args.limit:
        items = items[: args.limit]

    agg: dict[str, dict[str, float]] = {}
    per_item = []
    t0 = time.time()
    for n, it in enumerate(items, 1):
        payload = {"query": it["query"], "filters": it["filters"], "record_trace": False}
        try:
            res = assemble_context(payload)
        except Exception as exc:
            print(f"  [{n}/{len(items)}] 실패 {type(exc).__name__}: {exc}")
            continue
        # 건식 모드에는 트레이스가 없다. debug가 후보/선택을 그대로 들고 있으므로 거기서 읽는다 —
        # 이 둘을 구별해야 천장과 랭킹 손실이 갈린다(합치면 랭킹손실이 늘 0으로 보인다).
        dbg = res.get("debug") or {}
        cand = {str(x) for x in (dbg.get("raw_candidate_ids") or [])}
        sel = {str(x) for x in (dbg.get("selected_ids") or [])}
        if not sel:
            sel = {str(m.get("id")) for m in (res.get("memories") or []) if m.get("id")}
        cand |= sel      # 선택된 것은 정의상 후보였다
        if not cand:
            raise RuntimeError("후보·선택을 못 읽었다 — 채점 불가")

        gold, forbid = set(it["gold_ids"]), set(it["forbidden_ids"])
        s = agg.setdefault(it["stratum"], {})
        bump = lambda k, v=1.0: s.__setitem__(k, s.get(k, 0.0) + v)  # noqa: E731
        bump("n")
        row = {"id": it["id"], "stratum": it["stratum"]}
        if gold:
            bump("gold", len(gold))
            bump("gold_in_cand", len(gold & cand))
            bump("gold_in_sel", len(gold & sel))
            if gold & sel:
                bump("hit_any")
            row["gold_hit"] = f"{len(gold & sel)}/{len(gold)}"
            row["ceiling"] = f"{len(gold & cand)}/{len(gold)}"
        if forbid:
            bump("forbid", len(forbid))
            bump("forbid_resel", len(forbid & sel))
            if forbid & sel:
                bump("reinject_any")
            row["reinject"] = f"{len(forbid & sel)}/{len(forbid)}"
        row["n_sel"] = len(sel)
        per_item.append(row)
        if n % 10 == 0:
            print(f"  … {n}/{len(items)} ({time.time() - t0:.0f}s)")

    print(f"\n평가셋 {SET.name} · split={args.split} · {len(per_item)}문항 "
          f"· {time.time() - t0:.0f}s · DB={os.environ.get('MEM1_DB_PATH', '기본')}\n")
    head = f"{'층':16s} {'문항':>4s} {'천장':>7s} {'선택':>7s} {'랭킹손실':>8s} {'재주입':>7s}"
    print(head)
    print("-" * len(head))
    for name, s in sorted(agg.items(), key=lambda kv: -kv[1].get("n", 0)):
        ceil_ = s.get("gold_in_cand", 0)
        selg = s.get("gold_in_sel", 0)
        goldn = s.get("gold", 0)
        loss = ceil_ - selg
        print(f"{name:16s} {int(s['n']):4d} {pct(ceil_, goldn):>7s} {pct(selg, goldn):>7s} "
              f"{pct(loss, ceil_) if ceil_ else '    –':>8s} "
              f"{pct(s.get('forbid_resel', 0), s.get('forbid', 0)):>7s}")

    tot_gold = sum(s.get("gold", 0) for s in agg.values())
    tot_ceil = sum(s.get("gold_in_cand", 0) for s in agg.values())
    tot_sel = sum(s.get("gold_in_sel", 0) for s in agg.values())
    tot_forbid = sum(s.get("forbid", 0) for s in agg.values())
    tot_re = sum(s.get("forbid_resel", 0) for s in agg.values())
    print("-" * len(head))
    print(f"{'전체':16s} {len(per_item):4d} {pct(tot_ceil, tot_gold):>7s} {pct(tot_sel, tot_gold):>7s} "
          f"{pct(tot_ceil - tot_sel, tot_ceil) if tot_ceil else '    –':>8s} "
          f"{pct(tot_re, tot_forbid):>7s}")
    print(f"\n해석: 천장 {pct(tot_ceil, tot_gold).strip()}는 검색이 데려온 비율 — "
          f"랭킹으로 구제 가능한 상한이다. 그 위는 검색을 고쳐야 오른다.")

    if args.out:
        Path(args.out).write_text(json.dumps(
            {"split": args.split, "strata": agg, "items": per_item}, ensure_ascii=False, indent=2))
        print(f"상세: {args.out}")


if __name__ == "__main__":
    main()
