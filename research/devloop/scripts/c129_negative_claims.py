#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""c129 — 기록 부정 주장 감사 (관측 74 수용 기준 ③에 검출기를 붙인다)

무엇을 하는가
-------------
관측 74(c127 등재)의 수용 기준 ③은 이렇게 적혀 있다:

    "이후 사이클에서 '대장 미반영'류 부정 주장은 직독 근거를 병기한다 —
     병기 없는 부정 주장이 나오면 재발 1호로 계상한다."

이것은 **검출기 없는 검출 규칙**이었다. 누가 세는지가 없다. ③이 발효한 것은
c127 이후이므로 감사 가능한 사이클은 이 계기를 쓰는 시점에 **정확히 하나**(c128)다.
그 하나를 실제로 센다.

왜 손 판정을 먼저 쓰고 정규식을 나중에 쓰는가 (이 계기의 설계 핵심)
------------------------------------------------------------------
관측 74의 본체는 "손 판정이 파서 출력을 입력으로 받으면 감사가 아니라 **증폭**"이다.
그러므로 이 계기가 그 구조를 반복하면 자기가 감사하려는 결함을 자기가 저지른다.

배치를 뒤집었다:
  1. 저자가 **원문 전체**(원장 c128 행 산문 8필드 + 수확 커밋의 devloop md 추가 줄
     136행)를 먼저 통독하고 `HAND` 표를 작성했다. 이 표가 **감사 원본**이다.
  2. 정규식 검출기는 그 다음에 돌며, **판정의 근거가 아니라 감사의 대상**이다.
  3. 계기는 둘을 대조해 검출기의 재현율·정밀도를 인쇄한다.

즉 이 파일에서 정규식이 틀리면 지표가 나빠질 뿐 판정은 흔들리지 않는다.
c124는 반대 배치였고(파서 출력 → 손 판정), 그래서 P37 유령 청구가 3사이클을 살았다.

**이 사이클의 코퍼스는 손 통독이 가능한 크기(md 136행 + 산문 5,685자)이므로
재현율이 실제로 측정된다.** 코퍼스가 커지면 이 성질은 사라지고, 그때는
재현율 미지를 병기해야 한다 — 침묵은 부재의 증거가 아니다(관측 74 본문).

감사 대상의 정의 (자[尺] — 이 정의 밖은 세지 않는다)
---------------------------------------------------
**기록 부정 주장** = 다음 셋을 모두 만족하는 문장.
  (i)  지시대상이 **지속적 기록물**이다 (대장 절 · 원장 행/필드 · 파일 · 커밋 ·
       캡슐 · 스키마 · 기억 스토어).
  (ii) 그 기록물 **안에 무엇이 없다/빠졌다/미반영이다**라고 단언한다.
  (iii) 그 단언이 참이려면 **기록물을 열어봐야** 한다.

배제(사유 명시): 자기 행위의 계수(`짐작 0` · `손 편집 0` · `제품 코드 0행` ·
`신규 등록 0`)는 열어볼 기록이 아니라 수행 사실이므로 (iii)을 만족하지 않는다.
계측 결과(`437 passed`)도 같다. **부정의 부정**("하자는 판정 부재가 **아니라**
전사 누락이었다")은 (ii)를 만족하지 않는다 — 오히려 앞선 부정 주장의 반박이다.
관측 63이 실측한 기전(순수 부분문자열 탐색이 부정문에 격발)이 여기서 재발하지
않도록 검출기에 부정 문맥 가드를 둔다.

판정 3값
--------
  병기      — 같은 문장 또는 인접 문맥에 직독 근거(원문 인용 · 원장 행+필드명 ·
              git 명령 · 전수 열거 인쇄)가 있다.
  간접      — 근거가 동반되나 **부정 그 자체**를 열어 보인 것은 아니다.
  없음      — 근거가 없다. **③에 따라 재발로 계상한다.**

사용: .venv/bin/python research/devloop/scripts/c129_negative_claims.py [--cycle 128]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
METRICS = ROOT / "research" / "devloop" / "metrics.jsonl"

PROSE_FIELDS = [
    "restore_note", "recall_note", "frictions_note", "open_observations_note",
    "tests", "predictions_note", "gate_pending", "work",
]

# 사이클 → 수확 커밋 (md 코퍼스 취득용). 손으로 박지 않는다: git log로 찾는다.
HARVEST_SUBJECT = "loop(cycle {n}):"

# 코퍼스 스코프 — corpus()가 md 추가줄을 긁는 대상. **정본은 이 상수 하나다** (c151).
# 왜 상수로 올렸는가: c151이 붙인 harvest_stat.py(수확 --stat 계기, audit-150 R6)가
# "이번 커밋의 어느 부분이 다음 사이클 코퍼스에 들어오고 어느 부분이 사각인가"를
# 인쇄하려면 같은 스코프를 알아야 한다. 두 벌로 두면 그 순간 관측 30·34(자[尺]가
# 선언 없이 갈라지면 시점 간 비교가 소멸)의 다음 표본이 된다 — 그래서 재선언이
# 아니라 import다. 스코프가 바뀌면 여기만 바뀌고 두 계기가 함께 움직인다.
# (c146 실측 계보: 코퍼스 분모 급감의 원인이 이 스코프였고 — amendments/ 밖 —
#  그 사실이 손 노트에만 있었다. 이제 코드가 말한다.)
CORPUS_PATHS = [
    "research/devloop/frictions.md",
    "research/devloop/predictions.md",
]

# ── HAND: 감사 원본 ────────────────────────────────────────────────────────
# 저자가 원문 통독으로 작성했다. (id, 출처, 인용 니들, 판정, 사유)
# 하드 가드 (c131, audit-130 R2): 이 표는 아래 HAND_CYCLE 전용 하드코딩이다.
# c129 next_actions의 "사이클 인자만 바꾸면 그대로 돈다"는 c130 감사가 스크립트
# 직독으로 반증했다 — --cycle이 다르면 §1·§2 판정 인쇄를 거부하고 대조용 원시
# 검출만 인쇄한다(감사 원본은 매회 손 통독으로 새로 쓴다).
HAND_CYCLE = 128
HAND: list[tuple[str, str, str, str, str]] = [
    ("H1", "frictions/관측71잔여", "대장 본문에 판정이 없었고", "병기",
     "같은 절이 c127 전수 배정(41건 `- 상태:` 부여)을 배경으로 두고, 원장 c128 "
     "restore_note가 'P20·P25 절 전문 정독'을 명기했다."),
    ("H2", "frictions/관측71잔여", "확인하지 않은 채", "병기",
     "c127 원문을 직접 인용했다 — \"판정이 원장 c81 행에 있을 수 있으나\"."),
    ("H3", "frictions/관측71잔여", "판정 부재가 아니라", "대상외",
     "부정의 부정. (ii) 불만족 — 앞선 부정 주장의 반박이다. 검출기 위양성 시험 항."),
    ("H4", "frictions/관측71잔여", "대장으로만 오지 않았다", "병기",
     "원장 c81 work/tests 인용 + 대장 절 정독이 같은 절에 있다."),
    ("H5", "frictions/관측71잔여", "대차대조에서 **사라졌다**", "병기",
     "c124_retro_prep.py 전수 인쇄(41/41)가 근거이며, 그 계기는 관측 71 ③으로 "
     "v1·v2를 폐기하고 `- 상태:` 직독으로 전환된 판본이다."),
    ("H6", "frictions/관측73처분", "지표 추세 규칙 0건", "병기",
     "'세 계수 규칙 블록을 전부 대조했다'로 전수 훑기를 명시했다."),
    ("H7", "predictions/P20처분", "`restore_floor` 필드가 없어", "간접",
     "원장 c69 행 인용은 동반되나 **필드 부재 자체**를 키 열거로 열어 보이지 "
     "않았다. c69 캐비앗의 전재다. (사후 검증: c128 행 키 목록에 실제로 없다 — "
     "주장은 참이나 ③이 요구하는 것은 진위가 아니라 병기다.)"),
    ("H8", "predictions/P20처분", "0회 발화 = 등록 조건 미충족", "병기",
     "인용된 c69 restore_note가 'c66·c67·c68·c69 전부 restore_turns 3'을 담아 "
     "창 전수를 덮는다 — 3이면 격발 조건(4 유지)은 참이 될 수 없다."),
    ("H9", "predictions/P25처분", "발동하지 않았다", "병기",
     "원장 c81 work/tests 원문 인용이 같은 항에 병기됐다."),
    ("H10", "원장/restore_note", "거짓 항 0", "병기",
     "배달된 절차를 실제로 수행해 대조한 서술이 선행한다('배달된 절차가 그대로 옳았고')."),
    ("H11", "원장/restore_note", "devloop 무관 = miss", "병기",
     "c48 파트 B가 캡슐 원문을 인쇄하고 니들 도달을 계수한다 — 원문 동반."),
    ("H12", "원장/recall_note", "기억 스토어에 물을 것이 없었다", "없음",
     "**재발 1호.** 능동 검색 0회인 채로 스토어의 내용에 대해 부정을 단언했다. "
     "스토어를 열지 않고 '없다'를 적은 것이며, 이는 관측 74가 명명한 기전"
     "(계기의 침묵을 근거로 기록 상태를 주장)의 정확한 형태다. "
     "c129가 능동 검색 1회로 행동을 바꾼 hit를 얻어 **반례를 실측했다**."),
    ("H13", "원장/frictions_note", "파서 이탈 목록에서 확인", "병기",
     "이중 계상 회피 근거로 파서 이탈 목록 직독을 명시했다."),
    ("H14", "원장/open_observations_note", "여전히 이 눈 밖", "병기",
     "c123 계수 규칙 재사용 + 빈티지 범위(48~57) 병기."),
    ("H15", "원장/predictions_note", "필드 부재 0 · 어휘 오류 0", "병기",
     "H5와 같은 계기의 전수 인쇄가 근거."),
]

# ── 손 표 밖 검출의 재판정 ────────────────────────────────────────────────
# 검출기가 HAND 밖에서 문 8건을 물어왔다. 그중 저자가 통독에서 **빠뜨린 위반**이
# 있으면 감사의 방향이 뒤집힌다(파서가 손 판정을 교정한 것이 되므로 반드시 공표).
# 실제로 전수 재판정한 결과: 신규 위반 0. 내역을 남겨 다음 손이 다시 하지 않게 한다.
FP_ADJ: list[tuple[str, str, str]] = [
    ("정의 A: **능동 0회**", "대상외", "자기 행위의 계수(수행 사실) — 정의 (iii) 불만족"),
    ("행동의 순서를 지정", "대상외", "가정문('만약 절차 없이 배달됐다면') — 부정 단언 아님"),
    ("② 캡슐 **miss**", "중복/병기", "H11과 같은 주장의 다른 문장. c48 파트 B 원문 인쇄 동반"),
    ("**신규 등록 0 · 소급 기재 2건", "중복/병기", "'신규 등록 0'은 자기 계수, '무기재 소멸'은 H15와 동일 근거"),
    ("**신규 상신 1 · 큐 순증 1", "대상외", "게이트 큐 계수 — 열어볼 기록이 아니라 수행 사실"),
    ("판정은 c69, 대장 전사만 누락됐다", "중복/병기", "H4와 같은 주장. 직후에 원장 c69 원문 인용"),
    ("원장에 있었으나 대장에 오지 않았다", "중복/병기", "H4의 md 판본. 원장 행+필드명 병기"),
    ("판정은 c81 당일, 대장 전사만 누락됐다", "중복/병기", "H4 계열. 직후에 원장 c81 work/tests 인용"),
]


# ── 검출기 (감사 대상) ─────────────────────────────────────────────────────
# (i) 기록 지시대상
REF = r"(대장|원장|predictions|metrics|frictions|캡슐|스토어|기억|절|필드|행|커밋|파일|스키마|목록|표)"
# (ii) 존재 부정
NEG = r"(없|미반영|미기재|누락|부재|빠[졌지]|안 (?:왔|보이|담)|오지 않|않았다|못했다|미발동|무발동|0회|0건)"
# 부정 문맥 가드 — 관측 63 기전(순수 부분문자열이 부정문에 격발)의 예방
GUARD = re.compile(r"(부재가 아니|없는 것이 아니|아니라 전사|틀린 수가 아니)")

SENT_SPLIT = re.compile(r"(?<=다\.)\s+|(?<=다\.)(?=\*)|\n")


def harvest_commit(n: int) -> str:
    out = subprocess.run(
        ["git", "log", "--format=%H %s", "-50"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        sha, _, subj = line.partition(" ")
        if subj.startswith(HARVEST_SUBJECT.format(n=n)):
            return sha
    raise SystemExit(f"[FATAL] 사이클 {n} 수확 커밋을 찾지 못했다 — 코퍼스 취득 불가")


def corpus(n: int) -> list[tuple[str, str]]:
    """(출처, 문장) 목록. 원장 산문 8필드 + 수확 커밋의 devloop md 추가 줄."""
    items: list[tuple[str, str]] = []
    row = None
    for line in METRICS.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("cycle") == n:
            row = r
    if row is None:
        raise SystemExit(f"[FATAL] 원장에 사이클 {n} 행이 없다")
    for f in PROSE_FIELDS:
        for s in SENT_SPLIT.split(str(row.get(f, ""))):
            if s.strip():
                items.append((f"원장/{f}", s.strip()))

    sha = harvest_commit(n)
    diff = subprocess.run(
        ["git", "show", sha, "--", *CORPUS_PATHS],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    added = [l[1:] for l in diff.splitlines()
             if l.startswith("+") and not l.startswith("+++")]
    for s in SENT_SPLIT.split("\n".join(added)):
        if s.strip():
            items.append(("md/추가줄", s.strip()))
    return items


def detect(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    hits = []
    for src, s in items:
        if GUARD.search(s):
            continue
        if re.search(REF, s) and re.search(NEG, s):
            hits.append((src, s))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", type=int, default=128)
    args = ap.parse_args()
    n = args.cycle

    print(f"c129 — 기록 부정 주장 감사 (대상 사이클 c{n}, 관측 74 ③ 최초 집행)")
    print("=" * 78)
    print("배치: 손 통독(원문) → HAND 표 = 감사 원본 / 정규식 = 감사 대상.")
    print("      파서 출력은 판정의 입력이 아니다 (관측 74 '증폭' 기전의 예방).")

    items = corpus(n)
    sha = harvest_commit(n)
    print(f"\n[코퍼스] 원장 c{n} 산문 {len(PROSE_FIELDS)}필드 + 수확 커밋 {sha[:7]} "
          f"md 추가 줄 → 문장 {len(items)}개")

    if n != HAND_CYCLE:
        # audit-130 R2: HAND 표는 c{HAND_CYCLE} 전용 — 타 사이클 판정 인쇄를 거부한다.
        print(f"\n[!] HAND 갱신 필요 — HAND 표는 사이클 {HAND_CYCLE} 전용이다.")
        print(f"    §1(손 판정)·§2(재현율/정밀도)는 c{n}에 대해 인쇄하지 않는다.")
        print("    감사 원본은 매회 손 통독으로 새로 쓴다 (관측 74 배치 — 손=원본, 파서=대상).")
        print("    아래는 대조용 원시 검출뿐이며 판정이 아니다. 검출기 침묵은 부재의")
        print("    증거가 아니다 (c130 실측 재현율 64.3% — 유일한 실제 위반을 못 봤다).")
        hits = detect(items)
        print(f"\n[대조용 원시 검출] {len(hits)}문장")
        for src, s in hits:
            print(f"    · {src:26} {s[:78]}")
        return 0

    # ── 1. 손 판정 (정본) ────────────────────────────────────────────────
    print("\n[1. 손 판정 — 감사 원본]")
    tally: dict[str, int] = {}
    for hid, src, needle, verdict, why in HAND:
        tally[verdict] = tally.get(verdict, 0) + 1
        mark = {"병기": " ", "간접": "~", "없음": "!", "대상외": "·"}[verdict]
        print(f"  {mark}{hid:>3} [{verdict:4}] {src:28} \"{needle}\"")
        if verdict in ("없음", "간접"):
            for chunk in re.findall(r".{1,68}(?:\s|$)", why):
                if chunk.strip():
                    print(f"        {chunk.strip()}")
    audited = [h for h in HAND if h[3] != "대상외"]
    viol = [h for h in HAND if h[3] == "없음"]
    print(f"\n  감사 대상 {len(audited)}건 = 병기 {tally.get('병기', 0)} · "
          f"간접 {tally.get('간접', 0)} · 없음 {tally.get('없음', 0)}"
          f"  (대상외 {tally.get('대상외', 0)}건 별도)")
    print(f"  ③ 계상: **재발 {len(viol)}호** — {', '.join(h[0] for h in viol) or '없음'}")

    # ── 2. 검출기 대조 (감사 대상) ───────────────────────────────────────
    hits = detect(items)
    print(f"\n[2. 정규식 검출기 — 감사 대상, 판정 근거 아님]")
    print(f"  검출 {len(hits)}문장")
    found, missed = [], []
    for hid, src, needle, verdict, why in HAND:
        if verdict == "대상외":
            continue
        ok = any(needle in s for _, s in hits)
        (found if ok else missed).append(hid)
    recall = len(found) / len(audited) if audited else 0.0
    matched_needles = {s for _, s in hits
                       if any(nd in s for _, _, nd, v, _ in HAND if v != "대상외")}
    fp = [(src, s) for src, s in hits if s not in matched_needles]
    prec = len(matched_needles) / len(hits) if hits else 0.0
    print(f"  재현율 {len(found)}/{len(audited)} = {recall:.1%}  (미검출: {', '.join(missed) or '없음'})")
    print(f"  정밀도 {len(matched_needles)}/{len(hits)} = {prec:.1%}  (손 표 밖 검출 {len(fp)}문장)")

    # 대상외 항이 검출됐는가 = 관측 63 기전 재발 시험
    for hid, src, needle, verdict, why in HAND:
        if verdict == "대상외":
            fired = any(needle in s for _, s in hits)
            print(f"  [가드 시험] {hid} \"{needle}\" → "
                  f"{'격발(관측 63 재발!)' if fired else '무격발(가드 작동)'}")

    if fp:
        print("\n  [손 표 밖 검출 — 전수 재판정 결과]")
        unadjudicated = 0
        for src, s in fp:
            hit = next(((nd, v, why) for nd, v, why in FP_ADJ if nd in s), None)
            if hit is None:
                unadjudicated += 1
                print(f"    ? {src:26} [미판정] {s[:60]}")
            else:
                print(f"    · {src:26} [{hit[1]:8}] {hit[2]}")
        newv = [1 for _, v, _ in FP_ADJ if v == "위반"]
        print(f"    → 신규 위반 {len(newv)}건 · 미판정 {unadjudicated}건")
        if unadjudicated:
            print("    ※ 미판정이 남았다 — FP_ADJ를 채우기 전에는 이 감사가 완결이 아니다")
        else:
            print("    → 파서가 손 판정을 교정한 건 0. 감사 방향은 유지된다"
                  " (손 = 원본, 파서 = 대상).")

    # ── 3. 사각 (침묵은 부재의 증거가 아니다) ────────────────────────────
    print("\n[3. 이 계기가 보지 못하는 것 — 명시하지 않으면 이 계기가 관측 74의 다음 표본이다]")
    print("  · 코퍼스는 원장 산문 + 수확 커밋 md 추가 줄뿐이다. 스크립트 주석·커밋")
    print("    메시지 본문·task_state 산문·세션 발화는 감사 밖이다.")
    print("  · 문장 분할은 '다.' 경계 근사다 — 한 문장에 두 주장이 있으면 하나로 센다.")
    print("  · 재현율이 측정된 것은 코퍼스가 손 통독 가능한 크기였기 때문이다.")
    print("    코퍼스가 커지면 이 수는 미지가 되며, 그때 이 값을 그대로 인용하면")
    print("    그것이 관측 34(대조군 라벨의 만료)의 다음 표본이다.")
    print("  · HAND 표의 저자와 감사 대상 사이클의 저자는 같은 모델이다. 외부 심급이")
    print("    아니며, 이 한계는 적대 감사(c130)가 심문할 몫이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
