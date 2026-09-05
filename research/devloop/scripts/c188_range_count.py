#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계기 큐 ㉮ 집행 — 범위∖계수 검산기 (관측 117 수용 기준 ③).

증상(관측 117): «corpus(168)~(179) **11본** 영구 미감사»가 40차(c181) 이래 여섯 절에
재인쇄됐고 범위는 12본이었다(179−168+1). 범위와 계수가 한 칸에 살면서 서로를 검산하지
않았고, 재인쇄가 검산을 대체했다(관행 ⑲의 산술 판본).

기대 동작: 범위와 계수를 한 문장에 함께 쓰면 계수는 범위에서 **파생**되어야 한다.
이 계기는 그 파생을 사후에 대조한다 — «(a)~(b) … N<단위>» 서식을 만나면 `b−a+1`과 `N`을
대조해 인쇄한다.

선언된 한계 (이 계기가 못 보는 것):
  ① **닫힌 범위 가정.** `a~b`를 양끝 포함으로 읽는다. 반개구간(a 이상 b 미만) 의도였다면
     이 계기가 오고발한다. 이 저장소의 계열 서식은 전부 닫힌 범위이나 관례 선언은 없다.
  ② **근접 창.** 범위와 계수가 CO_WINDOW자 안에 있어야 짝으로 본다. 멀리 떨어진 짝은 못 본다.
  ③ **단위 목록이 손 유지 상수다.** UNITS 밖의 단위(예: «12벌»)는 이 눈 밖이다.
  ④ **계수는 범위의 크기가 아닐 수 있다.** «c174~c186 13행 직독»에서 13은 행 수이고
     범위는 사이클이다 — 우연히 1:1이라 맞지만, 1:1이 아닌 짝(«c1~c10 3건 위반»)은
     **정상인데 불일치로 뜬다.** 그래서 이 계기의 출력은 *고발이 아니라 질의*다.
     판정은 손이 한다 — 불일치 행마다 «1:1인가»를 묻고 원장에 답을 적는 것이 수용 기준이다.
  ⑤ 이 계기는 자기 자신을 검사하지 않는다(스크립트는 코퍼스 밖).
  ⑥ **맨숫자 범위(`168~179`)는 일부러 안 본다.** v0가 그것까지 잡자 258짝 중 195가
     불일치로 떴고 — 소음원은 날짜 파편(`08-13`→`8~13`) · 행번호 범위(`6280-6285`) ·
     비율 칸이었다. 신호 대비 소음이 4:1이면 계기가 아니라 소음기다. 그래서 **명시적
     계열 표지**(`cN~cM` · `corpus(N)~(M)`)를 요구한다 — 관측 117이 지목한 서식이
     정확히 그것이다. 대가: 표지 없이 쓴 범위는 이 눈 밖이다(거짓 음성을 골랐다).

probe_guard 채택 — 폴백 없음, 없는 것은 죽는다.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_guard import need_nonempty  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

# 손 유지 상수 — 한계 ③. 이 파일이 정본이며 사본을 갖지 않는다.
UNITS = ["본", "행", "개", "건", "사이클", "줄", "절", "종", "회"]
CO_WINDOW = 6  # 한계 ② — 동격 판정 창. 범위 끝과 계수 사이 최대 거리(자)

# **크기 주장 vs 내용 주장 판별자** — 한계 ④의 처치.
#   크기 주장 = 계수가 범위의 **크기**다.   «corpus(168)~(179) 12본» · «c174~c186 13행»
#   내용 주장 = 계수가 범위 **안 사건 수**다. «c157~c160에 불일치 0건» · «c130~c133 중 3회»
# 후자는 b−a+1과 같을 이유가 없으므로 대조하면 오고발이다(v1 실측: 123/179가 이 부류).
# 판별은 조사로 한다 — 포함 표지가 끼면 내용 주장이고, 계수가 범위에 **바로 붙으면** 동격이다.
# «의»는 회귀가 잡아 넣었다 — 실런 거짓 양성 2건(«c165~c170의 0건» · «c131~c155의 26건")이
# 전부 속격 서식이었다. 동격은 조사를 갖지 않는다는 것이 이 판별자의 전제다.
CONTAIN_MARK = re.compile(r"[에중내서의]|동안|부터|까지")

# 명시적 계열 표지만 — 한계 ⑥. «c168~c179» · «corpus(168)~(179)» · «corpus(168)~corpus(179)».
# 맨숫자 범위(«168~179»)는 일부러 제외한다(v0 신호:소음 = 63:195).
RANGE_RE = re.compile(
    r"(?:corpus\((\d{1,4})\)|c(\d{1,4}))\s*[~∼]\s*(?:corpus\()?\(?c?(\d{1,4})\)?"
)
COUNT_RE = re.compile(r"(\d{1,4})\s*(" + "|".join(UNITS) + r")")


def scan_text(text: str, label: str) -> list[dict]:
    """한 문서에서 (범위, 계수) 짝을 뜬다. 판정은 하지 않고 값만 돌려준다."""
    out: list[dict] = []
    for m in RANGE_RE.finditer(text):
        a = int(m.group(1) if m.group(1) else m.group(2))
        b = int(m.group(3))
        if b < a:
            continue  # 역방향은 범위가 아니다 (예: 날짜·버전 표기)
        span = b - a + 1
        tail = text[m.end():m.end() + CO_WINDOW]
        cm = COUNT_RE.search(tail)
        if not cm:
            continue
        gap = tail[:cm.start()]
        if CONTAIN_MARK.search(gap):
            continue  # 내용 주장 — 계수가 범위 크기가 아니다(한계 ④ 처치)
        n, unit = int(cm.group(1)), cm.group(2)
        line_no = text.count("\n", 0, m.start()) + 1
        ctx_start = max(0, m.start() - 40)
        ctx = text[ctx_start:cm.end() + m.end()].replace("\n", " ")
        out.append({
            "label": label, "line": line_no, "a": a, "b": b,
            "span": span, "n": n, "unit": unit,
            "match": bool(span == n), "ctx": ctx[:160],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="*", default=[
        "research/devloop/frictions.md",
        "research/devloop/predictions.md",
        "research/devloop/gate-queue.md",
    ])
    ap.add_argument("--only-mismatch", action="store_true")
    args = ap.parse_args()

    rows: list[dict] = []
    for rel in args.paths:
        p = ROOT / rel
        text = need_nonempty(p.read_text(encoding="utf-8"), rel)
        rows.extend(scan_text(text, rel))

    total = len(rows)
    bad = [r for r in rows if not r["match"]]
    print("[계기 큐 ㉮ — 범위∖계수 검산 (관측 117 수용 기준 ③)]")
    print(f"  대상 {len(args.paths)}본 · 짝 {total}건 · 일치 {total - len(bad)} · **불일치 {len(bad)}**")
    print("  ※ 불일치는 고발이 아니라 **질의**다 — 한계 ④(계수가 범위 크기가 아닐 수 있다).")
    print("     불일치 행마다 «1:1인가»를 묻고 답을 원장에 적는 것이 수용 기준이다.")
    print()
    show = bad if args.only_mismatch else rows
    for r in show:
        flag = "일치" if r["match"] else "**불일치**"
        print(f"  [{flag}] {r['label']}:{r['line']}  "
              f"{r['a']}~{r['b']} → b−a+1={r['span']} vs 인쇄 {r['n']}{r['unit']}")
        print(f"      … {r['ctx']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
