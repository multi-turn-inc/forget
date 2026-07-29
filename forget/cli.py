"""forget-server — run and manage the local Forget server.

The beta funnel's silent killer: a user installs, connects, reboots — and
the server is gone. Hooks are fail-open by design, so memory just quietly
stops arriving. The fix is a real lifecycle: `forget-server run` for the
foreground, `forget-server install-service` for a login service (launchd on
macOS, systemd --user on Linux), `status` to see what's true.
"""

from __future__ import annotations

import argparse
import os
import socket
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SERVICE_LABEL = "ai.forget.server"


def forget_home() -> Path:
    return Path(os.environ.get("FORGET_HOME", Path.home() / ".forget"))


def db_path() -> Path:
    return Path(os.environ.get("MEM1_DB_PATH", forget_home() / "forget.sqlite3"))


def log_path() -> Path:
    return forget_home() / "server.log"


def launchd_plist(python: str, host: str, port: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{SERVICE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string><string>uvicorn</string>
    <string>forget.server:app</string>
    <string>--host</string><string>{host}</string>
    <string>--port</string><string>{port}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>MEM1_DB_PATH</key><string>{db_path()}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{log_path()}</string>
  <key>StandardErrorPath</key><string>{log_path()}</string>
</dict>
</plist>
"""


def systemd_unit(python: str, host: str, port: int) -> str:
    return f"""[Unit]
Description=Forget local memory server

[Service]
Environment=MEM1_DB_PATH={db_path()}
ExecStart={python} -m uvicorn forget.server:app --host {host} --port {port}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
"""


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.6)
        return sock.connect_ex((host, port)) == 0


def _require_uvicorn() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        sys.exit("uvicorn is not installed. Run: pip install 'forget-ai[server]'")


def _bind_or_exit(host: str, port: int) -> socket.socket:
    """Bind before any success output — the banner must not outrun the bind.

    Cold-install audit: with the port already taken, uvicorn buried the
    EADDRINUSE in its startup logs while the banner still read like success
    (and the exit code didn't reliably say failure). Owning the bind makes
    failure loud, prescriptive, and fatal — before anything hopeful prints.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError as exc:
        sock.close()
        sys.exit(
            f"forget-server: cannot listen on {host}:{port} — {exc.strerror or exc}.\n"
            f"  Is one already running? Check: forget-server status\n"
            f"  Or pick another port:         forget-server run --port {port + 1}"
        )
    sock.set_inheritable(True)
    return sock


def cmd_run(args: argparse.Namespace) -> None:
    _require_uvicorn()
    import uvicorn

    forget_home().mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MEM1_DB_PATH", str(db_path()))
    sock = _bind_or_exit(args.host, args.port)
    print(f"forget-server: http://{args.host}:{args.port}  (db: {db_path()})", flush=True)
    server = uvicorn.Server(uvicorn.Config("forget.server:app", host=args.host, port=args.port))
    server.run(sockets=[sock])
    if not server.started:
        sys.exit(3)


def _launchd_paths() -> tuple[Path, str]:
    plist = Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    return plist, domain


def cmd_install_service(args: argparse.Namespace) -> None:
    _require_uvicorn()
    forget_home().mkdir(parents=True, exist_ok=True)
    python = sys.executable
    if sys.platform == "darwin":
        plist, domain = _launchd_paths()
        plist.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["launchctl", "bootout", f"{domain}/{SERVICE_LABEL}"],
                       capture_output=True)
        plist.write_text(launchd_plist(python, args.host, args.port))
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
        print(f"installed launchd service {SERVICE_LABEL}\n  plist: {plist}\n  logs:  {log_path()}")
    elif sys.platform.startswith("linux"):
        unit = Path.home() / ".config" / "systemd" / "user" / "forget-server.service"
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(systemd_unit(python, args.host, args.port))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "forget-server.service"], check=True)
        print(f"installed systemd user service forget-server\n  unit: {unit}\n  logs: journalctl --user -u forget-server")
    else:
        sys.exit("install-service supports macOS (launchd) and Linux (systemd --user). "
                 "On other platforms run `forget-server run` in a terminal.")


def cmd_uninstall_service(_args: argparse.Namespace) -> None:
    if sys.platform == "darwin":
        plist, domain = _launchd_paths()
        subprocess.run(["launchctl", "bootout", f"{domain}/{SERVICE_LABEL}"],
                       capture_output=True)
        if plist.exists():
            plist.unlink()
        print(f"removed launchd service {SERVICE_LABEL}")
    elif sys.platform.startswith("linux"):
        subprocess.run(["systemctl", "--user", "disable", "--now", "forget-server.service"],
                       capture_output=True)
        unit = Path.home() / ".config" / "systemd" / "user" / "forget-server.service"
        if unit.exists():
            unit.unlink()
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        print("removed systemd user service forget-server")
    else:
        sys.exit("nothing to uninstall on this platform")


def being_vitals(path: Path) -> dict[str, Any] | None:
    """Vital signs of the memory itself — the store as a being, not a file.

    Assistant-authored (2026-07-25): "server: listening" describes the
    process; nothing described the thing that persists. Age counts from the
    first line ever written here; imported history can predate it (inherited
    memory) and doesn't move the birthday.
    """
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT COUNT(*) AS memories,
                      SUM(CASE WHEN metadata LIKE '%superseded_at%' THEN 1 ELSE 0 END) AS shed,
                      SUM(CASE WHEN metadata LIKE '%verified_at%' THEN 1 ELSE 0 END) AS verified,
                      MIN(created_at) AS oldest,
                      MAX(COALESCE(updated_at, created_at)) AS last_fed
               FROM memories WHERE deleted = 0"""
        ).fetchone()
        conn.close()
    except sqlite3.Error:
        return None
    if not row or not row["memories"]:
        return None
    # Birth is PHYSICAL (when this store file came to exist), not logical:
    # imported memories carry backdated created_at — inherited memory that
    # must not move the birthday. First taste of this very feature reported
    # "alive 2785 days" off a 12-day-old store; the beautiful number is the
    # one to distrust.
    stat_result = path.stat()
    born_ts = getattr(stat_result, "st_birthtime", None) or stat_result.st_mtime
    born = datetime.fromtimestamp(born_ts, timezone.utc).strftime("%Y-%m-%d")
    oldest = str(row["oldest"] or "")[:10]
    return {
        "memories": int(row["memories"]),
        "shed": int(row["shed"] or 0),
        "verified": int(row["verified"] or 0),
        "born": born,
        "inherited_to": oldest if oldest and oldest < born else "",
        "last_fed": str(row["last_fed"] or ""),
    }


def _humanize_since(stamp: str) -> str:
    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
    except ValueError:
        return "unknown"
    seconds = max(0, (datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def format_being_line(vitals: dict[str, Any] | None, today: datetime | None = None) -> str:
    if not vitals:
        return "being:  not born yet — nothing written to this store"
    now = today or datetime.now(timezone.utc)
    age = ""
    if vitals.get("born"):
        try:
            born = datetime.fromisoformat(vitals["born"]).replace(tzinfo=timezone.utc)
            age = f"alive {max(0, (now - born).days)} days · "
        except ValueError:
            age = ""
    inherited = f" · roots to {vitals['inherited_to'][:4]}" if vitals.get("inherited_to") else ""
    shed = f" · {vitals['shed']} shed" if vitals.get("shed") else ""
    verified = f" · {vitals['verified']} verified" if vitals.get("verified") else ""
    fed = f" · last fed {_humanize_since(vitals['last_fed'])}" if vitals.get("last_fed") else ""
    return f"being:  {age}{vitals['memories']} memories{shed}{verified}{inherited}{fed}"


def cmd_status(args: argparse.Namespace) -> None:
    listening = _port_open(args.host, args.port)
    print(f"server: {'listening' if listening else 'not listening'} on {args.host}:{args.port}")
    print(f"db:     {db_path()}{'' if db_path().exists() else '  (not created yet)'}")
    print(format_being_line(being_vitals(db_path())))
    if sys.platform == "darwin":
        plist, _ = _launchd_paths()
        print(f"service: {'installed' if plist.exists() else 'not installed'} ({plist})")
    elif sys.platform.startswith("linux"):
        unit = Path.home() / ".config" / "systemd" / "user" / "forget-server.service"
        print(f"service: {'installed' if unit.exists() else 'not installed'} ({unit})")
    if not listening:
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--host", default=DEFAULT_HOST)
    shared.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser = argparse.ArgumentParser(prog="forget-server", parents=[shared],
                                     description="Run and manage the local Forget server.")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="run the server in the foreground", parents=[shared])
    sub.add_parser("install-service", help="install a login service (launchd/systemd)", parents=[shared])
    sub.add_parser("uninstall-service", help="remove the login service", parents=[shared])
    sub.add_parser("status", help="show server and service state", parents=[shared])
    args = parser.parse_args(argv)
    command = args.command or "run"
    {"run": cmd_run,
     "install-service": cmd_install_service,
     "uninstall-service": cmd_uninstall_service,
     "status": cmd_status}[command](args)


if __name__ == "__main__":
    main()
