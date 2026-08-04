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

import json
import subprocess
import sys
import urllib.request

import rumps

SERVER_BIN = sys.prefix + "/bin/forget-server"
GEARS = ["low", "medium", "high", "extra"]
DB_ENV = {"MEM1_DB_PATH": __import__("os").path.expanduser("~/.forget/forget.sqlite3")}


def _set_gear_direct(gear: str) -> None:
    """클릭 → 반영 ~10ms: 서브프로세스 대신 같은 venv에서 설정 직접 기록."""
    import os

    os.environ.setdefault("MEM1_DB_PATH", os.path.expanduser("~/.forget/forget.sqlite3"))
    from forget import db as app_db
    from pathlib import Path

    app_db.DB_PATH = Path(os.environ["MEM1_DB_PATH"])
    from forget.db import init_db

    init_db()
    from forget.providers import update_project_settings

    update_project_settings("proj_local", {"recall_default": gear})


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
        else:
            self.local_hint = rumps.MenuItem("로컬 LLM 연결 안내 (Ollama)", callback=self._open_local_guide)
            self.menu.add(self.local_hint)

    def _open_local_guide(self, _sender) -> None:
        # 설치는 그들의 손으로 — 문만 열어준다 (2026-08-04 결정)
        subprocess.run(["open", "https://ollama.com/download"])
        self.gear = "low"
        self.frame = 0
        self.anim = rumps.Timer(self._animate, 0.13)
        self._refresh(None)

    @rumps.timer(1)
    def _poll_activity(self, _sender) -> None:
        """기억을 감는 동안만 실이 돈다 — 쉬는 실은 멈춰 있다."""
        import os

        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/v3/recall/activity", timeout=0.4) as response:
                active = json.loads(response.read()).get("active", 0) > 0
        except Exception:
            active = False
        if active and not self.anim.is_alive():
            self.anim.start()
        elif not active and self.anim.is_alive():
            self.anim.stop()
            icon = os.path.join(self.icon_dir, f"gear-{self.gear}.png")
            if os.path.exists(icon):
                self.icon = icon

    def _animate(self, _sender) -> None:
        import os

        gear = self.gear if self.gear != "low" else "high"
        self.frame = (self.frame + 1) % 6
        icon = os.path.join(self.icon_dir, f"gear-{gear}-f{self.frame}.png")
        if os.path.exists(icon):
            self.icon = icon

    def _set_gear(self, sender: rumps.MenuItem) -> None:
        import os

        try:
            _set_gear_direct(sender.title)
        except Exception:
            _run("recall", "use", sender.title)
        self.gear = sender.title
        icon = os.path.join(self.icon_dir, f"gear-{self.gear}.png")
        if os.path.exists(icon) and not self.anim.is_alive():
            self.icon = icon
        for gear, item in self.gear_items.items():
            item.state = 1 if gear == self.gear else 0

    @rumps.timer(60)
    def _refresh(self, _sender) -> None:
        import os

        state = _recall_state()
        self.gear = state["gear"]
        if not self.anim.is_alive():
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
