#!/usr/bin/env python
"""c116 — 관측 59 수용 기준 ③ 창 마감 대조 (읽기 전용).

배포(훅 채널 08-12 13:40:22 KST, cycle-111 §1)의 전후 24h 창을 게이트 원장
전수 파싱으로 대조한다. c111 §3이 기준 문면: 창이 미완(10.9h)이라 판정을 유보했고,
어휘 분화(신몸은 타임아웃 시 degraded_to_low로 강등 생존) 때문에 올바른 비교량은
(a) 사망률 search_error 와 (b) 타임아웃류 발생률(search_error+degraded_to_low)
둘 다 병기라고 지정했다.

교정 검사: c111이 인쇄한 두 창(배포 직전 24h · 배포 후 경과분 10.9h)을 같은
파서로 재현한다 — 재현 실패면 이 계기의 숫자는 쓰지 않는다 (원칙 1: 직전 측정과의
비교 없는 숫자는 기록하지 않는다).

원장 행은 읽기만 한다. prompt_head는 인쇄하지 않는다 (관측 36·37: 실사용 프롬프트
원문의 저장소 전파 금지).
"""
import json
import os
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

LEDGER = os.path.expanduser("~/.forget/hooks/state/turnrecall_gate.jsonl")
KST = ZoneInfo("Asia/Seoul")


def ep(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).timestamp())


DEPLOY = ep("2026-08-12 13:40:22")  # 훅 채널 mtime, cycle-111 §1 1차 증거

WINDOWS = [
    ("원 관측 창 (c105, 참고)", ep("2026-08-10 20:38:00"), ep("2026-08-11 20:38:00")),
    ("배포 직전 24h", DEPLOY - 86400, DEPLOY),
    ("[교정] c111 배포 후 경과분 10.9h", DEPLOY, ep("2026-08-13 00:37:00")),
    ("배포 후 24h (마감 창 — 이 사이클의 표적)", DEPLOY, DEPLOY + 86400),
    ("창 마감 이후 잔여 (참고, 미완)", DEPLOY + 86400, None),
]

# c111 §3 표의 기재값 — 재현 대상
CALIBRATION = {
    "배포 직전 24h": {"injected": 24, "search_error": 2, "degraded_to_low": 0},
    "[교정] c111 배포 후 경과분 10.9h": {"injected": 15, "search_error": 1, "degraded_to_low": 5},
}


def main() -> int:
    rows = [json.loads(l) for l in open(LEDGER, encoding="utf-8") if l.strip()]
    print(f"게이트 원장 전수 파싱: {len(rows)}행  (마지막 at="
          f"{datetime.fromtimestamp(rows[-1]['at'], KST):%Y-%m-%d %H:%M:%S} KST)")
    print(f"배포 기준 시각: {datetime.fromtimestamp(DEPLOY, KST):%Y-%m-%d %H:%M:%S} KST (훅 mtime)")
    calib_fail = False
    for name, lo, hi in WINDOWS:
        sel = [r for r in rows if r["at"] >= lo and (hi is None or r["at"] < hi)]
        c = Counter(r["action"] for r in sel)
        inj, se, deg = c.get("injected", 0), c.get("search_error", 0), c.get("degraded_to_low", 0)
        attempts = inj + se + deg  # 게이트 통과 후 검색이 시도된 행 전체
        timeouts = se + deg
        errs = Counter(r.get("error", "").split(":")[0] for r in sel if r.get("error"))
        span_h = ((hi if hi is not None else rows[-1]["at"]) - lo) / 3600
        print(f"\n[{name}]  {span_h:.1f}h  전체 {len(sel)}행")
        print(f"  actions: {dict(c)}")
        print(f"  injected={inj}  search_error={se}  degraded_to_low={deg}")
        print(f"  (a) 사망률: search_error/injected = {se}/{inj}"
              + (f" = {se/inj:.3f}" if inj else " (분모 0)")
              + f"  ·  search_error/시도 = {se}/{attempts}"
              + (f" = {se/attempts:.3f}" if attempts else ""))
        print(f"  (b) 타임아웃류 계 = {timeouts}  발생률 = {timeouts}/{attempts}"
              + (f" = {timeouts/attempts:.3f}" if attempts else ""))
        if errs:
            print(f"  error 필드(클래스): {dict(errs)}")
        want = CALIBRATION.get(name)
        if want:
            got = {"injected": inj, "search_error": se, "degraded_to_low": deg}
            ok = got == want
            calib_fail |= not ok
            print(f"  [교정 검사] c111 기재 {want} → 재현 {'일치' if ok else f'불일치: {got}'}")
    if calib_fail:
        print("\n교정 실패 — 이 인쇄의 숫자는 기록하지 않는다 (원칙 1).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
