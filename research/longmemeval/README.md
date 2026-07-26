# LongMemEval harness — reproduction guide

Every accuracy number forget publishes maps to a run file in [`runs/`](runs/),
with per-question outputs and the exact configuration. This README is the map.
If you re-run and get different numbers, please open an issue — that is the point
of shipping this directory.

## Published numbers → runs

| public claim | run | config |
|---|---|---|
| **81.8%** best config | [`runs/full-v3-500`](runs/full-v3-500.summary.json) | dual mode, GPT-4o observer, GPT-4o reader/judge, top-k 84, obs-k 60, reader v3, n=500 |
| **76.2%** fully-local pipeline | [`runs/o2-qwen-full500`](runs/o2-qwen-full500.summary.json) | dual mode, Qwen2.5-14B-q4 observer (ollama), GPT-4o reader/judge, top-k 84, reader v1, n=500 |
| 92.3% knowledge-update | same as 81.8% run | per-type breakdown in the summary |
| 43.3% single-session-preference (our weakest) | same as 81.8% run | disclosed, not hidden |

Reference points we cite come from the [LongMemEval paper](https://arxiv.org/abs/2410.10813)
(ICLR 2025): GPT-4o full-context baseline **60.6%**, GPT-4o oracle ceiling **87.0%**
(92.4% with Chain-of-Note). We do not put competitor numbers in our tables: the numbers
in circulation were measured by different parties with different readers, and this
category has already had one benchmark war over exactly that.

## Multi-run variance (in progress, 2026-07-27)

Single-run point estimates are the norm in this category and they shouldn't be.
We are re-running both published configs 3× each; results land in
`runs/repro-best-r{1,2,3}` and `runs/repro-local-r{1,2,3}`, plus one probe
(`runs/local-v3-probe`) testing the v3 reader on the local pipeline.
Completed so far: repro-best-r1 **81.8%** (exact replication), repro-local-r1 **76.8%**.
Mean ± σ will be published here when all runs complete.

## Reproduce it yourself

Requirements: Python 3.12+, an OpenAI API key (reader/judge), a running forget server,
and the two dataset files in `research/longmemeval-data/` (from the
[LongMemEval repo](https://github.com/xiaowu0162/LongMemEval); `_s_cleaned` is the
S variant with normalized dates).

```bash
# 1. dedicated bench server (never your dogfood instance)
MEM1_DB_PATH=/tmp/bench.sqlite3 forget-server run --port 8002

# 2. best config (GPT-4o observer, cached in observations/)
python research/longmemeval/observer.py --dataset s --n 500 \
  --mode dual --observer-model gpt-4o --reader-model gpt-4o \
  --top-k 84 --obs-k 60 --reader-v2 3 --url http://localhost:8002 --tag my-repro

# 3. fully-local pipeline (Qwen observer, cached; regenerate with gen_local_obs.py)
python research/longmemeval/observer.py --dataset s --n 500 \
  --mode dual --observer-model "qwen2.5:14b-instruct-q4_K_M" --reader-model gpt-4o \
  --top-k 84 --url http://localhost:8002 --tag my-repro-local
```

A full 500-question run costs roughly $15–40 in API fees and 2–4 hours.
Observer outputs are cached in `observations/` (one JSON per question per model),
so re-runs only pay for reader + judge.

## What the pieces are

- [`harness.py`](harness.py) — Tier-0 pipeline: ingest haystack → retrieve → reader → judge.
  Judge prompts are the benchmark's own per-type templates, verbatim in `JUDGE_TEMPLATES`.
- [`observer.py`](observer.py) — write-time memory construction (the "observer"),
  dual-layer retrieval, reader prompt versions (v1 strict-abstain / v3 balanced+guarded).
- [`gen_local_obs.py`](gen_local_obs.py) — generates observer outputs with a local
  ollama model; no API calls at memory-construction time.
- [`observations/`](observations/) — cached observer outputs: 500 × gpt-4o, 500 × qwen2.5-14b.

## Honesty notes

- The 81.8% run's memory construction uses a GPT-4o observer — it is **not** the local
  configuration. The local pipeline number is 76.2%. We have published both since
  2026-07-26 and the distinction is load-bearing.
- Reader prompt was tuned on a 42-question seed-42 dev sample; published runs draw from
  the full set. Tuning history (including a v2 regression caught by a $3 pre-flight)
  is in the git log.
- Judge is GPT-4o with the benchmark's own templates. LLM judges are known to be
  lenient; we have not yet run an adversarial judge validation (planned).
