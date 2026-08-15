#!/usr/bin/env python3
"""B층 v0 실험 — 상태 주입이 인격의 예측력(순열 널 z)을 만드는가 (P39).

3조건 × 같은 턴 × 같은 예측기(persona_v0) × 같은 자(순열 널 z).
design-v0.md의 규격을 그대로 집행한다. 산출물 무덮어쓰기.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

TRANSCRIPT_DIR = Path.home() / ".claude/projects"
OUT = Path.home() / ".forget/twin/bstate_v0.results.json"
RAW = Path.home() / ".forget/twin/bstate_v0.rows.jsonl"

PERSONA_URL = "http://127.0.0.1:8024/v1/chat/completions"
PERSONA_MODEL = "persona_v0"
SUMM_URL = "http://127.0.0.1:11435/api/chat"   # Spark 27B — 요약기
SUMM_MODEL = "qwen3.6:27b"
EMB_URL = "http://127.0.0.1:11434/api/embed"
EMB_MODEL = "nomic-embed-text"
SYS = "너는 정훈과 함께 forget을 만드는 에이전트다. 아래는 정훈의 메시지다. 너로서 응답하라."

N_TURNS = int(os.environ.get("BSTATE_N", "50"))
PER_SESSION = 3
MIN_PRIOR = 6          # 세션 내 선행 턴 수 — "상태"가 실재해야 함
K = 3                  # 예측 표집
STATE_BUDGET = 600     # B상태 문자 예산
RAW_BUDGET = 2200      # 조건 B 원문 예산 (state 600 + asst 1600 근사 일치)
SHUFFLES = 200

NOISE = re.compile(
    r"\[forget 회상|\[forget 캡슐|<command-|<local-command|<bash-input"
    r"|<system-reminder|Caveat:|\[SYSTEM NOTIFICATION|<task-notification"
    r"|SUGGESTION MODE|Recap in under", re.I)


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _post(url: str, payload: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def mine_turns() -> list[dict]:
    """세션 내 선행 >= MIN_PRIOR 턴인 사용자 발화 + 그 이전 대화 전체."""
    picked, seen = [], set()
    files = sorted(TRANSCRIPT_DIR.glob("*/*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        turns = []          # (role, text)
        session_hits = 0
        try:
            for line in f.open():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ, msg = row.get("type"), (row.get("message") or {})
                if typ not in ("user", "assistant"):
                    continue
                t = _text(msg.get("content")).strip()
                if not t:
                    continue
                if typ == "user":
                    head = re.split(r"\n\[forget|\n<system-reminder|\nSessionStart:|<local-command", t)[0].strip()
                    if (len(head) >= 10 and not head.startswith("[{")
                            and not NOISE.search(head[:200])
                            and len(turns) >= MIN_PRIOR
                            and session_hits < PER_SESSION
                            and len(picked) < N_TURNS):
                        key = hashlib.md5(head[:80].encode()).hexdigest()
                        if key not in seen:
                            seen.add(key)
                            session_hits += 1
                            picked.append({"prior": list(turns), "actual": head[:800],
                                           "ts": str(row.get("timestamp") or ""), "src": f.name})
                    turns.append(("user", head or t[:400]))
                else:
                    turns.append(("assistant", t))
        except OSError:
            continue
        if len(picked) >= N_TURNS:
            break
    return picked


def last_assistant(prior: list) -> str:
    for role, t in reversed(prior):
        if role == "assistant":
            return t
    return ""


def raw_tail(prior: list, budget: int) -> str:
    parts, total = [], 0
    for role, t in reversed(prior):
        seg = f"[{'정훈' if role == 'user' else '에이전트'}] {t}"
        take = seg[:max(0, budget - total)]
        if not take:
            break
        parts.append(take)
        total += len(take)
    return "\n".join(reversed(parts))


def summarize_state(prior: list) -> str:
    """Spark가 세션-지금까지를 4청크 상태로 압축. 실발화는 입력에 없음."""
    dialogue = raw_tail(prior, 6000)
    body = _post(SUMM_URL, {
        "model": SUMM_MODEL, "stream": False, "think": False, "keep_alive": "3h",
        "messages": [{"role": "user", "content":
            "다음은 개발자(정훈)와 에이전트의 대화다. 이 시점의 작업 상태를 정확히 4줄로 압축하라.\n"
            "형식(각 줄 120자 이내):\n목표: …\n직전 사건: …\n미결: …\n다음 손: …\n\n" + dialogue}],
        "options": {"temperature": 0.0, "num_predict": 300},
    })
    return str((body.get("message") or {}).get("content") or "").strip()[:STATE_BUDGET]


def predict(ctx: str) -> list[str]:
    preds = []
    for _ in range(K):
        body = _post(PERSONA_URL, {
            "model": PERSONA_MODEL, "temperature": 0.7, "max_tokens": 150,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "system", "content": SYS},
                         {"role": "user", "content": ctx[-4000:]}],
        })
        t = str((body.get("choices") or [{}])[0].get("message", {}).get("content") or "").strip()
        if t:
            preds.append(t)
    return preds


def embed(texts: list[str]) -> list[list[float]]:
    out = []
    for i in range(0, len(texts), 64):
        out += _post(EMB_URL, {"model": EMB_MODEL, "input": texts[i:i + 64]}, timeout=180)["embeddings"]
    return out


def cos(a, b) -> float:
    d = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return d / max(1e-9, na * nb)


def perm_z(pred_lists: list[list[str]], acts: list[str], rng: random.Random) -> dict:
    flat = [p for ps in pred_lists for p in ps]
    E_p = embed(flat)
    E_a = embed(acts)
    grouped, i = [], 0
    for ps in pred_lists:
        grouped.append(E_p[i:i + len(ps)])
        i += len(ps)
    matched = [sum(cos(e, E_a[t]) for e in g) / len(g) for t, g in enumerate(grouped)]
    idx = list(range(len(acts)))
    nulls = []
    for _ in range(SHUFFLES):
        sh = idx[:]
        rng.shuffle(sh)
        pairs = [(t, sh[t]) for t in idx if sh[t] != t]
        nulls.append(sum(sum(cos(e, E_a[j]) for e in grouped[t]) / len(grouped[t])
                         for t, j in pairs) / max(1, len(pairs)))
    m = sum(matched) / len(matched)
    n = sum(nulls) / len(nulls)
    sd = (sum((x - n) ** 2 for x in nulls) / len(nulls)) ** 0.5
    return {"matched": round(m, 4), "null": round(n, 4), "sd": round(sd, 4),
            "z": round((m - n) / max(1e-9, sd), 2)}


def main() -> None:
    if OUT.exists() and os.environ.get("BSTATE_FORCE") != "1":
        sys.exit(f"산출물 존재 — 덮지 않는다: {OUT}")
    rng = random.Random(42)
    turns = mine_turns()
    print(f"실험 턴 {len(turns)}개 (선행 ≥{MIN_PRIOR}턴, 세션당 ≤{PER_SESSION})", file=sys.stderr)
    if len(turns) < 40:
        sys.exit("표본 미달 (<40)")

    conds = {"A_baseline": [], "B_raw": [], "C_state": []}
    acts = []
    with RAW.open("w") as fh:
        for i, turn in enumerate(turns):
            asst = last_assistant(turn["prior"])
            try:
                state = summarize_state(turn["prior"])
            except Exception as exc:
                print(f"[skip] 요약 실패: {exc}", file=sys.stderr)
                continue
            ctxs = {
                "A_baseline": asst,
                "B_raw": raw_tail(turn["prior"], RAW_BUDGET),
                "C_state": f"[현재 작업 상태]\n{state}\n\n[에이전트의 마지막 보고]\n{asst[-1600:]}",
            }
            row = {"i": i, "actual": turn["actual"], "ts": turn["ts"], "state": state}
            try:
                for c, ctx in ctxs.items():
                    preds = predict(ctx)
                    if not preds:
                        raise RuntimeError("빈 예측")
                    conds[c].append(preds)
                    row[c] = preds[0][:200]
            except Exception as exc:
                print(f"[skip] 예측 실패: {exc}", file=sys.stderr)
                for c in conds:
                    if len(conds[c]) > len(acts):
                        conds[c].pop()
                continue
            acts.append(turn["actual"][:800])
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            if len(acts) % 10 == 0:
                print(f"  {len(acts)}턴 완료", file=sys.stderr)

    results = {"n": len(acts), "k": K,
               "prereg": "(a) C z>=2 & A z<2 → B층 지지 / (b) B도 z>=2 & C≤B → 정보량 우세 / (c) 셋 다 <2 → 반증(R̂ 재지목)",
               "conditions": {}}
    for c, preds in conds.items():
        results["conditions"][c] = perm_z(preds, acts, random.Random(7))
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
