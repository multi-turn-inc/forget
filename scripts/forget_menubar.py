#!/usr/bin/env python3
"""forget menu bar — the dial, one click from anywhere.

Prototype (rumps). The menu is the product surface the terminal can't be:
always visible, machine-aware, and quiet. Hardware gating rule
(2026-08-04, 정훈): below 16GB RAM the local-LLM option is not shown at
all — perceived quality beats theoretical capability; cloud is the offer
there. Geeks keep the CLI escape hatch regardless.

Run:  ~/.forget/venv/bin/python scripts/forget_menubar.py &
"""

from __future__ import annotations

import subprocess
import sys

import rumps

SERVER_BIN = sys.prefix + "/bin/forget-server"
GEARS = ["low", "medium", "high", "extra"]
DB_ENV = {"MEM1_DB_PATH": __import__("os").path.expanduser("~/.forget/forget.sqlite3")}


def _run(*args: str) -> str:
    import os

    try:
        return subprocess.run(
            [SERVER_BIN, *args],
            capture_output=True, text=True, timeout=20,
            env={**os.environ, **DB_ENV},
        ).stdout
    except Exception:
        return ""


def _ram_gb() -> int:
    try:
        return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) // (1 << 30)
    except Exception:
        return 0


def _recall_state() -> dict:
    out = _run("recall", "status")
    state = {"gear": "low", "engine": "", "ready": "deep recall   : ready" in out}
    for line in out.splitlines():
        if line.startswith("dial"):
            for gear in GEARS:
                if f"[{gear}]" in line:
                    state["gear"] = gear
        if line.startswith("engine"):
            state["engine"] = line.split(":", 1)[1].strip()
    return state


class ForgetMenuBar(rumps.App):
    def __init__(self) -> None:
        import os

        self.icon_dir = os.path.expanduser("~/.forget/menubar-icons")
        super().__init__("forget", icon=os.path.join(self.icon_dir, "gear-low.png"), quit_button="종료")
        self.template = False
        self.gear_items = {gear: rumps.MenuItem(gear, callback=self._set_gear) for gear in GEARS}
        self.engine_item = rumps.MenuItem("engine: …")
        self.being_item = rumps.MenuItem("…")
        self.menu = [
            *self.gear_items.values(),
            None,
            self.engine_item,
            self.being_item,
        ]
        if _ram_gb() < 16:
            # Hardware gate: no local-LLM hint on small machines — cloud only.
            self.menu.add(rumps.MenuItem("forget cloud — 발열 없는 딥 리콜 (준비 중)"))
        self._refresh(None)

    def _set_gear(self, sender: rumps.MenuItem) -> None:
        _run("recall", "use", sender.title)
        self._refresh(None)

    @rumps.timer(60)
    def _refresh(self, _sender) -> None:
        import os

        state = _recall_state()
        icon_path = os.path.join(self.icon_dir, f"gear-{state['gear']}.png")
        if os.path.exists(icon_path):
            self.icon = icon_path
        for gear, item in self.gear_items.items():
            item.state = 1 if gear == state["gear"] else 0
        engine = state["engine"] or "미설정"
        self.engine_item.title = f"engine: {engine}"
        status = _run("status")
        for line in status.splitlines():
            if line.startswith("being:"):
                self.being_item.title = line.replace("being:", "").strip()
                break


if __name__ == "__main__":
    ForgetMenuBar().run()
