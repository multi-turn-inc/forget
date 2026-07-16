"""Standalone local-observation generator — runs ON the GPU box.

Generates Mastra-style dated observations for every LongMemEval instance
using a local ollama model, writing one JSON per instance in the same
format as the laptop-side cache (observations/<model-slug>--<qid>.json).
Restartable: existing files are skipped. No external API — the whole
point is that memory construction never leaves the box.

    nohup python3 gen_local_obs.py --data longmemeval_s_cleaned.json \
        --model qwen2.5:14b-instruct-q4_K_M --workers 4 > gen.log 2>&1 &
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OBSERVER_SYS = """You are a memory observer. You read one session of a user's conversation with an assistant and record compressed observations for long-term memory.

Rules:
- Output a bullet list. Each bullet starts with the session date in brackets.
- Capture: stable user facts, preferences, life events, plans, quantities, named entities, and anything the user did or decided. Also capture assistant recommendations the user acted on.
- When the session mentions when something happened relative to the session date, record the RESOLVED absolute date in parentheses.
- Be specific: keep numbers, names, dates exactly. One fact per bullet.
- Skip pleasantries, filler, and generic assistant explanations that carry no user-specific information.
- 3-15 bullets per session depending on information density."""


def chat(base: str, model: str, system: str, user: str, retries: int = 4) -> str:
    payload = json.dumps({
        "model": model, "stream": False,
        "options": {"temperature": 0, "num_predict": 700},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{base}/api/chat", data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read())["message"]["content"].strip()
        except Exception:  # noqa: BLE001
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def observe_instance(inst: dict, out_dir: Path, base: str, model: str, slug: str) -> str:
    out = out_dir / f"{slug}--{inst['question_id']}.json"
    if out.exists():
        return "skip"
    dates = inst.get("haystack_dates") or []
    entries = []
    for i, session in enumerate(inst["haystack_sessions"]):
        date = dates[i] if i < len(dates) else ""
        convo = "\n".join(f"{t['role']}: {t['content']}" for t in session
                          if "role" in t and "content" in t)
        obs = chat(base, model, OBSERVER_SYS,
                   f"Session date: {date}\n\nSession:\n{convo}\n\nObservations:")
        entries.append({"date": date, "observations": obs})
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1))
    tmp.rename(out)
    return "done"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--model", default="qwen2.5:14b-instruct-q4_K_M")
    ap.add_argument("--base", default="http://localhost:11434")
    ap.add_argument("--out", default="observations")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    # keep the raw model name — the laptop-side cache (observer.py
    # get_observations) looks files up by unmodified model name
    slug = args.model.replace("/", "-")
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)
    data = json.loads(Path(args.data).read_text())
    started = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(observe_instance, inst, out_dir, args.base, args.model, slug):
                inst["question_id"] for inst in data}
        done = 0
        for fut, qid in futs.items():
            try:
                status = fut.result()
                done += 1
                el = (time.time() - started) / 60
                print(f"[{done}/{len(data)}] {status} {qid} ({el:.0f}m)", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[{qid}] ERROR {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
