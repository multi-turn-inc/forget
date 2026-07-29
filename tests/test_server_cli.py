"""forget-server lifecycle CLI — service-file generation is pure and testable."""
from forget.cli import launchd_plist, systemd_unit, SERVICE_LABEL


def test_launchd_plist_shape() -> None:
    plist = launchd_plist("/usr/bin/python3", "127.0.0.1", 8123)
    assert SERVICE_LABEL in plist
    assert "<string>--port</string><string>8123</string>" in plist
    assert "<string>127.0.0.1</string>" in plist
    assert "MEM1_DB_PATH" in plist and "KeepAlive" in plist


def test_systemd_unit_shape() -> None:
    unit = systemd_unit("/usr/bin/python3", "127.0.0.1", 8123)
    assert "ExecStart=/usr/bin/python3 -m uvicorn forget.server:app --host 127.0.0.1 --port 8123" in unit
    assert "Restart=always" in unit and "MEM1_DB_PATH" in unit


def test_mcp_initialize_reports_installed_version() -> None:
    # Issue #5: initialize answered "0.1.0" for three releases running — a
    # server you can't identify is a server you can't file bugs against.
    # __version__ derives from the installed dist (pyproject), with a
    # "+source" marker when running from a bare source tree.
    import forget
    from forget.mcp import handle_mcp_rpc

    response = handle_mcp_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    version = response["result"]["serverInfo"]["version"]
    assert version == forget.__version__
    assert version != "0.1.0"


def test_being_line_formats_vitals_and_absence() -> None:
    # Assistant-authored: "server: listening" describes the process; this
    # line describes the thing that persists.
    from datetime import datetime, timezone

    from forget.cli import format_being_line

    line = format_being_line(
        {"memories": 641, "shed": 6, "verified": 8,
         "born": "2026-07-09", "last_fed": "2026-07-25T08:00:00Z"},
        today=datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
    )
    assert line.startswith("being:  alive 16 days · 641 memories · 6 shed · 8 verified · last fed")
    assert format_being_line(None) == "being:  not born yet — nothing written to this store"


def test_being_vitals_reads_a_real_store(tmp_path) -> None:
    import os

    from forget import db as app_db
    from forget.db import init_db
    from forget.cli import being_vitals

    path = tmp_path / "vitals.sqlite3"
    os.environ["MEM1_DB_PATH"] = str(path)
    app_db.DB_PATH = path
    init_db()
    from forget.store import add_memories
    add_memories({"messages": [{"role": "user", "content": "vital sign seed"}],
                      "infer": False, "user_id": "vitals-user"}, project_id="proj_local")
    vitals = being_vitals(path)
    assert vitals and vitals["memories"] >= 1
    assert being_vitals(tmp_path / "missing.sqlite3") is None


def test_bind_or_exit_refuses_occupied_port_with_prescription() -> None:
    # Cold-install audit: a taken port produced a buried uvicorn ERROR under
    # a success-looking banner. The bind now happens first, in our hands.
    import socket

    import pytest

    from forget.cli import _bind_or_exit

    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        with pytest.raises(SystemExit) as exc_info:
            _bind_or_exit("127.0.0.1", port)
        message = str(exc_info.value.code)
        assert f"cannot listen on 127.0.0.1:{port}" in message
        assert "forget-server status" in message
        assert f"--port {port + 1}" in message
    finally:
        blocker.close()


def test_run_binds_before_banner_and_hands_socket_to_uvicorn(monkeypatch, capsys, tmp_path) -> None:
    import sys as _sys
    import types

    from forget import cli

    captured: dict = {}

    class _FakeServer:
        def __init__(self, config) -> None:
            self.config = config
            self.started = False

        def run(self, sockets=None) -> None:
            captured["sockets"] = sockets
            self.started = True

    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.Config = lambda *a, **kw: (a, kw)
    fake_uvicorn.Server = _FakeServer
    monkeypatch.setitem(_sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setenv("FORGET_HOME", str(tmp_path))
    monkeypatch.setenv("MEM1_DB_PATH", str(tmp_path / "db.sqlite3"))

    cli.main(["run", "--port", "0"])  # port 0: OS picks a free one, no race

    sock = captured["sockets"][0]
    try:
        assert sock.getsockname()[1] > 0  # already bound when uvicorn got it
    finally:
        sock.close()
    assert "forget-server: http://127.0.0.1:" in capsys.readouterr().out


def test_run_on_occupied_port_exits_nonzero_without_banner(tmp_path) -> None:
    # End-to-end repro of the audit finding: real subprocess, real exit code.
    import os
    import socket
    import subprocess
    import sys as _sys
    from pathlib import Path

    import pytest

    pytest.importorskip("uvicorn")

    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    env = dict(os.environ, FORGET_HOME=str(tmp_path), MEM1_DB_PATH=str(tmp_path / "db.sqlite3"))
    try:
        proc = subprocess.run(
            [_sys.executable, "-m", "forget.cli", "run", "--port", str(port)],
            capture_output=True, text=True, timeout=60, env=env,
            cwd=Path(__file__).resolve().parents[1],
        )
    finally:
        blocker.close()
    assert proc.returncode != 0
    assert "forget-server: http://" not in proc.stdout  # no lying banner
    assert "forget-server status" in proc.stderr
    assert f"--port {port + 1}" in proc.stderr
