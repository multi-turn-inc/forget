"""α kill-switch pilot — do counterfactual utility labels exist and are they sparse?

For instances the locked v3 config answered CORRECTLY, remove one retrieved
memory at a time and re-score. A memory whose removal flips the answer has
positive marginal utility. Hypotheses this pilot must support to proceed:

  S1 (existence): most correct answers have >=1 flip-causing memory.
  S2 (sparsity):  flip-causing memories are a small fraction of retrieved
                  context (the learnable signal is sparse, like real labels).
  S3 (control):   low-rank random memories almost never flip (labels are not
                  noise from reader instability).

Cost control: LOO over top-8 observation + top-4 raw memories by rank,
plus 6 random low-rank controls -> 19 reader+judge pairs per instance,
12 instances (2 per question_type) ~= $10.

    python research/alpha/counterfactual_pilot.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import READER_SYS_V3, judge, read_answer  # noqa: E402
from observer import get_observations, normalize_date  # noqa: E402

DATA = json.loads((ROOT / "research" / "longmemeval-data" / "longmemeval_s_cleaned.json").read_text())
BYID = {d["question_id"]: d for d in DATA}
V3 = json.loads((ROOT / "research" / "longmemeval" / "runs" / "full-v3-500.results.json").read_text())
OUT = ROOT / "research" / "alpha"
URL = "http://localhost:8002"
OBS_MODEL = "gpt-4o"
OBS_K, RAW_K = 60, 42
LOO_OBS, LOO_RAW, N_CONTROL = 8, 4, 6


def build_and_retrieve(client: httpx.Client, inst: dict) -> tuple[list[dict], list[dict]]:
    oai = OpenAI()
    entries = get_observations(oai, OBS_MODEL, inst)  # cached
    scope, raw_scope = f"cf-{inst['question_id']}", f"cfraw-{inst['question_id']}"
    for s in (scope, raw_scope):
        client.request("DELETE", "/v1/memories/", json={"user_id": s, "app_id": "lme"})
    for e in entries:
        created = normalize_date(e["date"] or inst.get("question_date", ""))
        for line in e["observations"].splitlines():
            line = line.strip().lstrip("-• ").strip()
            if len(line) > 8:
                client.post("/v1/memories/", json={"text": line, "infer": False,
                    "user_id": scope, "app_id": "lme", "created_at": created}).raise_for_status()
    dates = inst.get("haystack_dates") or []
    for si, session in enumerate(inst["haystack_sessions"]):
        created = normalize_date(dates[si] if si < len(dates) else inst.get("question_date", ""))
        for turn in session:
            if "role" in turn and "content" in turn:
                client.post("/v1/memories/", json={"text": f"{turn['role']}: {turn['content']}",
                    "infer": False, "user_id": raw_scope, "app_id": "lme", "created_at": created}).raise_for_status()
    def search(s, k):
        r = client.post("/v3/memories/search/", json={"query": inst["question"], "top_k": k,
            "temporal_rerank": True, "filters": {"user_id": s, "app_id": "lme"}})
        r.raise_for_status()
        return r.json()["results"]
    obs_mem, raw_mem = search(scope, OBS_K), search(raw_scope, RAW_K)
    for s in (scope, raw_scope):
        client.request("DELETE", "/v1/memories/", json={"user_id": s, "app_id": "lme"})
    return obs_mem, raw_mem


def score(oai: OpenAI, inst: dict, memories: list[dict]) -> bool:
    hyp = read_answer(oai, "gpt-4o", inst["question"], inst.get("question_date", ""),
                      memories, two_stage=True, reader_sys=READER_SYS_V3)
    return judge(oai, "gpt-4o", inst, hyp)


def main() -> int:
    rng = random.Random(42)
    by_type = defaultdict(list)
    for r in V3:
        if r["correct"]:
            by_type[r["question_type"]].append(r["question_id"])
    picks = []
    for t in sorted(by_type):
        pool = by_type[t][:]
        rng.shuffle(pool)
        picks.extend(pool[:2])
    print(f"파일럿 인스턴스 {len(picks)}개", flush=True)

    oai = OpenAI()
    rows = []
    with httpx.Client(base_url=URL, timeout=180) as client:
        for qi, qid in enumerate(picks, 1):
            inst = BYID[qid]
            obs_mem, raw_mem = build_and_retrieve(client, inst)
            memories = obs_mem + raw_mem
            base_ok = score(oai, inst, memories)
            print(f"[{qi}/{len(picks)}] {inst['question_type']:26} base={'✓' if base_ok else '✗(재현실패)'}", flush=True)
            if not base_ok:
                rows.append({"question_id": qid, "type": inst["question_type"],
                             "base_reproduced": False})
                continue
            # LOO targets: top-ranked obs + raw, plus low-rank random controls
            targets = [("obs", i) for i in range(min(LOO_OBS, len(obs_mem)))]
            targets += [("raw", i) for i in range(min(LOO_RAW, len(raw_mem)))]
            tail = [("obs", i) for i in range(LOO_OBS, len(obs_mem))] + \
                   [("raw", i) for i in range(LOO_RAW, len(raw_mem))]
            rng.shuffle(tail)
            controls = tail[:N_CONTROL]
            flips = []
            for kind, idx in targets + controls:
                pool = obs_mem if kind == "obs" else raw_mem
                reduced = [m for j, m in enumerate(obs_mem) if not (kind == "obs" and j == idx)] + \
                          [m for j, m in enumerate(raw_mem) if not (kind == "raw" and j == idx)]
                ok = score(oai, inst, reduced)
                flips.append({"kind": kind, "rank": idx, "control": (kind, idx) in controls,
                              "flip": not ok, "memory": pool[idx]["memory"][:120]})
                time.sleep(0.2)
            n_flip = sum(f["flip"] for f in flips if not f["control"])
            c_flip = sum(f["flip"] for f in flips if f["control"])
            print(f"    표적플립 {n_flip}/{len(targets)} · 대조플립 {c_flip}/{len(controls)}", flush=True)
            rows.append({"question_id": qid, "type": inst["question_type"],
                         "base_reproduced": True, "flips": flips,
                         "target_flips": n_flip, "control_flips": c_flip})

    reproduced = [r for r in rows if r.get("base_reproduced")]
    s1 = sum(1 for r in reproduced if r["target_flips"] >= 1) / len(reproduced) if reproduced else 0
    all_target = sum(len([f for f in r["flips"] if not f["control"]]) for r in reproduced)
    all_tflip = sum(r["target_flips"] for r in reproduced)
    all_cn = sum(len([f for f in r["flips"] if f["control"]]) for r in reproduced)
    all_cflip = sum(r["control_flips"] for r in reproduced)
    summary = {
        "n_instances": len(picks), "n_reproduced": len(reproduced),
        "S1_existence_rate": round(s1, 3),
        "S2_target_flip_rate": round(all_tflip / all_target, 3) if all_target else None,
        "S3_control_flip_rate": round(all_cflip / all_cn, 3) if all_cn else None,
        "verdict_hint": "S1>=0.5 and S3<<S2 => signal exists; S2 low => sparse (good)",
    }
    (OUT / "pilot.results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    (OUT / "pilot.summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
