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

from . import scope_guard

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
    pools: list[tuple[str, str, int]], user: str
) -> list[tuple[str, str, int]]:
    """Pools that shouldn't live in this store — the F4 class of contamination.

    Shares its verdict with the write-time guard (scope_guard): a pool the
    guard admits (canonical or MEM1_ALLOWED_SCOPES) is never flagged here.
    """
    return [p for p in pools if not scope_guard.is_allowed_pool(p[0], p[1], owner=user)]


def _installed_version() -> str:
    try:
        from importlib.metadata import version
        return version("forget-ai")
    except Exception:
        return "unknown"


def _version_newer(candidate: str, current: str) -> bool:
    """True if candidate > current, comparing dotted integer parts."""
    def parts(v: str) -> list[int]:
        out = []
        for piece in v.split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            out.append(int(digits) if digits else 0)
        return out
    return parts(candidate) > parts(current)


def _pypi_latest(timeout: float = 3.0) -> str:
    """Latest published version, or '' when offline. Content-free request:
    nothing about the user or their memories leaves the machine — the same
    bytes pip itself would send. Never automatic: only runs inside the
    user-invoked doctor, and only ever *notifies* (apply stays in user hands).
    """
    import json as _json
    import urllib.request
    try:
        with urllib.request.urlopen("https://pypi.org/pypi/forget-ai/json",
                                    timeout=timeout) as response:
            return str(_json.load(response)["info"]["version"])
    except Exception:
        return ""


FALLBACK_STACK = {"deterministic-128", "rule-extractor", "lexical-v1"}


def stack_summary(settings: dict[str, Any]) -> tuple[str, bool]:
    """One line naming the memory stack, and whether any fallback is engaged.

    The LME-V2 lesson: the hash-embedding fallback ran a full benchmark
    without anyone noticing, because nothing ever *said* which stack was
    active. Identity is DB + scope + provider stack — so doctor names it.
    """
    emb = str(settings.get("embedding_model") or "?")
    llm = str(settings.get("llm_model") or "?")
    fallback = emb in FALLBACK_STACK or llm in FALLBACK_STACK
    return f"embedding={emb} · extractor={llm}", fallback


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
    if mcp_ok:
        try:
            cat = _mcp_call(args.host, args.port, "forget", user, "tools/call",
                            {"name": "get_provider_catalog", "arguments": {}})
            import json as _json2
            payload = _json2.loads(cat["result"]["content"][0]["text"])
            effective = payload.get("effective") or {}
            merged = dict(payload.get("settings", {}))
            if effective.get("embedding_model"):
                merged["embedding_model"] = effective["embedding_model"]
            line, fallback = stack_summary(merged)
            checks.append((not fallback, f"memory stack: {line}",
                           "semantic recall is OFF (hash fallback). Fix: "
                           "pip install -U 'forget-ai[server]' && forget-server reembed "
                           "— backup and receipt are automatic, then restart the service.",
                           False))
        except Exception:
            pass

    # Advisory, not failure: staying current is a choice, but a stale server
    # silently drops arguments newer hooks send — say so with a prescription.
    from . import updatecheck

    installed = _installed_version()
    latest = updatecheck.fetch_latest()
    if latest:
        checks.append((not updatecheck.is_older(installed, latest),
                       updatecheck.update_line(installed, latest),
                       "newer hooks against an older server lose features silently — "
                       "one command fixes it: forget-server upgrade",
                       False))

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
    report_lines: list[str] = []
    for ok, line, hint, hard in checks:
        mark = "✓" if ok else ("✗" if hard else "!")
        print(f"  {mark} {line}")
        report_lines.append(f"{mark} {line}")
        if not ok:
            failed += 1 if hard else 0
            print(f"      → {hint}")
            report_lines.append(f"    fix: {hint}")

    current = _installed_version()
    latest = _pypi_latest() if current != "unknown" else ""
    if latest and _version_newer(latest, current):
        print(f"  ! update available: {current} → {latest}   "
              f"(apply when you choose: pip install -U forget-ai)")
        report_lines.append(f"! update available: {current} -> {latest}")

    verdict = "healthy — safe to rely on" if not failed else \
        f"{failed} problem(s) — memory may be silently absent until fixed"
    print(f"\ndoctor: {verdict}")

    if getattr(args, "report", False):
        # Diagnostic bundle. Hard rule: zero memory content. The user sees
        # exactly what would be sent, and sending stays a human act.
        import platform
        bundle = [
            f"forget diagnostic bundle — {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
            f"version: forget-ai {current} · python {platform.python_version()} · {platform.platform()}",
            f"verdict: {verdict}",
            "", "checks:", *report_lines,
            "", f"pools (counts only): {[(u, a, n) for u, a, n in pools]}",
        ]
        log = log_path()
        if log.exists():
            tail = log.read_text(errors="replace").splitlines()[-40:]
            bundle += ["", f"server log tail ({log}) — REVIEW BEFORE SENDING:", *tail]
        out = forget_home() / f"diagnostic-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.txt"
        out.write_text("\n".join(bundle), encoding="utf-8")
        print(f"\nreport: {out}")
        print("        contains versions, check results, pool counts, log tail —")
        print("        no memory content. Read it, then send it yourself.")

    if failed:
        sys.exit(1)


def weekly_digest(path: Path, user: str, days: int = 7) -> dict[str, Any]:
    """What memory did for you this week — counts only, never content.

    The perceived-value device for the quiet early days (field report #2):
    accumulation and refusals are invisible by design, so this makes the
    invisible countable without making it public.
    """
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    since = f"-{days} days"
    try:
        added, corrected, verified = conn.execute(
            """SELECT COUNT(*),
                      SUM(CASE WHEN metadata LIKE '%superseded_at%' THEN 1 ELSE 0 END),
                      SUM(CASE WHEN metadata LIKE '%verified_at%' THEN 1 ELSE 0 END)
               FROM memories
               WHERE deleted = 0 AND user_id = ? AND app_id = 'forget'
                 AND created_at >= datetime('now', ?)""",
            (user, since),
        ).fetchone()
        refusals = conn.execute(
            """SELECT reason, COUNT(*) FROM gate_log
               WHERE created_at >= datetime('now', ?)
                 AND (user_id = ? OR user_id IS NULL)
               GROUP BY reason ORDER BY COUNT(*) DESC""",
            (since, user),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM memories WHERE deleted = 0 AND user_id = ? AND app_id = 'forget'",
            (user,),
        ).fetchone()[0]
    finally:
        conn.close()
    return {
        "added": int(added or 0),
        "corrected": int(corrected or 0),
        "verified": int(verified or 0),
        "refusals": [(str(r), int(n)) for r, n in refusals],
        "total": int(total or 0),
    }


def cmd_weekly(args: argparse.Namespace) -> None:
    import getpass

    user = os.environ.get("MEM1_MCP_DEFAULT_USER_ID") or getpass.getuser()
    path = db_path()
    if not path.exists():
        print("weekly: no store yet — it is born on first write")
        return
    digest = weekly_digest(path, user)
    print(f"this week, your memory ({user}):")
    print(f"  + {digest['added']} memories kept"
          + (f" ({digest['verified']} verified)" if digest["verified"] else ""))
    if digest["corrected"]:
        print(f"  ✎ {digest['corrected']} corrected — old versions kept as history, not truth")
    refused = sum(n for _, n in digest["refusals"])
    if refused:
        top = ", ".join(f"{r}×{n}" for r, n in digest["refusals"][:3])
        print(f"  ⛔ {refused} refused at the gate ({top}) — what almost got remembered, and didn't")
    print(f"  = {digest['total']} memories total, all on this machine")


def cmd_reembed(args: argparse.Namespace) -> None:
    """Re-embed every live memory with the currently active embedding stack.

    The one-word migration for stores born on the hash fallback: backup is
    automatic, progress is visible, a receipt lands next to the database.
    Search tolerates mixed dimensions meanwhile, so running this live is safe.
    """
    import json
    import shutil

    path = db_path()
    # embed_text reads project settings from the store get_db points at —
    # pin it to the same database we are re-embedding (first live run failed
    # here: unset env → wrong settings DB → "no such table: projects").
    os.environ.setdefault("MEM1_DB_PATH", str(path))
    from .providers import embed_text

    if not path.exists():
        sys.exit("reembed: no store yet — nothing to do")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.pre-reembed-{stamp}{path.suffix}")
    shutil.copy2(path, backup)
    print(f"backup: {backup}")

    probe = embed_text("dimension probe", role="query")
    conn = sqlite3.connect(path, timeout=30)
    try:
        rows = conn.execute(
            "SELECT id, memory FROM memories WHERE deleted = 0"
        ).fetchall()
        total, done, skipped = len(rows), 0, 0
        print(f"re-embedding {total} memories → {len(probe)}-dim active stack")
        for mid, text in rows:
            try:
                vec = embed_text(str(text or ""))
            except Exception:
                skipped += 1
                continue
            conn.execute("UPDATE memories SET embedding = ? WHERE id = ?",
                         (json.dumps(vec), mid))
            done += 1
            if done % 100 == 0:
                conn.commit()
                print(f"  {done}/{total}", flush=True)
        conn.commit()
    finally:
        conn.close()
    receipt_dir = path.parent / "migrations"
    receipt_dir.mkdir(exist_ok=True)
    receipt = receipt_dir / f"reembed-{stamp}.json"
    receipt.write_text(json.dumps({
        "migration": "reembed", "date": stamp, "dimensions": len(probe),
        "total": total, "reembedded": done, "skipped": skipped,
        "backup": str(backup),
    }, indent=1))
    print(f"done: {done}/{total} re-embedded ({skipped} skipped) · receipt: {receipt}")
    print("restart the server to pick up a consistent search index: "
          "launchctl kickstart -k gui/$(id -u)/ai.forget.server" if sys.platform == "darwin"
          else "restart the server now")


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
    from . import updatecheck

    line = updatecheck.update_line(_installed_version(), updatecheck.fetch_latest())
    if line:
        print(line)
    if sys.platform == "darwin":
        plist, _ = _launchd_paths()
        print(f"service: {'installed' if plist.exists() else 'not installed'} ({plist})")
    elif sys.platform.startswith("linux"):
        unit = Path.home() / ".config" / "systemd" / "user" / "forget-server.service"
        print(f"service: {'installed' if unit.exists() else 'not installed'} ({unit})")
    if not listening:
        sys.exit(1)


def cmd_upgrade(args: argparse.Namespace) -> None:
    """One command from "stale" to "verified current": pip -U → service
    restart → doctor. Every version warning in the product prescribes this,
    so it has to leave the user in a *checked* state, not just a newer one."""
    from . import updatecheck

    before = _installed_version()
    print(f"upgrading forget-ai (installed: {before})…")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "forget-ai[server]"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        sys.exit("pip upgrade failed:\n  " + "\n  ".join(tail))
    after = subprocess.run(
        [sys.executable, "-c", "from importlib.metadata import version; print(version('forget-ai'))"],
        capture_output=True, text=True,
    ).stdout.strip() or "unknown"
    print(f"installed: {before} → {after}")

    restarted = False
    if sys.platform == "darwin":
        plist, domain = _launchd_paths()
        if plist.exists():
            subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{SERVICE_LABEL}"], capture_output=True)
            restarted = True
    elif sys.platform.startswith("linux"):
        unit = Path.home() / ".config" / "systemd" / "user" / "forget-server.service"
        if unit.exists():
            subprocess.run(["systemctl", "--user", "restart", "forget-server.service"], capture_output=True)
            restarted = True
    print("service: restarted" if restarted else "service: not installed — restart your `forget-server run` terminal")

    updatecheck.fetch_latest(force=True)  # refresh the cache so capsules stop nagging
    print()
    try:
        cmd_doctor(args)
    except SystemExit:
        raise
    except Exception:
        print("doctor skipped (run `forget-server doctor` to verify)")


_GEARS = ["low", "medium", "high", "extra"]


def _dial_line(current: str) -> str:
    return "  ".join(f"[{g}]" if g == current else f" {g} " for g in _GEARS)


def cmd_recall(args) -> None:
    """The dial's home: see what gear you're in, change it, wire an LLM."""
    from .db import init_db

    init_db()
    from .providers import get_project_settings, update_project_settings
    from .store import _resolve_recall_llm

    if args.action == "use":
        gear = str(args.value or "").strip().lower()
        if gear in {"+", "-"}:
            current = str(get_project_settings("proj_local").get("recall_default") or "low")
            index = _GEARS.index(current) if current in _GEARS else 0
            index = min(index + 1, len(_GEARS) - 1) if gear == "+" else max(index - 1, 0)
            gear = _GEARS[index]
        if gear not in _GEARS:
            print("usage: forget recall use <low|medium|high|extra|+|->")
            return
        update_project_settings("proj_local", {"recall_default": gear})
        print(_dial_line(gear))
        if gear in {"high", "extra"} and not _resolve_recall_llm():
            print("note: no recall LLM available — high/extra will quietly fall back to instant search.")
            print("      attach one:  forget recall llm --base-url http://127.0.0.1:11434/v1 --model <name>")
        return

    if args.action == "engine":
        choice = str(args.value or "").strip().lower()
        if choice not in {"auto", "local", "byo"}:
            print("usage: forget recall engine <auto|local|byo>")
            print("  auto  : local runtime first, stored endpoint as fallback")
            print("  local : only a local runtime (Ollama/LM Studio) — free, private")
            print("  byo   : only the stored endpoint (forget recall llm ...)")
            return
        update_project_settings("proj_local", {"recall_engine": choice})
        resolved = _resolve_recall_llm()
        if resolved:
            print(f"engine → {choice}  ({resolved['model']} @ {resolved['base_url']})")
        else:
            print(f"engine → {choice}  (no LLM available yet — deep recall falls back to instant search)")
        return

    if args.action == "llm":
        if args.clear:
            update_project_settings("proj_local", {"recall_llm": {}})
            print("stored recall LLM cleared — will auto-attach a local runtime if one is running")
            return
        if not args.base_url or not args.model:
            print("usage: forget recall llm --base-url <url> --model <name> [--api-key-file <path>]")
            return
        config = {"base_url": args.base_url, "model": args.model}
        if args.api_key_file:
            config["api_key_file"] = args.api_key_file
        update_project_settings("proj_local", {"recall_llm": config})
        print(f"recall LLM → {args.model} @ {args.base_url}")
        return

    settings = get_project_settings("proj_local")
    gear = settings.get("recall_default") or "low"
    engine = settings.get("recall_engine") or "auto"

    def _ram_gb() -> int:
        try:
            import subprocess
            if sys.platform == "darwin":
                return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) // (1 << 30)
            with open("/proc/meminfo") as f:
                return int(f.readline().split()[1]) // (1 << 20)
        except Exception:
            return 0

    def _local_tier(ram: int) -> str:
        if ram >= 64:
            return "26~32B (클라우드 초과 품질)"
        if ram >= 32:
            return "14B"
        if ram >= 16:
            return "8~9B (현 클라우드와 동급)"
        if ram >= 8:
            return "3~4B — 또는 forget cloud (발열 없이 최고 품질)"
        return "forget cloud 권장"
    llm = _resolve_recall_llm()
    print(f"dial          : {_dial_line(str(gear))}")
    if llm:
        window = int(llm.get("context_window") or 131072)
        window_note = f", ctx {window//1024}k" if window < 32768 else ""
        print(f"engine        : {engine} → {llm['source']} ({llm['model']}{window_note})")
        if window < 32768:
            print("deep recall   : ready — 작은 컨텍스트 창에 맞춰 후보 수 자동 축소")
        else:
            print("deep recall   : ready — high (~3s, reads 40 candidates) / extra (~5s, reads 100)")
    else:
        print(f"engine        : {engine} → none")
    if llm is None:
        print("deep recall   : off — instant search only. Two ways to turn it on:")
        print("  · run a local LLM (Ollama or LM Studio) — free, forget attaches automatically")
        print("  · or use forget cloud — deep recall without heating your laptop (coming soon)")
    if llm is None or llm.get("source") not in ("ollama", "lm-studio"):
        ram = _ram_gb()
        if ram:
            print(f"local 추천    : 이 머신(RAM {ram}GB) → {_local_tier(ram)}  (추천일 뿐 — 상한 없음)")


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
    doc.add_argument("--report", action="store_true",
                     help="write a diagnostic bundle (no memory content) to ~/.forget "
                          "for you to review and send yourself")
    sub.add_parser("upgrade", help="pip upgrade + service restart + doctor, in one command",
                   parents=[shared])
    sub.add_parser("weekly", help="what memory did this week — counts only, never content",
                   parents=[shared])
    sub.add_parser("reembed", help="re-embed all memories with the active embedding stack "
                                   "(automatic backup + receipt)", parents=[shared])
    rec = sub.add_parser(
        "recall",
        help="show or set the recall budget dial (low/medium/high/extra) and its LLM",
        parents=[shared],
    )
    rec.add_argument("action", nargs="?", default="status", choices=["status", "use", "llm", "engine"],
                     help="status: show gear + engine; use: set default gear; llm: set BYO endpoint; engine: auto|local|byo")
    rec.add_argument("value", nargs="?", help="gear for 'use': low|medium|high|extra, or +/- to step")
    rec.add_argument("--base-url", help="OpenAI-compatible endpoint for 'llm' (e.g. http://127.0.0.1:11434/v1)")
    rec.add_argument("--model", help="model name for 'llm'")
    rec.add_argument("--api-key-file", help="path to a file holding the API key (kept out of config)")
    rec.add_argument("--clear", action="store_true", help="with 'llm': remove the stored recall LLM")
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
     "upgrade": cmd_upgrade,
     "weekly": cmd_weekly,
     "reembed": cmd_reembed,
     "recall": cmd_recall,
     "migrate-scope": cmd_migrate_scope}[command](args)


if __name__ == "__main__":
    main()
