#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""어휘 게이트 편집-후 기계 영수증 — ㉺ 집행 (관측 128 수용 기준 ③, c269 건설).

왜 이 파일이 존재하는가
-----------------------
파트 P(c48 step 0)는 자기 사이클의 상태줄 편집에 **원리적으로 눈멀다** — step 0
인쇄는 편집 **이전** 원장의 것이고, 파트 P 문면 «신규 위반 — 등록한 사이클이
처치한다»는 상태줄을 새로 쓰는 사이클에게 **집행 불가능한 주소**였다(관측 128 ①·
관측 47 부류): 검출은 항상 N+1로 이월되고 그 사이클은 «등록한 사이클»이 아니다.
c242~c268은 사람 사슬(같은 세션 손 재실행 + task_state 승계)로 메웠고 — 그 성실이
실패하는 모양이 바로 관측 116 재발 계열이다(관측 128 처분 문단이 명시).

처치 = **절차 5 배선**: harvest_stat.py(파트 H가 매 사이클 실행을 의무화)가 이
모듈을 소비해 수확 시점(= 상태줄 편집 **이후**)의 대장을 기계 재검한다.
손 단계 신설 0 — 기존 의무 호출에 승차한다. 신규 위반이면 harvest_stat의 종료
코드가 1로 붉어진다(침묵 없음).

자[尺]는 옮기지 않는다
----------------------
어휘 정본 = `c124_retro_prep.VOCAB` · 기지 위반 정본 = `c48_step0_check.
KNOWN_VOCAB_OFFENDERS`. 둘 다 **import해서 쓴다** — 복사하면 정본이 둘이 되고,
그것이 파트 P 자신이 진단한 병이다(관측 83). 영수증 서식은 c242가 세우고 c243이
전향 표본으로 확인한 자[尺](관측 128 처치·처분 문단)의 상설화이며, 이 파일은
`tmp/c243_vocab_receipt.py`(1표본 일회용)의 승격이다.

정직 병기 (이 계기가 하지 못하는 것)
------------------------------------
이 영수증은 **수확 시점의 대장**만 본다 — 수확 커밋 이후 같은 세션이 대장을 또
고치면 그 편집은 다음 사이클 step 0 파트 P의 몫이다(두 눈은 시계가 다를 뿐 같은
정본을 읽는다). 게이트 자체가 죽으면 '위반 0'이 아니라 **미측정**을 인쇄한다.

사용:
    .venv/bin/python research/devloop/scripts/vocab_receipt.py   # 단독 실행
    (통상은 harvest_stat.py 가 매 사이클 자동 호출한다)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def receipt(errors: list, known_offenders: tuple) -> dict:
    """위반 절 목록을 (신규, 기지)로 분류한다. **순수 함수**.

    파트 P(c48 `part_p`)와 같은 술어를 쓴다 — pid의 KNOWN_VOCAB_OFFENDERS
    등재 여부. 술어를 여기서 재발명하면 두 눈이 갈라진다(관측 30·34 규율).
    """
    fresh = [(pid, errs) for pid, errs in errors if pid not in known_offenders]
    known = [(pid, errs) for pid, errs in errors if pid in known_offenders]
    return {"fresh": fresh, "known": known}


def format_receipt(total: int, rec: dict, vocab_len: int) -> list[str]:
    """영수증 인쇄 행 목록. **순수 함수** — 이 반환값이 원장 전사의 자[尺]다."""
    n_fresh, n_known = len(rec["fresh"]), len(rec["known"])
    lines = [
        "[어휘 게이트 기계 영수증 — ㉺ (관측 128 ③, c269 배선) · 편집-후 재검]",
        f"  대장 {total}건 · 위반 절 {n_fresh + n_known}건 (신규 {n_fresh} · 기지 {n_known})"
        f" · 어휘 정본 VOCAB {vocab_len}값",
    ]
    if rec["fresh"]:
        lines.append("  !! 신규 위반 — **이 세션이 등록한 사이클이다: 지금 처치하라** (하드 에러)")
        for pid, errs in rec["fresh"]:
            for e in errs:
                lines.append(f"       {pid}: {e}")
    else:
        lines.append("  신규 위반 0 — 상태줄 어휘 클린.")
    for pid, errs in rec["known"]:
        lines.append(f"  [기지·게이트 대기] {pid}: {len(errs)}건 — KNOWN_VOCAB_OFFENDERS 등재분")
    return lines


def _load() -> tuple[int, list, int, tuple]:
    """정본 2본을 import해 (대장 크기, 위반 절, 어휘 크기, 기지 상수)를 채취한다."""
    from c124_retro_prep import VOCAB, predictions  # noqa: PLC0415
    from c48_step0_check import KNOWN_VOCAB_OFFENDERS  # noqa: PLC0415
    p = predictions()
    return len(p["records"]), p["errors"], len(VOCAB), KNOWN_VOCAB_OFFENDERS


def run_for_harvest(load=_load) -> int | None:
    """harvest_stat 배선 진입점. 신규 위반 수를 반환하고, 게이트 고장이면
    **None**(미측정 — 0으로 접지 않는다·compare_fingerprint 규율)을 반환한다."""
    try:
        total, errors, vocab_len, known_offenders = load()
    except Exception as exc:  # 계기 고장은 침묵이 아니라 인쇄다
        print("[어휘 게이트 기계 영수증 — ㉺]")
        print(f"  !! 게이트 자체가 돌지 않았다: {type(exc).__name__}: {exc}")
        print("     → 이 수확의 어휘 판정은 **미측정**이다. '위반 0'으로 읽지 말 것.")
        return None
    rec = receipt(errors, known_offenders)
    for line in format_receipt(total, rec, vocab_len):
        print(line)
    return len(rec["fresh"])


def main() -> int:
    fresh_n = run_for_harvest()
    if fresh_n is None:
        return 2
    return 0 if fresh_n == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
