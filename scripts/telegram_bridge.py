#!/usr/bin/env python3
"""텔레그램 다리 v2 (2026-09-07, 정훈 «텔레그램 켜») — 8/22 하나의 one_telegram.py를 잇는다.
폰 → 쪽지함(~/Documents/one/inbox.md) → 몸의 뇌(harness.body.brain, ~/.forget/attention/brain 선택) → 답을 쪽지함에 붙이고 폰으로.
몸·맥박이 쪽지함에 쓴 «— 나» 줄도 폰으로 민다. 주인 잠금(telegram_owner.txt). 토큰은 ~/.one_telegram_token 파일로만 — 값은 이 프로세스 안에만 산다."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(os.getenv("FORGET_REPO", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(REPO))
from harness.body import brain as _brain  # noqa: E402
from harness.body import context as _ctx  # noqa: E402

HOME = Path.home() / "Documents" / "one"
TOKEN_F = Path.home() / ".one_telegram_token"
OWNER_F = HOME / "telegram_owner.txt"
INBOX = HOME / "inbox.md"
BRAIN_F = Path.home() / ".forget" / "attention" / "brain"
LOG = Path.home() / ".forget" / "attention" / "telegram.log"
if not TOKEN_F.exists():
    sys.exit("토큰 없음: ~/.one_telegram_token")
API = "https://api.telegram.org/bot" + TOKEN_F.read_text().strip()


def log(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{datetime.now():%m-%d %H:%M} {s}\n")


def tg(method: str, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(f"{API}/{method}", data=data), timeout=70) as r:
        return json.load(r)


def send(chat_id: str, text: str) -> None:
    for i in range(0, len(text), 3800):
        tg("sendMessage", chat_id=chat_id, text=text[i:i + 3800])


def recent_notes(n: int = 8) -> str:
    try:
        lines = [l for l in INBOX.read_text().splitlines() if l.startswith("정훈:") or l.startswith("— 나")]
        return "\n".join(lines[-n:])
    except Exception:
        return ""


def answer(text: str) -> str:
    name = BRAIN_F.read_text().strip() if BRAIN_F.exists() else "claude"
    for candidate in (name, "spark"):                      # 뇌가 한도에 걸리면 Spark로
        try:
            b = _brain.make(candidate)
            msgs = [{"role": "system", "content": _ctx.system_prompt(candidate, "telegram")},
                    {"role": "system", "content": "폰(텔레그램) 채널 — 대화다. 사람과 말하듯 반말로, 길이는 말에 맞게(한 줄이면 한 줄, 설명이 필요하면 몇 줄). 보고체·머리말·번호 목록 없이. 모르면 모른다고. 최근 쪽지:\n" + recent_notes()},
                    {"role": "user", "content": text}]
            out = b.chat(msgs, tools=None)
            ans = (out.get("text") or "").strip()
            if ans:
                return ans[:1500] + ("" if candidate == name else "  (뇌: spark)")
        except Exception as e:
            log(f"뇌 {candidate} 실패 {str(e)[:100]}")
    return "(지금은 답을 못 만든다. 맥박은 뛰고 있다.)"


def main() -> None:
    owner = OWNER_F.read_text().strip() if OWNER_F.exists() else None
    offset = 0
    INBOX.parent.mkdir(parents=True, exist_ok=True)
    INBOX.touch(exist_ok=True)
    inbox_size = INBOX.stat().st_size
    log(f"다리 기동 (주인 {owner or '미정'})")
    while True:
        try:  # 쪽지함 → 폰: 몸·맥박이 붙인 «— 나» 줄
            sz = INBOX.stat().st_size
            if owner and sz > inbox_size:
                new = INBOX.read_text()[inbox_size:]
                inbox_size = sz
                mine = [l for l in new.splitlines() if l.startswith("— 나")]
                if mine:
                    send(owner, "\n".join(mine))
        except Exception as e:
            log(f"쪽지 전달 실패 {str(e)[:80]}")
        try:
            updates = tg("getUpdates", timeout=50, offset=offset)
        except Exception as e:
            log(f"폴링 실패 {str(e)[:80]}")
            time.sleep(10)
            continue
        for u in updates.get("result", []):
            offset = u["update_id"] + 1
            m = u.get("message") or {}
            chat_id = str(m.get("chat", {}).get("id", ""))
            text = (m.get("text") or "").strip()
            if not chat_id or not text:
                continue
            if owner is None:
                owner = chat_id
                OWNER_F.write_text(owner)
                log(f"주인 잠김 {owner}")
            if chat_id != owner:
                continue
            stamp = datetime.now().strftime("%m-%d %H:%M")
            with open(INBOX, "a") as f:
                f.write(f"\n정훈: {text}\n")
            ans = answer(text)
            with open(INBOX, "a") as f:
                f.write(f"— 나 ({stamp}): {ans.replace(chr(10), ' ')}\n")
            inbox_size = INBOX.stat().st_size      # 내가 쓴 줄은 다시 밀지 않는다
            log(f"Q {text[:60]} → A {ans[:60]}")
            try:
                send(chat_id, ans)
            except Exception as e:
                log(f"전송 실패 {str(e)[:80]}")


if __name__ == "__main__":
    main()
