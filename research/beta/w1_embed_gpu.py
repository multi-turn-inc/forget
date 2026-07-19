"""β W1 — GPU embedding cache builder (runs ON the 4090).

Same outputs as w1_embed_cache.py (cache/{qid}.npz + pools) but via
sentence-transformers BAAI/bge-small-en-v1.5 on CUDA. Skips existing files.
Inputs on box: longmemeval_s_cleaned.json, observations-gpt4o/, pools.json.
"""
import json, sys, time
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cuda")

def embed(texts):
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    e = model.encode(texts, batch_size=256, convert_to_numpy=True,
                     normalize_embeddings=True, show_progress_bar=False)
    return e.astype(np.float32)

pools = json.loads((HERE / "pools.json").read_text())
for name, texts in pools.items():
    out = CACHE / f"pool_{name}.npz"
    if not out.exists():
        np.savez_compressed(out, emb=embed(texts))
        print(f"pool {name}: {len(texts)}", flush=True)

data = json.loads((HERE / "longmemeval_s_cleaned.json").read_text())
started = time.time()
for idx, inst in enumerate(data, 1):
    out = CACHE / f"{inst['question_id']}.npz"
    if out.exists():
        continue
    turns, ans, sess = [], [], []
    for si, session in enumerate(inst["haystack_sessions"]):
        for t in session:
            if "role" in t and "content" in t:
                turns.append(f"{t['role']}: {t['content']}")
                ans.append(bool(t.get("has_answer")))
                sess.append(si)
    obs_texts, obs_sess = [], []
    of = HERE / "observations-gpt4o" / f"gpt-4o--{inst['question_id']}.json"
    if of.exists():
        for si, e in enumerate(json.loads(of.read_text())):
            for line in e["observations"].splitlines():
                line = line.strip().lstrip("-• ").strip()
                if len(line) > 8:
                    obs_texts.append(line)
                    obs_sess.append(si)
    ans_sess = {inst["haystack_session_ids"].index(s)
                for s in inst["answer_session_ids"] if s in inst["haystack_session_ids"]}
    np.savez_compressed(out, turn_emb=embed(turns), turn_ans=np.array(ans),
                        turn_sess=np.array(sess), obs_emb=embed(obs_texts),
                        obs_sess=np.array(obs_sess), q_emb=embed([inst["question"]])[0],
                        ans_sess=np.array(sorted(ans_sess)))
    if idx % 50 == 0:
        print(f"[{idx}/500] {(time.time()-started)/60:.1f}m", flush=True)
print("cache complete", flush=True)
