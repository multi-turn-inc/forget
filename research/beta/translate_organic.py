"""β W1 — translate the organic agent-exhaust corpus to English.

The substrate (LongMemEval) is English; our organic corpus is Korean. Left
untranslated, the embedder separates junk by LANGUAGE, not content — a
confound that would make C-organic look artificially harmless. We translate
with gpt-4o-mini and disclose the translation step in the paper (threat #6).

    python research/beta/translate_organic.py
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI

HERE = Path(__file__).resolve().parent
SRC = HERE / "corpus" / "dump-raw.json"
OUT = HERE / "corpus" / "organic-en.jsonl"


def main() -> int:
    items = json.loads(SRC.read_text())
    if isinstance(items, dict):
        items = items.get("results") or []
    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                done.add(json.loads(line)["id"])
    todo = [m for m in items if m["id"] not in done]
    print(f"{len(done)} cached, {len(todo)} to translate", flush=True)
    oai = OpenAI()

    def one(m):
        text = m["memory"][:2000]
        for attempt in range(4):
            try:
                r = oai.chat.completions.create(
                    model="gpt-4o-mini", temperature=0, max_tokens=600,
                    messages=[{"role": "system", "content":
                               "Translate to natural English. Keep the register and structure "
                               "(a fragment stays a fragment, a log line stays a log line). "
                               "Replace personal names with generic ones. Output only the translation."},
                              {"role": "user", "content": text}])
                return {"id": m["id"], "en": r.choices[0].message.content.strip(),
                        "created_at": m.get("created_at", "")}
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    return None
                time.sleep(2 * (attempt + 1))

    with OUT.open("a") as f:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i, res in enumerate(pool.map(one, todo), 1):
                if res:
                    f.write(json.dumps(res, ensure_ascii=False) + "\n")
                if i % 200 == 0:
                    f.flush()
                    print(f"[{i}/{len(todo)}]", flush=True)
    print("translation complete", flush=True)
    return 0


if __name__ == "__main__":
    return_code = main()
    raise SystemExit(return_code)
