#!/usr/bin/env python3
"""사이클 91 계기 — 규약의 **도달 시각**(arrival time) 가설 검사 (읽기 전용).

무엇을 재는가.
  audit-90 N1은 관측 42/46의 원인을 "배달 페이로드 소실"(next_actions[0]의 턴 배치
  규약이 c88부터 사라짐)로 지목하고 처치 R1(복원 + 계기 헤더 이중화)을 권고했다.
  c90이 복원을 집행했다. 그런데 c91에서 같은 규약이 또 깨졌다.
  → 내용이 돌아왔는데도 깨졌다면, 남은 변수는 **내용이 아니라 도착 시각**이다.

  이 계기는 원장에서 그 시각 가설의 흔적을 센다. 번호·모드 결정에는 쓰지 않는다
  (그건 c48_step0_check.py 첫 줄이 정본이다 — 규약 ③). 분석 목적의 파싱만 한다.
"""

from __future__ import annotations

import json
import os
import re

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PATH = os.path.join(REPO, "research", "devloop", "metrics.jsonl")


def load():
    with open(PATH, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def part_turns(rows):
    print("[A. restore_turns 시계열 — c60 이후]")
    for r in rows:
        c = r.get("cycle")
        if c is None or c < 60:
            continue
        print(f"  c{c}: turns={r.get('restore_turns')}  grade={r.get('restore_grade')}")


def part_capsule(rows, since=84):
    print(f"\n[B. restore_note 안의 '캡슐' 언급 — c{since} 이후]")
    for r in rows:
        c = r.get("cycle")
        if c is None or c < since:
            continue
        note = r.get("restore_note", "")
        hits = re.findall(r"[^.。]{0,80}캡슐[^.。]{0,120}", note)
        print(f"  --- c{c} ({len(hits)}건) ---")
        for h in hits[:3]:
            print("      " + h.strip().replace("\n", " ")[:200])


def part_literal(rows):
    print("\n[C. 턴 배치 규약 리터럴('ToolSearch')이 원장에 나타난 사이클]")
    for r in rows:
        note = r.get("restore_note", "")
        if "ToolSearch" in note:
            frag = re.findall(r"턴1[^/]{0,110}", note)
            print(f"  c{r.get('cycle')}: {frag[:1]}")


def main():
    rows = load()
    print(f"rows={len(rows)}  cycles={rows[0]['cycle']}..{rows[-1]['cycle']}")
    part_turns(rows)
    part_capsule(rows)
    part_literal(rows)


if __name__ == "__main__":
    main()
