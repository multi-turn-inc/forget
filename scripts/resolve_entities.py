"""엔티티 해소 (R2) — 임베딩은 후보 축소만, 판정은 LLM이. (본선 4-R, 2026-08-24)

Graphiti dedupe_nodes 원문의 규율 이식:
  · "같은 실세계 대상"일 때만 병합 — 관련 있지만 별개는 절대 병합 금지
  · 판정은 candidate_id, 확신 없으면 -1
  · 임베딩 문턱으로 자동 병합하지 않는다 (Java 언어 ≠ Java 섬)

절차: 정규화 완전일치 병합(공짜) → 빈도 내림차순 탐욕 — 각 이름을 기존 정본들과
mpnet 코사인으로 좁히고(상위 4, ≥0.72) LLM이 판정. 병합되면 별칭으로 등록.

사용: .venv/bin/python scripts/resolve_entities.py <triples.jsonl> <out_prefix>
      (LLM: localhost:18811 — 4090 터널)
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections import Counter, defaultdict

URL = "http://127.0.0.1:18811/v1/chat/completions"
TYPES = {0: "사람", 1: "조직", 2: "프로젝트", 3: "산출물", 4: "결정·규칙"}
SHORTLIST_MIN_COS = 0.72
SHORTLIST_K = 4

SCHEMA = {"type": "object",
          "properties": {"duplicate_candidate_id": {"type": "integer", "minimum": -1, "maximum": 9}},
          "required": ["duplicate_candidate_id"], "additionalProperties": False}

SYSTEM = """너는 엔티티 중복판정 전문가다. 절대 이름을 지어내지 말고, 서로 다른 대상을 중복으로 표시하지 마라.

중복 = 같은 실세계 대상을 가리키는 두 이름 (별칭·축약·표기 차이).
절대 병합 금지:
- 관련 있지만 별개인 것 (예: "forget 서버"와 "forget 저장소" — 같은 프로젝트의 다른 산출물)
- 이름이 비슷하지만 다른 인스턴스 (예: "커밋 ad968f8"과 "커밋 cc25839")
- 상위어-하위어 (예: "Quant"와 "Quant 페이퍼 기준선")
확신이 없으면 -1."""


def call_llm(user: str) -> int:
    body = {"model": "qwen", "temperature": 0.0, "max_tokens": 60,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": "d", "strict": True, "schema": SCHEMA}},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read())
    return int(json.loads(out["choices"][0]["message"]["content"])["duplicate_candidate_id"])


def norm(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def main() -> None:
    path, prefix = sys.argv[1], sys.argv[2]
    freq: Counter = Counter()
    types: dict[str, Counter] = defaultdict(Counter)
    for line in open(path):
        row = json.loads(line)
        for e in row.get("entities") or []:
            key = norm(e.get("name") or "")
            if len(key) < 2:
                continue
            freq[key] += 1
            types[key][int(e.get("type_id", 3))] += 1
    names = [n for n, _ in freq.most_common()]
    print(f"고유 이름(정규화 후) {len(names)}")

    from fastembed import TextEmbedding
    engine = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    vecs = {}
    ordered = list(names)
    embedded = list(engine.embed(ordered, batch_size=128))
    import math
    for name, v in zip(ordered, embedded):
        arr = [float(x) for x in v]
        nrm = math.sqrt(sum(x * x for x in arr)) or 1.0
        vecs[name] = [x / nrm for x in arr]

    canon: list[str] = []          # 정본 이름들 (빈도 내림차순 도착)
    alias: dict[str, str] = {}     # 이름 → 정본
    n_llm = n_merge = 0
    t0 = time.time()
    for i, name in enumerate(names):
        sims = []
        v = vecs[name]
        for c in canon:
            cos = sum(a * b for a, b in zip(v, vecs[c]))
            if cos >= SHORTLIST_MIN_COS:
                sims.append((cos, c))
        sims.sort(reverse=True)
        shortlist = sims[:SHORTLIST_K]
        verdict = -1
        if shortlist:
            t = TYPES.get(types[name].most_common(1)[0][0], "?")
            cands = "\n".join(
                f'{{"candidate_id": {j}, "name": "{c}", "type": "{TYPES.get(types[c].most_common(1)[0][0], "?")}", "cos": {cos:.2f}}}'
                for j, (cos, c) in enumerate(shortlist))
            user = (f'<새 엔티티>\n{{"name": "{name}", "type": "{t}"}}\n</새 엔티티>\n\n'
                    f"<기존 정본 후보>\n{cands}\n</기존 정본 후보>\n\n"
                    "새 엔티티가 어느 후보와 같은 실세계 대상이면 그 candidate_id를, 아니면 -1을 반환하라.")
            try:
                verdict = call_llm(user)
                n_llm += 1
            except Exception:
                verdict = -1
        if 0 <= verdict < len(shortlist):
            alias[name] = shortlist[verdict][1]
            n_merge += 1
        else:
            canon.append(name)
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(names)} · 정본 {len(canon)} · 병합 {n_merge} · LLM {n_llm} ({time.time()-t0:.0f}s)")

    with open(f"{prefix}_alias.json", "w") as f:
        json.dump(alias, f, ensure_ascii=False, indent=1)
    with open(f"{prefix}_canon.jsonl", "w") as f:
        for c in canon:
            f.write(json.dumps({"name": c, "freq": freq[c],
                                "type_id": types[c].most_common(1)[0][0]}, ensure_ascii=False) + "\n")
    print(f"\n정본 {len(canon)} · 별칭 병합 {n_merge} · LLM 판정 {n_llm} · {time.time()-t0:.0f}s")
    merged_pairs = list(alias.items())[:12]
    for a, c in merged_pairs:
        print(f"  {a}  →  {c}")


if __name__ == "__main__":
    main()
