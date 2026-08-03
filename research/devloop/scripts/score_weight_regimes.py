"""P11 (d): is cycle 43's 8% an underestimate? Re-measure in the regimes the
product actually issues queries in. (read-only, $0, cycle 44)

Cycle 43 measured the legacy (0.72 rule / 0.28 vector) vs semantic (0.45/0.55)
split with **leave-one-out self-text** probes: a memory's own text as the query.
Top-1 changed in 8% (2/25). That regime has abnormally high query/memory lexical
overlap, which is exactly the condition the rule channel is best at — so it
should understate how much the weighting matters. Registered before measuring
(predictions.md P11 (d)): the real regimes come out **above 8%**; <= 8% falsifies.

Two real regimes, corpus selection fixed in code (cycle 27 friction):

  S = the startup capsule query. `forget_sessionstart.py:103` sends the fixed
      template `session {source} in {cwd} - active tasks, open loops, recent
      decisions`. Path verified cycle 44 by reading the code, not by assuming:
      prepare_context_autopilot (store.py:9979) -> assemble_context (11418) ->
      search_memories (11497, query passes through unmodified) -> the
      misweighted _search_score_weights() (4599). The capsule gets it too.
      n is small on purpose: this is not a sample, it is *the* query.

  T = real turn queries. `forget_turnrecall.py:121` sends `prompt[:300]`. The
      corpus is real user prompts pulled from Claude Code transcripts -- the
      same primary-evidence channel cycle 42 established
      (f2_ledger_from_transcripts.py). The loop does not get to pick them.

Metric, pool, TOP_K and the two weight pairs are held identical to cycle 43 so
the numbers are directly comparable. Game-resistant (cycle 22's method): no hand
relevance labels -- only top-1 change and rank correlation between weightings.

Fidelity: query vectors come from the product's own fastembed path
(`_embed_with_fastembed_provider`, role="query"), and the script proves it is
the same embedder that wrote the stored vectors by re-embedding stored texts and
checking cosine against what is in the DB (printed as a receipt). No product DB
connection is opened -- sqlite mode=ro only, nothing is written anywhere.

    .venv/bin/python research/devloop/scripts/score_weight_regimes.py [n_probes]
"""

from __future__ import annotations

import glob
import json
import os
import random
import re
import sqlite3
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import numpy as np  # noqa: E402

from forget.memory_engine import score_memory  # noqa: E402
from forget.providers import _embed_with_fastembed_provider  # noqa: E402
from forget.utils import decode_embedding  # noqa: E402

DB = os.environ.get("FORGET_DB", os.path.expanduser("~/.forget/forget.sqlite3"))
LEGACY = (0.72, 0.28)      # what the dogfood server actually applies today
SEMANTIC = (0.45, 0.55)    # what P11 treatment 2 would apply
QUERY_CHARS = 300          # forget_turnrecall.py:121
TOP_K = 10                 # cycle 43 setting, held fixed
SEED = 44
THRESHOLD = 0.1            # assemble_context default (store.py:11429)
HOOK_MULT = 0.5            # store.py:4633, session-capture demotion
SUPERSEDED_MULT = 0.45     # _superseded_score_multiplier() default

TRANSCRIPT_DIRS = [
    os.path.expanduser("~/.claude/projects/-Users-junghunkim-orca-workspaces-forget----------------"),
]
# forget_sessionstart.py:103, verbatim.
CAPSULE_TEMPLATE = "session {source} in {cwd} — active tasks, open loops, recent decisions"
CAPSULE_SOURCES = ["startup", "resume", "clear", "compact"]
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT = "forget"  # project_key_for_path(REPO); both hooks send layered_filter(this)
# SessionEnd auto-capture rows. Not a judgement of value -- just a countable
# class, so "what fills the capsule's window" is a number and not an impression.
AUTOCAPTURE = "세션 캡처"

# Hook output and harness furniture are not user prompts. A transcript line
# carrying any of these is either an injection or a tool echo, not a query.
NOT_A_PROMPT = ("[forget 회상", "[forget 충돌지대", "[forget 캡슐", "<system-reminder>",
                "<command-name>", "<local-command", "Caveat:", "<user-prompt-submit-hook>")


def load_pool() -> tuple[list[dict], int]:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.text_factory = bytes
    cur = con.cursor()
    cur.execute("select id, memory, categories, updated_at, embedding, metadata from memories where deleted=0")
    rows = []
    for mem_id, text, cats, updated, raw, meta in cur:
        dec = lambda b: b.decode(errors="replace") if isinstance(b, bytes) else (b or "")  # noqa: E731
        value = raw
        if isinstance(raw, bytes) and raw[:4] != b"MEB1":
            try:
                value = raw.decode()
            except UnicodeDecodeError:
                value = raw
        try:
            categories = json.loads(dec(cats)) if cats else []
        except ValueError:
            categories = []
        try:
            metadata = json.loads(dec(meta)) if meta else {}
        except ValueError:
            metadata = {}
        rows.append({
            "id": dec(mem_id),
            "memory": dec(text),
            "categories": categories if isinstance(categories, list) else [],
            "updated_at": dec(updated),
            "_meta": metadata if isinstance(metadata, dict) else {},
            "_vec": decode_embedding(value),
        })
    con.close()
    # identical filter to cycle 43's score_weight_replay.py ...
    pool = [r for r in rows if len(r["_vec"]) == 384 and len(r["memory"]) >= 80]
    # ... plus the layered recall filter both hooks actually send
    # (forget_project.py:212): this project OR untagged OR the global layer.
    before = len(pool)
    pool = [r for r in pool if r["_meta"].get("project") in (PROJECT, None)
            or r["_meta"].get("scope_layer") == "global"]
    print(f"filter : layered_filter({PROJECT!r}) drops {before - len(pool)} of {before} pool rows")
    return pool, len(rows)


def walk_user_text(rec: dict):
    """Yield the text of a genuine user prompt record, or nothing."""
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("toolUseResult"):
        return
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                yield str(block.get("text") or "")


def load_prompts() -> list[str]:
    seen: dict[str, str] = {}
    for d in TRANSCRIPT_DIRS:
        for path in sorted(glob.glob(os.path.join(d, "*.jsonl"))):
            try:
                with open(path, errors="replace") as fh:
                    for line in fh:
                        if '"type":"user"' not in line and '"type": "user"' not in line:
                            continue
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        for text in walk_user_text(rec):
                            t = text.strip()
                            if len(t) < 40 or any(marker in t for marker in NOT_A_PROMPT):
                                continue
                            q = t[:QUERY_CHARS]
                            seen.setdefault(re.sub(r"\s+", " ", q).strip(), q)
            except OSError:
                continue
    return list(seen.values())


def kendall_tau(a: list[str], b: list[str]) -> float:
    """Tau over the union of two ranked lists; unranked items sit just past the end."""
    union = list(dict.fromkeys(a + b))
    ra = {m: i for i, m in enumerate(a)}
    rb = {m: i for i, m in enumerate(b)}
    miss = max(len(a), len(b)) + 1
    con = dis = 0
    for i in range(len(union)):
        for j in range(i + 1, len(union)):
            x, y = union[i], union[j]
            da = ra.get(x, miss) - ra.get(y, miss)
            db = rb.get(x, miss) - rb.get(y, miss)
            if da * db > 0:
                con += 1
            elif da * db < 0:
                dis += 1
    total = con + dis
    return (con - dis) / total if total else 1.0


def rank_pair(query: str, qvec: list[float], pool: list[dict], matrix: np.ndarray,
              norms: np.ndarray, post: np.ndarray,
              exclude: int | None = None) -> tuple[list[str], list[str], np.ndarray, np.ndarray]:
    qv = np.asarray(qvec, dtype=np.float64)
    qn = float(np.linalg.norm(qv)) or 1.0
    cos = (matrix @ qv) / (norms * qn)
    # production cosine_similarity(): round((cos+1)/2, 4) clipped to [0,1]
    vector = np.clip(np.round((cos + 1.0) / 2.0, 4), 0.0, 1.0)
    rule = np.asarray([score_memory(query, r) for r in pool], dtype=np.float64)
    # `post` is the multiplicative chain search_memories applies AFTER the
    # weighted sum (store.py:4619-4634): superseded x0.45, session-capture x0.5.
    # It is not order-preserving across classes, so it belongs inside the
    # comparison -- cycle 43's replay left it out entirely.
    legacy = np.round(LEGACY[0] * rule + LEGACY[1] * vector, 4) * post
    semantic = np.round(SEMANTIC[0] * rule + SEMANTIC[1] * vector, 4) * post
    legacy[legacy < THRESHOLD] = -1.0
    semantic[semantic < THRESHOLD] = -1.0
    if exclude is not None:  # leave-one-out
        legacy[exclude] = -1.0
        semantic[exclude] = -1.0
    top_a = [pool[i]["id"] for i in np.argsort(-legacy)[:TOP_K]]
    top_b = [pool[i]["id"] for i in np.argsort(-semantic)[:TOP_K]]
    return top_a, top_b, legacy, semantic


def measure(name: str, queries: list[str], pool: list[dict], matrix: np.ndarray,
            norms: np.ndarray, post: np.ndarray, byid: dict) -> dict:
    top1 = 0
    taus: list[float] = []
    moves: list[int] = []
    auto: list[float] = []
    detail = []
    for q in queries:
        qvec = _embed_with_fastembed_provider(q, {}, role="query")
        top_a, top_b, legacy, semantic = rank_pair(q, qvec, pool, matrix, norms, post)
        changed = top_a[0] != top_b[0]
        top1 += changed
        taus.append(kendall_tau(top_a, top_b))
        rb = {m: i for i, m in enumerate(top_b)}
        for i, m in enumerate(top_a):
            if m in rb:
                moves.append(abs(i - rb[m]))
        auto.append(sum(1 for m in top_a if AUTOCAPTURE in byid[m]["memory"][:40]) / float(TOP_K))
        detail.append({"query": q, "changed": changed, "tau": taus[-1],
                       "legacy_top": top_a, "semantic_top": top_b})
    n = len(queries)
    print(f"\n== {name}: legacy {LEGACY} vs semantic {SEMANTIC}, top-{TOP_K}, n={n} ==")
    print(f"  top-1 changed        : {top1}/{n} ({100.0 * top1 / n:.0f}%)")
    print(f"  mean Kendall tau     : {statistics.mean(taus):.4f}  (1.0 = identical order)")
    print(f"  tau < 1.0 (reordered): {sum(1 for t in taus if t < 1.0)}/{n}")
    if moves:
        print(f"  mean |rank shift|    : {statistics.mean(moves):.2f} positions")
    print(f"  자동캡처가 먹은 상위칸 : {100.0 * statistics.mean(auto):.0f}% of top-{TOP_K} (legacy 기준)")
    return {"name": name, "n": n, "top1": top1, "tau": statistics.mean(taus),
            "reordered": sum(1 for t in taus if t < 1.0),
            "autocapture_share": statistics.mean(auto), "detail": detail}


def main() -> None:
    n_probes = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    pool, live = load_pool()
    print(f"db     : {DB}")
    print(f"pool   : {len(pool)} rows (dim-384, text >= 80 chars) of {live} live")

    matrix = np.asarray([r["_vec"] for r in pool], dtype=np.float64)
    norms = np.linalg.norm(matrix, axis=1)
    norms[norms == 0.0] = 1.0
    byid = {r["id"]: r for r in pool}

    post = np.ones(len(pool), dtype=np.float64)
    for i, r in enumerate(pool):
        if r["_meta"].get("superseded_at"):
            post[i] *= SUPERSEDED_MULT
        if r["_meta"].get("hook"):
            post[i] *= HOOK_MULT
    n_hook = sum(1 for r in pool if r["_meta"].get("hook"))
    print(f"post   : metadata.hook x{HOOK_MULT} on {n_hook}/{len(pool)} rows "
          f"({100.0 * n_hook / len(pool):.0f}%), superseded x{SUPERSEDED_MULT} on "
          f"{sum(1 for r in pool if r['_meta'].get('superseded_at'))}, threshold {THRESHOLD}")

    # --- fidelity receipt: is our embedder the one that wrote these vectors? ---
    rng = random.Random(SEED)
    checks = rng.sample(range(len(pool)), 5)
    sims = []
    for i in checks:
        v = np.asarray(_embed_with_fastembed_provider(pool[i]["memory"], {}, role="passage"), dtype=np.float64)
        s = np.asarray(pool[i]["_vec"], dtype=np.float64)
        sims.append(float(v @ s / ((np.linalg.norm(v) or 1) * (np.linalg.norm(s) or 1))))
    print(f"embed  : re-embed vs stored cosine over 5 rows -> min {min(sims):.6f} "
          f"mean {statistics.mean(sims):.6f}  (1.0 = same embedder as the store)")
    qv = _embed_with_fastembed_provider("hello", {}, role="query")
    pv = _embed_with_fastembed_provider("hello", {}, role="passage")
    same = float(np.dot(qv, pv) / ((np.linalg.norm(qv) or 1) * (np.linalg.norm(pv) or 1)))
    print(f"         role query vs passage on same text -> cosine {same:.6f} "
          f"({'no prefix, roles equivalent' if same > 0.9999 else 'ROLE PREFIX ACTIVE'})")

    # --- regime L: cycle 43's own probes, re-run through the corrected chain.
    # Same seed (43), same n, same leave-one-out construction — so the ONLY
    # difference from cycle 43's published 8% is the post-weighting chain it
    # omitted. This separates "the regime was wrong" from "the method was wrong".
    l_rng = random.Random(43)
    l_idx = l_rng.sample(range(len(pool)), min(n_probes, len(pool)))
    l_top1 = 0
    l_taus = []
    for pi in l_idx:
        probe = pool[pi]
        top_a, top_b, _, _ = rank_pair(probe["memory"][:QUERY_CHARS], probe["_vec"],
                                       pool, matrix, norms, post, exclude=pi)
        l_top1 += top_a[0] != top_b[0]
        l_taus.append(kendall_tau(top_a, top_b))
    print(f"\n== L leave-one-out self-text (사이클 43 재현, 사후체인 교정), n={len(l_idx)} ==")
    print(f"  top-1 changed        : {l_top1}/{len(l_idx)} ({100.0 * l_top1 / len(l_idx):.0f}%)")
    print(f"  mean Kendall tau     : {statistics.mean(l_taus):.4f}")
    print(f"  (사이클 43 원 보고   : 2/25 = 8%, tau 0.8829 — 사후체인 미적용)")

    # --- regime S: the product's own fixed capsule query ---
    s_queries = [CAPSULE_TEMPLATE.format(source=src, cwd=REPO) for src in CAPSULE_SOURCES]
    s = measure("S startup capsule (the product's fixed template)", s_queries, pool, matrix, norms, post, byid)

    # --- regime T: real user prompts ---
    prompts = load_prompts()
    print(f"\nprompts: {len(prompts)} distinct real user prompts (>=40 chars, hook/tool lines excluded)")
    sample = random.Random(SEED).sample(prompts, min(n_probes, len(prompts)))
    t = measure(f"T real turn prompts (seed {SEED}, prompt[:{QUERY_CHARS}])", sample, pool, matrix, norms, post, byid)

    print("\n=== 사이클 43 대조 (동일 지표·풀·TOP_K, 레짐만 다름) ===")
    print(f"  L leave-one-out self-text : top-1  2/25 (8%)  tau 0.8829  재순위 16/25")
    print(f"  S startup capsule         : top-1 {s['top1']:>2}/{s['n']} "
          f"({100.0 * s['top1'] / s['n']:.0f}%)  tau {s['tau']:.4f}  재순위 {s['reordered']}/{s['n']}")
    print(f"  T real turn prompts       : top-1 {t['top1']:>2}/{t['n']} "
          f"({100.0 * t['top1'] / t['n']:.0f}%)  tau {t['tau']:.4f}  재순위 {t['reordered']}/{t['n']}")
    # (d) named BOTH S and T as "the regimes the product actually issues".
    # Reporting only the arm that agrees would be the exact move this loop keeps
    # catching itself at, so both arms are judged. Every verdict word below is
    # COMPUTED, never asserted -- an earlier revision of this very script printed
    # a fixed conclusion no matter what the numbers said (cycle 44 caught it).
    t_rate = 100.0 * t["top1"] / t["n"]
    s_rate = 100.0 * s["top1"] / s["n"]
    l_rate = 100.0 * l_top1 / len(l_idx)
    C43 = 8.0
    verdict = lambda r: "지지" if r > C43 else "반증"  # noqa: E731
    print(f"\n  P11 (d) 사전 등록 임계 {C43:.0f}% — 팔별 판정 (전부 계산값):")
    print(f"    T 실제 턴 질의  {t_rate:.0f}%  → {verdict(t_rate)}")
    print(f"    S startup 캡슐  {s_rate:.0f}%  → {verdict(s_rate)}"
          f"   (n={s['n']}, 사실상 단일 질의 — tau {s['tau']:.4f})")
    up = [n for n, r in (("T", t_rate), ("S", s_rate)) if r > C43]
    down = [n for n, r in (("T", t_rate), ("S", s_rate)) if r <= C43]
    print(f"    → {'분할 판정: ' + '/'.join(up) + ' 지지, ' + '/'.join(down) + ' 반증.' if up and down else ('두 팔 모두 지지.' if up else '두 팔 모두 반증.')}")

    # The confound (d) never anticipated: L is cycle 43's OWN regime, re-run
    # through the corrected chain. Whatever L moves is method, not regime --
    # so only the leftover T-minus-L gap can be credited to regime at all.
    print("\n  교란 분리 — L은 사이클 43과 '같은 레짐'이다:")
    print(f"    c43 원보고 {C43:.0f}%  →  L 사후체인 교정 {l_rate:.0f}%"
          f"   (레짐 고정, 방법만 교정)")
    if l_rate > C43:
        print(f"    → '8%는 과소추정'은 성립하나, 그 몫의 {l_rate - C43:.0f}%p는"
              f" 레짐이 아니라 **방법(사후체인 누락)**이다.")
        print(f"    → 레짐에 귀속 가능한 상한은 T-L = {t_rate - l_rate:+.0f}%p뿐이다."
              f" (d)의 결론은 살아남고, (d)가 댄 근거는 단독 설명이 아니다.")
    else:
        print("    → 방법 교정만으로는 임계를 넘지 못한다 — (d)의 레짐 근거가 온전히 남는다.")

    out = os.path.join("/tmp", "cycle44_regimes.json")
    with open(out, "w") as fh:
        json.dump({"S": s, "T": t}, fh, ensure_ascii=False, indent=1)
    print(f"  detail -> {out}")

    # --- receipt: does this replay reproduce what the LIVE capsule chose? ---
    # A replay that disagrees with the running server is measuring a fiction.
    # (Cycle 44 caught exactly that: without the post chain the replay said
    # 100% session-capture, the live capsule said 0%.)
    live_ids = []
    for state in sorted(glob.glob(os.path.expanduser("~/.forget/hooks/state/*.json")),
                        key=os.path.getmtime, reverse=True)[:1]:
        try:
            live_ids = json.load(open(state)).get("memory_ids") or []
        except (OSError, ValueError):
            pass
    if live_ids:
        replayed = s["detail"][0]["legacy_top"]
        hit = [m for m in replayed if m in live_ids]
        print(f"\n=== 라이브 대조 (가장 최근 캡슐 {len(live_ids)}건 vs 이 재생의 S top-{TOP_K}) ===")
        print(f"  겹침: {len(hit)}/{len(replayed)}  — 재생 1위가 라이브에 포함: "
              f"{'예' if replayed[0] in live_ids else '아니오'}")

    # what actually moves in the real capsule query, for the note
    print("\n=== S(startup) 최상위 변화 상세 ===")
    d = s["detail"][0]
    for label, ids in (("legacy 0.72/0.28", d["legacy_top"][:5]), ("semantic 0.45/0.55", d["semantic_top"][:5])):
        print(f"  [{label}]")
        for r, mid in enumerate(ids, 1):
            print(f"    {r}. {byid[mid]['memory'][:88].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
