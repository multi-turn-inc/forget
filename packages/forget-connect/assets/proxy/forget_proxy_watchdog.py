#!/usr/bin/env python3
"""forget proxy health watchdog — de-wires a dead proxy before it hurts.

Runs every minute under launchd (ai.forget.proxy.watchdog). The capture
proxy sits in front of every Claude Code request via the ANTHROPIC_BASE_URL
override in ~/.claude/settings.json; if the proxy dies and KeepAlive cannot
resurrect it, that override would take the user's Claude down with it. The
deal is the reverse: the product must never die for the sake of capture —
losing memory is cheaper than losing the tool.

Behavior (proxy-native redesign §1, defense ③):
  * probe GET {proxy}/healthz; after N consecutive failures (default 3),
    remove the settings.json override — but only when the current value is
    the one *we* wrote — restoring the user's original base URL if connect
    chained one. Every transition lands in a state file.
  * when the proxy answers again, re-install the override — but only onto
    the exact state the withdrawal left behind. A value the user changed in
    the meantime is theirs; we never overwrite it.

Standard library only. Configuration comes from the environment:
  FORGET_HOME                  state root      (default ~/.forget)
  FORGET_CLAUDE_SETTINGS       settings.json   (default ~/.claude/settings.json)
  FORGET_PROXY_FAIL_THRESHOLD  N               (default 3)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_THRESHOLD = 3
PROBE_TIMEOUT_SECONDS = 3.0
ENV_KEY = "ANTHROPIC_BASE_URL"


def forget_home() -> Path:
    return Path(os.environ.get("FORGET_HOME", Path.home() / ".forget"))


def settings_path() -> Path:
    return Path(
        os.environ.get(
            "FORGET_CLAUDE_SETTINGS", Path.home() / ".claude" / "settings.json"
        )
    )


def wiring_path() -> Path:
    return forget_home() / "proxy" / "wiring.json"


def state_path() -> Path:
    return forget_home() / "proxy" / "watchdog-state.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def probe(proxy_url: str, timeout: float = PROBE_TIMEOUT_SECONDS) -> bool:
    try:
        with urllib.request.urlopen(
            proxy_url.rstrip("/") + "/healthz", timeout=timeout
        ) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _is_ours(value, proxy_url: str) -> bool:
    return isinstance(value, str) and value.rstrip("/") == proxy_url.rstrip("/")


def _read_settings(path: Path):
    """Return (config, verdict). 'broken' means: do not touch this file."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, "missing"
    except OSError:
        return None, "broken"
    if not raw.strip():
        return {}, "ok"
    try:
        config = json.loads(raw)
    except ValueError:
        return None, "broken"
    if not isinstance(config, dict):
        return None, "broken"
    return config, "ok"


def withdraw(settings_file: Path, proxy_url: str, original: str | None) -> str:
    """Remove our override; only ever the value we wrote.

    Returns 'withdrawn' | 'not_ours' | 'broken'.
    """
    config, verdict = _read_settings(settings_file)
    if verdict == "broken":
        return "broken"
    env = config.get("env")
    if not isinstance(env, dict) or not _is_ours(env.get(ENV_KEY), proxy_url):
        return "not_ours"
    if original:
        env[ENV_KEY] = original
    else:
        del env[ENV_KEY]
        if not env:
            del config["env"]
    _atomic_write(
        settings_file, json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    )
    return "withdrawn"


def rewire(settings_file: Path, proxy_url: str, original: str | None) -> str:
    """Re-install the override after recovery — only onto the exact state the
    withdrawal left behind (the original value, or absence). Anything else
    means the user intervened, and their value wins.

    Returns 'rewired' | 'already' | 'user_changed' | 'broken'.
    """
    config, verdict = _read_settings(settings_file)
    if verdict == "broken":
        return "broken"
    env = config.get("env")
    if env is None:
        env = {}
    if not isinstance(env, dict):
        return "broken"
    current = env.get(ENV_KEY)
    if _is_ours(current, proxy_url):
        return "already"
    expected = original if original else None
    if current != expected:
        return "user_changed"
    env[ENV_KEY] = proxy_url
    config["env"] = env
    _atomic_write(
        settings_file, json.dumps(config, indent=2, ensure_ascii=False) + "\n"
    )
    return "rewired"


def main() -> int:
    wiring = _load_json(wiring_path())
    if not isinstance(wiring, dict) or not wiring.get("proxy_url"):
        return 0  # not wired — nothing to guard
    proxy_url = str(wiring["proxy_url"])
    original = wiring.get("original_base_url")
    original = original if isinstance(original, str) and original else None
    try:
        threshold = int(os.environ.get("FORGET_PROXY_FAIL_THRESHOLD", DEFAULT_THRESHOLD))
    except ValueError:
        threshold = DEFAULT_THRESHOLD

    state = _load_json(state_path())
    if not isinstance(state, dict):
        state = {}
    failures = int(state.get("consecutive_failures") or 0)
    withdrawn = bool(state.get("withdrawn"))

    healthy = probe(proxy_url)
    now = _now()
    state["last_check"] = now
    state["healthy"] = healthy

    if healthy:
        state["consecutive_failures"] = 0
        state["last_ok"] = now
        if withdrawn:
            outcome = rewire(settings_path(), proxy_url, original)
            if outcome in ("rewired", "already"):
                state["withdrawn"] = False
            state["last_transition"] = {"at": now, "action": "rewire", "outcome": outcome}
    else:
        failures += 1
        state["consecutive_failures"] = failures
        if failures >= threshold and not withdrawn:
            outcome = withdraw(settings_path(), proxy_url, original)
            if outcome in ("withdrawn", "not_ours"):
                # not_ours: nothing of ours is installed, so there is also
                # nothing to keep retrying — recovery re-checks before writing.
                state["withdrawn"] = True
            state["last_transition"] = {"at": now, "action": "withdraw", "outcome": outcome}
            print(
                f"forget-proxy-watchdog: proxy unhealthy x{failures} — "
                f"override {outcome}",
                file=sys.stderr,
            )

    state_path().parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(state_path(), json.dumps(state, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
