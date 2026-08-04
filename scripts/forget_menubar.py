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


def _read_gear_direct() -> str:
    """설정의 현재 기어를 직접 읽기 (~1ms) — 1초 폴링용."""
    import os

    os.environ.setdefault("MEM1_DB_PATH", os.path.expanduser("~/.forget/forget.sqlite3"))
    from forget.providers import get_project_settings

    return str(get_project_settings("proj_local").get("recall_default") or "low")


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


def _cloud_status() -> dict:
    """구독 상태 한 줄 — 토큰이 있으면 잔여량까지, 없으면 구독 안내.

    실패는 조용히: 메뉴바는 알림판이지 에러 콘솔이 아니다."""
    import os

    os.environ.setdefault("MEM1_DB_PATH", os.path.expanduser("~/.forget/forget.sqlite3"))
    try:
        from forget.providers import get_project_settings

        token = str(get_project_settings("proj_local").get("recall_cloud_token") or "")
    except Exception:
        token = ""
    if not token:
        return {"label": "forget cloud 구독 — 발열 없는 딥 리콜"}
    try:
        request = urllib.request.Request(
            "https://cloud.forget.sh/v1/usage",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            report = json.loads(response.read())
        if report.get("status") == "active":
            return {"label": f"cloud: {report.get('plan', 'pro')} · 딥 리콜 {report.get('remaining', 0):,}회 남음"}
        return {"label": "cloud: 구독 잠김 — 재구독하기"}
    except Exception:
        return {"label": "cloud: 상태 확인 불가 — 페이지 열기"}


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


ICON_PT = (52, 16)  # 메뉴바 표시 치수(pt) — 가로 실이 눌리지 않게 직접 지정 (2026-08-05 2배의 2/3)


class ForgetMenuBar(rumps.App):
    def _set_icon(self, path: str) -> None:
        try:
            # _nsimage_from_file은 rumps._internal이 아니라 rumps.rumps에 산다 —
            # 잘못된 주소는 AttributeError → 폴백 → 20×20 스쿼시로 조용히 샌다.
            from rumps.rumps import _nsimage_from_file

            image = _nsimage_from_file(path, dimensions=ICON_PT)
            self._icon_nsimage = image
            try:
                self._nsapp.setStatusBarIcon()
            except AttributeError:
                pass  # run() 이전 — 초기 아이콘은 run 시점에 반영됨
        except Exception:
            self.icon = path  # 어떤 rumps 내부 변경에도 폴백

    def __init__(self) -> None:
        import os

        self.icon_dir = os.path.expanduser("~/.forget/menubar-icons")
        super().__init__("forget", icon=os.path.join(self.icon_dir, "gear-low.png"), quit_button="종료")
        self.template = False
        self.gear_items = {gear: rumps.MenuItem(gear, callback=self._set_gear) for gear in GEARS}
        self.engine_item = rumps.MenuItem("engine: …")
        self.being_item = rumps.MenuItem("…")
        self.cloud_item = rumps.MenuItem("forget cloud 구독 — 발열 없는 딥 리콜", callback=self._open_cloud)
        self.menu = [
            *self.gear_items.values(),
            None,
            self.engine_item,
            self.being_item,
            None,
            self.cloud_item,
        ]
        if _ram_gb() >= 16:
            # Hardware gate: local-LLM hint only where it would feel good.
            self.local_hint = rumps.MenuItem("로컬 LLM 연결 안내 (Ollama)", callback=self._open_local_guide)
            self.menu.add(self.local_hint)
        self.gear = "low"
        self.frame = 0
        self.anim = rumps.Timer(self._animate, 0.13)
        self._refresh(None)

    def _open_local_guide(self, _sender) -> None:
        # 설치는 그들의 손으로 — 문만 열어준다 (2026-08-04 결정)
        subprocess.run(["open", "https://ollama.com/download"])

    def _open_cloud(self, _sender) -> None:
        subprocess.run(["open", "https://forget.sh/cloud"])

    @rumps.timer(1)
    def _poll_activity(self, _sender) -> None:
        """기억을 감는 동안만 실이 돈다 — 쉬는 실은 멈춰 있다."""
        import os

        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/v3/recall/activity", timeout=0.4) as response:
                active = json.loads(response.read()).get("active", 0) > 0
        except Exception:
            active = False
        # 외부 변경(CLI·다른 세션) 동기화: 기어가 바뀌었으면 1초 안에 실이 바뀐다
        try:
            gear_now = _read_gear_direct()
            if gear_now != self.gear:
                self.gear = gear_now
                for gear, item in self.gear_items.items():
                    item.state = 1 if gear == gear_now else 0
                if not self.anim.is_alive():
                    icon = os.path.join(self.icon_dir, f"gear-{gear_now}.png")
                    if os.path.exists(icon):
                        self._set_icon(icon)
        except Exception:
            pass
        if active and not self.anim.is_alive():
            self.anim.start()
        elif not active and self.anim.is_alive():
            self.anim.stop()
            icon = os.path.join(self.icon_dir, f"gear-{self.gear}.png")
            if os.path.exists(icon):
                self._set_icon(icon)

    def _animate(self, _sender) -> None:
        import os

        gear = self.gear if self.gear != "low" else "high"
        self.frame = (self.frame + 1) % 6
        icon = os.path.join(self.icon_dir, f"gear-{gear}-f{self.frame}.png")
        if os.path.exists(icon):
            self._set_icon(icon)

    def _set_gear(self, sender: rumps.MenuItem) -> None:
        import os

        try:
            _set_gear_direct(sender.title)
        except Exception:
            _run("recall", "use", sender.title)
        self.gear = sender.title
        icon = os.path.join(self.icon_dir, f"gear-{self.gear}.png")
        if os.path.exists(icon) and not self.anim.is_alive():
            self._set_icon(icon)
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
                self._set_icon(icon_path)
        for gear, item in self.gear_items.items():
            item.state = 1 if gear == state["gear"] else 0
        engine = state["engine"] or "미설정"
        self.engine_item.title = f"engine: {engine}"
        status = _run("status")
        for line in status.splitlines():
            if line.startswith("being:"):
                self.being_item.title = line.replace("being:", "").strip()
                break
        self.cloud_item.title = _cloud_status()["label"]


if __name__ == "__main__":
    ForgetMenuBar().run()
