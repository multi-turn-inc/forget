"""간선 기질 빌더 — 추출 트리플 + 해소 별칭 → graph.sqlite3. (본선 4-R R3 준비)

실원장과 분리된 파생 파일이다: 원장에서 언제든 재구축 가능하고, 원장에 아무것도
쓰지 않는다 (게이트 불요). 확산·이웃 조회의 유일한 기질이 되며, co-mention
memory_entities(오염 실측)는 이 기질로 대체를 검토한다.

스키마:
  entities(name PK, type_id, freq)                          — R2 정본
  mentions(memory_id, entity)                               — 기억 ↔ 정본 (트리플 원천)
  edges(src, relation, dst, fact, valid_at, episode_key)    — 술어 간선 (사실 문장 보존)

사용: .venv/bin/python scripts/build_graph_substrate.py <triples.jsonl> <alias.json> <out.sqlite3>
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter


def main() -> None:
    triples_path, alias_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    alias = json.load(open(alias_path))

    def canon(name: str) -> str:
        key = " ".join(str(name).strip().lower().split())
        return alias.get(key, key)

    con = sqlite3.connect(out_path)
    con.executescript("""
        DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS mentions; DROP TABLE IF EXISTS edges;
        CREATE TABLE entities (name TEXT PRIMARY KEY, type_id INTEGER, freq INTEGER);
        CREATE TABLE mentions (memory_id TEXT, entity TEXT);
        CREATE TABLE edges (src TEXT, relation TEXT, dst TEXT, fact TEXT, valid_at TEXT, episode_key TEXT);
        CREATE INDEX idx_mentions_mem ON mentions(memory_id);
        CREATE INDEX idx_mentions_ent ON mentions(entity);
        CREATE INDEX idx_edges_src ON edges(src);
        CREATE INDEX idx_edges_dst ON edges(dst);
    """)
    freq: Counter = Counter()
    types: dict[str, Counter] = {}
    n_mentions = n_edges = 0
    with con:
        for line in open(triples_path):
            row = json.loads(line)
            episode = str(row.get("id"))
            names = {}
            for e in row.get("entities") or []:
                c = canon(e.get("name") or "")
                if len(c) < 2:
                    continue
                names[" ".join(str(e["name"]).strip().lower().split())] = c
                freq[c] += 1
                types.setdefault(c, Counter())[int(e.get("type_id", 3))] += 1
                for mid in row.get("memory_ids") or []:
                    con.execute("INSERT INTO mentions VALUES (?, ?)", (str(mid), c))
                    n_mentions += 1
            for f in row.get("facts") or []:
                src, dst = canon(f.get("source")), canon(f.get("target"))
                if src in freq and dst in freq and src != dst:
                    con.execute("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?)",
                                (src, str(f.get("relation")), dst, str(f.get("fact"))[:300],
                                 f.get("valid_at"), episode))
                    n_edges += 1
        for name, count in freq.items():
            con.execute("INSERT INTO entities VALUES (?, ?, ?)",
                        (name, types[name].most_common(1)[0][0], count))

    deg = Counter()
    for src, dst in con.execute("SELECT src, dst FROM edges"):
        deg[src] += 1
        deg[dst] += 1
    print(f"정본 엔티티 {len(freq)} · 언급 {n_mentions} · 술어 간선 {n_edges}")
    print(f"최대 허브: {[f'{n}({c})' for n, c in deg.most_common(5)]}")
    con.close()


if __name__ == "__main__":
    main()
