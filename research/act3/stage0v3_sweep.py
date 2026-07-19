"""Act-3 Stage 0-v3 — budget sweep k in {4,8,16,42} (validation.md v1.2).

Content-delivery semantics: the unit is the TURN (doc2query: doc=turn).
Cues are index-only entries; a cue hit delivers its turn's text; delivered
set = first 42 unique payload turns. Ground truth = per-turn has_answer.

Arms (dev-42, _abs excluded — no evidence to find):
  baseline     rank turns by query
  placebo      turns + cues mapped to WRONG turns (style/volume control)
  cue-prior    turns + cues mapped correctly; generator gets a query-
               distribution prior (5 few-shot questions from OTHER instances)
  read-expand  HyDE at query time (no cues) — the strong read-side rival
  combo        cue-prior + read-expand (additivity)

Binding bar (v1.1): cue-prior error-reduction >=25% vs baseline AND sign-test
p<0.05. Novelty verdict needs cue-prior > read-expand; parity downgrades the
claim to write-once economics; below read-expand kills.
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from math import comb
from pathlib import Path

import numpy as np
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "longmemeval"))
from harness import DATASETS, stratified_sample  # noqa: E402

HERE = Path(__file__).resolve().parent
CUE_DIR = HERE / "cues-v2"
CUE_MODEL = "gpt-4o-mini"
TOP_K = 42
MIN_TURN_CHARS = 60

CUE_SYS = (
    "You index one message from a user's conversation history for future recall. "
    "Below are examples of the KINDS of questions users later ask their assistant:\n"
    "{examples}\n\n"
    "Write 2 short questions in that style whose answer is contained in the given "
    "message. Keep concrete details (names, numbers, dates). One per line, no numbering. "
    "If the message contains nothing a user would ever ask about, output NONE."
)


def few_shot_examples(data, self_qid, rng) -> str:
    pool = [d["question"] for d in data if d["question_id"] != self_qid]
    return "\n".join(f"- {q}" for q in rng.sample(pool, 5))


def gen_turn_cues(oai, inst, data, rng) -> dict[int, list[str]]:
    CUE_DIR.mkdir(exist_ok=True)
    cache = CUE_DIR / f"{CUE_MODEL}--{inst['question_id']}.json"
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text()).items()}
    sys_prompt = CUE_SYS.format(examples=few_shot_examples(data, inst["question_id"], rng))
    turns = []
    for si, sess in enumerate(inst["haystack_sessions"]):
        for t in sess:
            if "role" in t and "content" in t:
                turns.append((len(turns), f"{t['role']}: {t['content']}"))
    target = [(i, txt) for i, txt in turns if len(txt) >= MIN_TURN_CHARS]

    def one(pair):
        i, txt = pair
        for attempt in range(4):
            try:
                r = oai.chat.completions.create(
                    model=CUE_MODEL, temperature=0.3, max_tokens=120,
                    messages=[{"role": "system", "content": sys_prompt},
                              {"role": "user", "content": txt[:3000]}])
                out = r.choices[0].message.content.strip()
                if out.upper().startswith("NONE"):
                    return i, []
                lines = [l.strip("-•. ").strip() for l in out.splitlines()]
                return i, [l for l in lines if len(l) > 10][:2]
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    return i, []
                time.sleep(2 * (attempt + 1))

    cues: dict[int, list[str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, cs in pool.map(one, target):
            if cs:
                cues[i] = cs
    cache.write_text(json.dumps(cues, ensure_ascii=False))
    return cues


def hyde(oai, question: str) -> str:
    for attempt in range(4):
        try:
            r = oai.chat.completions.create(
                model=CUE_MODEL, temperature=0.3, max_tokens=120,
                messages=[{"role": "user", "content":
                           f"Write a plausible short answer passage (2-3 sentences, invented "
                           f"specifics are fine) for: {question}"}])
            return r.choices[0].message.content.strip()
        except Exception:  # noqa: BLE001
            if attempt == 3:
                return question
            time.sleep(2 * (attempt + 1))


def delivered(scores, owners, k):
    seen, out = set(), []
    for i in np.argsort(-scores):
        t = owners[i]
        if t not in seen:
            seen.add(t)
            out.append(t)
            if len(out) == k:
                break
    return set(out)


def run_instance(inst, model, oai, data, rng):
    turns, answers = [], []
    for sess in inst["haystack_sessions"]:
        for t in sess:
            if "role" in t and "content" in t:
                turns.append(f"{t['role']}: {t['content']}")
                answers.append(bool(t.get("has_answer")))
    ans_idx = {i for i, a in enumerate(answers) if a}
    if not ans_idx:
        return None
    cues = gen_turn_cues(oai, inst, data, rng)
    t_emb = np.array(list(model.embed(turns)))
    t_emb /= np.linalg.norm(t_emb, axis=1, keepdims=True)
    cue_texts, cue_owner = [], []
    for i, cs in cues.items():
        for c in cs:
            cue_texts.append(c)
            cue_owner.append(i)
    c_emb = np.array(list(model.embed(cue_texts))) if cue_texts else np.zeros((0, t_emb.shape[1]))
    if len(c_emb):
        c_emb /= np.linalg.norm(c_emb, axis=1, keepdims=True)
    q = np.array(list(model.embed([inst["question"]])))[0]
    q /= np.linalg.norm(q)
    h = np.array(list(model.embed([hyde(oai, inst["question"])])))[0]
    h /= np.linalg.norm(h)
    qh = (q + h) / np.linalg.norm(q + h)

    wrong = cue_owner[:]
    rng.shuffle(wrong)

    def arm(query_vec, use_cues, owner_map):
        scores = np.concatenate([t_emb @ query_vec, (c_emb @ query_vec) if use_cues and len(c_emb) else []]) \
            if use_cues else t_emb @ query_vec
        owners = list(range(len(turns))) + (owner_map if use_cues else [])
        out = {}
        for k in (4, 8, 16, 42):
            d = delivered(scores, owners, k)
            out[f"k{k}"] = {"hit": bool(d & ans_idx), "recall": len(d & ans_idx) / len(ans_idx)}
        return out

    return {
        "question_id": inst["question_id"], "type": inst["question_type"],
        "n_ans_turns": len(ans_idx),
        "baseline": arm(q, False, None),
        "placebo": arm(q, True, wrong),
        "cue_prior": arm(q, True, cue_owner),
        "read_expand": arm(qh, False, None),
        "combo": arm(qh, True, cue_owner),
    }


def sign_test(b_hits, t_hits):
    wins = sum(1 for b, t in zip(b_hits, t_hits) if t and not b)
    losses = sum(1 for b, t in zip(b_hits, t_hits) if b and not t)
    n = wins + losses
    if n == 0:
        return wins, losses, 1.0
    p = sum(comb(n, k) for k in range(0, min(wins, losses) + 1)) / 2 ** n * 2
    return wins, losses, min(p, 1.0)


def main() -> int:
    from fastembed import TextEmbedding
    data = json.loads(DATASETS["s"].read_text())
    insts = [d for d in stratified_sample(data, 42, random.Random(42))
             if "_abs" not in d["question_id"]]
    oai = OpenAI()
    model = TextEmbedding("BAAI/bge-small-en-v1.5")
    rng = random.Random(7)
    rows = []
    for i, inst in enumerate(insts, 1):
        r = run_instance(inst, model, oai, data, rng)
        if r:
            rows.append(r)
            print(f"[{i}/{len(insts)}] k8: b={r['baseline']['k8']['hit']} c={r['cue_prior']['k8']['hit']} {r['type']}", flush=True)

    arms = ["baseline", "placebo", "cue_prior", "read_expand", "combo"]
    summary = {"n": len(rows)}
    for k in (4, 8, 16, 42):
        kk = f"k{k}"
        summary[kk] = {}
        for a in arms:
            summary[kk][a] = {"hit": round(float(np.mean([r[a][kk]["hit"] for r in rows])), 4),
                              "recall": round(float(np.mean([r[a][kk]["recall"] for r in rows])), 4)}
        b_hit = [r["baseline"][kk]["hit"] for r in rows]
        for a in arms[1:]:
            w, l, p = sign_test(b_hit, [r[a][kk]["hit"] for r in rows])
            summary[kk][a]["vs_baseline"] = f"+{w}/-{l} p={p:.3f}"
        eb = 1 - summary[kk]["baseline"]["hit"]
        ec = 1 - summary[kk]["cue_prior"]["hit"]
        summary[kk]["cue_error_reduction"] = round((eb - ec) / eb, 3) if eb > 0 else None
    (HERE / "stage0v3.results.json").write_text(json.dumps(rows, indent=1))
    (HERE / "stage0v3.summary.json").write_text(json.dumps(summary, indent=1))
    print("\n" + json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
