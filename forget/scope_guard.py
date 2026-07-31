"""Write-time scope guard — the F4 recurrence check.

F4 (2026-07-31) soft-deleted 339 memories that demo seed scripts and an
experiment burst had written into the dogfood store under foreign pools
(demo-redis×demo, demo-fastapi×demo, offreco×…). The write path accepted
any (user_id, app_id) pair without question, so a new pool could be born
by one stray request; doctor's "scope clean" check could only report the
contamination after the fact.

Scope isolation is a product feature — per-context pools are a legitimate
use — so the guard is a mode, not a rule:

  off      — current behavior, no check
  warn     — the write proceeds, but a foreign-pool write is stamped
             metadata.scope_guard="foreign" (cleanup becomes one query)
             and the response carries an in-band warning
  enforce  — a foreign-pool write is rejected with the remedy in the error
             (allowlist the scope, or point demos at a dedicated instance)

The canonical pool and the allowlist are shared with doctor's
foreign_pools() so the write-time verdict and the health check can never
drift apart.
"""
from __future__ import annotations

import os

MODES = ("off", "warn", "enforce")


def guard_mode() -> str:
    mode = (os.getenv("MEM1_SCOPE_GUARD") or "").strip().lower()
    return mode if mode in MODES else "warn"


def default_owner() -> str:
    """The store's single-tenant owner — same derivation as the MCP default scope."""
    configured = (os.getenv("MEM1_MCP_DEFAULT_USER_ID") or "").strip()
    if configured:
        return configured
    try:
        import getpass

        username = getpass.getuser().strip()
    except Exception:
        username = ""
    return username or "local"


CANONICAL_APP_ID = "forget"


def allowed_scopes() -> list[tuple[str, str]]:
    """Extra permitted pools: MEM1_ALLOWED_SCOPES="user:app,user2:*"."""
    raw = os.getenv("MEM1_ALLOWED_SCOPES") or ""
    pairs: list[tuple[str, str]] = []
    for item in raw.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        user, _, app = item.partition(":")
        pairs.append((user.strip(), app.strip()))
    return pairs


def is_allowed_pool(user_id: str | None, app_id: str | None, owner: str | None = None) -> bool:
    owner = owner if owner is not None else default_owner()
    user = (user_id or "").strip()
    app = (app_id or "").strip()
    if user == owner and app == CANONICAL_APP_ID:
        return True
    for allowed_user, allowed_app in allowed_scopes():
        if allowed_user in ("*", user) and allowed_app in ("*", app):
            return True
    return False


def evaluate_write_scope(user_id: str | None, app_id: str | None) -> str | None:
    """None if the write may land silently; otherwise why the pool is foreign."""
    if guard_mode() == "off":
        return None
    if is_allowed_pool(user_id, app_id):
        return None
    owner = default_owner()
    pool = f"{(user_id or '∅')}×{(app_id or '∅')}"
    return (
        f"scope guard: write landed in foreign pool {pool} — canonical is "
        f"{owner}×{CANONICAL_APP_ID}. If intentional, allowlist it "
        f"(MEM1_ALLOWED_SCOPES='{user_id or '*'}:{app_id or '*'}'); demos and "
        "experiments belong on a dedicated instance (FORGET_HOME=<dir>)."
    )
