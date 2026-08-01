"""Update awareness without a phone-home habit.

Early-stage reality (2026-08-01): patches land weekly and a stale server
doesn't just miss features — it silently drops arguments newer hooks send
(the 0.3.7/0.5.0 mismatch shipped exactly that bug class). The cure has to
respect the product's identity: memory that never leaves the machine.

Contract:
- The network is touched ONLY when the user runs `doctor`/`status`/`upgrade`
  — never from hooks, never from the server, never on a timer.
- One request, version metadata only, cached 24h in ~/.forget/.
- `FORGET_UPDATE_CHECK=off` disables even that.
- Hooks may READ the cache (a local file) to surface "0.3.9 나옴" in the
  session capsule, but they never refresh it.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/forget-ai/json"
CACHE_TTL_SECONDS = 24 * 3600
REQUEST_TIMEOUT_SECONDS = 3


def _cache_path() -> Path:
    home = Path(os.environ.get("FORGET_HOME") or Path.home() / ".forget")
    return home / "update-check.json"


def check_disabled() -> bool:
    return str(os.environ.get("FORGET_UPDATE_CHECK", "")).strip().lower() in {"0", "off", "false", "no"}


def read_cached_latest() -> str:
    """The cache-only read used by hooks: a local file, never the network."""
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return str(data.get("latest") or "")
    except Exception:
        return ""


def fetch_latest(force: bool = False) -> str:
    """Latest released version, at most one PyPI request per 24h. '' on any failure."""
    if check_disabled():
        return ""
    cache = _cache_path()
    if not force:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if time.time() - float(data.get("checked_at") or 0) < CACHE_TTL_SECONDS:
                return str(data.get("latest") or "")
        except Exception:
            pass
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            latest = str(json.load(response)["info"]["version"])
    except Exception:
        return ""
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"latest": latest, "checked_at": time.time()}), encoding="utf-8")
    except Exception:
        pass
    return latest


def parse_version(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(value or "").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def is_older(current: str, latest: str) -> bool:
    if not current or not latest:
        return False
    return parse_version(current) < parse_version(latest)


def update_line(current: str, latest: str) -> str:
    """One line, verdict plus prescription — the doctor house style."""
    if not latest:
        return ""
    if is_older(current, latest):
        return f"version: {current} → {latest} available — upgrade: forget-server upgrade"
    return f"version: {current} (latest)"
