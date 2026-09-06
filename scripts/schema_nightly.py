#!/usr/bin/env python3
"""정훈의 모델 — 스키마 블록 (2026-09-07, goal:observe-junghun ①).

원장에서 정훈이 직접 말한 것(origin=user)·관찰([관찰·])·자기층 교훈·목표를 모아 최전선 모델이
«정훈은 이런 사람이다» ≤2,000토큰을 다시 쓴다. 산출: ~/.forget/attention/schema.md (이전본은 schema.prev.md).
모델: Claude Code 헤드리스(claude -p, 도구 없음) — 구독 OAuth로 돈다. 실패하면 이전본 유지(fail-open).
"""
from __future__ import annotations
import json, os, re, shutil, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

ATTN = Path(os.getenv("FORGET_ATTENTION_DIR") or Path.home() / ".forget" / "attention")
DB = Path(os.getenv("MEM1_DB_PATH") or Path.home() / ".forget" / "forget.sqlite3")
DAYS = int(os.getenv("FORGET_SCHEMA_DAYS", "60"))
MAX_CHARS = 14000


def gather() -> str:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); conn.row_factory = sqlite3.Row
    cutoff = datetime.now(timezone.utc).timestamp() - DAYS * 86400
    since = datetime.fromtimestamp(cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute("""SELECT memory, created_at, metadata FROM memories
        WHERE created_at > ? AND (json_extract(metadata,'$.origin')='user' OR memory LIKE '[관찰·%' OR json_extract(metadata,'$.layer')='self'
              OR memory LIKE '%정훈 원문%' OR memory LIKE '%정훈 직접%')
          AND (json_extract(metadata,'$.superseded_by') IS NULL)
        ORDER BY created_at DESC LIMIT 400""", (since,)).fetchall()
    goals = conn.execute("SELECT memory FROM memories WHERE memory LIKE 'Task goal:%' ORDER BY created_at DESC LIMIT 6").fetchall()
    parts, n = [], 0
    for r in rows:
        line = f"- [{r['created_at'][:10]}] {re.sub(r'\\s+', ' ', r['memory'])[:420]}"
        if n + len(line) > MAX_CHARS:
            break
        parts.append(line); n += len(line)
    goal_txt = "\n".join(f"- {re.sub(r'\\s+', ' ', g['memory'])[:300]}" for g in goals)
    return f"## 목표\n{goal_txt}\n\n## 정훈이 말한 것·관찰·교훈 (최근 {DAYS}일, 최신 우선, {len(parts)}건)\n" + "\n".join(parts)


PROMPT = """너는 정훈의 에이전트의 «느린 루프»다. 아래 원장 발췌(정훈이 직접 말한 것, 관찰, 자기층 교훈, 목표)만 근거로
«정훈의 모델»을 한국어로 다시 써라. 이 글은 매 세션 시스템 프롬프트에 들어가 에이전트가 정훈을 예측하는 데 쓰인다.

형식(마크다운, 전체 2,000토큰 이하, 반말 서술체, 이모지 없음, 지어내지 않음 — 근거 없는 건 쓰지 않는다):
# 정훈
## 누구인가 (5줄 이내: 역할·지금 하는 일·북극성)
## 결정의 결 (어떻게 정하나 — 패턴 6개 이내, 각 근거가 된 원문 한 조각 인용)
## 거부·정정의 패턴 (무엇에 «아니야»라고 하나 — 6개 이내, 원문 인용)
## 말투와 리듬 (짧게)
## 지금의 목표와 열린 걱정
## 예측 (다음 세션에서 정훈이 할 법한 말·요구 3개 — 각각 «틀리면 배울 것» 한 줄)
## 에이전트에게 (정훈을 대할 때 지킬 것 5개 이내 — 정훈이 정정한 것에서만)

원장 발췌:
"""


def main() -> int:
    ATTN.mkdir(parents=True, exist_ok=True)
    src = gather()
    t0 = time.time()
    try:
        out = subprocess.run(["claude", "-p", "--model", os.getenv("FORGET_SCHEMA_MODEL", "claude-fable-5-1"), "--tools", "", "--output-format", "text"],
                             input=PROMPT + src, capture_output=True, text=True, timeout=600, cwd=str(Path.home()))
    except Exception as e:
        print(json.dumps({"ok": False, "error": repr(e)[:200]})); return 1
    text = (out.stdout or "").strip()
    if out.returncode != 0 or len(text) < 400 or not text.startswith("#"):
        print(json.dumps({"ok": False, "code": out.returncode, "err": (out.stderr or text)[:300]})); return 1
    dst = ATTN / "schema.md"
    if dst.exists():
        shutil.copy(dst, ATTN / "schema.prev.md")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    dst.write_text(f"<!-- 정훈의 모델 · {stamp} · 근거 {src.count(chr(10))}행 · 느린 루프(claude) -->\n{text}\n")
    print(json.dumps({"ok": True, "chars": len(text), "src_lines": src.count("\n"), "secs": round(time.time() - t0)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
