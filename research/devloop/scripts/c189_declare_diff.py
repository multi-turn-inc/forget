#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""계기 큐 ㉭ 집행 — 선언∖정본-diff 검산기 (관측 116 수용 기준 ③).

증상(관측 116): c185가 «표 부기 1(A-168.1 행 44차)»를 **세 채널**(frictions.md 절 ·
원장 frictions_note + gate_pending · task_state)에 선언하고 **완주**했는데, 정본
gate-queue.md의 A-168.1 행은 43차에서 멈춰 있었다. 채널 수는 진실성을 늘리지 않는다 —
같은 손이 쓴 사본이 늘 뿐이다. 그리고 **세는 계기가 없었다**: 파트 D·F·O·P·X 어느 눈도
«산문의 부기/상신 선언 ∖ 표의 diff»를 비교하지 않는다.

기대 동작: 표를 만지는 선언(상신·부기·승격·해소)은 선언 채널이 아니라 **정본 diff**로
검증된다.

**핵심 난점 — 프레임 이동이 매 사이클 전 행을 만진다.** 경과값이 26행 전부 +1 되므로
«그 행이 diff에 있는가»는 항상 참이고, 순진한 검사는 관측 116을 **절대 못 잡는다**
(c185의 A-168.1 행도 그날 +1 됐다). 그래서 이 계기는 경과값을 **마스킹한 뒤** 비교해
«프레임 이동뿐인 행»과 «실질 편집된 행»을 가른다. 관측 116은 정확히 전자다.

선언된 한계 (이 계기가 못 보는 것):
  ① **선언에서 대상 ID를 산문으로 뽑는다.** 산문이 «A-168.1» 대신 «서열 18′»로만
     부르면 이 눈 밖이다. ID 표기가 이 계기의 정의역이다. (c261 보강: 무-ID 서열
     표기는 «판정 불가» 질의 대신 정의역-밖 **노트**로 내린다 — 침묵 아님.)
  ② **경과 서식 의존.** 마스킹은 «N사이클째» 서식을 가정한다. 다른 경과 서식이
     생기면 그 행은 «실질 편집»으로 오고발된다.
  ③ **서열 변동은 이 눈 밖이다.** 행 이동·재번호는 ID 집합을 바꾸지 않으므로
     상신/해소로도 실질 편집으로도 잡히지 않을 수 있다.
  ④ **`gate-queue.md`만 본다.** 다른 정본(predictions.md 등)의 선언∖착지 병은 밖이다.
  ⑤ **불일치는 고발이 아니라 질의다** — ㉮와 같은 규율. 판정은 손이 하고 답을 원장에 적는다.
     (선언이 ID를 안 쓴 채 옳게 집행된 경우가 ①에 의해 불일치로 뜬다.)
  ⑥ **서식 census는 오늘 실측분이지 전수 보증이 아니다**(관측 118 — 이 계기의 형제
     검증기가 서식을 추측하다 한 사이클에 세 번 오고발했다. 추측하지 말고 세라).
  ⑦ **부기 «건수»는 대조하지 않는다 — 대상 ID의 실질 편집 «여부»만 본다.** c186은
     «표 부기 2»(44차 백필 + 45차)를 선언했고 정본의 실질 편집 행은 **1행**이었다 —
     둘 다 같은 A-168.1 행에 들어갔기 때문이다. 건수와 행 수는 1:1이 아니므로 건수를
     대조하면 정직한 사이클을 오고발한다(관측 118의 교훈을 이 계기에 적용한 자리).
  ⑧ **동결 판정(㉵ⓐ)은 현재 워킹트리의 정본을 읽는다** — 과거 사이클 검산에서
     시대착오가 원리상 가능하나, 해소 행은 지우지 않고 취소선+사유로 보존하는
     규약(gate-queue c193 정산)상 동결→비동결 전이가 없어 실무 방향은 단조다.
  ⑨ **부기 대상이 선언 괄호 밖 산문에 사는 서식은 이 눈 밖이다**(c261 부기 창
     수리의 선언 한계). 센서스(c261 · 표 부기 선언 70행 전수) 반례 1행 = c168
     («표 부기 1건(2세션)» — 대상 A-156.1이 뒤 산문에). 그 서식의 재생은 «판정
     불가» 질의로 뜬다 — 침묵이 아니라 손 판정 요청이다.

㉵ⓐ 규칙 — 취소선 동결 행 질의 제외 (c251 집행, audit-250 R2 소비 = «깨진 계기의
자기 수리» 재분류 · 선례 c232 계약 수리·c241 이동기 ㉵ⓑ):
  해소 행은 보존되고 이동기 ㉵ⓑ(c241)가 그 경과 칸을 동결하므로, 동결 행은 diff에
  없는 것이 **정상**이다. 그런데 «행이 없다» 질의에는 그 구별이 없어 A-192.1 거짓
  양성이 c237~c250 **14연속** 났다(기전 = 한계 ① 부기 창 과수집이 이동기 서술
  «A-192.1 재증분 0»을 부기 대상으로 오독 → 동결 행이라 diff 부재 → 질의).
  규칙: 부기 대상이 정본의 취소선 동결 행이면 «행이 없다» 축의 질의를 **제외**하고
  노트만 남긴다. frame_only 질의(= 동결 행의 재증분 = ⓑ 승계 실패)는 **유지**한다 —
  그 채널이 이동기 스킵 분기의 사망 검출기다. 판정 채널 = 집행 차기 ㉭ 런의
  A-192.1 질의 소멸(질의가 계속 나오면 이 수리는 반증이다).

부기 창 규칙 — 선언 괄호 경계 (c261 집행, audit-260 R2 소비 = «깨진 devloop 소유
계기의 자기 수리» 넷째 선례 · c232 계약 수리·c241 ㉵ⓑ·c251 ㉵ⓐ):
  구판 부기 창(«표 부기 N» 뒤 고정 400자)이 무관 산문의 ID를 과수집했다 — 취소선
  스킵 서술 «A-192.1 재증분 0»(㉵ⓐ가 흡수한 잠재 계열 c257~c260) · 이동기 합류
  서술 «A-255.1 합류 31→32»(c256 거짓 양성) · «A-245.1 편입 +1» 이형(c247 거짓
  양성). 수리 = 창을 **선언 직후 균형 괄호군**으로 한정 + «표 부기 0»은 무수집.
  어휘 마스킹(개별 서술 패턴 제거)이 아니라 구조 경계라 이형 어휘까지 함께 죽는다.
  센서스(c261 원장 전수 70행): 진성 ID 대상 12행 전부 괄호 안 적중 · 구판과의 차이
  47행 전부 노이즈 제거 방향 · 반례 c168 1행(한계 ⑨로 강등). 불균형·부재 괄호는
  무수집(과수집보다 «판정 불가» 질의가 안전한 방향). 판정 채널 = 차기 ㉭ 런들의
  A-192.1 ㉵ⓐ 제외 노트 소멸 + 과수집발 질의 재발 0(재발 = 반증 · predictions
  무등록 — R2 소비 문면이 등록 대체[c241·c251 선례]).

대조군 실측 (c189 등록 시점, 원칙 1):
  c185 = **질의 1건**(A-168.1 부기 선언 · 정본은 프레임 이동뿐) ← **관측 116 독립 재검출**
  c186 · c187 · c188 = **질의 0건**(부기 착지 확인분) — 참 음성 3/3.
  즉 이 계기는 기지 결함 1건을 재현하고 정직한 3사이클에 침묵했다. 예방 효능은 미측정이며
  **P65**가 잰다.

probe_guard 채택 — 폴백 없음, 없는 것은 죽는다.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_guard import need_nonempty  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "research" / "devloop" / "metrics.jsonl"
CANON = "research/devloop/gate-queue.md"

CLAIM_ID = re.compile(r"A-\d{1,4}\.\d{1,3}")
# 무-ID 부기 대상 표기 (한계 ① c261 보강). census: «서열 1′» 서식 30행.
SEQ_TARGET = re.compile(r"서열\s*\d+[′″‴⁗']*")
# 한계 ② — 경과 서식. census(c189 실측): 큐 표의 경과 칸은 «N사이클째» 단일 서식이다.
AGE = re.compile(r"\d{1,4}\s*사이클째")
FRAME = re.compile(r"프레임\s*N\s*=\s*\d{1,4}")

DECL = {
    "신규 상신": re.compile(r"신규 상신\s*\**\s*(\d{1,3})"),
    "해소": re.compile(r"해소\s*\**\s*(\d{1,3})"),
    "표 부기": re.compile(r"표 부기\s*\**\s*(\d{1,3})"),
    "서열 변동": re.compile(r"서열 변동\s*\**\s*(\d{1,3})"),
}


def normalize(row: str) -> str:
    """경과값·프레임을 지운 행. 두 행이 여기서 같으면 **프레임 이동뿐**이다."""
    return FRAME.sub("프레임N", AGE.sub("AGE", row)).strip()


def parse_diff(diff_text: str) -> dict:
    """통합 diff에서 표 행을 뜬다. 판정하지 않고 값만 돌려준다."""
    old: dict[str, str] = {}
    new: dict[str, str] = {}
    for line in diff_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if not line[:1] in ("+", "-"):
            continue
        body = line[1:]
        if not body.lstrip().startswith("|"):
            continue
        m = CLAIM_ID.search(body)
        if not m:
            continue
        (old if line[0] == "-" else new)[m.group(0)] = body

    both = sorted(set(old) & set(new))
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "frame_only": [i for i in both if normalize(old[i]) == normalize(new[i])],
        "substantive": [i for i in both if normalize(old[i]) != normalize(new[i])],
    }


def bogi_window(text: str, decl_end: int) -> str:
    """부기 창 = 선언 직후 균형 괄호군 (c261 수리 — 위 «부기 창 규칙» 참조).
    구판 고정 400자 창의 과수집을 구조 경계로 근절한다. 괄호가 30자 안에
    없거나 400자 안에 닫히지 않으면 무수집 — 그 서식은 «판정 불가» 질의로
    손에 넘어간다(한계 ⑨)."""
    i = text[decl_end:decl_end + 30].find("(")
    if i < 0:
        return ""
    start = decl_end + i
    depth = 0
    for j in range(start, min(len(text), start + 400)):
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
    return ""


def parse_declaration(text: str) -> dict:
    """원장 gate_pending 산문에서 선언 건수와 부기 대상(ID·무-ID 서열)을 뜬다."""
    counts = {}
    for k, rx in DECL.items():
        m = rx.search(text)
        counts[k] = int(m.group(1)) if m else None
    # 부기 대상 — «표 부기 N(...)» 선언 괄호군 안에서만 뽑는다(한계 ①·c261 수리).
    targets: list[str] = []
    seq_targets: list[str] = []
    m = DECL["표 부기"].search(text)
    if m and int(m.group(1)) > 0:
        window = bogi_window(text, m.end())
        targets = list(dict.fromkeys(CLAIM_ID.findall(window)))
        if not targets:
            seq_targets = list(dict.fromkeys(SEQ_TARGET.findall(window)))
    return {"counts": counts, "부기_대상": targets, "무ID_대상": seq_targets}


def frozen_ids(canon_text: str) -> set[str]:
    """정본의 취소선 동결 행 ID 집합 (㉵ⓐ). 술어는 이동기 ㉵ⓑ와 동일:
    행의 마지막 AGE 적중 칸이 `~~`를 포함하면 동결. ID 귀속은 parse_diff와
    같은 규칙(행 첫 CLAIM_ID)이다."""
    out: set[str] = set()
    for line in canon_text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        m = CLAIM_ID.search(line)
        if not m:
            continue
        cells = line.split("|")
        idx = [j for j, c in enumerate(cells) if AGE.search(c)]
        if idx and "~~" in cells[idx[-1]]:
            out.add(m.group(0))
    return out


def build_queries(decl: dict, d: dict, frozen: set[str]) -> tuple[list[str], list[str]]:
    """질의 목록과 ㉵ⓐ 동결-제외 노트. 판정하지 않는다 — 한계 ⑤."""
    q: list[str] = []
    notes: list[str] = []
    c = decl["counts"]
    if c["신규 상신"] is not None and c["신규 상신"] != len(d["added"]):
        q.append(f"신규 상신 선언 {c['신규 상신']} vs 정본 신규 행 {len(d['added'])}")
    if c["해소"] is not None and c["해소"] != len(d["removed"]):
        q.append(f"해소 선언 {c['해소']} vs 정본 소멸 행 {len(d['removed'])}")
    for t in decl["부기_대상"]:
        if t in d["frame_only"]:
            # ㉵ⓐ는 여기를 건드리지 않는다 — 동결 행의 재증분은 ⓑ 승계 실패라 질의 유지.
            q.append(f"**{t} 부기 선언 — 그러나 정본에서 프레임 이동뿐**(관측 116 그 서식)")
        elif t not in d["substantive"] and t not in d["added"]:
            if t in frozen:
                notes.append(f"{t} — 취소선 동결 행: diff 부재 정상(㉵ⓐ 질의 제외)")
            else:
                q.append(f"{t} 부기 선언 — 그러나 정본 diff에 그 행이 없다")
    if c["표 부기"] is not None and c["표 부기"] > 0 and not decl["부기_대상"]:
        if decl.get("무ID_대상"):
            notes.append(
                f"무-ID 부기 대상 {decl['무ID_대상']} — ID 검산 정의역 밖"
                f"(한계 ① c261 보강 · 질의 아님)")
        else:
            q.append(f"표 부기 {c['표 부기']} 선언 — 산문에 대상 ID 표기 없음(한계 ①, 판정 불가)")
    return q, notes


def harvest_commit(cycle: int) -> str:
    out = subprocess.run(
        ["git", "log", "--format=%H", "-1", f"--grep=loop(cycle {cycle}):"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return need_nonempty(out, f"c{cycle} 수확 커밋")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", type=int, required=True)
    args = ap.parse_args()
    n = args.cycle

    sha = harvest_commit(n)
    diff = subprocess.run(["git", "show", sha, "--", CANON],
                          cwd=ROOT, capture_output=True, text=True, check=True).stdout
    d = parse_diff(diff)

    rows = [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]
    row = next((r for r in rows if r["cycle"] == n), None)
    if row is None:
        raise SystemExit(f"원장에 c{n} 행이 없다 — 선언 없이 diff만 있는 사이클은 이 계기 밖")
    decl = parse_declaration(str(row.get("gate_pending", "")))
    frozen = frozen_ids((ROOT / CANON).read_text(encoding="utf-8"))

    print(f"[계기 큐 ㉭ — 선언∖정본-diff 검산 (관측 116 수용 기준 ③)]  c{n} · {sha[:7]}")
    print(f"  선언(원장 gate_pending): {decl['counts']} · 부기 대상 {decl['부기_대상'] or '—'}"
          f" · 무-ID {decl['무ID_대상'] or '—'}")
    print(f"  정본 diff({CANON}):")
    print(f"    신규 행 {len(d['added'])} {d['added'] or ''}")
    print(f"    소멸 행 {len(d['removed'])} {d['removed'] or ''}")
    print(f"    **프레임 이동뿐** {len(d['frame_only'])}행")
    print(f"    **실질 편집** {len(d['substantive'])} {d['substantive'] or ''}")
    print()

    q, notes = build_queries(decl, d, frozen)
    for x in notes:
        # 노트는 두 갈래다(㉵ⓐ 동결 제외 · 무-ID 정의역-밖) — 본문이 자기 분류를
        # 들고 있으므로 접두는 중립으로 인쇄한다(관측 94: 갈린 분류에 한 도장 금지).
        print(f"  노트: {x}")

    if q:
        print(f"  **질의 {len(q)}건** — 고발이 아니다. 손이 답하고 원장에 적는다(한계 ⑤).")
        for x in q:
            print(f"    · {x}")
    else:
        print("  질의 0건 — 선언과 정본이 일치한다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
