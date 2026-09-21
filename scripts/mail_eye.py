"""mail_eye — 정훈의 hiworks 받은편지함·스팸함을 «읽기만» 훑어 기한·회신 문구를 먼저 올리는 눈.

배경(2026-09-21): 9/14 DIP 박연진의 «홍보물 제작 내용 요청(~9/18)»이 스팸함에 들어가 기한을 모른 채 넘겼다.
정훈은 창에 «답글 왔나»·«또 뭐가 왔어»로 폴링한다 — 그가 묻기 전에 온 것을 보는 눈이 없었다.

원칙
- 읽기만. 발신·삭제·이동·답장 없음. 메일을 열지 않고 목록 화면(발신자·시각·제목)만 읽는다(열면 읽음 처리가 남는다).
- 다른 `aside --permission` 세션이 돌고 있으면 실행하지 않는다(브라우저를 공유하므로 겹치면 그쪽 작업을 깨뜨릴 수 있다).
- 결과는 ~/.forget/attention/mail_eye.jsonl 에 append. 외부 발신 없음.

사용
  .venv/bin/python scripts/mail_eye.py --since "2026-09-21 12:00"      # 실행
  .venv/bin/python scripts/mail_eye.py --since "..." --dry               # 프롬프트만 인쇄
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ASIDE = Path.home() / ".local/bin/aside"
OUT = Path.home() / ".forget/attention/mail_eye.jsonl"
KST = timezone(timedelta(hours=9))
ACCOUNT = "hiworks 메일(jhkim@sillaenc.co.kr, https://mail.office.hiworks.com)"
DEADLINE_RE = re.compile(r"(기한|마감|까지|회신|요청|제출|~\s*\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2}\s*\))")
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def build_prompt(since_kst: str) -> str:
    return (
        f"{ACCOUNT}의 받은편지함과 스팸함을 목록 화면에서만 읽어라. 메일을 열지 마라(읽음 처리가 남는다). "
        f"{since_kst} 이후 도착한 메일을 전부 «발신자 | 시각 | 제목 | 함(받은편지함/스팸함)» 한 줄씩 보고해라. "
        "제목에 기한·마감·~날짜·회신·요청·제출 문구가 있으면 줄 앞에 [기한] 을 붙여라. "
        "발송·삭제·이동·답장·읽음 표시 등 어떤 조작도 하지 마라. 해당 메일이 없으면 «없음»이라고만 써라."
    )


def aside_busy(ps_output: str | None = None) -> bool:
    """다른 aside 브라우저 세션이 돌고 있으면 True."""
    if ps_output is None:
        ps_output = subprocess.run(["ps", "-ax", "-o", "command"], capture_output=True, text=True, errors="replace").stdout
    return any(line.lstrip().startswith("aside ") and "--permission" in line for line in ps_output.splitlines())


def run_aside(prompt: str, timeout: int = 600) -> str:
    r = subprocess.run([str(ASIDE), "--permission", "ask", prompt], capture_output=True, text=True, errors="replace", timeout=timeout)
    return _ANSI.sub("", (r.stdout or "") + (r.stderr or ""))


def parse(report: str) -> list[dict]:
    """보고 텍스트에서 «발신자 | 시각 | 제목 | 함» 줄을 뽑는다. 기한 플래그는 [기한] 표시 또는 제목 정규식."""
    rows = []
    for line in report.splitlines():
        s = line.strip().lstrip("-*• ").strip()
        if s.count("|") < 2:
            continue
        flagged = s.startswith("[기한]")
        s = s.removeprefix("[기한]").strip()
        parts = [p.strip() for p in s.split("|")]
        sender, when, subject = parts[0], parts[1], parts[2]
        box = parts[3] if len(parts) > 3 else ""
        rows.append({"sender": sender, "at": when, "subject": subject, "box": box,
                     "deadline": bool(flagged or DEADLINE_RE.search(subject))})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None, help="KST 'YYYY-MM-DD HH:MM' (기본: 지금-6h)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args(argv)
    since = a.since or (datetime.now(KST) - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M")
    prompt = build_prompt(since)
    if a.dry:
        print(prompt)
        return 0
    if not ASIDE.exists():
        print("aside not installed", file=sys.stderr)
        return 2
    if aside_busy():
        print("busy: another aside session is running — skip", file=sys.stderr)
        return 3
    report = run_aside(prompt, timeout=a.timeout)
    rows = parse(report)
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
           "since_kst": since, "n": len(rows), "deadline": [r for r in rows if r["deadline"]], "rows": rows,
           "raw": report[-4000:]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({k: rec[k] for k in ("at", "since_kst", "n", "deadline")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
