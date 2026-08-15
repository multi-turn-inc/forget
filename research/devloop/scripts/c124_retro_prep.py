#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""c124 — 회고 c125 사전 재료 추출기 (프로그램 재도출본)

목적
----
회고 사이클의 입력은 헌장이 정한 넷이다: 지표 추세 · 마찰 분류 · 감사 결과 ·
예측 대차대조 (LOOP.md "개선 절차"). c125가 이 넷을 **직전 사이클 요약문에서
전사(轉寫)하지 않고 원본에서 재도출**할 수 있도록, 이 계기가 셋을 인쇄한다
(감사 결과는 audits/ 정독 몫이라 여기서는 목록·미처분 권고 열거까지만).

계수 규칙 발행 의무 (c123 신규 R9)
---------------------------------
"원장에 계수를 적는 사이클은 그 계수의 규칙을 계기에 성문화한다."
c122의 무번호 24 vs c123의 25는 어느 쪽이 틀린 게 아니라 **규칙이 없어 대조가
원리적으로 불가능**했다. 그래서 아래 세 절의 계수는 모두 규칙을 함께 인쇄한다.

필드 직독으로의 전환 (c127, 관측 71 수용 기준 ③)
------------------------------------------------
**v1·v2 두 추측 규칙은 대차대조의 산출 경로에서 폐기됐다.** c127이 41건 전수에
`- 상태:` 필드를 소급 부여했으므로(`c127_assign_status.py`가 부여 표 = 감사 원본),
대차대조는 이제 **필드를 직독**한다 — 추측이 없으므로 미감사도 없다.

v1·v2는 **역사 계기로만** 남는다: §1-B의 폐기 정산(전수 오류율)을 한 번 내기
위해서다. c124는 불일치 17건만 손 판정하고 일치 24건을 미감사로 남겨 오류율을
**하한**(v1 ≥ 34.1% · v2 ≥ 19.5%)으로만 공표할 수 있었다. 이제 41/41이 감사됐으므로
그 하한이 실제로 얼마나 하한이었는지가 계산 가능하다. 이 정산 이후 v1·v2를 산출
경로로 되살리지 말 것 — 되살리면 관측 71이 다시 열린다.

거짓 양성 회피 (c123 관측 63 상속 금지 — 역사 계기 v1/v2에만 해당)
-----------------------------------------------------------------
관측 63은 처분 판정을 격발어 존재만으로 내려 부정문("…로 닫지 않는다")을
처분으로 오독한 사고다. v1/v2는 그 기전을 상속하지 않으려 표지 줄 한정·SPLIT
보류·시계 강등을 뒀으나, **그 방어로도 부족했다는 것이 관측 71의 실측**이다.

사용: .venv/bin/python research/devloop/scripts/c124_retro_prep.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEVLOOP = ROOT / "research" / "devloop"
PRED = DEVLOOP / "predictions.md"
FRIC = DEVLOOP / "frictions.md"
LEDGER = DEVLOOP / "metrics.jsonl"
AUDITS = DEVLOOP / "audits"
AMENDS = DEVLOOP / "amendments"

# ── 계수 규칙 (성문) ────────────────────────────────────────────────────────
def rule_pred(n_sec: int, n_row: int, n_total: int, n_arm: int, n_missing: int) -> str:
    """계수 규칙 발행문 — **분모는 전부 계산값이다** (c128 개정, 관측 73 재발 2호의 처치).

    왜 함수가 됐는가: c127이 이 규칙을 문자열 상수로 발행하면서 분모를 손으로 박았고,
    `절 41건`은 우연히 맞았지만 `팔 96건`은 그 시점 실계산 **90**과 갈렸다(c128 실측,
    도입 커밋 b7be3f5 = 관측 73을 등재한 바로 그 커밋). 관측 73이 명명한 기전
    — *발행은 규칙을 보이게 할 뿐이고 규칙과 구현의 일치는 별도 검산이 필요하다* —
    가 **관측 73을 등재하는 문단 옆에서 그대로 재발**한 것이다.

    상수를 고쳐 96→95로 맞추는 것은 처치가 아니다. 다음 배정 한 번이면 다시 갈린다.
    분모를 인쇄하는 유일한 경로를 실계산으로 묶어 **표류 자체를 불가능하게** 한다.
    """
    return f"""[계수 규칙 — 예측 (c127 개정: 추측 → 필드 직독 / c128 개정: 분모 = 계산값)]
  단위    = P-식별자 1개. 서식지 둘: (H1) 상단 표의 `| Pn |` 행(상태 열),
            (H2) `## Pn — …` 절(헤딩 직후 `- 상태:` 줄).
            **총 {n_total} = 절 {n_sec} + 표행 {n_row}** ← 이 줄의 수는 전부 실계산이다.
  중복    = `P7`은 번호 충돌로 절이 2개다(회계 / reembed). 둘 다 독립 단위로 센다 —
            분모에서 빼지 않으며 개명(P7-2)은 c35 사람 게이트.
  상태    = **절의 `- 상태:` 필드를 그대로 읽는다.** 산문 추론·격발어 매칭 없음.
            필드가 없으면 그것이 곧 결함이며 MISSING으로 인쇄하고 분모에 남긴다
            (숨기지 않는다). 현재 MISSING {n_missing}건{' = 전수 감사 가능' if n_missing == 0 else ' — 전수 감사 불가'}.
  팔      = `(a) X · (b) Y` 는 팔별 값, 값 하나면 전 팔 동일. 팔은 개별 계상하되
            **절 단위 계수와 팔 단위 계수를 갈라 인쇄**한다(합산 금지 — 절 {n_total}건과
            팔 {n_arm}개는 다른 분모다).
  어휘    = amendment-125 §4-R10 11값 + 하자 `무기재` + c127 전수 배정이 발견한 2값
            (`비예측`·`마감-미가동`, 사유는 c127_assign_status.py 헤더)
            + c136 집행분(amendment-135 §4-R10): `마감-조기(지지/반증)` 방향 병기
            의무(방향 없는 `마감-조기`는 하드 에러) · `수반((형제팔))`은 독립 증거를
            담지 않으므로 지지/반증 계수 밖 별도 칸.
            어휘 밖 값은 하드 에러 — 조용히 삼키면 관측 71이 값 칸으로 재발한다.
  [분모 구성 — 관측 73 수용 기준 ② 이행] 아래 `id/line/상태` 표가 분모의 전수 열거다.
            산문이 인용하는 수는 그 표의 행 수({n_total})와 대조 가능해야 한다."""

RULE_FRIC = """[계수 규칙 — 마찰/관측]
  단위    = frictions.md의 `^## ` 헤딩 1개(= 1절).
  분류    = 헤딩 문자열만 본다(본문 미열람 — 이 계기는 처분 판정을 하지 않는다).
            NUMBERED  : `관측 <숫자>` 가 있고 `보강` 이 없음
            REINFORCE : `보강` 포함 (신규 번호 아님 — 분모 무영향)
            UNNUMBERED: `미분류 관측` 인데 숫자 없음
            F_SERIES  : `F<숫자>` 로 시작하는 대장/절
            OTHER     : 나머지
  재발    = 헤딩에 `재발` 또는 `n=<숫자>` 포함 여부(헤딩 자기 신고 기준).
  주의    = 이 계수는 **재고(미해소 수)가 아니다.** 재고는 c123이 정독으로
            48~57 범위를 냈고, 그 시점 원장의 open_observations는 자동 36으로 범위 하단이었다.
            **48~57과 36은 둘 다 c123 빈티지 상수다**(c128 표기 수리 — 종전 문면은 36을
            현재형 "원장의 open_observations(자동 36)"로 적어 현재값처럼 읽혔다. 실제
            현재값은 이 계기가 아니라 `c48_step0_check.py` 파트 F가 낸다). 빈티지를
            현재값으로 읽으면 그것이 관측 34(대조군 라벨의 만료)의 다음 표본이다."""

RULE_METRIC = """[계수 규칙 — 지표 추세]
  단위    = metrics.jsonl 한 행 = 한 사이클. 창 = 10사이클 고정 폭.
  결측    = 필드가 없는 행은 그 필드의 분모에서 제외하고 n을 병기(0으로 채우지 않음).
  tests   = 문자열에서 `^(\\d+) passed` 를 뽑아 정수화. 실패 서술은 None으로 두고 별도 열거."""

SUP = ("성립", "적중", "지지", "확정", "인정")
REF = ("반증", "기각", "불성립")
DIS = ("폐기", "표본 부재", "마감")

MARK_RE = re.compile(r"^-\s*\*{0,2}(결과|판정|처분)")
CLOCK_RE = re.compile(r"^-\s*\*{0,2}시계")

# ── 규칙 v2 (c124 신설) — 표지 줄의 다의성 처치 ─────────────────────────────
# 이 대장에서 `- 판정:` 은 **두 가지**를 라벨한다: (α) 등록 시 판정 **기준**
# ("각 처치 배선 후 +5사이클. 양방향 반증 가능") 과 (β) 사후 판정 **결과**
# ("**판정 (c76, 2026-08-08)**: 적중"). v1은 둘을 구분하지 않아 (α)의
# "양방향 **반증** 가능"·"…이면 **반증**으로 계상" 같은 **조건절의 격발어**를
# 결과로 읽는다 — 관측 63과 같은 계열의 거짓 양성이며, 서식지만 다르다.
# 판별자: 결과 줄은 **판정 시점 도장**(사이클 N / cN / 날짜)을 달고 있다.
#         조항 줄(`처분 조항`·`판정 조항`·`판정 시한`)은 미래 조건이므로 제외.
STAMP_RE = re.compile(r"\(\s*(?:사이클\s*\d+|c\d+|\d{4}-\d{2}-\d{2})")
CLAUSE_RE = re.compile(r"^-\s*\*{0,2}(처분 조항|판정 조항|판정 시한|판정 채널)")


def _is_verdict_line(s: str) -> bool:
    """v2: 표지 줄이 '판정 결과'를 담는가 (기준 선언·조항이 아니라)."""
    if CLAUSE_RE.match(s):
        return False
    return bool(STAMP_RE.search(s))
PSEC_RE = re.compile(r"^##\s+(P\d+[a-z]?)\s*[—-]")
PROW_RE = re.compile(r"^\|\s*(P\d+[a-z]?)\s*\|")


# ── 손 판정 (c124, v1↔v2 불일치 17건 전수) ─────────────────────────────────
# 규칙: 각 절의 표지 줄 전문을 읽고 "이 예측의 실제 처분"을 정한 뒤, v1·v2가
# 그것을 맞혔는지 채점한다. **불일치 집합만** 판정했다 — 두 규칙이 일치하는
# 24건은 미감사이며, 따라서 아래 오류율은 전수가 아니라 **하한**이다.
# 값 = (실제 처분, v1 정오, v2 정오). 'BOTH_WRONG'은 어느 규칙도 못 맞힌 것.
ADJUDICATED: dict[str, tuple[str, bool, bool]] = {
    "P3b": ("CLOCK_UNSTARTED", False, True),
    "P5":  ("CLOCK_UNSTARTED", False, True),
    "P6":  ("CLOCK_UNSTARTED", False, True),
    "P11": ("CLOCK_UNSTARTED", False, True),
    "P27": ("CLOCK_UNSTARTED", False, True),
    "P12": ("CLOCK_RUNNING", False, True),
    "P25": ("UNRESOLVED(판정줄 부재)", False, True),
    "P36": ("PENDING(달력 시계 09-10)", False, True),
    "P37": ("PENDING→외부 판정(커밋 4ed88f1, 대장 미반영)", False, True),
    # v1이 맞고 v2가 틀린 것 — 도장 없는 진짜 처분 줄을 v2가 버렸다
    "P26": ("DISCARDED(기한 도과 강제 마감)", True, False),
    "P29": ("DISCARDED(표본 2로 마감)", True, False),
    "P8":  ("PARTIAL(문면 성립·처치 귀속 불가)", True, False),
    # 둘 다 틀린 것 — 어휘에 없는 상태이거나, 도장 없는 처분 줄
    "P10": ("전제 소멸(예측 자체가 무효화)", False, False),
    "P18": ("DISCARDED(처분=폐기, 무도장)", False, False),
    "P28": ("DISCARDED(표본 1로 마감, 무도장)", False, False),
    "P33": ("무판정 마감(지지도 반증도 아님)", False, False),
    # 어느 쪽도 단독으로 옳다고 하기 어려운 것
    "P30": ("혼합(예측 존속 + (a) 표본 부재 마감)", False, False),
}

# 어휘 밖 상태 — 두 규칙 다 원리적으로 표현할 수 없는 처분들 (c124 발견, R10이 흡수)
VOCAB_GAP = ["무판정 마감(P33)", "표본 부재 마감(P30)", "전제 소멸(P10)",
             "문면 성립·귀속 불가(P8)"]

# ── 처분 어휘 (c127 / c136 개정) ────────────────────────────────────────────
# amendment-125 §4-R10의 11값 + 하자 라벨 1 + c127 전수 배정 발견분 2
# + c136 집행분(amendment-135 §4-R10): 조기 마감은 판정을 낸 사건이므로 방향을
# 의무 병기하고(`마감-조기(지지/반증)`), 형제 팔 판정에 논리적으로 수반되어 독립
# 증거를 담지 않는 팔은 `수반((형제팔))`로 지지/반증 계수 밖 별도 칸에 센다.
# 방향 없는 `마감-조기`와 수반 대상 없는 `수반`은 어휘 밖 값(하드 에러)이다.
VOCAB_R10 = ("지지", "반증", "부분", "시계-미시작", "시계-가동", "마감-표본부재",
             "마감-무판정", "마감-기한도과", "전제소멸", "폐기")
VOCAB_DEFECT = ("무기재",)
VOCAB_C127 = ("비예측", "마감-미가동")
VOCAB_C136 = ("마감-조기(지지)", "마감-조기(반증)", "수반")
VOCAB = VOCAB_R10 + VOCAB_DEFECT + VOCAB_C127 + VOCAB_C136

# 수반 팔 서식: `(b) 수반((a))` — 어느 팔에 수반되는지 병기 의무.
SUBSUME_RE = re.compile(r"^수반\(\([a-z]\)\)$")


def _vocab_key(val: str) -> str:
    """계수용 어휘 키 — `수반((a))`류는 `수반` 한 칸으로 모은다. 그 외 원문 그대로."""
    return "수반" if SUBSUME_RE.match(val) else val


def _r10_base(val: str) -> str:
    """방향/수반-대상 괄호를 벗긴 밑값 — c124 손 자[尺]와의 대조 전용.

    손 판정(c124)은 방향 무기록 어휘로 쟀으므로(`DISCARDED(표본 N로 마감)` →
    `마감-조기`), c136 방향 병기 이후의 필드와 대조하려면 밑값으로 내려야 한다.
    산출 경로에는 쓰지 않는다 — 대차대조 계수는 방향을 산 채로 센다.
    """
    if val.startswith("마감-조기("):
        return "마감-조기"
    return _vocab_key(val)

STATUS_RE = re.compile(r"^-\s*상태:\s*(.+?)\s*$")
ARM_RE = re.compile(r"^\((?P<arm>[a-z]|비)\)\s*(?P<val>.+)$")

# c124 손 판정 17건의 값을 R10 어휘로 사상 — 대조는 같은 자로 재야 성립한다.
# (c124는 자기 파서의 라벨을 썼고 R10 어휘는 c125에 생겼다.)
HAND_TO_R10 = {
    "CLOCK_UNSTARTED": "시계-미시작",
    "CLOCK_RUNNING": "시계-가동",
    "UNRESOLVED(판정줄 부재)": "무기재",
    "PENDING(달력 시계 09-10)": "시계-가동",
    "PENDING→외부 판정(커밋 4ed88f1, 대장 미반영)": "무기재",
    "DISCARDED(기한 도과 강제 마감)": "마감-기한도과",
    "DISCARDED(표본 2로 마감)": "마감-조기",
    "DISCARDED(표본 1로 마감, 무도장)": "마감-조기",
    "DISCARDED(처분=폐기, 무도장)": "폐기",
    "PARTIAL(문면 성립·처치 귀속 불가)": "부분",
    "전제 소멸(예측 자체가 무효화)": "전제소멸",
    "무판정 마감(지지도 반증도 아님)": "마감-무판정",
    "혼합(예측 존속 + (a) 표본 부재 마감)": "마감-표본부재",
}

# v1/v2(역사 계기)의 라벨 → R10 어휘. SPLIT·MARK_NO_TOKEN은 값을 내지 못하므로 사상 없음
# (= 어떤 필드와도 일치하지 않는다. 이 규칙을 인쇄해 채점 기준을 노출한다).
GUESS_TO_R10 = {
    "SUPPORTED": "지지", "REFUTED": "반증", "DISCARDED": "폐기",
    "CLOCK_UNSTARTED": "시계-미시작", "CLOCK_RUNNING": "시계-가동",
    "UNRESOLVED": "무기재",
}


def parse_status(raw: str) -> tuple[list[tuple[str, str]], list[str]]:
    """`- 상태:` 원문 → ([(팔, 값)], 오류). 팔 없으면 팔 이름은 '-'."""
    body = raw.replace("`", "").strip()
    parts = [p.strip() for p in body.split("·") if p.strip()]
    arms: list[tuple[str, str]] = []
    errs: list[str] = []
    for p in parts:
        m = ARM_RE.match(p)
        arm, val = (m.group("arm"), m.group("val").strip()) if m else ("-", p)
        if val == "마감-조기":
            errs.append("어휘 밖 값 '마감-조기' — 방향 병기 의무 위반"
                        "(c136 강등, amendment-135 §4-R10: 마감-조기(지지/반증))")
        elif val == "수반":
            errs.append("어휘 밖 값 '수반' — 수반 대상 병기 의무 위반(서식: 수반((a)))")
        elif _vocab_key(val) not in VOCAB:
            errs.append(f"어휘 밖 값 {val!r}")
        arms.append((arm, val))
    if len(arms) > 1 and any(a == "-" for a, _ in arms):
        errs.append("팔이 둘 이상인데 라벨 없는 값이 섞였다")
    return arms, errs


def _read(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


# ── 1. 예측 대차대조 ────────────────────────────────────────────────────────
def predictions() -> dict:
    lines = _read(PRED)
    # 절 경계
    sections: list[tuple[str, int, int]] = []
    starts = [(i, m.group(1)) for i, l in enumerate(lines) if (m := PSEC_RE.match(l))]
    for k, (i, pid) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        # 다음 `## ` 헤딩(P가 아닌 것 포함)에서도 끊는다
        for j in range(i + 1, end):
            if lines[j].startswith("## "):
                end = j
                break
        sections.append((pid, i, end))

    # 표 서식지는 **등록 표 하나뿐**이다 — 첫 `## ` 헤딩 이전 구간.
    # (c127 수리: 종전 규칙은 문서 전체의 `| Pn |` 행을 훑어 「게이트 종속 상태표」
    #  (c45 스냅샷 부기)의 `| P2 |` 행까지 등록으로 셌다. 그 결과 계기는 42건을
    #  열거하는데 c124 산문과 공표 백분율은 전부 41을 분모로 썼고, 셋 다 어긋난 채
    #  c124→c126 3사이클을 갔다. 스냅샷은 등록이 아니므로 41이 옳다 —
    #  즉 틀린 것은 산문이 아니라 계기였고, R9가 막으려던 바로 그 형태다.)
    first_head = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    table_only = []
    seen_sec = {pid for pid, _, _ in sections}
    for i, l in enumerate(lines[:first_head]):
        m = PROW_RE.match(l)
        if m and m.group(1) not in seen_sec:
            table_only.append((m.group(1), i))

    dup = [pid for pid, c in Counter(p for p, _, _ in sections).items() if c > 1]

    def _classify(marks: list[str], clocks: list[str]) -> str:
        blob = " ".join(marks)
        flags = [any(t in blob for t in SUP), any(t in blob for t in REF),
                 any(t in blob for t in DIS)]
        if marks:
            if sum(flags) > 1:
                return "SPLIT"
            if flags[0]:
                return "SUPPORTED"
            if flags[1]:
                return "REFUTED"
            if flags[2]:
                return "DISCARDED"
            return "MARK_NO_TOKEN"
        if clocks:
            cb = " ".join(clocks)
            return "CLOCK_UNSTARTED" if ("미시작" in cb or "미가동" in cb) else "CLOCK_RUNNING"
        return "UNRESOLVED"

    recs = []
    for pid, s, e in sections:
        body = lines[s:e]
        # ── 정본 경로: `- 상태:` 필드 직독 (c127) ──────────────────────
        field = next((m.group(1) for l in body if (m := STATUS_RE.match(l.strip()))), None)
        arms, errs = parse_status(field) if field is not None else ([], ["필드 부재"])
        # ── 역사 경로: v1/v2 (폐기 정산 전용, 산출에 쓰지 않는다) ──────
        marks = [l.strip() for l in body if MARK_RE.match(l.strip())]
        clocks = [l.strip() for l in body if CLOCK_RE.match(l.strip())]
        v_marks = [l for l in marks if _is_verdict_line(l)]
        recs.append({"id": pid, "line": s + 1, "habitat": "절",
                     "field": field, "arms": arms, "errs": errs,
                     "status": _classify(marks, clocks),
                     "status2": _classify(v_marks, clocks),
                     "title": lines[s].lstrip("# ").strip()[:90]})

    for pid, i in table_only:
        cell = lines[i].split("|")
        field = cell[-2].strip() if len(cell) >= 3 else ""
        last = cell[-3].strip() if len(cell) >= 4 else ""
        arms, errs = parse_status(field) if field else ([], ["필드 부재"])
        has_sup, has_ref = (any(t in last for t in SUP), any(t in last for t in REF))
        guess = ("SPLIT" if has_sup and has_ref else "REFUTED" if has_ref
                 else "SUPPORTED" if has_sup else
                 "CLOCK_RUNNING" if "대기" in last else "UNRESOLVED")
        recs.append({"id": pid, "line": i + 1, "habitat": "표행",
                     "field": field, "arms": arms, "errs": errs,
                     "status": guess, "status2": guess, "title": "(표행 단독)"})

    recs.sort(key=lambda r: (int(re.sub(r"\D", "", r["id"]) or 0), r["id"], r["line"]))
    arm_counts = Counter(_vocab_key(v) for r in recs for _, v in r["arms"])
    return {"records": recs, "duplicates": dup,
            "arm_counts": arm_counts,
            "missing": [r for r in recs if r["field"] is None or not r["field"]],
            "errors": [(r["id"], r["errs"]) for r in recs if r["errs"]],
            "counts": Counter(r["status"] for r in recs),
            "counts2": Counter(r["status2"] for r in recs),
            "disagree": [r for r in recs if r["status"] != r["status2"]]}


def _armset(rec: dict) -> set[str]:
    return {v for _, v in rec["arms"]}


def reconcile(p: dict) -> dict:
    """대조 2종. **채점 규칙을 값과 함께 인쇄한다** — 규칙 없는 일치율은 비교 불가.

    포함 기준 = 상대의 단일 값이 소급 부여된 **팔별 값 집합에 포함**되면 일치.
      (상대는 절 하나에 값 하나를 매겼고 c127은 팔별로 매겼으므로, 다중 팔 절에서
       완전일치를 요구하면 서식 차이가 전부 불일치로 계상돼 대조가 무의미해진다.)
    완전일치 기준 = 절의 상태가 **단일 값**이고 그 값이 상대와 같을 때만 일치.
      (엄격 하한. 다중 팔 절은 정의상 전부 불일치이므로 이 수는 서식 차를 포함한다.)
    """
    by_id: dict[str, dict] = {}
    for r in p["records"]:
        by_id.setdefault(r["id"], r)          # P7 중복은 첫 절(회계)을 대표로

    hand = []
    for pid, (truth, _, _) in ADJUDICATED.items():
        rec = by_id.get(pid)
        mapped = HAND_TO_R10.get(truth)
        # 손 자[尺](c124)는 방향 무기록이므로 밑값으로 대조한다(c136 방향 병기 이후).
        aset = {_r10_base(v) for v in _armset(rec)} if rec else set()
        hand.append({"id": pid, "hand": truth, "mapped": mapped,
                     "field": rec["field"] if rec else None,
                     "incl": mapped in aset,
                     "exact": len(aset) == 1 and mapped in aset})

    # v1/v2가 **원리상 낼 수 없는** 값만 참인 절 = 어휘 불가능.
    # 이 분해가 없으면 "파서가 83% 틀렸다"가 과잉 주장이 된다 —
    # 그중 일부는 파싱이 아니라 어휘에 그 칸이 없어서 틀린 것이다(관측 71 기전 ③).
    reachable = set(GUESS_TO_R10.values())
    guess = []
    for r in p["records"]:
        aset = _armset(r)
        guess.append({"id": r["id"], "line": r["line"],
                      "v1": r["status"], "v2": r["status2"],
                      "v1_ok": GUESS_TO_R10.get(r["status"]) in aset,
                      "v2_ok": GUESS_TO_R10.get(r["status2"]) in aset,
                      "impossible": not (aset & reachable)})
    return {"hand": hand, "guess": guess}


# ── 달력 산식 (c136 수리, 관측 78) ──────────────────────────────────────────
# 정본은 지시서 절차 1의 분기 순서다: N%10==0 → 감사가 N%5==0(회고)에 **우선**한다.
# 구 산식(((nxt//5)+1)*5 if nxt%5 else nxt)은 이 선행 규칙을 몰라 10의 배수를
# 회고로 인쇄했고(nxt=126~129 → "다음 회고 = c130"(감사), 재발 주기 10사이클),
# `다음 감사` 팔은 nxt 자신이 10의 배수일 때 자기를 건너뛰었다. 이 함수들이
# 달력의 유일한 산출 경로다 — 인쇄 지점에 산식을 다시 쓰지 말 것(관측 78).
def next_audit(n: int) -> int:
    """n 포함, 10의 배수 최소값."""
    return n if n % 10 == 0 else ((n // 10) + 1) * 10


def next_retro(n: int) -> int:
    """n 포함, 5의 배수이되 10의 배수가 아닌 최소값 — 감사 선행 규칙 반영."""
    m = n if n % 5 == 0 else ((n // 5) + 1) * 5
    return m + 5 if m % 10 == 0 else m


# ── 2. 마찰/관측 헤딩 계수 ──────────────────────────────────────────────────
def frictions() -> dict:
    heads = [(i + 1, l) for i, l in enumerate(_read(FRIC)) if l.startswith("## ")]
    buckets: dict[str, list] = defaultdict(list)
    recur = []
    for ln, h in heads:
        t = h[3:].strip()
        if "보강" in t:
            kind = "REINFORCE"
        elif re.search(r"관측\s*\d+", t):
            kind = "NUMBERED"
        elif "미분류 관측" in t:
            kind = "UNNUMBERED"
        elif re.match(r"F\d+", t):
            kind = "F_SERIES"
        else:
            kind = "OTHER"
        buckets[kind].append((ln, t))
        if "재발" in t or re.search(r"n=\d+", t):
            recur.append((ln, kind, t[:100]))
    return {"buckets": buckets, "recurrences": recur,
            "counts": {k: len(v) for k, v in sorted(buckets.items())}}


# ── 3. 지표 추세 ────────────────────────────────────────────────────────────
def ledger() -> dict:
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows.sort(key=lambda r: r["cycle"])
    out = []
    lo = 0
    while lo <= rows[-1]["cycle"]:
        hi = lo + 9
        w = [r for r in rows if lo <= r["cycle"] <= hi]
        if w:
            rt = [r["restore_turns"] for r in w if isinstance(r.get("restore_turns"), (int, float))]
            gr = Counter(r.get("restore_grade") for r in w)
            hits = sum(r.get("recall_hits", 0) or 0 for r in w)
            miss = sum(r.get("recall_misses", 0) or 0 for r in w)
            fl = sum(r.get("frictions_logged", 0) or 0 for r in w)
            ff = sum(r.get("frictions_fixed", 0) or 0 for r in w)
            tp = []
            fails = []
            for r in w:
                m = re.match(r"(\d+)\s+passed", str(r.get("tests", "")))
                if m:
                    tp.append(int(m.group(1)))
                else:
                    fails.append((r["cycle"], str(r.get("tests"))[:60]))
            out.append({"window": f"c{lo}-c{hi}", "n": len(w),
                        "rt_n": len(rt), "rt_mean": (sum(rt) / len(rt)) if rt else None,
                        "rt_max": max(rt) if rt else None,
                        "grades": dict(gr), "hits": hits, "misses": miss,
                        "fl": fl, "ff": ff,
                        "tests_min": min(tp) if tp else None,
                        "tests_max": max(tp) if tp else None,
                        "tests_nonnum": fails})
        lo += 10
    oo = [(r["cycle"], r["open_observations"]) for r in rows if "open_observations" in r]
    pcu = [(r["cycle"], r["product_code_unchanged_streak"]) for r in rows
           if "product_code_unchanged_streak" in r]
    return {"windows": out, "open_obs": oo, "pcu": pcu, "rows": rows}


def main() -> int:
    print("=" * 78)
    print("c124 — 회고 c125 사전 재료 (프로그램 재도출 / 전사 금지)")
    print("=" * 78)

    # 1
    p = predictions()
    n = len(p["records"])
    n_arm = sum(len(r["arms"]) for r in p["records"])
    n_sec = sum(1 for r in p["records"] if r["habitat"] == "절")
    n_row = n - n_sec
    # 규칙 발행은 계수 **뒤에** 온다 — 발행문의 분모가 실계산이어야 하므로(c128).
    print("\n" + rule_pred(n_sec, n_row, n, n_arm, len(p["missing"])))
    print(f"\n[1] 예측 대차대조 — 절·표행 {n}건 / 팔 {n_arm}개 (필드 직독)")
    if p["duplicates"]:
        print(f"    !! DUPLICATE 식별자: {p['duplicates']}  (개명 패킷 게이트 대기 항목과 대조할 것)")

    # ── 1-A. 전수 감사 가능성 (수용 기준 ③의 판정 지점) ─────────────────
    print(f"\n    [전수 감사] 필드 부재 {len(p['missing'])}건 · 어휘/서식 오류 {len(p['errors'])}건")
    for pid, errs in p["errors"]:
        print(f"      !! {pid}: {errs}")
    for r in p["missing"]:
        print(f"      !! {r['id']} (L{r['line']}) 필드 부재")
    if not p["missing"] and not p["errors"]:
        print(f"      → **미감사 0건** — {n}/{n} 전수가 값을 갖고 전부 어휘 안이다.")

    print(f"\n    [절 단위 {n}건]                      [팔 단위 {n_arm}개]")
    sec_counts = Counter(v for r in p["records"] for v in {_vocab_key(x) for x in _armset(r)})
    for k in VOCAB:
        s, a = sec_counts.get(k, 0), p["arm_counts"].get(k, 0)
        if s or a:
            tag = ("  ← c136 개정(R10)" if k in VOCAB_C136 else
                   "  ← c127 신설" if k in VOCAB_C127 else
                   "  ← 하자" if k in VOCAB_DEFECT else "")
            print(f"    {k:14s} 절 {s:3d}                       팔 {a:3d}{tag}")
    print("    (절 계수는 그 절에 그 값을 가진 팔이 하나라도 있으면 1 — 다중 팔 절은 여러 칸에 든다.")
    print(f"     따라서 절 계수의 합은 {n}을 넘을 수 있다. 두 분모를 합산하지 말 것.")
    print("     `수반` 팔은 독립 증거를 담지 않으므로 지지/반증 계수에 넣지 않는다 — 별도 칸이")
    print("     그 자체로 계상이다. 지지/반증 수를 인용하는 산문은 수반 칸을 합산하지 말 것.)")

    print("\n    id      line  상태(필드 직독)")
    for r in p["records"]:
        print(f"    {r['id']:6s} {r['line']:5d}  {r['field']}")

    # ── 1-B. 대조 1 — c124 손 판정 17건 (수용 기준 ②의 공표 지점) ───────
    rc = reconcile(p)
    hand = rc["hand"]
    incl = sum(1 for h in hand if h["incl"])
    exact = sum(1 for h in hand if h["exact"])
    print(f"\n    [대조 1 — c124 손 판정 {len(hand)}건 vs c127 소급 부여]")
    print(reconcile.__doc__.split("\n", 1)[1].rstrip())
    print(f"      포함 기준: 일치 {incl}/{len(hand)} · **불일치 {len(hand)-incl}건**")
    print(f"      완전일치 기준: 일치 {exact}/{len(hand)} · 불일치 {len(hand)-exact}건")
    print("      (수용 기준 ②는 불일치 0을 요구하지 않는다 — 손 판정도 표본 1이다.)")
    print("      불일치 내역 (포함 기준):")
    for h in hand:
        if not h["incl"]:
            print(f"        {h['id']:5s} 손={h['hand']}")
            print(f"              → 사상 {h['mapped']!r} / c127 필드 {h['field']!r}")

    # ── 1-C. 대조 2 — v1·v2 폐기 정산 (역사 계기, 이후 산출 금지) ────────
    g = rc["guess"]
    v1_ok = sum(1 for x in g if x["v1_ok"])
    v2_ok = sum(1 for x in g if x["v2_ok"])
    print(f"\n    [대조 2 — v1·v2 폐기 정산] 전수 {n}건 기준 (c124는 17건만 감사해 하한만 냈다)")
    print(f"      v1 적중 {v1_ok}/{n} → **오류율 {100*(n-v1_ok)/n:.1f}%** (c124 공표 하한 34.1%)")
    print(f"      v2 적중 {v2_ok}/{n} → **오류율 {100*(n-v2_ok)/n:.1f}%** (c124 공표 하한 19.5%)")
    print("      채점 규칙: 사상값(GUESS_TO_R10)이 팔별 값 집합에 포함되면 적중.")
    print("      SPLIT·MARK_NO_TOKEN은 값을 내지 못하므로 정의상 오답이다(규칙 노출).")
    imp = [x["id"] for x in g if x["impossible"]]
    n_par = n - len(imp)
    v1p = sum(1 for x in g if not x["impossible"] and x["v1_ok"])
    v2p = sum(1 for x in g if not x["impossible"] and x["v2_ok"])
    print(f"\n      [오류 분해 — 과잉 주장 방지] 어휘 불가능 {len(imp)}건 {imp}")
    print("        = 참값이 전부 v1/v2 어휘 밖(무기재·비예측·마감-*·부분·전제소멸 등)이라")
    print("          정규식을 어떻게 고쳐도 맞힐 수 없는 절. 관측 71 기전 ③의 크기다.")
    print(f"        어휘 도달 가능 {n_par}건 한정 오류율: v1 {100*(n_par-v1p)/n_par:.1f}%"
          f" · v2 {100*(n_par-v2p)/n_par:.1f}%")
    print("      → 두 수를 함께 읽어야 한다: 전수 오류율은 **어휘 결함을 포함한 총량**이고,")
    print("        도달 가능 한정 오류율이 **파싱 자체의 몫**이다. c124가 '본체는 정규식이")
    print("        아니라 어휘 공백'이라 진단한 것이 이 분해로 수치화됐다.")
    print("      캐비앗(자기 불리 방향 병기): '어휘 불가능'의 정의가 **관대**하다 —")
    print("        다중 팔 절은 팔 하나만 도달 가능해도 가능으로 세지만 v1/v2는 값을 하나만")
    print("        내므로 실제 난도는 더 높다. 즉 도달 가능 한정 오류율은 **상한 쪽으로**")
    print("        치우쳐 있고, 파싱의 책임을 실제보다 크게 잡은 수다.")
    print(f"      → 그리고 하한은 실제보다 낮았다(34.1%→{100*(n-v1_ok)/n:.1f}% ·"
          f" 19.5%→{100*(n-v2_ok)/n:.1f}%). 미감사 24건이 오류를 숨기고 있었음이")
    print("        전수 감사로 확인됐다 — '하한 병기'가 정직 장치였던 이유다.")
    print(f"\n    [어휘 공백] c124가 발견한 4종은 R10이 흡수했고, 전수 배정이 {len(VOCAB_C127)}종을 더 냈다:")
    for v in VOCAB_C127:
        print(f"        - {v} (팔 {p['arm_counts'].get(v, 0)}개)")
    print("      → 관측 71의 '기계 도출 불가'는 **해소**됐다. 도출을 가능하게 한 것은")
    print("        정규식 개량이 아니라 **대장이 자기 상태를 필드로 말하게 한 것**이다.")

    # 2
    f = frictions()
    print("\n" + RULE_FRIC)
    print(f"\n[2] 마찰/관측 헤딩 — 총 {sum(f['counts'].values())}절")
    for k, v in f["counts"].items():
        print(f"    {k:12s} {v:3d}")
    print(f"    재발 자기신고 헤딩 {len(f['recurrences'])}건:")
    for ln, kind, t in f["recurrences"]:
        print(f"      L{ln:5d} {kind:10s} {t}")

    # 3
    g = ledger()
    print("\n" + RULE_METRIC)
    print(f"\n[3] 지표 추세 — {len(g['rows'])}행 (c{g['rows'][0]['cycle']}~c{g['rows'][-1]['cycle']})")
    print("    window     n  rt_mean(n)  rt_max  recall h/m   fric l/f  tests min~max  grades")
    for w in g["windows"]:
        rtm = f"{w['rt_mean']:.2f}({w['rt_n']})" if w["rt_mean"] is not None else "  —  "
        tm = f"{w['tests_min']}~{w['tests_max']}" if w["tests_min"] is not None else "—"
        print(f"    {w['window']:9s} {w['n']:2d}  {rtm:>10s}  {w['rt_max']:>6}  "
              f"{w['hits']:4d}/{w['misses']:<4d}  {w['fl']:3d}/{w['ff']:<3d}  {tm:>12s}  {w['grades']}")
    nonnum = [x for w in g["windows"] for x in w["tests_nonnum"]]
    print(f"    tests 비수치 행 {len(nonnum)}건: {[c for c, _ in nonnum]}")
    print(f"    open_observations 기재 {len(g['open_obs'])}행: {g['open_obs']}")
    print(f"    product_code_unchanged_streak 기재 {len(g['pcu'])}행: 최대 {max(v for _, v in g['pcu'])} "
          f"(c{[c for c, v in g['pcu'] if v == max(x for _, x in g['pcu'])][0]})")

    # 4 감사·개정 목록 (정독 몫은 c125)
    print("\n[4] 감사·개정 문서 재고 (정독은 c125 몫 — 여기서는 존재 열거만)")
    au = sorted(AUDITS.glob("audit-*.md"), key=lambda x: int(re.sub(r"\D", "", x.stem)))
    am = sorted(AMENDS.glob("amendment-*.md"), key=lambda x: int(re.sub(r"\D", "", x.stem)))
    print(f"    audits {len(au)}: {[x.stem for x in au]}")
    print(f"    amendments {len(am)}: {[x.stem for x in am]}")
    nxt = (g["rows"][-1]["cycle"] + 1)
    print(f"    다음 감사 = c{next_audit(nxt)} · 다음 회고 = c{next_retro(nxt)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
