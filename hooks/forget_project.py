#!/usr/bin/env python3
"""Project identity for hooks: which repo is this session working in?

Design principle (2026-08-01): a scope the user has to declare is a scope that
fails. Our two worst scope bugs were fragmentation (one topic scattered across
five pools, so search missed it) and contamination (339 demo rows living
alongside live memory, F4). Asking the user to create and select a project
scope hands both diseases to the user. So the boundary is DETECTED, never
configured — every hook already receives `cwd`, and the git repository root is
the project.

Layering, not splitting: one store, two layers distinguished by metadata.
Splitting into separate pools would re-introduce fragmentation by construction.

- metadata.project     — origin key, always attached on write (provenance)
- metadata.scope_layer — "global" | "project" (which layer recall reads)

Recall then reads: this project's rows + everything global + everything
untagged. Untagged-means-global is what keeps every pre-existing memory
visible, so turning this on changes nothing until new writes land.

Stdlib only, and no imports from the `forget` package: the hooks are deployed
as standalone scripts under ~/.forget/hooks/ and run with the system python.
"""

from __future__ import annotations

import configparser
import json
import os
import re

CONFIG_PATH = os.path.expanduser("~/.forget/projects.json")
KEY_MAX_LEN = 40

# Directories that hold projects instead of being one. Keying off them would
# file unrelated work under "documents" — fragmentation's other direction.
_CONTAINER_NAMES = {
    "code",
    "desktop",
    "dev",
    "documents",
    "downloads",
    "git",
    "projects",
    "repos",
    "src",
    "tmp",
    "work",
    "workspaces",
}

# Crude v1 classifier (same spirit as the mechanical-echo-v1 outcome labeler:
# its job is to start the flywheel, not to be right). A fact about the user
# themself outlives any single repo; everything else stays with its repo.
# The default is deliberately "project": global contamination costs more than
# a project-local miss, and the miss is recoverable by asking across projects.
_GLOBAL_PATTERNS = (
    r"(?:나는|내가|제가|정훈은|정훈이|사용자는|유저는)[^.\n]{0,40}"
    r"(?:선호|좋아|싫어|원해|원한다|스타일|성향|습관|정체성|목표|철학)",
    r"\b(?:i|my)\b[^.\n]{0,40}\b(?:prefer|preference|always|never|habit|style|identity)\b",
    r"(?:모든 프로젝트|어느 프로젝트|어디서나|프로젝트 무관|전역|전체적으로)",
    r"\b(?:globally|across (?:all )?projects|regardless of (?:the )?project)\b",
)

# Explicit permission to cross the boundary. Recall stays inside the current
# project unless the user asks to look elsewhere — the boundary doubles as a
# privacy gate (the other company's strategy must not leak into this session's
# capsule), so crossing has to be asked for, and is flagged when it happens.
_CROSS_PROJECT_PATTERNS = (
    r"다른 (?:프로젝트|레포|repo|회사)",
    r"(?:프로젝트|레포)(?:들)? ?(?:전체|전부|통틀어|건너|넘어)",
    r"(?:다른 곳|딴 데|저쪽)에서",
    r"\b(?:other|another|across|all) (?:project|projects|repo|repos|repositories)\b",
    r"\b(?:everywhere|any project)\b",
)


def _config() -> dict:
    """Optional overrides: {"aliases": {...}, "ignore": [...]}.

    The escape hatch for the one case detection cannot resolve on its own —
    two repositories that share a name. Nobody needs to write this file for
    the common case.
    """
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            config = json.load(fh)
        return config if isinstance(config, dict) else {}
    except Exception:
        return {}


def _slug(raw: str) -> str:
    """Readable, stable key. Unicode word chars survive — a Korean directory
    name is a perfectly good key, and transliterating would only obscure it."""
    slug = re.sub(r"[^\w.-]+", "-", str(raw).strip(), flags=re.UNICODE).strip("-._")
    return slug.lower()[:KEY_MAX_LEN]


def _git_common_dir(start: str) -> str | None:
    """The shared .git of the repo containing `start`, worktrees included.

    The worktree case is the trap: this very session runs in an Orca worktree
    whose directory is named after a throwaway branch topic, while the same
    repo is also checked out at ~/Documents/forget. Keying off the worktree
    directory would file the same project under two keys — fragmentation
    again. Resolving to the common .git collapses them.
    """
    current = os.path.realpath(start)
    while True:
        candidate = os.path.join(current, ".git")
        if os.path.isdir(candidate):
            return candidate
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    pointer = fh.read().strip()
            except OSError:
                return None
            if pointer.startswith("gitdir:"):
                path = pointer.split(":", 1)[1].strip()
                if not os.path.isabs(path):
                    path = os.path.join(current, path)
                path = os.path.realpath(path)
                marker = os.sep + "worktrees" + os.sep
                if marker in path:
                    path = path.split(marker)[0]
                return path
            return None
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def _origin_url(common_dir: str) -> str:
    parser = configparser.ConfigParser(strict=False)
    try:
        parser.read(os.path.join(common_dir, "config"), encoding="utf-8")
    except Exception:
        return ""
    for section in ('remote "origin"', "remote origin"):
        if parser.has_option(section, "url"):
            return str(parser.get(section, "url") or "").strip()
    return ""


def repo_identity(url: str) -> str:
    """github.com/owner/repo, scheme- and suffix-free, for alias lookups."""
    identity = re.sub(r"^[a-z+]+://", "", url.strip(), flags=re.IGNORECASE)
    identity = re.sub(r"^[^/@]+@", "", identity)  # git@host:owner/repo
    identity = identity.replace(":", "/", 1) if "/" not in identity.split(":")[0] else identity
    identity = re.sub(r"\.git/?$", "", identity).rstrip("/")
    return identity.lower()


def project_key_for_path(path: str | None) -> str | None:
    """The project key for a working directory, or None for "no project".

    None means global-only: a session started in $HOME or some scratch
    directory has no project to be about, and inventing one there would
    scatter memories across as many keys as the user has stray folders.
    """
    if not path:
        return None
    real = os.path.realpath(path)
    config = _config()
    aliases = config.get("aliases") if isinstance(config.get("aliases"), dict) else {}
    ignore = {str(item).lower() for item in (config.get("ignore") or []) if str(item)}

    common_dir = _git_common_dir(real)
    identity = ""
    if common_dir:
        identity = repo_identity(_origin_url(common_dir))
        if identity:
            raw = identity.rsplit("/", 1)[-1]
        else:
            # No remote: the repo directory itself names the project. Use the
            # common .git's parent, not cwd — same worktree reason as above.
            repo_root = os.path.dirname(common_dir.rstrip(os.sep))
            raw = os.path.basename(repo_root)
    else:
        if real in (os.path.realpath(os.path.expanduser("~")), os.sep):
            return None
        raw = os.path.basename(real)
        if raw.lower() in _CONTAINER_NAMES:
            return None

    for candidate in (identity, raw):
        if candidate and str(aliases.get(candidate) or "").strip():
            return _slug(aliases[candidate])
    key = _slug(raw)
    if not key or key in ignore:
        return None
    return key


def layered_filter(project_key: str | None) -> dict | None:
    """Recall filter: this project + the global layer + everything untagged."""
    if not project_key:
        return None
    return {
        "OR": [
            {"metadata.project": project_key},
            {"metadata.project": None},  # written before layering existed
            {"metadata.scope_layer": "global"},
        ]
    }


def classify_layer(text: str) -> str:
    """"global" for facts about the user themself, else "project"."""
    body = str(text or "")
    for pattern in _GLOBAL_PATTERNS:
        if re.search(pattern, body, flags=re.IGNORECASE | re.UNICODE):
            return "global"
    return "project"


def wants_cross_project(prompt: str) -> bool:
    body = str(prompt or "")
    return any(re.search(p, body, flags=re.IGNORECASE | re.UNICODE) for p in _CROSS_PROJECT_PATTERNS)


def scope_disabled() -> bool:
    return str(os.environ.get("FORGET_PROJECT_SCOPE", "")).strip().lower() in {"0", "off", "false"}
