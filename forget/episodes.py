"""Episodic recall — open the raw scene when the summary is too thin.

Assistant-authored (user zero, 2026-07-25). The store keeps semantic
memory: conclusions, decisions, doctrines. But a compacted session hands
the next instance doctrine without the scene it came from — it inherited
"trust labels exist" while the morning it was deceived, the pet name the
bug was given, and the stammering minute an idea was born stayed on disk,
unreachable. Session transcripts ARE the episodic store; this module is
the bridge: search them on demand, return dated excerpts with receipts
(file, line, timestamp), never copies.

Local-only by construction: reads the transcript directories on this
machine, writes nothing, uploads nothing.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_ROOTS = ("~/.claude/projects",)
MAX_FILES_SCANNED = 40
MAX_BYTES_PER_FILE = 64 * 1024 * 1024


def transcript_roots() -> list[Path]:
    raw = os.environ.get("MEM1_EPISODE_ROOTS", "")
    roots = [part for part in raw.split(os.pathsep) if part.strip()] or list(DEFAULT_ROOTS)
    return [Path(root).expanduser() for root in roots]


def _iter_transcript_files(roots: list[Path], since: datetime | None) -> list[Path]:
    files: list[tuple[float, Path]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if since is not None and datetime.fromtimestamp(mtime, timezone.utc) < since:
                continue
            files.append((mtime, path))
    files.sort(reverse=True)  # newest transcripts first — recency is relevance
    return [path for _, path in files[:MAX_FILES_SCANNED]]


def _event_text(event: dict[str, Any]) -> tuple[str, str]:
    message = event.get("message") or {}
    role = str(message.get("role") or event.get("type") or "")
    content = message.get("content")
    if isinstance(content, str):
        return role, content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return role, " ".join(part for part in parts if part)
    return role, ""


def _excerpt(text: str, terms: list[str], width: int = 320) -> str:
    lowered = text.lower()
    anchor = min((lowered.find(term) for term in terms if term in lowered), default=0)
    start = max(0, anchor - width // 4)
    clipped = " ".join(text[start:start + width].split())
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + width < len(text) else ""
    return f"{prefix}{clipped}{suffix}"


def recall_episodes(
    query: str,
    *,
    limit: int = 5,
    days: float | None = None,
    roots: list[Path] | None = None,
) -> list[dict[str, Any]]:
    """Return raw-scene excerpts matching the query, newest first.

    Matching is deliberately dumb (every term must appear): the caller is
    an LLM that can iterate on queries; what it cannot do is read 13MB of
    JSONL — precision of the receipt matters more than recall of the rank.
    """
    terms = [term.lower() for term in re.split(r"\s+", str(query or "").strip()) if term]
    if not terms:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    hits: list[dict[str, Any]] = []
    for path in _iter_transcript_files(roots or transcript_roots(), since):
        try:
            if path.stat().st_size > MAX_BYTES_PER_FILE:
                continue
            with path.open() as handle:
                for lineno, line in enumerate(handle, start=1):
                    lowered = line.lower()
                    if not all(term in lowered for term in terms):
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    role, text = _event_text(event)
                    if not text or not all(term in text.lower() for term in terms):
                        continue
                    hits.append({
                        "excerpt": _excerpt(text, terms),
                        "role": role or "unknown",
                        "timestamp": str(event.get("timestamp") or ""),
                        "receipt": f"{path}:{lineno}",
                    })
                    if len(hits) >= limit * 6:
                        break
        except OSError:
            continue
        if len(hits) >= limit * 6:
            break
    hits.sort(key=lambda item: item["timestamp"], reverse=True)
    return hits[:limit]


def recall_episodes_payload(payload: dict[str, Any]) -> dict[str, Any]:
    query = str(payload.get("query") or "")
    limit = int(payload.get("limit") or 5)
    days = payload.get("days")
    results = recall_episodes(
        query,
        limit=max(1, min(limit, 20)),
        days=float(days) if days else None,
    )
    return {
        "results": results,
        "note": (
            "raw transcript excerpts (episodic layer) — scenes, not conclusions; "
            "quote receipts when acting on them"
        ),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: python -m forget.episodes <query> [--days N] [--limit N]")
        return 1
    days = None
    limit = 5
    terms: list[str] = []
    iterator = iter(args)
    for arg in iterator:
        if arg == "--days":
            days = float(next(iterator, "0") or 0)
        elif arg == "--limit":
            limit = int(next(iterator, "5") or 5)
        else:
            terms.append(arg)
    for hit in recall_episodes(" ".join(terms), limit=limit, days=days):
        stamp = hit["timestamp"][:16] or "?"
        print(f"[{stamp} · {hit['role']}] {hit['excerpt']}")
        print(f"  └ {hit['receipt']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
