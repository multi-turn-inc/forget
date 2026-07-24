"""forget — memory for your AI. It forgets the junk, keeps what matters.

The engine stores durable facts, retrieves them newest-first, retires stale
ones non-destructively (supersede), and runs a verification loop so the
memory keeps proving itself. The secret is the forgetting: an observation
gate decides what is worth keeping at all.
"""
from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version as _package_version

# Single source of truth is the installed distribution (pyproject version).
# A hardcoded string here shipped as "0.1.0" for three releases running —
# issue #5's "which server am I even talking to?" wart.
try:
    __version__ = _package_version("forget-ai")
except PackageNotFoundError:  # source tree without an installed dist
    __version__ = "0.0.0+source"

# Environment compatibility shim: the engine historically reads MEM1_*
# variables. FORGET_* is the public spelling; either works — FORGET_* fills
# in only where the MEM1_* twin is unset.
for _key, _value in list(os.environ.items()):
    if _key.startswith("FORGET_"):
        os.environ.setdefault("MEM1_" + _key[len("FORGET_"):], _value)
