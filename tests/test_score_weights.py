"""Search score weights must follow the effective embedding stack.

Cycle 43 found the live dogfood store running fastembed/bge-small (384d)
while _semantic_embedding_active() consulted only MEM1_EMBEDDING_PROVIDER —
so semantic-by-default users (the env-less majority) were scored with the
hash-fallback 0.72/0.28 split. P11 treatment 2: judge from
effective_embedding_stack(), the same resolution embed_text uses.
"""
from __future__ import annotations

import forget.providers as providers
import forget.store as store


def _pin_settings(monkeypatch, settings: dict) -> None:
    monkeypatch.setattr(providers, "get_project_settings", lambda project_id="proj_local": dict(settings))


def test_semantic_by_default_activates_semantic_weights(monkeypatch):
    # Unconfigured stack + importable fastembed = semantic-by-default:
    # embed_text serves bge-small, so the weights must follow.
    monkeypatch.delenv("MEM1_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(providers, "_fastembed_available", lambda: True)
    _pin_settings(monkeypatch, {"embedding_provider": "local"})
    assert store._semantic_embedding_active() is True
    assert store._search_score_weights() == (0.45, 0.55)


def test_explicit_local_pin_keeps_fallback_weights(monkeypatch):
    # An explicit local/deterministic pin is a real choice (tests,
    # constrained machines) — hash-bag vectors keep the legacy split.
    monkeypatch.setenv("MEM1_EMBEDDING_PROVIDER", "local")
    monkeypatch.setattr(providers, "_fastembed_available", lambda: True)
    _pin_settings(monkeypatch, {"embedding_provider": "local"})
    assert store._semantic_embedding_active() is False
    assert store._search_score_weights() == (0.72, 0.28)


def test_settings_configured_provider_counts_as_semantic(monkeypatch):
    # Providers configured via project settings never touch the env var;
    # the old env-only check left them on fallback weights too.
    monkeypatch.delenv("MEM1_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(providers, "_fastembed_available", lambda: False)
    _pin_settings(monkeypatch, {"embedding_provider": "openai", "embedding_model": "text-embedding-3-small"})
    assert store._semantic_embedding_active() is True
    assert store._search_score_weights() == (0.45, 0.55)


def test_unconfigured_without_fastembed_stays_on_fallback(monkeypatch):
    # No env, no fastembed, no configured provider: embed_text falls back
    # to deterministic-128, so semantic weights must NOT activate.
    monkeypatch.delenv("MEM1_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setattr(providers, "_fastembed_available", lambda: False)
    _pin_settings(monkeypatch, {"embedding_provider": "local"})
    assert store._semantic_embedding_active() is False
    assert store._search_score_weights() == (0.72, 0.28)
