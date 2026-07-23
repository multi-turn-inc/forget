"""e5 asymmetric prefixes: the gate-ready half of the embedding switch.

The 2026-07 contrast-set validation showed multilingual-e5-large beats the
default ONLY with "query:"/"passage:" prefixes (paraphrase rank 92→2 with,
regression without). The model swap itself stays measurement-gated; this
wires the prefix so that flipping FASTEMBED_MODEL to an e5 model delivers
the validated behavior instead of silently forfeiting it.
"""

from forget.providers import e5_prefixed


def test_e5_models_get_role_prefixes():
    assert e5_prefixed("고양이", "intfloat/multilingual-e5-large", "query") == "query: 고양이"
    assert e5_prefixed("고양이", "intfloat/multilingual-e5-large", "passage") == "passage: 고양이"
    assert e5_prefixed("x", "intfloat/e5-base-v2", "query") == "query: x"


def test_non_e5_models_are_untouched():
    # Token match, not substring: "gte-large" and "base5" must not trip.
    assert e5_prefixed("x", "thenlper/gte-large", "query") == "x"
    assert e5_prefixed("x", "multi-qa-MiniLM-L6-cos-v1", "query") == "x"
    assert e5_prefixed("x", "custom/base5-model", "query") == "x"
    assert e5_prefixed("x", "", "query") == "x"


def test_unknown_role_defaults_to_passage():
    assert e5_prefixed("x", "intfloat/e5-base-v2", "document") == "passage: x"
