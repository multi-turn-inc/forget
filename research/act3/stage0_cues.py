"""Act-3 Stage 0 — prospective-cue kill switch (retrieval-only, no reader).

Three arms on dev-42: baseline (raw turns), treatment (turns + per-session
predicted cues), placebo (cues shuffled to wrong sessions). Metric:
evidence-session coverage@42 against LongMemEval answer_session_ids.
Cue generator sees ONLY session content — never the benchmark question.

Pre-registered bar (research/act3/validation.md): treatment >= baseline
+5pp AND treatment > placebo +3pp, else act-3 dies.

    python research/act3/stage0_cues.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import DATASETS, stratified_sample  # noqa: E402

CUES = Path(__file__).resolve().parent / "cues"
OUT = Path(__file__).resolve().parent
CUE_MODEL = "gpt-4o-mini"
TOP_K = 42

CUE_SYS = (
    "You index a user's conversation session for future recall. Read the session and "
    "write 3 short questions the user might plausibly ask LATER whose answers this "
    "session contains. Focus on user-specific facts, events, plans, preferences, and "
    "concrete details (names, numbers, dates). One question per line, no numbering."
)


def gen_cues(oai: OpenAI, inst: dict) -> list[list[str]]:
    CUES.mkdir(exist_ok=True)
    cache = CUES / f"{CUE_MODEL}--{inst['question_id']}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    def one(session):
        convo = "\n".join(f"{t['role']}: {t['content']}" for t in session
                          if "role" in t and "content" in t)
        for attempt in range(4):
            try:
                r = oai.chat.completions.create(
                    model=CUE_MODEL, temperature=0.3, max_tokens=150,
                    messages=[{"role": "system", "content": CUE_SYS},
                              {"role": "user", "content": convo[:6000]}])
                lines = [l.strip("-•. ").strip() for l in
                         r.choices[0].message.content.strip().splitlines()]
                return [l for l in lines if len(l) > 10][:3]
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
    with ThreadPoolExecutor(max_workers=8) as pool:
        cues = list(pool.map(one, inst["haystack_sessions"]))
    cache.write_text(json.dumps(cues, ensure_ascii=False))
    return cues


def coverage(model, inst, cues_per_session, arm: str, rng) -> float:
    """Fraction of answer sessions present in the top-K entry->session map."""
    entries, owners = [], []
    for si, session in enumerate(inst["haystack_sessions"]):
        for t in session:
            if "role" in t and "content" in t:
                entries.append(f"{t['role']}: {t['content']}")
                owners.append(si)
    if arm != "baseline":
        cue_sets = cues_per_session
        if arm == "placebo":  # shuffle cue sets to wrong sessions (derangement-ish)
            idx = list(range(len(cue_sets)))
            rng.shuffle(idx)
            cue_sets = [cues_per_session[i] for i in idx]
        for si, cs in enumerate(cue_sets):
            for c in (cs or []):
                entries.append(c)
                owners.append(si)
    embs = np.array(list(model.embed(entries)))
    embs /= np.linalg.norm(embs, axis=1, keepdims=True)
    q = np.array(list(model.embed([inst["question"]])))[0]
    q /= np.linalg.norm(q)
    top = np.argsort(-(embs @ q))[:TOP_K]
    top_sessions = {owners[i] for i in top}
    ans = {inst["haystack_session_ids"].index(sid)
           for sid in inst["answer_session_ids"] if sid in inst["haystack_session_ids"]}
    if not ans:
        return None
    return len(ans & top_sessions) / len(ans)


def main() -> int:
    from fastembed import TextEmbedding
    data = json.loads(DATASETS["s"].read_text())
    insts = stratified_sample(data, 42, random.Random(42))
    oai = OpenAI()
    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    rng = random.Random(7)
    rows = []
    for i, inst in enumerate(insts, 1):
        cues = gen_cues(oai, inst)
        row = {"question_id": inst["question_id"], "type": inst["question_type"]}
        for arm in ("baseline", "treatment", "placebo"):
            row[arm] = coverage(model, inst, cues, arm, rng)
        rows.append(row)
        print(f"[{i}/42] b={row['baseline']} t={row['treatment']} p={row['placebo']} "
              f"{inst['question_type']}", flush=True)
    valid = [r for r in rows if r["baseline"] is not None]
    summary = {arm: round(float(np.mean([r[arm] for r in valid])), 4)
               for arm in ("baseline", "treatment", "placebo")}
    summary["n"] = len(valid)
    d_t = summary["treatment"] - summary["baseline"]
    d_p = summary["treatment"] - summary["placebo"]
    summary["verdict"] = ("PASS" if d_t >= 0.05 and d_p >= 0.03 else "KILL")
    (OUT / "stage0.results.json").write_text(json.dumps(rows, indent=1))
    (OUT / "stage0.summary.json").write_text(json.dumps(summary, indent=1))
    print("\n" + json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
