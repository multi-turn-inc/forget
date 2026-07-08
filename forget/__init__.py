"""forget — memory for your AI. It forgets the junk, keeps what matters.

The engine stores durable facts, retrieves them newest-first, retires stale
ones non-destructively (supersede), and runs a verification loop so the
memory keeps proving itself. The secret is the forgetting: an observation
gate decides what is worth keeping at all.
"""
from __future__ import annotations

import os

__version__ = "0.1.0"

# Environment compatibility shim: the engine historically reads MEM1_*
# variables. FORGET_* is the public spelling; either works — FORGET_* fills
# in only where the MEM1_* twin is unset.
for _key, _value in list(os.environ.items()):
    if _key.startswith("FORGET_"):
        os.environ.setdefault("MEM1_" + _key[len("FORGET_"):], _value)
