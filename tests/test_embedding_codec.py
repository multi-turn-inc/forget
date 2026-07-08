"""Embedding column codec — MEB1 float32 blobs with legacy-JSON sniffing."""

import json
import math

from forget.utils import EMBEDDING_BLOB_MAGIC, decode_embedding, encode_embedding


def test_roundtrip_preserves_vector_within_float32() -> None:
    vector = [0.123456, -1.5, 0.0, 42.25, -0.000031]
    blob = encode_embedding(vector)
    assert isinstance(blob, bytes) and blob.startswith(EMBEDDING_BLOB_MAGIC)
    decoded = decode_embedding(blob)
    assert len(decoded) == len(vector)
    assert all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6) for a, b in zip(decoded, vector))


def test_legacy_json_text_still_decodes() -> None:
    vector = [0.25, -0.5, 1.0]
    assert decode_embedding(json.dumps(vector)) == vector


def test_empty_and_corrupt_values_decode_to_empty() -> None:
    assert decode_embedding(None) == []
    assert decode_embedding("") == []
    assert decode_embedding(b"") == []
    assert encode_embedding([]) == ""
    assert decode_embedding(b"XXXX\x00\x00\x00\x00") == []  # wrong magic
    assert decode_embedding(EMBEDDING_BLOB_MAGIC + b"\x00\x00\x00") == []  # truncated payload
    assert decode_embedding("not json") == []


def test_memoryview_input_decodes() -> None:
    blob = encode_embedding([1.0, 2.0])
    assert decode_embedding(memoryview(blob)) == [1.0, 2.0]
