"""Injection seams for hosted concerns.

The open-source core is single-tenant and quota-free by default. A hosted
deployment can replace these hooks at startup to plug in billing and
multi-tenant session auth without the core importing either.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

# --- quota ------------------------------------------------------------------

def _no_quota(project_id: str, operation: str, auth_context: dict[str, Any] | None = None) -> None:
    return None

enforce_project_quota: Callable[..., None] = _no_quota

# --- tenancy / sessions -----------------------------------------------------

def _no_org(project_id: str) -> Optional[str]:
    return None

def _no_session(token: str, project_id: str | None = None, org_id: str | None = None) -> Optional[dict[str, Any]]:
    return None

def _no_csrf(request: Any) -> None:
    return None

project_org_id: Callable[[str], Optional[str]] = _no_org
session_context_for_token: Callable[..., Optional[dict[str, Any]]] = _no_session
validate_csrf_for_cookie_request: Callable[[Any], None] = _no_csrf


def install(**hooks: Callable[..., Any]) -> None:
    """Replace any of the default hooks (used by hosted deployments)."""
    g = globals()
    for name, fn in hooks.items():
        if name not in g:
            raise KeyError(f"unknown port: {name}")
        g[name] = fn
