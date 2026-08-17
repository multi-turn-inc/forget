#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""수확 커밋 --stat 계기 — 다음 HAND 분모를 손에서 빼앗는다 (audit-150 R6, c151 배선).

왜 이 파일이 존재하는가
-----------------------
매 사이클 절차 5는 다음 사이클을 위해 "이번 수확 커밋이 코퍼스를 얼마나 키웠는가"를
task_state에 남긴다. 그 수치는 지금까지 **손으로 옮겨적혔고**, 계열은 이렇게 갔다:

    c147 Δ−1  →  c148 클린  →  c149 Δ±1 교차  →  c150 Δ−19

처치는 세 번 다 **규약 문면 추가**였다. 실효는 0이었다. 가장 선명한 영수증:
c149가 이 계열의 처치로 '쓰기 직전 재대조 의무'를 신설했고, **신설 당사이클의
task_state 쓰기가 그 의무를 위반**했다(audit-150 §4). 문면은 다음 손이 읽어야
작동하는데, 틀리는 손은 바로 그 순간 읽지 않고 있다.

그래서 남은 처치는 하나다: 손을 경로에서 뺀다. 이 스크립트가 숫자를 만들고,
사람은 **붙여넣기만** 한다.

무엇을 인쇄하는가
-----------------
  1. `--numstat` 파싱 — 파일별 삽입/삭제. (`--stat`의 사람용 정렬 문자열이 아니라
     기계용 탭 구분 형식을 읽는다. `--stat`은 넓은 트리에서 파일명을 `...`로 줄여
     경로를 손상시킨다 — 옮겨적기 오류를 고치러 와서 파싱 오류를 심지 않는다.)
  2. `--shortstat`과의 **교차검산** — 두 번째 독립 읽기. 손이 "2회 교차 확인"이라고
     적어 온 절차를 기계가 한다. 불일치면 시끄럽게 말한다.
  3. **corpus() 스코프 분류** — 이번 커밋의 어느 부분이 다음 사이클 HAND 코퍼스에
     들어오고 어느 부분이 사각인가. 스코프 정본은 c129의 `CORPUS_PATHS` 하나이며
     여기서 재선언하지 않고 import한다(관측 30·34: 자[尺]를 두 벌 두지 않는다).
  4. **붙여넣기 블록** — task_state에 그대로 들어갈 문장.

정직 병기 (이 계기가 하지 못하는 것)
------------------------------------
행 수는 **문장 수가 아니다.** corpus()는 SENT_SPLIT으로 재분절하므로 여기서 나오는
`+N`은 문장 수의 상한도 하한도 아니다(c146·c148 실측: '행−공백=문장' 정합은 우연).
이 스크립트는 **행 수만** 책임진다. 문장 수는 다음 사이클이 corpus(N) 직호출로
실측해야 하고, 붙여넣기 블록은 그 사실을 문면에 달고 나간다.

사용:
    .venv/bin/python research/devloop/scripts/harvest_stat.py            # HEAD
    .venv/bin/python research/devloop/scripts/harvest_stat.py <ref>
    .venv/bin/python research/devloop/scripts/harvest_stat.py --cycle 151
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c129_negative_claims import CORPUS_PATHS, HARVEST_SUBJECT  # noqa: E402


def sh(args: list[str]) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout


def parse_numstat(text: str) -> list[tuple[int | None, int | None, str]]:
    """`git show --numstat --format=` 출력을 (삽입, 삭제, 경로)로. **순수 함수**.

    바이너리 파일은 `-\t-\t경로`로 오며 (None, None, 경로)로 남긴다 — 0으로 접지
    않는다. 0으로 접으면 "삽입 0"이라는 **거짓 사실**이 총계에 섞이고, 그것이 바로
    이 스크립트가 없애러 온 종류의 오류다(모르는 것을 '일치'로 보고하지 않는 규율).
    """
    rows: list[tuple[int | None, int | None, str]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins, dele, path = parts[0], parts[1], "\t".join(parts[2:])
        rows.append((None if ins == "-" else int(ins),
                     None if dele == "-" else int(dele),
                     path.strip()))
    return rows


def parse_shortstat(text: str) -> tuple[int, int, int]:
    """`--shortstat` 한 줄에서 (파일수, 삽입, 삭제). **순수 함수** — 독립 2차 읽기.

    누락 항목은 0이다: 삭제가 없는 커밋의 출력에는 `deletions` 절 자체가 없다.
    여기서의 0은 '못 봄'이 아니라 git이 명시한 '없음'이므로 접어도 안전하다.
    """
    import re
    files = re.search(r"(\d+) files? changed", text)
    ins = re.search(r"(\d+) insertions?\(\+\)", text)
    dele = re.search(r"(\d+) deletions?\(-\)", text)
    return (int(files.group(1)) if files else 0,
            int(ins.group(1)) if ins else 0,
            int(dele.group(1)) if dele else 0)


def classify_scope(rows: list[tuple[int | None, int | None, str]],
                   corpus_paths: list[str]) -> tuple[list, list]:
    """(코퍼스 안, 코퍼스 밖=사각). **순수 함수**.

    경로 완전 일치로만 가른다. corpus()가 `git show -- <경로>`로 긁으므로 그
    의미론과 같다 — 디렉터리 접두 매칭을 여기서 발명하면 두 계기가 갈라진다.
    """
    inside = [r for r in rows if r[2] in corpus_paths]
    outside = [r for r in rows if r[2] not in corpus_paths]
    return inside, outside


def format_denominator_block(sha: str, subject: str,
                             rows: list[tuple[int | None, int | None, str]],
                             corpus_paths: list[str], cycle: int | None) -> str:
    """task_state에 그대로 들어갈 문장. **순수 함수** — 이 반환값이 R6의 산출물이다."""
    inside, outside = classify_scope(rows, corpus_paths)
    total_ins = sum(r[0] or 0 for r in rows)

    def seg(items: list) -> str:
        return " · ".join(f"{Path(p).name} +{i or 0}" for i, _, p in items) or "없음"

    nxt = f"corpus({cycle}) 직호출" if cycle is not None else "corpus(N) 직호출"
    return (
        f"다음 HAND 분모 — 수확 커밋 {sha[:7]} --numstat 기계 직독"
        f"(harvest_stat.py, 손 옮겨적기 0): "
        f"코퍼스 내 = {seg(inside)} · 코퍼스 밖(사각) = {seg(outside)} · "
        f"총 {total_ins} 삽입. "
        f"교차검산 --shortstat 일치. "
        f"**행 수는 문장 수가 아니다**(corpus()는 SENT_SPLIT 재분절) — "
        f"문장 수는 {nxt} 실측으로만."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="수확 커밋 --stat 계기 (audit-150 R6)")
    ap.add_argument("ref", nargs="?", default=None, help="대상 커밋 (기본 HEAD)")
    ap.add_argument("--cycle", type=int, default=None,
                    help="수확 커밋을 'loop(cycle N):' 제목으로 찾는다")
    ap.add_argument("--next-cycle", type=int, default=None,
                    help="붙여넣기 블록에 적을 다음 사이클 번호 (기본: --cycle+1)")
    args = ap.parse_args()

    if args.cycle is not None:
        want = HARVEST_SUBJECT.format(n=args.cycle)
        sha = ""
        for line in sh(["git", "log", "--format=%H %s", "-50"]).splitlines():
            h, _, subj = line.partition(" ")
            if subj.startswith(want):
                sha = h
                break
        if not sha:
            print(f"[FATAL] 사이클 {args.cycle} 수확 커밋을 찾지 못했다 — 아직 커밋 전인가?")
            return 2
    else:
        sha = sh(["git", "rev-parse", args.ref or "HEAD"]).strip()

    subject = sh(["git", "log", "-1", "--format=%s", sha]).strip()
    rows = parse_numstat(sh(["git", "show", "--numstat", "--format=", sha]))
    s_files, s_ins, s_del = parse_shortstat(
        sh(["git", "show", "--shortstat", "--format=", sha]))

    n_ins = sum(r[0] or 0 for r in rows)
    n_del = sum(r[1] or 0 for r in rows)
    binary = [r for r in rows if r[0] is None]
    agree = (n_ins == s_ins and n_del == s_del and len(rows) == s_files)

    print("[수확 --stat 계기 — audit-150 R6 (c151). 손 옮겨적기 대신 붙여넣기.]")
    print(f"  ref={sha[:7]}  {subject}")
    print()
    print(f"  {'삽입':>6s} {'삭제':>6s}  경로")
    for ins, dele, path in rows:
        mark = "  ← 바이너리(수치 없음)" if ins is None else ""
        print(f"  {('-' if ins is None else ins):>6} "
              f"{('-' if dele is None else dele):>6}  {path}{mark}")
    print()
    print(f"  numstat 합계 : 파일 {len(rows)} · 삽입 {n_ins} · 삭제 {n_del}")
    print(f"  shortstat    : 파일 {s_files} · 삽입 {s_ins} · 삭제 {s_del}")
    print(f"  교차검산     : {'일치' if agree else '**불일치 — 손으로 확인할 것**'}"
          + (f"  (바이너리 {len(binary)}건은 numstat에 수치 없음)" if binary else ""))

    inside, outside = classify_scope(rows, CORPUS_PATHS)
    print()
    print(f"  [corpus() 스코프 — 정본 = c129.CORPUS_PATHS {CORPUS_PATHS}]")
    print(f"    코퍼스 내   : {[p for _, _, p in inside] or '없음'}")
    print(f"    코퍼스 밖(사각): {[p for _, _, p in outside] or '없음'}")
    print("    ※ 사각은 '작다'는 뜻이 아니다 — c150은 감사문 +243행 전량이 사각이었다.")

    nxt = args.next_cycle
    if nxt is None and args.cycle is not None:
        # c156 수정 (c155 발견 · 관측 83 둘째 표본 · P42 판정 직후 집행).
        # 구본은 `args.cycle + 1`이었다. 다음 손의 HAND는 **이 사이클의** 코퍼스를
        # 감사하므로(관행 = corpus(N−1) 감사, 즉 N번 수확의 다음 손은 corpus(N)) 정답은
        # args.cycle이다. N+1은 그 시점 원장 행이 없어 corpus()가 FATAL로 죽으며,
        # c153·c154가 그 FATAL을 각각 '부수 재확인 — 정상'으로 3연속 오독했다.
        nxt = args.cycle
    print()
    print("  [붙여넣기 블록 — task_state 주의문에 그대로]")
    print("  " + "─" * 70)
    print(format_denominator_block(sha, subject, rows, CORPUS_PATHS, nxt))
    print("  " + "─" * 70)
    return 0 if agree else 1


if __name__ == "__main__":
    raise SystemExit(main())
