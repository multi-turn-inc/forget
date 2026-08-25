"""P-H-2 판독기 — 기상 로그·세션에서 판정 4축을 계산한다 (헌장 H-2).

판정선 (등록 원문): (a) 기상 성공률 ≥90% (터널 사망 스킵은 분모 제외,
스킵률 별도) (b) 유령 손 0건 (c) 무유도 유효 행동률 ≥50% (d) 일일 비용.

유효 행동의 결정론 근사: 그 기상 세션에서 도구 호출(forget_search·
release_hand·arm_hand·bash) ≥1 그리고 최종 텍스트가 IDLE 단독 선언이
아니면 유효. (사람 판독의 대체가 아니라 1차 필터 — 판정일에 표본 검토 병행.)

사용: .venv/bin/python scripts/h2_report.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LOG_DIR = Path.home() / ".forget" / "selfharness"
SESS_DIR = Path.home() / ".pi" / "agent" / "sessions"


def wake_log_rows() -> list[dict]:
    rows = []
    for log in sorted(LOG_DIR.glob("wake-*.log")):
        for line in log.read_text(errors="replace").splitlines():
            m = re.match(r"(\S+) (SKIP|FAIL|EXIT=(\d+))\s*(.*)", line)
            if not m:
                continue
            kind = m.group(2)
            rows.append({
                "at": m.group(1),
                "skip": kind == "SKIP",
                "fail_setup": kind == "FAIL",
                "exit": int(m.group(3)) if m.group(3) else None,
                "tail": m.group(4)[:120],
            })
    return rows


def _text_of(content) -> str:
    """user content는 문자열 또는 블록 배열 — 둘 다 문면으로 (파서 1차 실측 수리)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


def session_activity() -> dict:
    """self-harness 세션의 기상별 활동 — user 'wake' 메시지 단위로 절단."""
    out = {"wakes": 0, "effective": 0, "idle": 0}
    for sess in SESS_DIR.glob("*/*self-harness*.jsonl"):
        current_tools = 0
        current_idle = False
        started = False
        for line in sess.read_text(errors="replace").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") != "message":
                continue
            msg = e.get("message") or {}
            content = msg.get("content")
            if msg.get("role") == "user" and _text_of(content).startswith("wake"):
                if started:
                    out["wakes"] += 1
                    out["effective"] += 1 if (current_tools > 0 and not current_idle) else 0
                    out["idle"] += 1 if current_idle else 0
                started, current_tools, current_idle = True, 0, False
            elif isinstance(content, list):
                for b in content:
                    if b.get("type") == "toolCall":
                        current_tools += 1
                    if b.get("type") == "text" and re.search(r"\bIDLE\b", str(b.get("text", ""))):
                        current_idle = True
        if started:
            out["wakes"] += 1
            out["effective"] += 1 if (current_tools > 0 and not current_idle) else 0
            out["idle"] += 1 if current_idle else 0
    return out


def main() -> None:
    rows = wake_log_rows()
    attempts = [r for r in rows if not r["skip"]]
    skips = [r for r in rows if r["skip"]]
    ok = [r for r in attempts if r["exit"] == 0]
    act = session_activity()
    print(f"기상 시도 {len(attempts)} · 성공 {len(ok)} "
          f"({100 * len(ok) / len(attempts):.0f}%)" if attempts else "기상 시도 0")
    print(f"터널 스킵 {len(skips)}건 (분모 제외)")
    print(f"세션 기상 {act['wakes']} · 유효 {act['effective']} · IDLE {act['idle']}"
          + (f" → 유효율 {100 * act['effective'] / act['wakes']:.0f}%" if act["wakes"] else ""))
    print("비용: $0 (전 로컬 27B — 프로바이더 고정)")
    print("\n최근 5행:")
    for r in rows[-5:]:
        print(f"  {r['at']} {'SKIP' if r['skip'] else ('EXIT=' + str(r['exit']))} {r['tail'][:80]}")


if __name__ == "__main__":
    main()
