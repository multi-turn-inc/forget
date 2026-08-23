"""추출기 A/B 채점 — v0(적당한 프롬프트) vs v2(Graphiti 방법론). (본선 4-R R1)

등록 판정 (docs/graph-substrate-research.md §4.5):
  정크 엔티티율 v2 < v0, 그리고 간선의 목록-외 이름 비율 v2 ≈ 0.
정크의 기계 대리: NEVER-어휘(일반명사·추상어) 적중 + 2자 미만 + 유형 불명.
최종 판단은 상위 30 눈검사 — 기계 지표는 보조다. 허브 검사(최대 차수)가
'Here'=person 4,146건의 재발 여부를 본다.

사용: .venv/bin/python scripts/analyze_extraction.py <v0.jsonl> <v2.jsonl>
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter

JUNK = set("""서버 파일 테스트 모델 코드 시스템 사용자 세션 기억 질의 문제 개선 성능 결과
상태 목표 판단 정직 데이터 정보 내용 작업 방식 방법 과정 상황 경우 이유 부분 기능 구조
설정 완료 실패 성공 확인 검증 기록 원장 doc docs file test model system user session memory
query problem data info work status here users do this you can if the and""".split())


def load(path: str):
    rows = [json.loads(l) for l in open(path)]
    entities, edges, per_row = Counter(), [], []
    violations = 0
    for r in rows:
        ents = r.get("entities") or []
        names = []
        for e in ents:
            name = str(e.get("name") or "").strip()
            if name:
                names.append(name)
                entities[name.lower()] += 1
        per_row.append(len(names))
        for t in (r.get("facts") or r.get("triples") or []):
            if isinstance(t, dict):
                s, o = str(t.get("source")), str(t.get("target"))
            else:
                if len(t) != 3:
                    continue
                s, o = str(t[0]), str(t[2])
            edges.append((s, o))
            if s not in names or o not in names:
                violations += 1
    return rows, entities, edges, per_row, violations


def junk_rate(entities: Counter) -> float:
    total = sum(entities.values())
    junk = sum(c for name, c in entities.items()
               if name in JUNK or len(name) < 2
               or re.fullmatch(r"[\d\W_]+", name))
    return junk / max(1, total)


def report(tag: str, path: str) -> None:
    rows, entities, edges, per_row, violations = load(path)
    degree = Counter()
    for s, o in edges:
        degree[s.lower()] += 1
        degree[o.lower()] += 1
    print(f"══ {tag} ({path.split('/')[-1]}) ══")
    print(f"  행 {len(rows)} · 엔티티 언급 {sum(entities.values())} (고유 {len(entities)}) "
          f"· 간선 {len(edges)} · 행당 엔티티 중위 {sorted(per_row)[len(per_row)//2] if per_row else 0}")
    print(f"  정크율(기계 대리) {100*junk_rate(entities):.1f}% · 목록-외 간선 {violations}/{len(edges)}")
    print(f"  최대 허브: {[f'{n}({c})' for n, c in degree.most_common(5)]}")
    print(f"  상위 엔티티 30 (눈검사):")
    for name, c in entities.most_common(30):
        print(f"    {c:3d}  {name}")
    print()


def main() -> None:
    report("v0 적당한 프롬프트", sys.argv[1])
    report("v2 Graphiti 방법론", sys.argv[2])


if __name__ == "__main__":
    main()
