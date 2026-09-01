"""frictions.md 관측별 1줄 인덱스 생성기 — 계기 큐 ㉻ (c272 집행).

기원 = audit-240 R3(감사 소스 정독 불능: frictions.md 1.02MB = Read 캡 256KB의 4배 ·
c240 거부 2회 실측) → c245 회고 설계·상신(amendment-245 §4-ⓐ). 산출은
`research/devloop/frictions-index.md` — **정본 아님 · 재생성 가능** 파생 캐시이며,
머리말에 생성 시각 + 원본 sha256을 강제한다(정본 이중화 금지 — parse_observations
독스트링의 «두 번째 원장은 썩는다» 규율과 충돌하지 않는 이유가 바로 이 머리말이다:
캐시는 정본 지위를 주장하지 않고, 낡음이 sha 대조로 즉시 판별된다).

**감사 소스 사용은 A-245.1 승인 전 금지** — 승인 전 캐시는 비-감사 사이클의 보조
열람만 가능하다(지시서 절차 1 금독 규율 보존, amendment-245 §5).

분류 술어는 c48_step0_check에서 전량 import한다 — 자[尺] 무복제(㉺·㉷ 선례).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c48_step0_check import (  # noqa: E402
    FRICTIONS, header_kind, open_observation_numbers, parse_observations,
)

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "..", ".."))
INDEX_PATH = os.path.join(REPO, "research", "devloop", "frictions-index.md")


def origin_lines(text: str) -> dict[int, int]:
    """관측 번호 → 원본 헤더의 1-기준 행 번호 (첫 원본만). **순수 함수**.

    종류 판별은 header_kind 단일 술어 — 처분/보강/재발 헤더(어순 불문)는
    원본 행으로 등재하지 않는다(관측 76 어순 둔감 승계)."""
    out: dict[int, int] = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        hk = header_kind(line)
        if hk is None:
            continue
        num, kind = hk
        if kind == "원본" and num not in out:
            out[num] = lineno
    return out


def build_index(text: str) -> list[dict]:
    """관측별 1줄 인덱스 행 재료. **순수 함수** — 파일도 시계도 만지지 않는다.

    상태 어휘(3값): '회부 존속' = 태그 있고 이탈 없음(파트 F open과 동일 집합) ·
    '회부 이탈' = 이탈 마커 확정 · '무태그' = 계상 밖(유형 기귀속 등).
    부분 처분(partial_disposal)은 존속에 '·처분文有' 병기 — 파트 F 인쇄와 같은 서식."""
    obs = parse_observations(text)
    lines = origin_lines(text)
    open_set = set(open_observation_numbers(obs))
    rows: list[dict] = []
    for num in sorted(obs):
        o = obs[num]
        if num in open_set:
            status = "회부 존속" + ("·처분文有" if o["partial_disposal"] else "")
        elif o["tagged"]:
            status = "회부 이탈"
        else:
            status = "무태그"
        rows.append({
            "num": num,
            "opened": o["opened"],
            "last": o["last"],
            "title": o["title"],
            "status": status,
            "line": lines.get(num),
        })
    return rows


def format_index(rows: list[dict], source_sha: str, generated_at: str,
                 source_path: str, source_lines: int) -> str:
    """인덱스 문서 서식. **순수 함수** — 머리말 3요소(비정본·시각·sha)는 계약이다."""
    head = [
        "# frictions-index — 파생 캐시 (**정본 아님 · 재생성 가능**)",
        "",
        f"- 원본: `{source_path}` ({source_lines}행) · sha256 `{source_sha}`",
        f"- 생성 시각: {generated_at} · 생성기: `research/devloop/scripts/frictions_index.py` (계기 큐 ㉻)",
        "- **낡음 판별 = sha 대조**: 원본 sha가 다르면 이 캐시는 죽은 것이다 — 재생성 없이 읽지 말 것(관측 35 부류).",
        "- **감사 소스 사용 금지 (A-245.1 게이트 대기)** — 승인 전에는 비-감사 사이클의 보조 열람만.",
        "- 서식: `관측 N · 주조 cN · 상태 · 원본 L행 · 제목` — 상태 어휘는 파트 F와 동일 술어(c48 import).",
        "",
    ]
    body = []
    for r in rows:
        opened = f"c{r['opened']}" if r["opened"] else "c?"
        last = f"→c{r['last']}" if r["last"] and r["last"] != r["opened"] else ""
        line = f"L{r['line']}" if r["line"] else "L?"
        title = r["title"] or "(제목 없음)"
        body.append(f"관측 {r['num']} · 주조 {opened}{last} · {r['status']} · {line} · {title}")
    return "\n".join(head + body) + "\n"


def main() -> int:
    with open(FRICTIONS, encoding="utf-8") as fh:
        text = fh.read()
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rows = build_index(text)
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc = format_index(rows, sha, now, "research/devloop/frictions.md",
                       len(text.splitlines()))
    with open(INDEX_PATH, "w", encoding="utf-8") as fh:
        fh.write(doc)
    n_open = sum(1 for r in rows if r["status"].startswith("회부 존속"))
    n_exit = sum(1 for r in rows if r["status"] == "회부 이탈")
    n_untag = sum(1 for r in rows if r["status"] == "무태그")
    print(f"관측 {len(rows)}건 → {INDEX_PATH}")
    print(f"  회부 존속 {n_open} · 회부 이탈 {n_exit} · 무태그 {n_untag}")
    print(f"  원본 sha256 {sha[:16]}… · 캐시 크기 {len(doc.encode('utf-8'))}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
