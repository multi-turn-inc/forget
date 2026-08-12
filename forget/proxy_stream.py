"""Session/turn reconstruction over the forget-proxy capture stream.

forget-proxy (proxy.py) appends one JSON line per completed /v1/messages
exchange to ``~/.forget/proxy/stream/YYYY-MM-DD.jsonl``:
``{ts, session_hint, model, request_messages, response_content, usage,
latency_ms}``. Clients resend the *full* message history on every request,
so consecutive requests of one session share a prefix. This module folds
that redundancy back into sessions and turns — the delta-diff design of
research/proxy-native-redesign.md §2 — and adapts the result to the
Claude-Code transcript row shape the existing miners already consume.

Model:
  * session key — ``session_hint`` when present, else a fingerprint of the
    first system-role message in ``request_messages``, else "anon". One key
    can hold several threads (a system fingerprint is shared by every
    session of that client).
  * thread assignment — a request joins the thread whose canonical history
    it shares the longest (role, content-hash) prefix with. Sharing no
    prefix at all starts a new thread.
  * turns — messages beyond the common prefix are appended as new turns,
    then the row's ``response_content`` as an assistant turn.
  * forks — when the common prefix ends *inside* the canonical history
    (retry, context compaction), no merge is attempted: the current
    segment closes and a new one opens with ``fork_from`` = length of the
    shared prefix, i.e. the absolute turn index the branch grew from. The
    canonical history follows the new branch (the client's live view).

Everything here is read-only over the stream except ``purge_expired``,
which enforces the raw-stream TTL (design §3: raw lives short, distillates
persist) and never touches today's file.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# row parsing


def iter_stream_rows(stream_dir: Path, stats: dict[str, int] | None = None) -> Iterator[dict]:
    """Yield capture rows from every ``*.jsonl`` in ``stream_dir``, files in
    name order (date-named files sort chronologically), lines in append
    order — which is completion order, and within one session completion
    order equals conversation order because clients wait for each response.

    Broken rows — bad JSON, non-dict, or a missing/empty
    ``request_messages`` list — are skipped and counted in ``stats``
    ("broken"); good rows count as "rows". Pass a dict to observe the
    counts; ``reconstruct`` passes its own.
    """
    counters = stats if stats is not None else {}
    counters.setdefault("rows", 0)
    counters.setdefault("broken", 0)
    stream_dir = Path(stream_dir)
    if not stream_dir.is_dir():
        return
    for path in sorted(stream_dir.glob("*.jsonl")):
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except ValueError:
                        counters["broken"] += 1
                        continue
                    if not isinstance(row, dict) or not isinstance(row.get("request_messages"), list) or not row["request_messages"]:
                        counters["broken"] += 1
                        continue
                    counters["rows"] += 1
                    yield row
        except OSError:
            continue


# ---------------------------------------------------------------------------
# identity — session keys and content hashing


def _session_key(row: dict) -> str:
    """session_hint, else "sys-" + fingerprint of the first system-role
    message (same prefix convention as proxy._session_hint — Anthropic
    requests carry system separately, but OpenAI-compat clients put it in
    messages), else "anon"."""
    hint = row.get("session_hint")
    if isinstance(hint, str) and hint:
        return hint
    for message in row["request_messages"]:
        if isinstance(message, dict) and message.get("role") == "system":
            return "sys-" + _content_hash(message.get("content"))[:12]
    return "anon"


def _normalize_content(content: Any) -> Any:
    """Canonical form for hashing only (stored turns keep the original).

    A single text block equals its plain string — clients flip between the
    two spellings across requests. None-valued keys are dropped so decorative
    nulls (``citations: null`` and friends) don't fake a divergence.
    """
    if isinstance(content, list):
        if len(content) == 1 and isinstance(content[0], dict) and content[0].get("type") == "text":
            return content[0].get("text", "")
        return [
            {k: v for k, v in block.items() if v is not None} if isinstance(block, dict) else block
            for block in content
        ]
    return content


def _content_hash(content: Any) -> str:
    canonical = json.dumps(_normalize_content(content), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _message_seq(messages: list) -> list[tuple[str, str]]:
    """The (role, content-hash) sequence prefix matching runs on."""
    seq: list[tuple[str, str]] = []
    for message in messages:
        if isinstance(message, dict):
            seq.append((str(message.get("role") or ""), _content_hash(message.get("content"))))
        else:
            seq.append(("", _content_hash(message)))
    return seq


def _common_prefix(a: list, b: list) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


# ---------------------------------------------------------------------------
# reconstruction


class _Thread:
    __slots__ = ("key", "segments", "hashes", "updated")

    def __init__(self, key: str):
        self.key = key
        self.segments: list[dict] = [{"turns": [], "fork_from": None}]
        self.hashes: list[tuple[str, str]] = []  # canonical (role, hash) history
        self.updated = 0


def _request_turn(message: Any, ts: str) -> dict:
    if isinstance(message, dict):
        return {"role": str(message.get("role") or ""), "content": message.get("content"), "ts": ts, "source": "request"}
    return {"role": "", "content": message, "ts": ts, "source": "request"}


def reconstruct(stream_dir: Path) -> dict:
    """Fold the capture stream into sessions.

    Returns ``{"sessions": [{key, segments: [{turns, fork_from}]}],
    "stats": {rows, threads, forks, broken}}``. One session per thread,
    in first-seen order; segments store only the turns grown since their
    fork point (segment i's full history = the first ``fork_from`` turns
    of the thread's timeline + its own turns).
    """
    stats = {"rows": 0, "threads": 0, "forks": 0, "broken": 0}
    by_key: dict[str, list[_Thread]] = {}
    threads: list[_Thread] = []
    clock = 0

    for row in iter_stream_rows(stream_dir, stats=stats):
        clock += 1
        seq = _message_seq(row["request_messages"])
        key = _session_key(row)
        group = by_key.setdefault(key, [])

        # Longest shared prefix wins; recency breaks ties. No shared prefix
        # at all is a different conversation under the same key.
        thread: _Thread | None = None
        best = (0, -1)
        for candidate in group:
            rank = (_common_prefix(candidate.hashes, seq), candidate.updated)
            if rank[0] > 0 and rank > best:
                thread, best = candidate, rank
        if thread is None:
            thread = _Thread(key)
            group.append(thread)
            threads.append(thread)
            stats["threads"] += 1
        common = best[0]

        if common < len(thread.hashes):
            # Divergence inside the canonical history (retry / compaction):
            # never merge — close the segment, branch from the shared prefix.
            thread.segments.append({"turns": [], "fork_from": common})
            stats["forks"] += 1

        segment = thread.segments[-1]
        ts = str(row.get("ts") or "")
        for message in row["request_messages"][common:]:
            segment["turns"].append(_request_turn(message, ts))
        thread.hashes = thread.hashes[:common] + seq[common:]

        response = row.get("response_content")
        if response is not None:
            segment["turns"].append(
                {"role": "assistant", "content": response, "ts": ts, "source": "response", "model": row.get("model")}
            )
            thread.hashes.append(("assistant", _content_hash(response)))
        thread.updated = clock

    return {
        "sessions": [{"key": thread.key, "segments": thread.segments} for thread in threads],
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# miner adapter


def to_cc_rows(segment: dict) -> list[dict]:
    """Adapt one segment to Claude-Code transcript rows —
    ``{"type": "user"|"assistant", "message": {role, content}, "timestamp"}``
    — so existing mining logic consumes proxy sessions unchanged.

    Content passes through verbatim: tool_result blocks keep ``is_error``,
    the load-bearing signal for trap-arc mining. Non-assistant roles (user,
    tool, system) all map to type "user" — CC carries tool results inside
    user rows, and the miners key off blocks, not row type.
    """
    rows = []
    for turn in segment.get("turns", []):
        role = str(turn.get("role") or "user")
        rows.append(
            {
                "type": "assistant" if role == "assistant" else "user",
                "message": {"role": role, "content": turn.get("content")},
                "timestamp": str(turn.get("ts") or ""),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# TTL


def purge_expired(stream_dir: Path, ttl_days: int = 14) -> list[Path]:
    """Delete stream files whose mtime is older than ``ttl_days``; return
    the deleted paths. Today's (UTC) file is never deleted — it is the one
    being written, whatever its mtime claims."""
    stream_dir = Path(stream_dir)
    if not stream_dir.is_dir():
        return []
    today_name = datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"
    cutoff = time.time() - ttl_days * 86400
    deleted: list[Path] = []
    for path in sorted(stream_dir.glob("*.jsonl")):
        if path.name == today_name:
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted.append(path)
        except OSError:
            continue
    return deleted
