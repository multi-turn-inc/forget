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
import subprocess
import sys
from pathlib import Path

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


def cmd_run(args: argparse.Namespace) -> None:
    _require_uvicorn()
    import uvicorn

    forget_home().mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MEM1_DB_PATH", str(db_path()))
    print(f"forget-server: http://{args.host}:{args.port}  (db: {db_path()})")
    uvicorn.run("forget.server:app", host=args.host, port=args.port)


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


def cmd_status(args: argparse.Namespace) -> None:
    listening = _port_open(args.host, args.port)
    print(f"server: {'listening' if listening else 'not listening'} on {args.host}:{args.port}")
    print(f"db:     {db_path()}{'' if db_path().exists() else '  (not created yet)'}")
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
