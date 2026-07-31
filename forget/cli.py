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


def hooks_wired(settings: dict[str, Any]) -> dict[str, bool]:
    """Which Claude Code lifecycle hooks mention forget.

    A silent nervous system is the cold-start killer: hooks are fail-open,
    so a user with broken wiring experiences forget as "nothing happens" —
    which is exactly what a *working* install feels like on day one. Doctor
    must tell those two apart.
    """
    wired = {}
    for event in ("SessionStart", "UserPromptSubmit", "PreCompact", "SessionEnd"):
        entries = settings.get("hooks", {}).get(event, [])
        commands = " ".join(
            h.get("command", "")
            for entry in entries if isinstance(entry, dict)
            for h in entry.get("hooks", []) if isinstance(h, dict)
        )
        wired[event] = "forget" in commands
    return wired


def pool_report(path: Path) -> list[tuple[str, str, int]]:
    """Distinct (user_id, app_id) pools with live-memory counts, largest first."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            """SELECT COALESCE(user_id,'∅'), COALESCE(app_id,'∅'), COUNT(*)
               FROM memories WHERE deleted = 0
               GROUP BY user_id, app_id ORDER BY COUNT(*) DESC"""
        ).fetchall()
    finally:
        conn.close()
    return [(str(u), str(a), int(n)) for u, a, n in rows]


def foreign_pools(
    pools: list[tuple[str, str, int]], user: str, canonical_app: str = "forget"
) -> list[tuple[str, str, int]]:
    """Pools that shouldn't live in this store — the F4 class of contamination."""
    return [p for p in pools if p[0] != user or p[1] != canonical_app]


def _mcp_call(host: str, port: int, app: str, user: str, method: str,
              params: dict[str, Any], timeout: float = 8.0) -> dict[str, Any]:
    import json as _json
    import urllib.request

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    request = urllib.request.Request(
        f"http://{host}:{port}/mcp/{app}/http/{user}",
        data=_json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return _json.loads(urllib.request.urlopen(request, timeout=timeout).read())


def cmd_doctor(args: argparse.Namespace) -> None:
    """End-to-end health verdict: every line is a symptom with a prescription.

    `status` says whether the process is up; doctor says whether the whole
    nervous system works — server answers MCP, the store is sound and
    uncontaminated, and the agent-side hooks are actually wired.
    """
    import getpass
    import json as _json

    user = os.environ.get("MEM1_MCP_DEFAULT_USER_ID") or getpass.getuser()
    # (ok, line, hint-if-bad, hard) — hard checks fail the verdict; soft ones advise.
    checks: list[tuple[bool, str, str, bool]] = []

    listening = _port_open(args.host, args.port)
    checks.append((listening, f"server listening on {args.host}:{args.port}",
                   "start it: forget-server install-service  (or: forget-server run)", True))

    mcp_ok = False
    if listening:
        try:
            body = _mcp_call(args.host, args.port, "forget", user, "tools/list", {})
            mcp_ok = bool(body.get("result", {}).get("tools"))
        except Exception:
            mcp_ok = False
    checks.append((mcp_ok, f"MCP endpoint answers (/mcp/forget/http/{user})",
                   "server is up but MCP failed — check server version: pip install -U forget-ai",
                   True))

    path = db_path()
    db_ok, pools = False, []
    if path.exists():
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            db_ok = conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            conn.close()
            pools = pool_report(path)
        except sqlite3.Error:
            db_ok = False
    # A store that doesn't exist yet is a normal day-zero state, not a failure.
    checks.append((db_ok or not path.exists(),
                   f"store {'readable and sound' if db_ok else 'not created yet (born on first write)'} ({path})",
                   "database corrupt — if this store held memories, restore from backup",
                   True))

    foreign = foreign_pools(pools, user)
    canonical = sum(n for u, a, n in pools if u == user and a == "forget")
    scope_ok = not foreign
    detail = f"{canonical} memories in your pool ({user} × forget)"
    if foreign:
        worst = ", ".join(f"{u}×{a}:{n}" for u, a, n in foreign[:3])
        detail += f" — plus {len(foreign)} foreign pool(s): {worst}"
    checks.append((scope_ok, f"scope clean: {detail}",
                   "foreign pools contaminate recall — merge or inspect: "
                   "forget-server migrate-scope --from-app <app> --to-app forget (dry-run first)",
                   True))

    settings_path = Path.home() / ".claude" / "settings.json"
    wired: dict[str, bool] = {}
    if settings_path.exists():
        try:
            wired = hooks_wired(_json.loads(settings_path.read_text()))
        except (OSError, ValueError):
            wired = {}
    # Advisory, not failure: MCP-only is a valid standard setup (the capsule
    # arrives via CLAUDE.md instructions); hooks are the deluxe wiring.
    hooks_ok = wired.get("SessionStart", False)
    wired_names = [k for k, v in wired.items() if v]
    checks.append((hooks_ok,
                   f"Claude Code hooks wired: {', '.join(wired_names) or 'none (optional)'}",
                   "capsule injection via hooks is off — fine if your CLAUDE.md asks the "
                   "agent to call prepare_context_autopilot at session start",
                   False))

    probe_ok = None
    if getattr(args, "probe", False) and mcp_ok:
        # Round trip in a dedicated probe scope — never the user's real pool.
        probe_text = "doctor round-trip probe"
        try:
            _mcp_call(args.host, args.port, "doctor", user, "tools/call",
                      {"name": "add_memory", "arguments": {"text": probe_text}})
            found = _mcp_call(args.host, args.port, "doctor", user, "tools/call",
                              {"name": "search_memories",
                               "arguments": {"query": "round-trip probe"}})
            probe_ok = "probe" in _json.dumps(found.get("result", {}))
        except Exception:
            probe_ok = False
        checks.append((bool(probe_ok), "write→search round trip (probe scope)",
                       "writes are queued but not searchable — check server logs: "
                       f"{log_path()}", True))

    failed = 0
    for ok, line, hint, hard in checks:
        mark = "✓" if ok else ("✗" if hard else "!")
        print(f"  {mark} {line}")
        if not ok:
            failed += 1 if hard else 0
            print(f"      → {hint}")
    verdict = "healthy — safe to rely on" if not failed else \
        f"{failed} problem(s) — memory may be silently absent until fixed"
    print(f"\ndoctor: {verdict}")
    if failed:
        sys.exit(1)


def cmd_migrate_scope(args: argparse.Namespace) -> None:
    import json as _json

    from .migrate import migrate_scope

    receipt = migrate_scope(
        from_app=args.from_app,
        to_app=args.to_app,
        user=args.user,
        claim_null_user=args.claim_null_user,
        db_path=args.db,
        apply=args.apply,
    )
    print(_json.dumps(receipt, ensure_ascii=False, indent=1))
    if not args.apply:
        print("\n(dry-run — re-run with --apply to write. A receipt will be saved next to the database.)")


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
    doc = sub.add_parser(
        "doctor",
        help="end-to-end health check: server, MCP, store, scope, agent hooks",
        parents=[shared],
    )
    doc.add_argument("--probe", action="store_true",
                     help="also run a write→search round trip in a dedicated probe scope")
    mig = sub.add_parser(
        "migrate-scope",
        help="merge a legacy app pool into its canonical successor (dry-run by default)",
        parents=[shared],
    )
    mig.add_argument("--from-app", required=True, help="legacy app_id to migrate away from")
    mig.add_argument("--to-app", required=True, help="canonical app_id to merge into")
    mig.add_argument("--user", help="restrict to one user_id")
    mig.add_argument(
        "--claim-null-user",
        help="explicitly assign ownerless (user_id IS NULL) records in the affected pools to this user",
    )
    mig.add_argument("--db", help="database path (default: the running server's database)")
    mig.add_argument("--apply", action="store_true", help="write changes; without this flag nothing is modified")
    args = parser.parse_args(argv)
    command = args.command or "run"
    {"run": cmd_run,
     "install-service": cmd_install_service,
     "uninstall-service": cmd_uninstall_service,
     "status": cmd_status,
     "doctor": cmd_doctor,
     "migrate-scope": cmd_migrate_scope}[command](args)


if __name__ == "__main__":
    main()
