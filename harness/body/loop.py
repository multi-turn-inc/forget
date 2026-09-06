"""루프 — 몸의 심장. 메시지가 오면 뇌↔도구를 끝까지 돌리고, 도중에 새 말이 오면 다음 뇌 호출 전에 끼워 넣는다(steer).
세션은 ~/.forget/body/<id>.jsonl(Claude 전사와 같은 모양 — 사이드카가 그대로 읽는다). 죽어도 그 줄부터 다시 산다."""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import brain as _brain
from . import context as _ctx
from . import tools as _tools

BODY_DIR = Path(os.getenv("BODY_DIR", Path.home() / ".forget" / "body"))
MAX_STEPS = int(os.getenv("BODY_MAX_STEPS", "80"))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Body:
    def __init__(self, brain_name: str = "astra", session_id: str | None = None, channel: str = "terminal",
                 on_event: Callable[[dict], None] | None = None):
        BODY_DIR.mkdir(parents=True, exist_ok=True)
        self.brain_name = brain_name
        self.brain = _brain.make(brain_name)
        self.channel = channel
        self.session_id = session_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        self.path = BODY_DIR / f"{self.session_id}.jsonl"
        self.on_event = on_event or (lambda e: None)
        self.inbox: "queue.Queue[str]" = queue.Queue()
        self.busy = False
        self.history: list[dict] = []
        if self.path.exists():
            self._load()

    # ── 세션 파일(Claude 전사 모양) ───────────────────────────────────────
    def _append(self, kind: str, message: dict, extra: dict | None = None) -> None:
        row = {"type": kind, "timestamp": _now(), "sessionId": self.session_id, "message": message, **(extra or {})}
        with open(self.path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _load(self) -> None:
        for line in self.path.read_text().splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            m = d.get("message") or {}
            if d.get("type") == "user" and isinstance(m.get("content"), str):
                self.history.append({"role": "user", "content": m["content"]})
            elif d.get("type") == "user" and isinstance(m.get("content"), list):
                for p in m["content"]:
                    if p.get("type") == "tool_result":
                        self.history.append({"role": "tool", "tool_call_id": p["tool_use_id"], "content": p.get("content", "")})
            elif d.get("type") == "assistant":
                raw = d.get("raw_assistant")
                if raw:
                    self.history.append(raw)
                else:
                    txt = "".join(p.get("text", "") for p in m.get("content", []) if p.get("type") == "text")
                    self.history.append({"role": "assistant", "content": txt})

    # ── 말 받기 ───────────────────────────────────────────────────────────
    def say(self, text: str) -> None:
        """채널이 부른다. 바쁘면 큐에 넣고(steer), 아니면 바로 돈다."""
        if self.busy:
            self.inbox.put(text)
            self.on_event({"type": "queued", "text": text})
        else:
            threading.Thread(target=self.run_turn, args=(text,), daemon=True).start()

    def _drain_inbox(self) -> None:
        while True:
            try:
                t = self.inbox.get_nowait()
            except queue.Empty:
                return
            self.history.append({"role": "user", "content": t})
            self._append("user", {"role": "user", "content": t})
            self.on_event({"type": "steer", "text": t})

    # ── 한 턴: 뇌↔도구 끝까지 ───────────────────────────────────────────
    def run_turn(self, text: str) -> str:
        self.busy = True
        self.on_event({"type": "turn_start"})
        try:
            self.history.append({"role": "user", "content": text})
            self._append("user", {"role": "user", "content": text})
            final = ""
            for step in range(MAX_STEPS):
                msgs = [{"role": "system", "content": _ctx.system_prompt(self.brain_name, self.channel)}]
                hist = _ctx.compact_history(self.history)
                if len(hist) < len(self.history):
                    msgs.append({"role": "system", "content": _ctx.brief_summary(self.history[:-len(hist)] if hist else self.history)})
                msgs += hist
                t0 = time.time()
                try:
                    out = self.brain.chat(msgs, _tools.SPEC)
                except Exception as e:
                    err = f"뇌 호출 실패: {type(e).__name__}: {str(e)[:200]}"
                    self.on_event({"type": "error", "text": err})
                    final = err
                    break
                raw = out.get("raw_assistant") or {"role": "assistant", "content": out.get("text") or ""}
                if raw.get("content") is None and not raw.get("tool_calls"):
                    raw["content"] = ""
                self.history.append(raw)
                blocks = ([{"type": "text", "text": out["text"]}] if out.get("text") else []) + \
                         [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in out["tool_calls"]]
                self._append("assistant", {"role": "assistant", "content": blocks},
                             {"raw_assistant": raw, "usage": out.get("usage"), "latency_s": round(time.time() - t0, 2)})
                if out.get("text"):
                    self.on_event({"type": "text", "text": out["text"]})
                if not out["tool_calls"]:
                    final = out.get("text") or ""
                    break
                results = []
                for c in out["tool_calls"]:
                    self.on_event({"type": "tool_start", "name": c["name"], "args": c["args"]})
                    r = _tools.run(c["name"], c["args"])
                    self.on_event({"type": "tool_end", "name": c["name"], "result": r[:400]})
                    self.history.append({"role": "tool", "tool_call_id": c["id"], "content": r})
                    results.append({"type": "tool_result", "tool_use_id": c["id"], "content": r})
                self._append("user", {"role": "user", "content": results})
                self._drain_inbox()          # 도구 사이에 정훈이 말했으면 여기서 듣는다
            else:
                final = "(단계 상한에 닿았다 — task_state에 남기고 멈춘다)"
            self.on_event({"type": "turn_end", "text": final})
            return final
        finally:
            self.busy = False
            if not self.inbox.empty():   # 턴 끝난 뒤 남은 말은 새 턴
                nxt = self.inbox.get()
                threading.Thread(target=self.run_turn, args=(nxt,), daemon=True).start()
