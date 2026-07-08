from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


UTC = timezone.utc

ENTITY_FIELDS = ("user_id", "agent_id", "app_id", "run_id")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str | None = None) -> str:
    value = str(uuid4())
    return f"{prefix}_{value}" if prefix else value


def content_hash(text: str, *parts: Any) -> str:
    h = hashlib.sha256()
    h.update(text.strip().encode("utf-8"))
    for part in parts:
        h.update(b"\0")
        h.update(str(part or "").encode("utf-8"))
    return h.hexdigest()


TOKEN_RE = re.compile(
    r"[a-zA-Z0-9_']+"                    # latin / digits (legacy behavior, unchanged)
    r"|[가-힣]+"                 # Hangul syllables
    r"|[぀-ヿ]+"                 # Hiragana / Katakana
    r"|[一-鿿]+"                 # CJK unified ideographs
)

CJK_CHAR_RE = re.compile(r"[가-힣぀-ヿ一-鿿]")


def _cjk_bigrams(run: str) -> list[str]:
    # Character bigrams are the standard analyzer-free fallback for CJK
    # search: they survive Korean particles (조사) well enough for token
    # overlap and hashed-embedding matching.
    if len(run) < 2:
        return [run]
    return [run[i : i + 2] for i in range(len(run) - 1)]


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "user",
    "what",
    "where",
    "who",
    "with",
}


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_RE.findall(text or ""):
        token = raw.lower().strip("'")
        if not token or token in STOPWORDS:
            continue
        if CJK_CHAR_RE.match(token):
            tokens.extend(_cjk_bigrams(token))
        else:
            tokens.append(token)
    return tokens


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                return None
    return None


# --- embedding column codec --------------------------------------------------
# Embeddings live in the memories.embedding column. Historically JSON text
# (~18KB per bge-m3 1024-dim row, json-parsed on every hydration); new writes
# are a little-endian float32 blob behind a 4-byte magic (4KB, ~10x faster to
# decode). decode sniffs the format so legacy rows keep working without a
# migration; scripts/migrate_embedding_blob.py converts them at leisure.

EMBEDDING_BLOB_MAGIC = b"MEB1"


def encode_embedding(vector: list[float] | None) -> bytes | str:
    if not vector:
        return ""
    import struct

    return EMBEDDING_BLOB_MAGIC + struct.pack(f"<{len(vector)}f", *[float(v) for v in vector])


def decode_embedding(value: Any) -> list[float]:
    if value is None or value == "" or value == b"":
        return []
    if isinstance(value, (bytes, memoryview)):
        raw = bytes(value)
        if raw[:4] != EMBEDDING_BLOB_MAGIC or (len(raw) - 4) % 4:
            return []
        import struct

        return list(struct.unpack(f"<{(len(raw) - 4) // 4}f", raw[4:]))
    if isinstance(value, str):
        try:
            import json

            data = json.loads(value)
        except (ValueError, TypeError):
            return []
        return [float(v) for v in data] if isinstance(data, list) else []
    if isinstance(value, list):
        return [float(v) for v in value]
    return []
